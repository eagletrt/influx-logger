"""Tests for parser telemetry status handling."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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

        self.assertIn(parser_fsm.tlm_fsm.idling,
                      parser_fsm.tlm_fsm.configuration)

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
            parser_fsm.get_state())

    def test_topic_derived_from_name_if_not_explicit(self) -> None:
        """Topic is derived from ParserFSM[vehicle_id/device_id] name if not explicitly set."""
        parser_fsm = ParserFSM(name="ParserFSM[fenice/telemetry]")

        self.assertEqual(parser_fsm.vehicle_id, "fenice")
        self.assertEqual(parser_fsm.device_id, "telemetry")
        self.assertEqual(
            parser_fsm.topic,
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

    def test_topic_override_callback_replacement_and_state_helpers(
            self) -> None:
        """
        Test that the topic can be overridden, the log callback can be replaced,
        and that state helpers work as expected.
        """
        parser_fsm = ParserFSM(vehicle_id="v", device_id="d")
        parser_fsm.topic = "custom/topic"
        self.assertEqual(parser_fsm.topic, "custom/topic")
        callback = MagicMock()
        parser_fsm.set_log_callback(callback)
        self.assertIs(parser_fsm.log_callback, callback)
        self.assertIn("ParserFSM", parser_fsm.get_log_header())
        parser_fsm.log_state("quiet", signal=False)
        self.assertEqual(parser_fsm.get_state(), parser_fsm.configuration)
        self.assertFalse(parser_fsm.is_logging())

    def test_incoming_message_timeout_returns_running_fsm_to_idle(
            self) -> None:
        """
        Test that the FSM transitions to idling after a message timeout.
        """
        parser_fsm = ParserFSM()
        with patch("src.parser.parserfsm.Timer") as timer_cls:
            parser_fsm.on_message_received()
        timer_cls.assert_called_once()
        timer_cls.return_value.start.assert_called_once_with()
        parser_fsm.send("initialization")
        parser_fsm.send("message_received")
        parser_fsm._ParserFSM__handle_message_timeout()  # pylint: disable=protected-access
        self.assertIn(parser_fsm.idling, parser_fsm.configuration)

    def test_telemetry_run_starts_logging_and_finish_cancels_timer(
            self) -> None:
        """
        Test that telemetry RUN state starts logging and on_finish cancels the message timer.
        """
        parser_fsm = ParserFSM()
        parser_fsm.send("initialization")
        parser_fsm.new_telemetry_status(
            SimpleNamespace(state=TelemetryState.RUN.value))
        self.assertTrue(parser_fsm.is_logging())
        parser_fsm._timeout_waiting_for_run = True  # pylint: disable=protected-access
        parser_fsm.new_telemetry_status(
            SimpleNamespace(state=TelemetryState.IDLE.value))
        self.assertFalse(parser_fsm.is_logging())
        timer = MagicMock()
        parser_fsm._message_timer = timer  # pylint: disable=protected-access
        parser_fsm.on_finish()
        timer.cancel.assert_called_once_with()
        self.assertIsNone(parser_fsm._message_timer)  # pylint: disable=protected-access

    def test_invalid_telemetry_state_is_ignored(self) -> None:
        """Invalid telemetry state values do not change the FSM configuration."""
        parser_fsm = ParserFSM()
        parser_fsm.new_telemetry_status(SimpleNamespace(state=99))
        self.assertIn(parser_fsm.starting, parser_fsm.configuration)
