"""Tests for parser telemetry status handling."""

from types import SimpleNamespace

from src.parser.parserfsm import ParserFSM
from src.utils.tlm_fsm import TelemetryState


def test_new_telemetry_status_passes_enum_to_telemetry_fsm() -> None:
    """A protobuf integer state is converted before updating the telemetry FSM."""
    parser_fsm = ParserFSM()

    parser_fsm.new_telemetry_status(
        SimpleNamespace(state=TelemetryState.IDLE.value))

    assert parser_fsm.tlm_fsm.current_state.name == TelemetryState.IDLE.name
