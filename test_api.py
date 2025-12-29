"""
Unit tests for NetSentry backend API.
Run with: pytest test_api.py -v
"""
import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from main import app
from models import NodeCreate, NodeBase
from pydantic import ValidationError

client = TestClient(app)


class TestIPValidation:
    """Test IP address validation in NodeCreate model."""
    
    def test_valid_ip_addresses(self):
        """Test that valid IP addresses are accepted."""
        valid_ips = [
            "192.168.1.1",
            "10.0.0.1",
            "172.16.0.1",
            "8.8.8.8",
            "1.1.1.1",
            "0.0.0.0",
            "255.255.255.255",
        ]
        for ip in valid_ips:
            node = NodeCreate(name="test", ip=ip, group_id=1)
            assert node.ip == ip, f"Valid IP {ip} should be accepted"
    
    def test_invalid_ip_octets_too_high(self):
        """Test that IP addresses with octets > 255 are rejected."""
        invalid_ips = [
            "999.999.999.999",
            "256.1.1.1",
            "1.256.1.1",
            "1.1.256.1",
            "1.1.1.256",
            "300.300.300.300",
        ]
        for ip in invalid_ips:
            with pytest.raises(ValidationError) as exc_info:
                NodeCreate(name="test", ip=ip, group_id=1)
            assert "IP address" in str(exc_info.value), f"Invalid IP {ip} should be rejected"
    
    def test_invalid_ip_format(self):
        """Test that malformed IP addresses are rejected."""
        invalid_formats = [
            "192.168.1",          # Missing octet
            "192.168.1.1.1",      # Too many octets
            "192.168.1.",         # Trailing dot
            ".192.168.1.1",       # Leading dot
            "abc.def.ghi.jkl",    # Non-numeric
            "192.168.1.1a",       # Letters in octet
            "192.168.1.-1",       # Negative number
            "",                   # Empty string
            "localhost",          # Hostname
        ]
        for ip in invalid_formats:
            with pytest.raises(ValidationError) as exc_info:
                NodeCreate(name="test", ip=ip, group_id=1)
            assert "ip" in str(exc_info.value).lower(), f"Invalid format {ip} should be rejected"


class TestAPIEndpoints:
    """Test API endpoints for IP validation."""
    
    def test_create_node_with_invalid_ip_returns_422(self):
        """Test that creating a node with invalid IP returns 422 Unprocessable Entity."""
        response = client.post(
            "/config/nodes",
            json={"name": "BadNode", "ip": "999.999.999.999", "group_id": 1}
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        assert "ip" in response.text.lower() or "validation" in response.text.lower()
    
    def test_create_node_with_valid_ip_format(self):
        """Test that creating a node with valid IP format passes validation."""
        # This may fail with 404 if group doesn't exist, but should NOT fail with 422
        response = client.post(
            "/config/nodes",
            json={"name": "GoodNode", "ip": "192.168.1.100", "group_id": 999}
        )
        # Accept 404 (group not found) or 200 (success), but NOT 422 (validation error)
        assert response.status_code != 422, "Valid IP should pass validation"


class TestCascadeDelete:
    """Test cascade deletion of nodes when group is deleted."""
    
    def test_group_deletion_removes_nodes(self):
        """Test that deleting a group also deletes its nodes."""
        # Create a group
        group_resp = client.post(
            "/config/groups",
            json={"name": "CascadeTestGroup", "interval": 60}
        )
        if group_resp.status_code == 400:
            # Group exists, try to delete and recreate
            groups = client.get("/config/groups").json()
            for g in groups:
                if g["name"] == "CascadeTestGroup":
                    client.delete(f"/config/groups/{g['id']}")
            group_resp = client.post(
                "/config/groups",
                json={"name": "CascadeTestGroup", "interval": 60}
            )
        
        assert group_resp.status_code == 200, f"Failed to create group: {group_resp.text}"
        group_id = group_resp.json()["id"]
        
        # Create a node in the group
        node_resp = client.post(
            "/config/nodes",
            json={"name": "CascadeTestNode", "ip": "10.0.0.1", "group_id": group_id}
        )
        assert node_resp.status_code == 200, f"Failed to create node: {node_resp.text}"
        node_id = node_resp.json()["id"]
        
        # Verify node exists
        nodes = client.get("/config/nodes").json()
        assert any(n["id"] == node_id for n in nodes), "Node should exist before deletion"
        
        # Delete the group
        del_resp = client.delete(f"/config/groups/{group_id}")
        assert del_resp.status_code == 200, f"Failed to delete group: {del_resp.text}"
        
        # Verify node is gone (cascade delete)
        nodes_after = client.get("/config/nodes").json()
        assert not any(n["id"] == node_id for n in nodes_after), "Node should be deleted with group"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
