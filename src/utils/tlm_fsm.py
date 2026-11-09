'''
Finite State Machine of Telemetry as far as the Influx Logger knows.
'''

from enum import IntEnum
from threading import Lock

from statemachine import State, StateMachine
from statemachine.contrib.diagram import DotGraphMachine
from statemachine.transition_list import TransitionList


class TelemetryState(IntEnum):
    """State values defined by ``telemetry/status.proto``."""

    INIT = 0
    IDLE = 1
    SETUP_RUN = 2
    RUN = 3
    WAIT_READY = 4
    ERROR = 5

    def get_from_value(self: int) -> "TelemetryState":
        """
        Returns the TelemetryState corresponding to the given integer value.
        Args:
            value (int): The integer value representing a TelemetryState.
        Returns:
            TelemetryState: The corresponding TelemetryState.
        Raises:
            ValueError: If the value does not correspond to any TelemetryState.
        """
        for state in TelemetryState:
            if state.value == self:
                return state
        raise ValueError(f"Invalid TelemetryState value: {self}")


class TelemetryFSM(StateMachine):
    '''
    Finite State Machine of Telemetry as far as the Influx Logger knows.
    '''

    # States
    initializing: State = State(TelemetryState.INIT.name, initial=True)
    waiting: State = State(TelemetryState.WAIT_READY.name)
    idling: State = State(TelemetryState.IDLE.name)
    setup_running: State = State(TelemetryState.SETUP_RUN.name)
    running: State = State(TelemetryState.RUN.name)
    erroring: State = State(TelemetryState.ERROR.name)

    # Eventless transitions
    init_to_waitready: TransitionList = initializing.to(waiting)
    init_to_idle: TransitionList = initializing.to(idling)
    init_to_error: TransitionList = initializing.to(erroring)
    waitready_to_idle: TransitionList = waiting.to(idling)
    waitready_to_error: TransitionList = waiting.to(erroring)
    idle_to_setuprun: TransitionList = idling.to(setup_running)
    idle_to_error: TransitionList = idling.to(erroring)
    setuprun_to_run: TransitionList = setup_running.to(running)
    setuprun_to_error: TransitionList = setup_running.to(erroring)
    run_to_idle: TransitionList = running.to(idling)
    run_to_error: TransitionList = running.to(erroring)
    error_to_init: TransitionList = erroring.to(initializing)

    def __init__(self, name: str = "TelemetryFSM") -> None:
        """
        Initializes the TelemetryFSM instance.
        Args:
            name (str): The name of the FSM.
        """
        self.name: str = name
        '''
        Name of the FSM, used for logging purposes.
        '''
        StateMachine.__init__(self)
        self.activate_initial_state()
        self._mutex: Lock = Lock()
        '''
        Mutex for thread-safe operations on the FSM.
        '''

    @staticmethod
    def draw(filename: str = 'handler_fsm.png'):
        """
        Draws the FSM structure and saves it to a file.
        Args:
            filename (str): The name of the file to save the FSM diagram.
        """
        DotGraphMachine(TelemetryFSM).get_graph().write(filename, format='png')

    def set_current_state(self, state: TelemetryState) -> bool:
        """
        Sets the current state of the FSM based on the provided state.
        Args:
            state (TelemetryState): The state to set as the current state.
        """
        state_mapping = {
            TelemetryState.INIT: "initializing",
            TelemetryState.WAIT_READY: "waiting",
            TelemetryState.IDLE: "idling",
            TelemetryState.SETUP_RUN: "setup_running",
            TelemetryState.RUN: "running",
            TelemetryState.ERROR: "erroring",
        }
        try:
            target_state = self.states_map[state_mapping[state]]
        except KeyError as error:
            raise ValueError(f"Invalid state name: {state}") from error

        if self.current_state != target_state:
            self._change_state(target_state)
            return True
        return False

    def _change_state(self, new_state: State) -> None:
        """
        Changes the current state of the FSM to the specified state.
        Args:
            new_state (TelemetryState): The state to change to.
        """
        with self._mutex:
            self.current_state = new_state
