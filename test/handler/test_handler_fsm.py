"""
Unit tests for the HandlerFSM class.
"""
import unittest
from unittest.mock import MagicMock

from src.handler.handler_fsm import HandlerFSM


class _DummyCondition:
    """Condition test double that records wait calls."""

    def __init__(self):
        """Initialize the recorded wait calls."""
        self.wait_calls = []

    def __enter__(self):
        """Enter the condition context."""
        return self

    def __exit__(self, exc_type, exc, tb):
        """Exit the condition context."""
        return False

    def wait(self, timeout=None):
        """Record the requested timeout."""
        self.wait_calls.append(timeout)


class TestHandlerFSM(unittest.TestCase):
    """Tests for HandlerFSM state behavior."""

    def test_do_run_transitions_to_disconnection_when_connection_drops(self):
        """Transition to disconnection when a connection drops."""
        fsm = object.__new__(HandlerFSM)
        dummy_condition = _DummyCondition()
        fsm._HandlerFSM__connection_condition = dummy_condition  # pylint: disable=protected-access
        fsm.are_both_connected = MagicMock(side_effect=[True, False, False])
        fsm.send = MagicMock()
        fsm.log_state = MagicMock()

        HandlerFSM.do_run(fsm)

        self.assertEqual(dummy_condition.wait_calls, [60])
        fsm.send.assert_called_once_with('disconnection')

    def test_log_on_mqtt_with_custom_topic(self):
        """Publish to custom topic when provided to log_on_mqtt."""
        fsm = object.__new__(HandlerFSM)
        mock_mqtt_conn = MagicMock()
        mock_mqtt_conn.is_connected.return_value = True
        mock_publish_result = MagicMock()
        mock_publish_result.rc = 0
        mock_mqtt_conn.connection.publish.return_value = mock_publish_result
        mock_handler = MagicMock()
        mock_handler.mqtt = mock_mqtt_conn
        fsm.handler = mock_handler
        mock_config = MagicMock()
        mock_config.log_on_mqtt = "default/topic"
        fsm.config = mock_config

        HandlerFSM.log_on_mqtt(
            fsm,
            message="running",
            topic="vehicle/device/info/status/influx-logger")

        mock_mqtt_conn.connection.publish.assert_called_once_with(
            topic="vehicle/device/info/status/influx-logger",
            payload="running",
            qos=0,
            retain=False)
