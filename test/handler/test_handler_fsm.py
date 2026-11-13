"""
Unit tests for the HandlerFSM class.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.handler.handler_fsm import HandlerFSM
from src.parser.libmanager import LibcanManager

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


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

    def notify_all(self):
        """Allow callback tests to record a notification without blocking."""


class TestHandlerFSM(unittest.TestCase):
    """Tests for HandlerFSM state behavior."""

    def test_initialization_wires_dispatcher_and_connection_handler(self):
        """HandlerFSM initializes with a dispatcher and connection handler."""
        config = SimpleNamespace(vehicle_whitelist=["v"])
        with patch("src.handler.handler_fsm.MsgDispatcher") as dispatcher_cls, \
                patch("src.handler.handler_fsm.ConnectionHandler") as handler_cls:
            fsm = HandlerFSM(config, name="test-handler")
        self.assertTrue(fsm.name)
        dispatcher_cls.assert_called_once_with(vehicle_whitelist=["v"])
        handler_cls.assert_called_once()
        self.assertIn(HandlerFSM.starting, fsm.configuration)

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

    def test_do_start_stop_machine_and_do_stop(self):
        """
        Test the do_start, stop_machine, and do_stop methods of HandlerFSM.
        """
        fsm = object.__new__(HandlerFSM)
        fsm.config = SimpleNamespace(github_token="token")
        fsm.handler = MagicMock()
        fsm.send = MagicMock()
        fsm._HandlerFSM__notify_connection_change = MagicMock()  # pylint: disable=protected-access
        fsm._HandlerFSM__connection_condition = _DummyCondition()  # pylint: disable=protected-access
        setattr(fsm, "_HandlerFSM__event", False)
        with patch.object(LibcanManager, "TOKEN", None):
            HandlerFSM.do_start(fsm)
        fsm.handler.set.assert_called_once()
        fsm.send.assert_called_once_with("init")
        fsm.msg_dispatcher = MagicMock()
        fsm.log_state = MagicMock()
        HandlerFSM.do_stop(fsm)
        fsm.msg_dispatcher.graceful_stop.assert_called_once_with()
        fsm.handler.stop_connections.assert_called_once_with()
        HandlerFSM.stop_machine(fsm)
        self.assertTrue(getattr(fsm, "_HandlerFSM__event"))
        self.assertEqual(fsm.send.call_args_list[-1].args, ("finish", ))

    def test_idle_and_running_entry_setup(self):
        """
        Test that entering the idling and running states performs the expected setup.
        """
        fsm = object.__new__(HandlerFSM)
        fsm.log_state = MagicMock()
        fsm.do_idle = MagicMock()
        HandlerFSM.on_enter_idling(fsm)
        fsm.do_idle.assert_called_once_with()

        fsm.config = SimpleNamespace(influx=SimpleNamespace(buckets={
            "adr": "a",
            "logs": "l"
        }),
                                     excluded_networks=[])
        fsm.handler = SimpleNamespace(influx_adr=MagicMock(), mqtt=MagicMock())
        fsm.msg_dispatcher = MagicMock()
        fsm.do_run = MagicMock()
        with patch("src.handler.handler_fsm.InfluxWriter") as writer_cls:
            fsm.msg_dispatcher.influx_writer = writer_cls.return_value
            HandlerFSM.on_enter_running(fsm)
        fsm.msg_dispatcher.set.assert_called_once_with(
            influx_writer=writer_cls.return_value, mqtt=fsm.handler.mqtt)
        writer_cls.return_value.parser.set_log_callback.assert_called_once_with(
            fsm.log_on_mqtt)
        fsm.msg_dispatcher.handle_existing_messages.assert_called_once_with()
        fsm.do_run.assert_called_once_with()

    def test_do_idle_connects_and_notifies_state_machine(self):
        """
        Test that do_idle connects and notifies the state machine.
        """
        fsm = object.__new__(HandlerFSM)
        fsm.handler = MagicMock()
        fsm.handler.start_connections = MagicMock()
        fsm.are_both_connected = MagicMock(return_value=True)
        fsm.log_state = MagicMock()
        fsm.send = MagicMock()
        fsm._HandlerFSM__event = False  # pylint: disable=protected-access
        HandlerFSM.do_idle(fsm)
        fsm.handler.start_connections.assert_called_once_with()
        fsm.send.assert_called_once_with("connection")

    def test_connection_change_notifies_waiters(self):
        """
        Test that connection change notifications wake up waiting threads.
        """
        fsm = object.__new__(HandlerFSM)
        condition = _DummyCondition()
        fsm._HandlerFSM__connection_condition = condition  # pylint: disable=protected-access
        fsm.log_state = MagicMock()
        HandlerFSM._HandlerFSM__notify_connection_change(fsm)  # pylint: disable=protected-access
        fsm.log_state.assert_called_once_with(
            "Connection state changed, notifying FSM")
