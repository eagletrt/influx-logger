"""Tests that FSM diagram helpers delegate output to the graph renderer."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from src.handler.handler_fsm import HandlerFSM
from src.parser.parserfsm import ParserFSM
from src.utils.tlm_fsm import TelemetryFSM


class TestFSMDiagrams(TestCase):
    """
    Tests that FSM diagram helpers delegate output to the graph renderer.
    """

    def test_each_machine_writes_a_png_graph(self):
        """
        Tests that each FSM class delegates to the DotGraphMachine renderer
        and that the renderer's graph is written to a PNG file.
        """
        for module, machine, filename in (("src.handler.handler_fsm",
                                           HandlerFSM, "handler.png"),
                                          ("src.parser.parserfsm", ParserFSM,
                                           "parser.png"), ("src.utils.tlm_fsm",
                                                           TelemetryFSM,
                                                           "telemetry.png")):
            with self.subTest(machine=machine.__name__):
                renderer = MagicMock()
                with patch(f"{module}.DotGraphMachine", return_value=renderer):
                    machine.draw(filename)
                renderer.get_graph.return_value.write.assert_called_once_with(
                    filename, format="png")
