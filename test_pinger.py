import pytest
import asyncio
from unittest.mock import MagicMock, patch
from node_pinger import Pinger
from models import NodeDB, GroupDB

# Mock database objects
def create_mock_node(node_id=1, interval=60, max_retries=3):
    group = MagicMock(spec=GroupDB)
    group.interval = interval
    group.max_retries = max_retries
    group.packet_count = 1
    group.name = "TestGroup"
    
    node = MagicMock(spec=NodeDB)
    node.id = node_id
    node.name = "TestNode"
    node.ip = "1.2.3.4"
    node.group = group
    node.group_id = 1
    # Node overrides (set to None to use group defaults)
    node.interval = None
    node.packet_count = None
    node.max_retries = None
    
    return node

@pytest.mark.asyncio
async def test_pinger_state_machine():
    """
    Test transitions:
    1. UP -> FAIL -> PENDING (Retry 1)
    2. PENDING -> FAIL -> PENDING (Retry 2)
    3. PENDING -> FAIL -> PENDING (Retry 3)
    4. PENDING -> FAIL -> DOWN
    5. DOWN -> SUCCESS -> UP
    """
    pinger = Pinger()
    node = create_mock_node(max_retries=3)
    
    # Setup mocks
    # We patch ping3.ping to return None (failure) or 0.01 (success)
    with patch('node_pinger.ping') as mock_ping:
        with patch('node_pinger.storage.write_ping_result') as mock_storage:
            
            # --- Initial State: UP (implicitly) ---
            
            # 1. UP -> FAIL -> PENDING
            mock_ping.return_value = None # Failure
            
            # Force time check to pass
            pinger.last_ping_time[node.id] = 0 
            
            await pinger.process_node(node)
            
            state = pinger.get_node_state(node.id)
            assert state['status'] == 'PENDING', "Should transition to PENDING on first failure"
            assert state['failure_count'] == 1, "Failure count should be 1"
            assert pinger.latest_results[node.id]['status'] == 'PENDING'
            
            # 2. PENDING -> FAIL -> PENDING (Retry 2)
            # Reset last_ping_time to simulate time passing (1/3 interval)
            pinger.last_ping_time[node.id] = 0
            
            await pinger.process_node(node)
            
            state = pinger.get_node_state(node.id)
            assert state['status'] == 'PENDING', "Should stay PENDING on retry 2"
            assert state['failure_count'] == 2, "Failure count should be 2"
            
            # 3. PENDING -> FAIL -> PENDING (Retry 3)
            pinger.last_ping_time[node.id] = 0
            await pinger.process_node(node)
            
            state = pinger.get_node_state(node.id)
            assert state['status'] == 'PENDING', "Should stay PENDING on retry 3"
            assert state['failure_count'] == 3, "Failure count should be 3"
            
            # 4. PENDING -> FAIL -> DOWN (Exceeded Max Retries)
            pinger.last_ping_time[node.id] = 0
            await pinger.process_node(node)
            
            state = pinger.get_node_state(node.id)
            assert state['status'] == 'DOWN', "Should transition to DOWN after exceeding max retries"
            
            # 5. DOWN -> SUCCESS -> UP
            mock_ping.return_value = 0.01 # Success
            pinger.last_ping_time[node.id] = 0
            await pinger.process_node(node)
            
            state = pinger.get_node_state(node.id)
            assert state['status'] == 'UP', "Should recover to UP on success"
            assert state['failure_count'] == 0, "Failure count should reset to 0"

@pytest.mark.asyncio
async def test_pinger_retry_interval():
    """
    Verify that the 'effective_interval' changes based on state.
    """
    pinger = Pinger()
    node = create_mock_node(interval=60) # 60s normal interval
    
    # 1. Normal State (UP)
    # Ping should happen if delta >= 60
    pinger.last_ping_time[node.id] = 0
    now = 100 # arbitrary time
    
    # Determine effective interval logic is inside process_node, but we can't easily check local variables.
    # Instead, we can control 'now' and 'last_ping_time' to see if it pings.
    # But process_node uses time.time(). We should patch time.time.
    
    with patch('node_pinger.time.time') as mock_time:
        with patch('node_pinger.ping') as mock_ping:
             with patch('node_pinger.storage.write_ping_result'):
                mock_ping.return_value = 0.01 # Success
                
                # Case A: UP, time delta = 59s (Should NOT ping)
                mock_time.return_value = 1000
                pinger.last_ping_time[node.id] = 1000 - 59 
                
                await pinger.process_node(node)
                assert mock_ping.call_count == 0, "Should NOT ping if delta < interval"
                
                # Case B: UP, time delta = 60s (Should ping)
                mock_time.return_value = 2000
                pinger.last_ping_time[node.id] = 2000 - 60
                
                await pinger.process_node(node)
                assert mock_ping.call_count == 1, "Should ping if delta >= interval"
                mock_ping.reset_mock()
                
                # NOW simulate failure and transition to PENDING
                mock_ping.return_value = None
                pinger.last_ping_time[node.id] = 2000
                mock_time.return_value = 2060 # Trigger next ping
                
                await pinger.process_node(node)
                assert pinger.get_node_state(node.id)['status'] == 'PENDING'
                mock_ping.reset_mock()
                
                # Case C: PENDING, time delta = 19 (Should NOT ping, 20 is target)
                # Interval 60 / 3 = 20s
                last_ping = 3000
                pinger.last_ping_time[node.id] = last_ping
                mock_time.return_value = last_ping + 19
                
                await pinger.process_node(node)
                assert mock_ping.call_count == 0, "Should NOT ping in PENDING if delta < retry_interval (20s)"
                
                # Case D: PENDING, time delta = 20 (Should ping)
                mock_time.return_value = last_ping + 20
                
                await pinger.process_node(node)
                assert mock_ping.call_count == 1, "Should ping in PENDING if delta >= retry_interval (20s)"
