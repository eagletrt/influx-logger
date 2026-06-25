import unittest
from unittest.mock import MagicMock

from src.handler.handler_fsm import HandlerFSM


class _DummyCondition:
    def __init__(self):
        self.wait_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)


class TestHandlerFSM(unittest.TestCase):
    def test_do_run_transitions_to_disconnection_when_connection_drops(self):
        fsm = object.__new__(HandlerFSM)
        dummy_condition = _DummyCondition()
        fsm._HandlerFSM__connection_condition = dummy_condition
        fsm.are_both_connected = MagicMock(side_effect=[True, False])
        fsm.send = MagicMock()

        HandlerFSM.do_run(fsm)

        self.assertEqual(dummy_condition.wait_calls, [1])
        fsm.send.assert_called_once_with('disconnection')
