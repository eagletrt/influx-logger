"""Tests for timestamp and telemetry state helpers."""

import unittest

from src.utils.timestamp import TimestampPrecision
from src.utils.tlm_fsm import TelemetryFSM, TelemetryState


class TestTimestampPrecision(unittest.TestCase):

    def test_precision_name_and_factor_mappings(self):
        for name, factor in (("ns", 1), ("us", 1_000), ("ms", 1_000_000),
                             ("s", 1_000_000_000)):
            self.assertEqual(TimestampPrecision.get_factor(name), factor)
            self.assertEqual(TimestampPrecision.get_name(factor), name)
        self.assertIsNone(TimestampPrecision.get_factor("minutes"))
        self.assertIsNone(TimestampPrecision.get_name(0))


class TestTelemetryFSM(unittest.TestCase):

    def test_state_value_conversion(self):
        self.assertIs(TelemetryState.IDLE.get_from_value(),
                      TelemetryState.IDLE)
        with self.assertRaisesRegex(ValueError, "Invalid TelemetryState"):
            TelemetryState.get_from_value(10)

    def test_state_change_reports_whether_state_changed(self):
        fsm = TelemetryFSM()
        self.assertTrue(fsm.set_current_state(TelemetryState.IDLE))
        self.assertFalse(fsm.set_current_state(TelemetryState.IDLE))
        self.assertIn(fsm.idling, fsm.configuration)

    def test_invalid_state_is_rejected(self):
        fsm = TelemetryFSM()
        with self.assertRaisesRegex(ValueError, "Invalid state name"):
            fsm.set_current_state("invalid")
