"""Tests for shared Influx manager thread state."""

from unittest import TestCase
from unittest.mock import MagicMock

from src.influx.influx_manager import InfluxManager


class TestInfluxManager(TestCase):

    def test_stop_flag_and_configuration(self):
        manager = InfluxManager(MagicMock(),
                                timestamp_precision="ms",
                                name="worker")
        self.assertFalse(manager.stopped())
        self.assertEqual(manager.timestamp_precision, "ms")
        self.assertEqual(manager.name, "worker")
        manager.stop()
        self.assertTrue(manager.stopped())
