"""
Finite State Machine for the parser.
This module defines the states and transitions for the parser's finite state machine.
"""

from queue import Queue

from statemachine import State, StateMachine
from statemachine.contrib.diagram import DotGraphMachine
from statemachine.transition_list import TransitionList

from src.utils.logger_utils import logger


class ParserFSM(StateMachine):
    """
    Finite State Machine for the parser.
    This class defines the states and transitions for
    the parser's finite state machine.
    """

    # Finite State Machine states
    # ing form is used due to conflicts with Thread reserved words
    starting: State = State("start", initial=True)
    idling: State = State("idle")
    running: State = State("running")
    logging: State = State("logging")
    erroring: State = State("error")
    final: State = State("stop", final=True)

    # Event transitions
    initialization: TransitionList = starting.to(idling)
    message_received: TransitionList = idling.to(running)
    no_messages_to_process: TransitionList = (running.to(idling)
                                              | logging.to(idling))
    log_started: TransitionList = running.to(logging)
    log_stopped: TransitionList = logging.to(running)
    error_occurred: TransitionList = (running.to(erroring)
                                      | logging.to(erroring))
    restore_from_error: TransitionList = erroring.to(idling)
    finish: TransitionList = idling.to(final)

    def __init__(self,
                 name: str = "ParserFSM",
                 log_callback: callable = None) -> None:
        """
        Initialize the parser.
        Args:
            name (str): The name of the FSM.
            log_callback (callable): The callback function to be set for logging.
        """
        self.name = name
        '''
        Name of the FSM, used for logging purposes.
        '''
        self.log_callback = log_callback
        '''
        The callback function to be set for logging.
        '''
        StateMachine.__init__(self)
        self.logging_states: Queue = Queue
        '''Queue to hold the logging states.'''

    def set_log_callback(self, callback: callable) -> None:
        """
        Sets the log callback function for the parser's finite state machine.
        Args:
            callback (callable): The callback function to be set for logging.
        """
        self.log_callback = callback
        self.log_state(f"Log callback set to {callback}")

    @staticmethod
    def draw(filename: str = 'parser_fsm.png'):
        """
        Draws the FSM structure and saves it to a file.
        Args:
            filename (str): The name of the file to save the FSM diagram.
        """
        DotGraphMachine(ParserFSM).get_graph().write(filename, format='png')

    def get_log_header(self) -> str:
        """
        Returns a string containing the name of the FSM
        and its current state for logging purposes.
        Returns:
            str: A string containing the name of the FSM and its current state.
        """
        return f"{self.name} {self.current_state}"

    def log_state(self, message: str = "", signal: bool = True):
        """
        Logs a message with the FSM name and current state.
        Args:
            message (str): The message to log.
            signal (bool): Whether to signal the current state after logging.
        """
        logger.info("%s - %s", self.get_log_header(), message)
        if signal:
            self.signal_state()

    def on_initialization(self):
        """
        Callback for the initialization event.
        Logs the initialization of the FSM.
        """
        self.log_state("Initialization")

    def signal_state(self) -> bool:
        """
        Signals the current state of the FSM.
        This method is intended to be called to signal
        the current state of the FSM.
        It sends the current state via MQTT.
        """
        if self.log_callback:
            try:
                self.log_callback(self.current_state)
                return True
            except Exception as e:  # pylint: disable=broad-except
                self.log_state(f"Error signaling state: {e}", signal=False)
        return False

    def restore(self):
        """
        Restores the FSM from an error state to the idling state.
        This method is intended to be called when an error has occurred
        and the FSM needs to be restored to a stable state.
        """
        self.send('restore_from_error')

    def on_message_received(self):
        """
        Callback for the message_received event.
        Logs the reception of a message.
        """
        self.log_state("Message received")

    def on_log_started(self):
        """
        Callback for the log_started event.
        Logs the start of logging.
        """
        self.log_state("Start logging")

    def on_log_stopped(self):
        """
        Callback for the log_stopped event.
        Logs the stop of logging.
        """
        self.log_state("Stop logging")

    def on_error_occurred(self):
        """
        Callback for the error_occurred event.
        Logs the occurrence of an error.
        """
        self.log_state("Error occurred")

    def on_restore(self):
        """
        Callback for the restore event.
        Logs the restoration from an error state.
        """
        self.log_state("Restored from error")

    def on_finish(self):
        """
        Callback for the finish event.
        Logs the termination of the FSM.
        """
        self.log_state("Terminating")

    def on_enter_starting(self):
        """
        Callback for entering the starting state.
        Logs the entry into the starting state.
        """
        self.log_state("Entering starting state")
        self.signal_state()

    def on_enter_idling(self):
        """
        Callback for entering the idling state.
        Logs the entry into the idling state.
        """
        self.log_state("Entering idling state")
        self.signal_state()

    def on_enter_running(self):
        """
        Callback for entering the running state.
        Logs the entry into the running state.
        """
        self.log_state("Entering running state")
        self.signal_state()

    def on_enter_logging(self):
        """
        Callback for entering the logging state.
        Logs the entry into the logging state.
        """
        self.log_state("Entering logging state")
        self.signal_state()

    def on_enter_erroring(self):
        """
        Callback for entering the erroring state.
        Logs the entry into the erroring state.
        """
        self.log_state("Entering erroring state")
        self.signal_state()
        self.restore()

    def on_enter_final(self):
        """
        Callback for entering the final state.
        Logs the entry into the final state.
        """
        self.log_state("Entering final state")
        self.signal_state()


#ParserFSM.draw('parser_fsm.png')
