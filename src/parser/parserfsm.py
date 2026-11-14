"""
Finite State Machine for the parser.
This module defines the states and transitions for the parser's finite state machine.
"""

from threading import Lock, Timer

from google.protobuf.message import Message
from statemachine import State, StateMachine
from statemachine.contrib.diagram import DotGraphMachine
from statemachine.orderedset import OrderedSet
from statemachine.transition_list import TransitionList

from src.utils.logger_utils import logger

TLM_LOGGING_STATES: set[int] = {
    2,  # TelemetryState.SETUP_RUN.value,
    3  # TelemetryState.RUN.value,
}


class ParserFSM(StateMachine):  # pylint: disable=too-many-instance-attributes
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
    final: State = State("stop", final=True)

    # Event transitions
    initialization: TransitionList = starting.to(idling)
    message_received: TransitionList = (idling.to(running)
                                        | running.to(running)
                                        | logging.to(logging))
    no_messages_to_process: TransitionList = (running.to(idling)
                                              | logging.to(idling))
    log_started: TransitionList = (running.to(logging) | idling.to(logging))
    log_stopped: TransitionList = logging.to(running)
    finish: TransitionList = idling.to(final)

    MESSAGE_TIMEOUT: float = 5.5
    '''
    The timeout duration in seconds for waiting for messages.
    If no messages are received within this duration, the FSM will transition to the idle state.
    '''

    def __init__(self,
                 name: str = "ParserFSM",
                 log_callback: callable = None,
                 vehicle_id: str | None = None,
                 device_id: str | None = None,
                 topic: str | None = None) -> None:
        """
        Initialize the parser.
        Args:
            name (str): The name of the FSM.
            log_callback (callable): The callback function to be set for logging.
            vehicle_id (str, optional): The unique identifier for the vehicle.
            device_id (str, optional): The unique identifier for the device.
            topic (str, optional): The MQTT topic for signaling the FSM status.
        """
        self.name = name
        '''
        Name of the FSM, used for logging purposes.
        '''
        self.vehicle_id = vehicle_id
        '''
        Vehicle ID associated with this FSM.
        '''
        self.device_id = device_id
        '''
        Device ID associated with this FSM.
        '''
        if (self.vehicle_id is None or self.device_id is None) and self.name:
            if self.name.startswith("ParserFSM[") and self.name.endswith("]"):
                parts = self.name[10:-1].split("/", 1)
                if len(parts) == 2:
                    if self.vehicle_id is None:
                        self.vehicle_id = parts[0]
                    if self.device_id is None:
                        self.device_id = parts[1]

        self._topic = topic
        self.log_callback = log_callback
        '''
        The callback function to be set for logging.
        '''
        StateMachine.__init__(self)

        self._message_timer: Timer | None = None
        self._message_timer_lock = Lock()
        self._timeout_waiting_for_run = False

        self.tlm_state: int = 0
        '''
        Current Telemetry known state
        '''

    @property
    def topic(self) -> str | None:
        """
        Returns the MQTT topic for signaling the FSM status.
        Formatted as vehicle_id/device_id/info/status/influx-logger.
        """
        if self._topic is not None:
            return self._topic
        if self.vehicle_id and self.device_id:
            return f"{self.vehicle_id}/{self.device_id}/info/status/influx-logger/parserfsm"
        return None

    @topic.setter
    def topic(self, value: str | None) -> None:
        self._topic = value

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
        return f"{self.name} {str(self.get_state().name)}"

    def log_state(self, message: str = "", signal: bool = True):  # pylint: disable=unused-argument
        """
        Logs a message with the FSM name and current state.
        Args:
            message (str): The message to log.
            signal (bool): Whether to signal the current state after logging.
        """
        #logger.info("%s - %s", self.get_log_header(), message)
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
                topic = self.topic
                if topic is not None:
                    try:
                        self.log_callback(topic, self.get_state())
                    except TypeError:
                        try:
                            self.log_callback(topic, self.get_state())
                        except TypeError:
                            return False
                else:
                    self.log_callback(self.get_state())
                return True
            except Exception as e:  # pylint: disable=broad-except
                self.log_state(f"Error signaling state: {e}", signal=False)
        return False

    def on_message_received(self):
        """
        Callback for the message_received event.
        Logs the reception of a message.
        """
        self.__reset_message_timer()
        #self.log_state("Message received")

    def __reset_message_timer(self) -> None:
        """
        Restart the inactivity timer after receiving a message.
        """
        with self._message_timer_lock:
            if self._message_timer is not None:
                self._message_timer.cancel()
            self._message_timer = Timer(self.MESSAGE_TIMEOUT,
                                        self.__handle_message_timeout)
            self._message_timer.daemon = True
            self._message_timer.start()

    def __handle_message_timeout(self) -> None:
        """
        Return to idle after X seconds without a message.
        """
        with self._message_timer_lock:
            self._message_timer = None
            if self.get_state() == self.running:
                self.send('no_messages_to_process')
            elif self.get_state() == self.logging:
                self._timeout_waiting_for_run = True

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
        if self._timeout_waiting_for_run:
            self._timeout_waiting_for_run = False
            if self.get_state() == self.running:
                self.send('no_messages_to_process')

    def on_finish(self):
        """
        Callback for the finish event.
        Logs the termination of the FSM.
        """
        with self._message_timer_lock:
            if self._message_timer is not None:
                self._message_timer.cancel()
                self._message_timer = None
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
        #self.log_state("Entering idling state")
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

    def on_enter_final(self):
        """
        Callback for entering the final state.
        Logs the entry into the final state.
        """
        self.log_state("Entering final state")
        self.signal_state()

    def __set_tlm_state(self, telemetry_state: int) -> bool:
        """
        Sets the current telemetry state.
        This method is intended to be called when a new telemetry state is received.
        It updates the current telemetry state and handles any necessary
        state changes in the parser's FSM.
        Args:
            telemetry_state: The new telemetry state.
        Returns:
            bool: True if the telemetry state changed, False otherwise.
        """
        if telemetry_state != self.tlm_state:
            self.tlm_state = telemetry_state
            return True
        return False

    def new_telemetry_status(self, telemetry_status: Message) -> None:
        """
        Handles a new telemetry status message.
        This method is intended to be called when a new telemetry status message is received.
        It sends the telemetry status message to the TelemetryFSM instance for processing.
        Args:
            telemetry_status: The new telemetry status message.
        """
        #logger.info("parserfsm: New telemetry status received: %s", telemetry_status)
        try:
            telemetry_state: int = int(telemetry_status.state)
            if telemetry_state:
                if self.__set_tlm_state(telemetry_state):
                    self.__tlm_state_changed(telemetry_state)
        except ValueError as e:
            logger.error("%s - Error setting current state: %s",
                         self.get_log_header(), str(e))
            logger.exception("Telemetry status handling failed")

    def __is_state_in_logging_states(self, tlm_state: int) -> bool:
        """
        Checks if the given telemetry state is in the set of logging states.
        Args:
            tlm_state: The telemetry state to check.
        Returns:
            bool: True if the telemetry state is in the set of logging states, False otherwise.
        """
        return tlm_state in TLM_LOGGING_STATES

    def __tlm_state_changed(self, new_state: int) -> None:
        """
        Handles a change in the telemetry state.
        This method is intended to be called when the telemetry state changes.
        It sends the appropriate event to the parser's FSM based on the new telemetry state.
        Args:
            new_state: The new telemetry state.
        """
        self.log_state(f"Telemetry state changed to: {new_state}")
        if self.__is_state_in_logging_states(
                new_state) and not self.is_logging():
            self.send('log_started')
        elif self.__is_state_in_logging_states(
                new_state) and self.is_logging():
            self.send('log_stopped')

    def msg_incoming(self) -> None:
        """
        Handles an incoming message.
        This method is intended to be called when a new message is received.
        It sends the 'message_received' event to the parser's FSM.
        """
        self.send('message_received')

    def get_state(self) -> State:
        """
        Returns the current state of the parser's FSM as a string.
        Returns:
            State: The current state of the parser's FSM.
        """
        set_of_states: OrderedSet[State] = self.configuration
        state: State = next(iter(set_of_states))
        return state

    def is_logging(self) -> bool:
        """
        Checks if the parser's FSM is currently in the logging state.
        Returns:
            bool: True if the FSM is in the logging state, False otherwise.
        """
        return self.get_state() == self.logging
