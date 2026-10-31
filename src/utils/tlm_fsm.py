'''
Finite State Machine of Telemetry as far as the Influx Logger knows.
'''

from threading import Lock

from statemachine import State, StateMachine
from statemachine.contrib.diagram import DotGraphMachine
from statemachine.transition_list import TransitionList

from lib.external.serializers.py.telemetry.status import TelemetryState


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
        if state.name in self.states:
            if self.current_state != self.states[state.name]:
                self._change_state(state)
                return True
            else:
                # If the current state is already the desired state, do nothing
                pass
        else:
            raise ValueError(f"Invalid state name: {state}")
        return False

    def _change_state(self, new_state: TelemetryState) -> None:
        """
        Changes the current state of the FSM to the specified state.
        Args:
            new_state (TelemetryState): The state to change to.
        """
        with self._mutex:
            self.current_state.exit()
            self.current_state = self.states[new_state.name]
            self.current_state.enter()


#TelemetryFSM.draw('handler_fsm.png')
