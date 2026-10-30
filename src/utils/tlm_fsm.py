'''
Finite State Machine of Telemetry as far as the Influx Logger knows.
'''

from statemachine import State, StateMachine
from statemachine.contrib.diagram import DotGraphMachine
from statemachine.transition_list import TransitionList


class TelemetryFSM(StateMachine):
    '''
    Finite State Machine of Telemetry as far as the Influx Logger knows.
    '''

    # States
    initializing: State = State('INIT', initial=True)
    waiting: State = State('WAIT_READY')
    idling: State = State('IDLE')
    setup_running: State = State('SETUP_RUN')
    running: State = State('RUN')
    erroring: State = State('ERROR')

    # Transitions
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

    @staticmethod
    def draw(filename: str = 'handler_fsm.png'):
        """
        Draws the FSM structure and saves it to a file.
        Args:
            filename (str): The name of the file to save the FSM diagram.
        """
        DotGraphMachine(TelemetryFSM).get_graph().write(filename, format='png')
