"""
Capability probe: scalar batching, absent-OID detection and labelled instance
discovery. The SNMP layer is faked, so no device is needed.
"""
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("TESTING", "1")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capability_probe import CapabilityProbe, _is_absent  # noqa: E402


class FakeValue:
    """Stands in for a pysnmp value object."""
    def __init__(self, rendered):
        self._rendered = rendered

    def prettyPrint(self):
        return self._rendered


def var_bind(oid, rendered):
    return (oid, FakeValue(rendered))


SCALARS = [
    {"id": "d-load", "name": "Load", "oid_template": "1.3.6.1.4.1.2021.10.1.5.1", "requires_index": False},
    {"id": "d-unifi", "name": "CPU (UniFi)", "oid_template": "1.3.6.1.2.1.25.3.3.1.2.196608", "requires_index": False},
]
SENSOR = {
    "id": "d-temp", "name": "Sensor Temperature",
    "oid_template": "1.3.6.1.4.1.2021.13.16.2.1.3.{index}",
    "requires_index": True, "instance_oid": "1.3.6.1.4.1.2021.13.16.2.1.2",
}


class TestAbsenceDetection(unittest.TestCase):
    def test_recognises_every_absent_marker(self):
        for rendered in ("No Such Object currently exists at this OID",
                         "No Such Instance currently exists at this OID",
                         "noSuchObject", "noSuchInstance"):
            self.assertTrue(_is_absent(rendered), rendered)

    def test_real_values_are_not_absent(self):
        for rendered in ("175", "0", "48000", "temp-cpu", ""):
            self.assertFalse(_is_absent(rendered))


class TestScalarProbe(unittest.IsolatedAsyncioTestCase):
    async def test_one_get_marks_supported_and_unsupported(self):
        probe = CapabilityProbe()
        response = (None, None, None, [
            var_bind("1.3.6.1.4.1.2021.10.1.5.1", "175"),
            var_bind("1.3.6.1.2.1.25.3.3.1.2.196608", "No Such Object currently exists at this OID"),
        ])
        with patch("capability_probe.get_cmd", new=AsyncMock(return_value=response)) as get_mock, \
             patch("capability_probe.UdpTransportTarget.create", new=AsyncMock(return_value=object())):
            rows = await probe.probe("10.0.0.1", "public", 161, SCALARS)

        # A single GET carried both OIDs
        self.assertEqual(get_mock.await_count, 1)
        self.assertEqual(len(get_mock.await_args.args) - 4, 2)  # engine, auth, target, context, *varbinds

        by_id = {r["definition_id"]: r for r in rows}
        self.assertTrue(by_id["d-load"]["supported"])
        self.assertEqual(by_id["d-load"]["sample_value"], "175")
        self.assertFalse(by_id["d-unifi"]["supported"])
        self.assertIsNone(by_id["d-unifi"]["sample_value"])

    async def test_unreachable_device_reports_nothing(self):
        probe = CapabilityProbe()
        with patch("capability_probe.get_cmd", new=AsyncMock(return_value=("timeout", None, None, []))), \
             patch("capability_probe.UdpTransportTarget.create", new=AsyncMock(return_value=object())):
            rows = await probe.probe("10.0.0.1", "public", 161, SCALARS)
        # Better to report no data than to claim every metric is unsupported
        self.assertEqual(rows, [])

    async def test_batches_stay_within_the_varbind_limit(self):
        probe = CapabilityProbe()
        many = [{"id": f"d{i}", "name": str(i), "oid_template": f"1.3.6.1.2.1.1.{i}.0", "requires_index": False}
                for i in range(70)]

        async def fake_get(engine, auth, target, context, *var_binds):
            return (None, None, None, [var_bind("x", "1") for _ in var_binds])

        with patch("capability_probe.get_cmd", new=AsyncMock(side_effect=fake_get)) as get_mock, \
             patch("capability_probe.UdpTransportTarget.create", new=AsyncMock(return_value=object())):
            rows = await probe.probe("10.0.0.1", "public", 161, many)

        self.assertEqual(len(rows), 70)
        self.assertEqual(get_mock.await_count, 3)  # 30 + 30 + 10
        for call in get_mock.await_args_list:
            self.assertLessEqual(len(call.args) - 4, 30)


class TestIndexedProbe(unittest.IsolatedAsyncioTestCase):
    async def test_instances_come_back_labelled(self):
        probe = CapabilityProbe()

        async def fake_walk(engine, auth, target, context, obj_type, **kw):
            for index, name in ((1, "temp-CPU"), (4, "temp-cpu")):
                yield (None, None, None, [var_bind(f"1.3.6.1.4.1.2021.13.16.2.1.2.{index}", name)])

        async def fake_get(engine, auth, target, context, *var_binds):
            return (None, None, None, [var_bind("x", "48000"), var_bind("x", "67000")])

        with patch("capability_probe.walk_cmd", new=fake_walk), \
             patch("capability_probe.get_cmd", new=AsyncMock(side_effect=fake_get)), \
             patch("capability_probe.UdpTransportTarget.create", new=AsyncMock(return_value=object())):
            rows = await probe.probe("10.0.0.1", "public", 161, [SENSOR])

        self.assertEqual(len(rows), 2)
        by_index = {r["instance_index"]: r for r in rows}
        self.assertEqual(by_index[1]["instance_label"], "temp-CPU")
        self.assertEqual(by_index[4]["instance_label"], "temp-cpu")
        self.assertTrue(all(r["supported"] for r in rows))

    async def test_name_column_walked_once_per_table(self):
        probe = CapabilityProbe()
        walks = []

        async def fake_walk(engine, auth, target, context, obj_type, **kw):
            walks.append(obj_type)
            yield (None, None, None, [var_bind("1.3.6.1.2.1.2.2.1.2.1", "eth0")])

        async def fake_get(engine, auth, target, context, *var_binds):
            return (None, None, None, [var_bind("x", "42") for _ in var_binds])

        shared = "1.3.6.1.2.1.2.2.1.2"
        two_interface_metrics = [
            {"id": "in", "name": "In", "oid_template": "1.3.6.1.2.1.2.2.1.10.{index}", "requires_index": True, "instance_oid": shared},
            {"id": "out", "name": "Out", "oid_template": "1.3.6.1.2.1.2.2.1.16.{index}", "requires_index": True, "instance_oid": shared},
        ]

        with patch("capability_probe.walk_cmd", new=fake_walk), \
             patch("capability_probe.get_cmd", new=AsyncMock(side_effect=fake_get)), \
             patch("capability_probe.UdpTransportTarget.create", new=AsyncMock(return_value=object())):
            rows = await probe.probe("10.0.0.1", "public", 161, two_interface_metrics)

        self.assertEqual(len(walks), 1, "the shared ifDescr column must be walked only once")
        self.assertEqual(len(rows), 2)

    async def test_indexed_metric_without_instance_oid_is_unsupported(self):
        probe = CapabilityProbe()
        no_column = [{"id": "d", "name": "X", "oid_template": "1.2.3.{index}", "requires_index": True}]
        with patch("capability_probe.UdpTransportTarget.create", new=AsyncMock(return_value=object())):
            rows = await probe.probe("10.0.0.1", "public", 161, no_column)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["supported"])
        self.assertIsNone(rows[0]["instance_index"])


if __name__ == "__main__":
    unittest.main()
