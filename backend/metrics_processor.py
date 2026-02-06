import logging
import time
import json
import os
import pathlib
import asyncio
from typing import Optional, Any
from storage import storage
from models import NodeDB, NodeMetricDB
from notifications import PushoverClient

logger = logging.getLogger("BeamState.MetricProcessor")

class MetricProcessor:
    def __init__(self, pushover: PushoverClient):
        self.pushover = pushover
        self.previous_values = {} # node_metric_id -> {'value': val, 'timestamp': ts}
        
        # Concurrency lock for file operations
        self.state_lock = asyncio.Lock()
        
        # Notification cooldown - prevent sending same alert within 60s
        self.notification_cooldown = {}  # metric_id -> last_notification_timestamp
        self.COOLDOWN_SECONDS = 60
        
        # Load persistence state
        # Use absolute path relative to this file to ensure consistency across processes
        base_dir = pathlib.Path(__file__).parent
        self.state_file = base_dir / "data" / "alert_states.json"
        
        # Ensure directory exists
        os.makedirs(self.state_file.parent, exist_ok=True)
        
        self.alert_states = self._load_alert_states()
        
        # Force save to verify file creation
        self._save_alert_states()

    def _load_alert_states(self):
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load alert states: {e}")
        return {}

    def _save_alert_states(self):
        try:
            # Ensure directory exists (should exist since 'data' is standard)
            with open(self.state_file, 'w') as f:
                json.dump(self.alert_states, f)
        except Exception as e:
            logger.error(f"Failed to save alert states: {e}")

    def get_node_alert_status(self, node: NodeDB) -> str:
        """
        Calculates the aggregated status for a node based on active metric alerts.
        Returns: 'DOWN' (Critical), 'PENDING' (Warning), or 'UP' (Normal)
        """
        status = "UP"
        if not node.node_metrics:
            return status

        # Access persisted alerts directly from memory
        # No lock needed for read if we accept slight staleness, or use lock if strict
        # Using self.alert_states directly (it's a dict, atomic enough for this)
        
        has_critical = False
        has_warning = False
        
        for metric in node.node_metrics:
            alert_level = self.alert_states.get(metric.id)
            if alert_level == "CRITICAL":
                has_critical = True
                break # Optimization: Critical is highest severity
            elif alert_level == "WARNING":
                has_warning = True
                
        if has_critical:
            status = "DOWN"
        elif has_warning:
            status = "PENDING"
            
        return status

    async def process_metric(self, node: NodeDB, node_metric: NodeMetricDB, value: Any) -> Optional[dict]:
        """
        Process a metric value: calculate rate (if needed), check thresholds, send alerts, and persist.
        Returns the processed entry (value, rate, timestamp) or None if invalid.
        """
        now = time.time()
        metric_def = node_metric.metric_definition
        node_metric_id = node_metric.id
        metric_type = metric_def.metric_type
        unit = metric_def.unit

        # 1. Calculate Rate (if Counter)
        processed_value = value
        rate = None
        
        # Determine if we should treat as float/int
        try:
             float_val = float(value)
             processed_value = float_val
        except Exception as e:
             # Keep as string/original if float conversion fails
             # logger.debug(f"Float conversion failed for {value}: {e}")
             pass

        if metric_type == 'counter':
            rate = self._calculate_rate(node_metric_id, value, now, unit)
            if rate is None:
                # First run or invalid delta
                return None
            processed_value = rate

        # 2. Check Thresholds & Alert (use processed_value which is rate for counters, or float for gauges)
        await self._check_thresholds(node, node_metric, processed_value)

        # 3. Persist to Storage
        if processed_value is not None:
             # Adjust unit if rate
             final_unit = unit
             if metric_type == 'counter' and unit == 'bytes':
                 final_unit = 'bps'
             
             await storage.write_snmp_metric(
                 node_name=node.name,
                 ip=node.ip,
                 group_name=node.group.name if node.group else "global",
                 metric_name=metric_def.name,
                 value=processed_value,
                 unit=final_unit,
                 interface=node_metric.interface_name,
                 metric_type=metric_type
             )
             
        return {
            "value": value,  # Raw value - frontend will format based on unit
            "rate": rate,
            "timestamp": now,
            "processed_value": processed_value  # Used for alerting (rate for counters)
        }

    def _calculate_rate(self, node_metric_id: str, current_value: Any, now: float, unit: str) -> Optional[float]:
        try:
            cur_val = float(current_value)
        except (ValueError, TypeError):
            return None

        prev = self.previous_values.get(node_metric_id)
        
        # Update previous value store
        self.previous_values[node_metric_id] = {
            "value": cur_val,
            "timestamp": now
        }

        if not prev:
            return None

        try:
            prev_val = float(prev['value'])
            time_delta = now - prev['timestamp']
            
            if time_delta > 0:
                val_delta = cur_val - prev_val
                # Handle Wrap-around or Reset (ignore negative delta)
                if val_delta >= 0:
                    rate = val_delta / time_delta
                    if unit == 'bytes':
                        rate = rate * 8  # Convert to bits/sec
                    return rate
        except Exception:
            pass
            
        return None

    async def _check_thresholds(self, node: NodeDB, node_metric: NodeMetricDB, value: float):
        """Check values against warning/critical thresholds and trigger alerts on state change"""
        
        # Ensure we have a numeric value
        if not isinstance(value, (int, float)):
            return

        # Suppress numeric alerts if node is paused
        if not node.enabled:
            async with self.state_lock:
                 # Clear alert state if paused to avoid sticking
                 # We need to reload to safely remove if present in disk
                 self.alert_states = self._load_alert_states()
                 if node_metric.id in self.alert_states:
                     self.alert_states.pop(node_metric.id, None)
                     self._save_alert_states()
            return

        # Check global Pushover Enabled setting
        pushover_config = storage.config.get("pushover", {})
        if not pushover_config.get("enabled", False):
            return

        warning = node_metric.warning_threshold
        critical = node_metric.critical_threshold
        
        # Determine condition (default to 'gt' if missing for backward compatibility)
        condition = getattr(node_metric, 'alert_condition', 'gt') or 'gt'
        
        # If no thresholds set, return
        if warning is None and critical is None:
            return
            
        current_alert_level = None
        
        # Determine strict level based on thresholds
        # Critical Check
        if critical is not None:
            if condition == 'gt' and value >= critical:
                current_alert_level = "CRITICAL"
            elif condition == 'lt' and value <= critical:
                 current_alert_level = "CRITICAL"

        # Warning Check (only if not critical)
        if current_alert_level is None and warning is not None:
            if condition == 'gt' and value >= warning:
                 current_alert_level = "WARNING"
            elif condition == 'lt' and value <= warning:
                 current_alert_level = "WARNING"

        # State Handling & Hysteresis
        # CRITICAL: Use lock to prevent concurrency race conditions on the JSON file
        async with self.state_lock:
            # Reload to ensure sync across processes
            self.alert_states = self._load_alert_states()
            prev_alert_level = self.alert_states.get(node_metric.id)
            
            # Debug: trace what we loaded
            logger.debug(f"ALERT_CHECK: {node.name}-{node_metric.metric_definition.name} id={node_metric.id} | prev={prev_alert_level} current={current_alert_level}")
            
            # Apply Hysteresis to prevent flapping
            HYSTERESIS_FACTOR = 0.05 # 5% buffer
            
            if prev_alert_level == "CRITICAL" and current_alert_level != "CRITICAL":
                # Trying to drop from Critical. Check buffer.
                # If condition is > (High Value Bad), we need to be safely BELOW critical
                if condition == 'gt' and value > (critical * (1.0 - HYSTERESIS_FACTOR)):
                    current_alert_level = "CRITICAL" # Hold Critical
                # If condition is < (Low Value Bad), we need to be safely ABOVE critical
                elif condition == 'lt' and value < (critical * (1.0 + HYSTERESIS_FACTOR)):
                    current_alert_level = "CRITICAL" # Hold Critical
                    
            elif prev_alert_level == "WARNING" and current_alert_level is None:
                 # Trying to drop from Warning to Normal. Check buffer.
                 if condition == 'gt' and value > (warning * (1.0 - HYSTERESIS_FACTOR)):
                    current_alert_level = "WARNING" # Hold Warning
                 elif condition == 'lt' and value < (warning * (1.0 + HYSTERESIS_FACTOR)):
                    current_alert_level = "WARNING" # Hold Warning

            
            # If state unchanged, do nothing (suppress duplicates)
            if current_alert_level == prev_alert_level:
                logger.debug(f"ALERT_SUPPRESSED: {node.name}-{node_metric.metric_definition.name} | {prev_alert_level} == {current_alert_level}")
                return
                
            # Update state AND SAVE
            self.alert_states[node_metric.id] = current_alert_level
            self._save_alert_states()
            
            # Debug trace
            logger.info(f"ALERT_STATE_CHANGE: {node.name}-{node_metric.metric_definition.name} | {prev_alert_level} -> {current_alert_level} | value={value}")
            
            # Prepare and Send Notification (INSIDE lock for atomicity)
            cond_symbol = ">=" if condition == 'gt' else "<="
            
            if current_alert_level:
                # ALERT (Warning or Critical)
                priority = 1 if current_alert_level == "CRITICAL" else 0
                trigger_val = critical if current_alert_level == "CRITICAL" else warning
                
                title = f"BeamState {current_alert_level}: {node.name} - {node_metric.metric_definition.name}"
                message = f"{node_metric.metric_definition.name} is {value:.2f} {node_metric.metric_definition.unit or ''} ({cond_symbol} {trigger_val})"
                
                # Check cooldown to prevent duplicate notifications
                now = time.time()
                last_sent = self.notification_cooldown.get(node_metric.id, 0)
                if now - last_sent < self.COOLDOWN_SECONDS:
                    logger.debug(f"NOTIFICATION_COOLDOWN: {node.name}-{node_metric.metric_definition.name} | suppressed (last sent {now - last_sent:.1f}s ago)")
                    return
                
                node_prio = node.notification_priority if node.notification_priority is not None else 0
                final_priority = node_prio
                if current_alert_level == "CRITICAL" and final_priority < 1:
                    final_priority = 1
                
                await self.pushover.send_notification(title, message, final_priority)
                self.notification_cooldown[node_metric.id] = now
                
            elif prev_alert_level is not None:
                # RESOLVED (Was Alerting, now Normal)
                # Check cooldown for resolved notifications too
                now = time.time()
                last_sent = self.notification_cooldown.get(node_metric.id, 0)
                if now - last_sent < self.COOLDOWN_SECONDS:
                    logger.info(f"NOTIFICATION_COOLDOWN: {node.name}-{node_metric.metric_definition.name} RESOLVED | suppressed")
                    return
                    
                title = f"BeamState RESOLVED: {node.name} - {node_metric.metric_definition.name}"
                message = f"{node_metric.metric_definition.name} returned to normal ({value:.2f} {node_metric.metric_definition.unit or ''})"
                await self.pushover.send_notification(title, message, priority=0)
                self.notification_cooldown[node_metric.id] = now
