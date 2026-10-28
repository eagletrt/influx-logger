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
        fsm.log_status = MagicMock()

        HandlerFSM.do_run(fsm)

        self.assertEqual(dummy_condition.wait_calls, [60])
        fsm.send.assert_called_once_with('disconnection')
