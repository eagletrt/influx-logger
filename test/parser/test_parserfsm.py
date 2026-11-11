"""Tests for parser telemetry status handling."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.parser.parserfsm import ParserFSM
from src.utils.tlm_fsm import TelemetryState

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


class TestParserFSM(unittest.TestCase):
    """Tests for ParserFSM status signaling and telemetry state handling."""

    def test_new_telemetry_status_passes_enum_to_telemetry_fsm(self) -> None:
        """A protobuf integer state is converted before updating the telemetry FSM."""
        parser_fsm = ParserFSM()

        parser_fsm.new_telemetry_status(
            SimpleNamespace(state=TelemetryState.IDLE.value))

        self.assertEqual(parser_fsm.tlm_fsm.current_state.name,
                         TelemetryState.IDLE.name)

    def test_signal_state_sends_to_mqtt_topic(self) -> None:
        """signal_state invokes log_callback with state and expected MQTT topic."""
        mock_callback = MagicMock()
        parser_fsm = ParserFSM(vehicle_id="kraken",
                               device_id="onboard",
                               log_callback=mock_callback)

        mock_callback.reset_mock()
        result = parser_fsm.signal_state()

        self.assertTrue(result)
        mock_callback.assert_called_once_with(
            "kraken/onboard/info/status/influx-logger/parserfsm",
            parser_fsm.current_state)

    def test_topic_derived_from_name_if_not_explicit(self) -> None:
        """Topic is derived from ParserFSM[vehicle_id/device_id] name if not explicitly set."""
        parser_fsm = ParserFSM(name="ParserFSM[fenice/telemetry]")

        self.assertEqual(parser_fsm.vehicle_id, "fenice")
        self.assertEqual(parser_fsm.device_id, "telemetry")
        self.assertEqual(parser_fsm.topic,
                         "fenice/telemetry/info/status/influx-logger/parserfsm")

    def test_signal_state_rejects_single_arg_callback(self) -> None:
        """signal_state reports failure when the callback has the wrong signature."""
        calls = []

        def single_arg_callback(state):
            calls.append(state)

        parser_fsm = ParserFSM(vehicle_id="kraken", device_id="onboard")
        parser_fsm.set_log_callback(single_arg_callback)
        calls.clear()

        result = parser_fsm.signal_state()

        self.assertFalse(result)
        self.assertEqual(calls, [])
