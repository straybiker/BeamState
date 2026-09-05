import logging
import time
import json
import os
import pathlib
import asyncio
from typing import Optional, Any
from storage import storage
from models import NodeDB, NodeMetricDB

logger = logging.getLogger("BeamState.MetricProcessor")

LEVEL_RANK = {None: 0, "WARNING": 1, "CRITICAL": 2}


class MetricProcessor:
    """
    Turns raw metric samples into rates, alert levels and notifications.

    Alert state is evaluated independently of notification channels so the
    dashboard shows DEGRADED even when no channel is configured.
    """

    def __init__(self, notifier):
        self.notifier = notifier
        self.previous_values = {} # node_metric_id -> {'value': val, 'timestamp': ts}

        # Concurrency lock for alert state changes
        self.state_lock = asyncio.Lock()

        # Notification cooldown - prevent sending same alert within 60s
        self.notification_cooldown = {}  # metric_id -> last_notification_timestamp
        self.COOLDOWN_SECONDS = 60

        # Consecutive breach tracking: metric_id -> {'level': candidate, 'count': n}
        self.breach_counts = {}

        # Persisted alert levels: metric_id -> "WARNING" | "CRITICAL"
        base_dir = pathlib.Path(__file__).parent
        self.state_file = pathlib.Path(os.getenv("ALERT_STATE_FILE", base_dir / "data" / "alert_states.json"))
        os.makedirs(self.state_file.parent, exist_ok=True)
        self.alert_states = self._load_alert_states()

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
            with open(self.state_file, 'w') as f:
                json.dump(self.alert_states, f)
        except Exception as e:
            logger.error(f"Failed to save alert states: {e}")

    def clear_node(self, node: NodeDB):
        """Drop alert state for all metrics of a node (pause, delete)."""
        changed = False
        for metric in node.node_metrics or []:
            if metric.id in self.alert_states:
                self.alert_states.pop(metric.id, None)
                changed = True
            self.breach_counts.pop(metric.id, None)
        if changed:
            self._save_alert_states()

    def get_node_alert_status(self, node: NodeDB) -> tuple[Optional[str], Optional[str]]:
        """
        Highest active metric alert level for a node.
        Returns: (level, offending_metric_id) with level in CRITICAL, WARNING or None.
        """
        level = None
        offending_metric_id = None

        for metric in node.node_metrics or []:
            alert_level = self.alert_states.get(metric.id)
            if alert_level == "CRITICAL":
                return "CRITICAL", metric.id
            if alert_level == "WARNING" and level is None:
                level = "WARNING"
                offending_metric_id = metric.id

        return level, offending_metric_id

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

        try:
            processed_value = float(value)
        except Exception:
            # Keep as string/original if float conversion fails
            pass

        if metric_type == 'counter':
            rate = self._calculate_rate(node_metric_id, value, now, unit)
            if rate is None:
                # First run or invalid delta
                return None
            processed_value = rate

        # 2. Check Thresholds & Alert (use processed_value which is rate for counters, or float for gauges)
        await self._check_thresholds(node, node_metric, processed_value)

        # 3. Persist to Storage (InfluxDB when enabled, plus short-term SQLite history)
        if processed_value is not None:
            if isinstance(processed_value, (int, float)):
                await asyncio.to_thread(self._store_sample, node_metric_id, now, float(processed_value))
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
            "processed_value": processed_value,  # Used for alerting (rate for counters)
            "alert_level": self.alert_states.get(node_metric_id)
        }

    @staticmethod
    def _store_sample(node_metric_id: str, ts: float, value: float):
        """Append one sample to metric_samples (runs in a worker thread)."""
        try:
            from database import SessionLocal
            from models import MetricSampleDB
            db = SessionLocal()
            try:
                db.add(MetricSampleDB(node_metric_id=node_metric_id, timestamp=ts, value=value))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"Could not store metric sample: {e}")

    @staticmethod
    def prune_samples(retention_days: int) -> int:
        """Delete samples older than retention_days. Returns rows removed."""
        if not retention_days or retention_days <= 0:
            return 0
        try:
            from database import SessionLocal
            from models import MetricSampleDB
            cutoff = time.time() - retention_days * 86400
            db = SessionLocal()
            try:
                removed = db.query(MetricSampleDB).filter(MetricSampleDB.timestamp < cutoff).delete()
                db.commit()
            finally:
                db.close()
            if removed:
                logger.info(f"Pruned {removed} metric samples older than {retention_days} days")
            return removed
        except Exception as e:
            logger.error(f"Failed to prune metric samples: {e}")
            return 0

    def _calculate_rate(self, node_metric_id: str, current_value: Any, now: float, unit: str) -> Optional[float]:
        try:
            cur_val = float(current_value)
        except (ValueError, TypeError):
            return None

        prev = self.previous_values.get(node_metric_id)

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

    @staticmethod
    def _raw_level(value: float, condition: str, warning: Optional[float], critical: Optional[float]) -> Optional[str]:
        """Alert level a single sample maps to, before hysteresis and sample counting."""
        if critical is not None:
            if condition == 'gt' and value >= critical:
                return "CRITICAL"
            if condition == 'lt' and value <= critical:
                return "CRITICAL"
        if warning is not None:
            if condition == 'gt' and value >= warning:
                return "WARNING"
            if condition == 'lt' and value <= warning:
                return "WARNING"
        return None

    async def _check_thresholds(self, node: NodeDB, node_metric: NodeMetricDB, value: float):
        """Check values against warning/critical thresholds and trigger alerts on state change"""

        if not isinstance(value, (int, float)):
            return

        # Paused node or paused group: clear any active alert and stop evaluating
        # (None means "not set", which counts as enabled)
        group_paused = node.group is not None and node.group.enabled is False
        if node.enabled is False or group_paused:
            async with self.state_lock:
                if node_metric.id in self.alert_states:
                    self.alert_states.pop(node_metric.id, None)
                    self._save_alert_states()
                self.breach_counts.pop(node_metric.id, None)
            return

        warning = node_metric.warning_threshold
        critical = node_metric.critical_threshold
        condition = getattr(node_metric, 'alert_condition', 'gt') or 'gt'
        min_samples = max(1, int(getattr(node_metric, 'alert_min_samples', 1) or 1))

        if warning is None and critical is None:
            return

        current_alert_level = self._raw_level(value, condition, warning, critical)
        metric_name = node_metric.metric_definition.name

        async with self.state_lock:
            prev_alert_level = self.alert_states.get(node_metric.id)

            logger.debug(f"ALERT_CHECK: {node.name}-{metric_name} id={node_metric.id} | prev={prev_alert_level} current={current_alert_level}")

            # Hysteresis: hold a level until the value is clearly back on the safe side
            HYSTERESIS_FACTOR = 0.05 # 5% buffer

            if prev_alert_level == "CRITICAL" and current_alert_level != "CRITICAL":
                if condition == 'gt' and value > (critical * (1.0 - HYSTERESIS_FACTOR)):
                    current_alert_level = "CRITICAL"
                elif condition == 'lt' and value < (critical * (1.0 + HYSTERESIS_FACTOR)):
                    current_alert_level = "CRITICAL"

            elif prev_alert_level == "WARNING" and current_alert_level is None:
                if condition == 'gt' and value > (warning * (1.0 - HYSTERESIS_FACTOR)):
                    current_alert_level = "WARNING"
                elif condition == 'lt' and value < (warning * (1.0 + HYSTERESIS_FACTOR)):
                    current_alert_level = "WARNING"

            # Escalation needs min_samples consecutive samples at the candidate level.
            # De-escalation and recovery are immediate (hysteresis already applies).
            if LEVEL_RANK[current_alert_level] > LEVEL_RANK[prev_alert_level]:
                tracker = self.breach_counts.get(node_metric.id)
                if tracker and tracker["level"] == current_alert_level:
                    tracker["count"] += 1
                else:
                    tracker = {"level": current_alert_level, "count": 1}
                    self.breach_counts[node_metric.id] = tracker

                if tracker["count"] < min_samples:
                    logger.info(f"ALERT_PENDING: {node.name}-{metric_name} | {current_alert_level} sample {tracker['count']}/{min_samples} (value={value})")
                    return
            else:
                self.breach_counts.pop(node_metric.id, None)

            if current_alert_level == prev_alert_level:
                logger.debug(f"ALERT_SUPPRESSED: {node.name}-{metric_name} | {prev_alert_level} == {current_alert_level}")
                return

            # State change: persist, then notify
            if current_alert_level is None:
                self.alert_states.pop(node_metric.id, None)
            else:
                self.alert_states[node_metric.id] = current_alert_level
            self._save_alert_states()
            self.breach_counts.pop(node_metric.id, None)

            logger.info(f"ALERT_STATE_CHANGE: {node.name}-{metric_name} | {prev_alert_level} -> {current_alert_level} | value={value}")

            cond_symbol = ">=" if condition == 'gt' else "<="
            unit = node_metric.metric_definition.unit or ''
            now = time.time()
            last_sent = self.notification_cooldown.get(node_metric.id, 0)
            context = {
                "node": node.name,
                "ip": node.ip,
                "group": node.group.name if node.group else None,
                "metric": metric_name,
                "value": value,
                "unit": unit,
                "level": current_alert_level,
            }

            if current_alert_level:
                trigger_val = critical if current_alert_level == "CRITICAL" else warning
                title = f"BeamState {current_alert_level}: {node.name} - {metric_name}"
                message = f"{metric_name} is {value:.2f} {unit} ({cond_symbol} {trigger_val})"

                if now - last_sent < self.COOLDOWN_SECONDS:
                    logger.debug(f"NOTIFICATION_COOLDOWN: {node.name}-{metric_name} | suppressed (last sent {now - last_sent:.1f}s ago)")
                    return

                node_prio = node.notification_priority if node.notification_priority is not None else 0
                final_priority = node_prio
                if current_alert_level == "CRITICAL" and final_priority < 1:
                    final_priority = 1

                event = "metric_critical" if current_alert_level == "CRITICAL" else "metric_warning"
                await self.notifier.send(title, message, final_priority, event=event, **context)
                self.notification_cooldown[node_metric.id] = now

            elif prev_alert_level is not None:
                if now - last_sent < self.COOLDOWN_SECONDS:
                    logger.info(f"NOTIFICATION_COOLDOWN: {node.name}-{metric_name} RESOLVED | suppressed")
                    return

                title = f"BeamState RESOLVED: {node.name} - {metric_name}"
                message = f"{metric_name} returned to normal ({value:.2f} {unit})"
                await self.notifier.send(title, message, 0, event="metric_resolved", **context)
                self.notification_cooldown[node_metric.id] = now
