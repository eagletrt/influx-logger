from threading import Thread, Condition
from statemachine import StateMachine, State
from statemachine.contrib.diagram import DotGraphMachine

# Info about FSM at https://github.com/fgmacedo/python-statemachine

from src.utils.logger_utils import logger
from src.utils.configuration import Configuration
from src.influx.influx_writer import InfluxWriter
from src.handler.msg_dispatcher import MsgDispatcher
from src.connections.connection_handler import ConnectionHandler

class HandlerFSM(Thread, StateMachine):
    """
    This class implements a finite state machine (FSM) to manage the states and transitions of the handler.
    It extends the StateMachine class from the statemachine library and the Thread class from the threading library.
    The FSM has four states: start, idle, run, and stop. It also defines events to transition between these states based on the connection status of InfluxDB and MQTT broker.
    Attributes:
        parser: An instance of the Parser class to parse incoming data.
        influx_logger: An instance of the InfluxLogger class to manage logging to InfluxDB

        start: The initial state of the FSM.
        idle: The state when the handler is idle and waiting for connections.
        run: The state when the handler is running and both connections are established.
        stop: The final state of the FSM when the handler is stopped.
    """
    # Finite State Machine states
    # ing form is used due to conflicts with Thread reserved words
    starting: State = State('start', initial=True)
    idling: State = State('idle')
    running: State = State('run')
    final: State = State('stop', final=True)

    # Events
    init = starting.to(idling)
    connection = (
        idling.to(running, cond=['are_both_connected'])
        |   idling.to(idling, unless=['are_both_connected'])
    )
    disconnection = (
        running.to(idling)
        | idling.to(idling)
    )
    finish = (
        running.to(final)
        | idling.to(final)
    )

    def __init__(self, config: Configuration, name: str = "HandlerFSM"):
        self.msg_dispatcher: MsgDispatcher = MsgDispatcher()
        '''MsgDispatcher object responsible for handling incoming MQTT messages and dispatching them to the appropriate handlers.'''
        self.config: Configuration = config
        '''Configuration object containing settings for MQTT and InfluxDB connections.'''
        self.__connection_condition: Condition = Condition()
        '''Condition variable used to synchronize connection state changes between threads.'''
        self.handler: ConnectionHandler = ConnectionHandler(
            self.config,
            on_state_change=self.__notify_connection_change,
        )
        '''ConnectionHandler object responsible for managing connections to InfluxDB and MQTT broker.'''
        self.__event: bool = False
        '''Flag indicating whether an event has occurred that requires the FSM to transition to a different state.'''
        Thread.__init__(self, name=name)
        StateMachine.__init__(self)

    def __notify_connection_change(self) -> None:
        logger.info(f"{self.get_log_header()} - Connection state changed, notifying FSM")
        with self.__connection_condition:
            self.__connection_condition.notify_all()

    @staticmethod
    def draw(filename: str = 'handler_fsm.png'):
        DotGraphMachine(HandlerFSM).get_graph().write_png(filename)

    def get_log_header(self) -> str:
        """
        Returns a string containing the name of the FSM and its current state for logging purposes.
        Returns:
            str: A string containing the name of the FSM and its current state.
        """
        return f"{self.name} {self.current_state}"

    def are_both_connected(self) -> bool:
        """
        Check if both InfluxDB and MQTT connections are established.

        Returns:
            bool: True if both connections are established, False otherwise.
        """
        return self.handler.are_both_connected()

    def on_connection(self):
        """
        Event triggered when a connection is established. It checks if both connections are established and transitions to the appropriate state.
        If both connections are established, it transitions to the running state. If only one connection is established, it remains in the idle state and continues to check for both connections.
        If neither connection is established, it remains in the idle state and continues to check for both connections.
        """
        logger.info(f"{self.get_log_header()} - on_connection event triggered")
    
    def on_disconnection(self):
        """
        Event triggered when a disconnection occurs. It checks if both connections are still established and transitions to the appropriate state.
        If both connections are still established, it remains in the running state. If one or both connections are lost, it transitions to the idle state and continues to check for both connections.
        """
        logger.info(f"{self.get_log_header()} - on_disconnection event triggered")
    
    def on_finish(self):
        """
        Event triggered when the finish event is called. It transitions to the final state and performs any necessary cleanup operations.
        """
        logger.info(f"{self.get_log_header()} - on_finish event triggered")
    
    def on_enter_starting(self):
        """
        Method called when entering the start state. It initializes the connections and prepares the handler for operation.
        """
        logger.info(f"{self.get_log_header()} - Entering start state")

    def on_enter_idling(self):
        """
        Method called when entering the idle state. It starts the connections and waits for both connections to be established before transitioning to the running state.
        If both connections are not established, it remains in the idle state and continues to check for both connections.
        """
        logger.info(f"{self.get_log_header()} - Entering idle state")
        self.do_idle()
    
    def on_enter_running(self):
        """
        Method called when entering the running state. It starts the handler's main operation, which involves processing incoming data and logging it to InfluxDB.
        If either connection is lost while in the running state, it transitions back to the idle state and continues to check for both connections.
        """
        logger.info(f"{self.get_log_header()} - Entering running state")
        self.msg_dispatcher.set(
            influx_writer=InfluxWriter(self.handler.influx_connection), # TODO: Add timestamp precision and other parameters if needed
            influx_reader=None, # TODO: Add InfluxReader if needed
            mqtt=self.handler.mqtt_connection,
        )
        self.do_run()

    def on_enter_final(self):
        """
        Method called when entering the stop state. It performs any necessary cleanup operations, such as stopping the connections and releasing resources.
        """
        logger.info(f"{self.get_log_header()} - Entering stop state")
        self.do_stop()
    
    def on_exit_running(self):
        """
        Method called when exiting the running state. It performs any necessary cleanup operations, such as stopping the handler's main operation and releasing resources.
        """
        logger.info(f"{self.get_log_header()} - Exiting running state")
        if not self.handler.are_both_connected():
            self.msg_dispatcher.stop()  # Stop the MsgDispatcher if connections are lost

    def do_start(self):
        """
        Method to start the FSM. It triggers the init event to transition from the start state to the idle state and begins the FSM operation.
        """
        self.handler.set(
            self.config,
            on_state_change=self.__notify_connection_change,
            on_message=self.on_message,
        )
        self.send('init')

    def do_idle(self):
        """
        Method to handle the idle state. It triggers the connection event to check for both connections and transition to the appropriate state based on the connection status.
        If both connections are established, it transitions to the running state. If only one connection is established, it remains in the idle state and continues to check for both connections.
        If neither connection is established, it remains in the idle state and continues to check for both connections.
        """
        self.__event = False
        while not self.__event and not self.are_both_connected():
            logger.info(f"{self.get_log_header()} - Trying connection")
            self.handler.start_connections()
            with self.__connection_condition:
                self.__connection_condition.wait(timeout=1.0)
        if self.are_both_connected():
            logger.info(f"{self.get_log_header()} - Both connections established, transitioning to running state")
            self.send('connection')

    def do_run(self):
        """
        Method to handle the running state. It performs the main operation of the handler, which involves processing incoming data and logging it to InfluxDB.
        If either connection is lost while in the running state, it triggers the disconnection event to transition back to the idle state and continues to check for both connections.
        """
        self.__event = False
        while not self.__event and self.are_both_connected():
            # TODO: Implement the main operation of the handler, such as processing incoming data and logging it to InfluxDB
            logger.info(f"{self.get_log_header()} - Running")
            with self.__connection_condition:
                self.__connection_condition.wait(timeout=60)  # Simulate work being done
            #with self.__connection_condition:
            #    self.__connection_condition.wait()
        if not self.are_both_connected():
            logger.info(f"{self.get_log_header()} - Connection lost, transitioning to idle state")
            self.send('disconnection')

    def do_stop(self):
        """
        Method to handle the stop state. It performs any necessary cleanup operations, such as stopping the connections and releasing resources.
        """
        self.handler.stop_connections()
        logger.info(f"{self.get_log_header()} - Connections stopped, handler in finale state")

    def do_state(self):
        """
        Method to handle the current state of the FSM. It checks the current state and calls the appropriate method to handle that state.
        This method is called in the run method to continuously check and handle the current state of the FSM.
        """
        if self.current_state == self.starting:
            self.do_start()
        elif self.current_state == self.idling:
            self.do_idle()
        elif self.current_state == self.running:
            self.do_run()
        else:
            self.do_stop()

    def stop_machine(self):
        """
        Method to stop the FSM. It triggers the finish event to transition to the final state and perform any necessary cleanup operations.
        """
        self.__event = True
        self.send('finish')
        with self.__connection_condition:
            self.__connection_condition.notify_all()

    def run(self):
        logger.info(f"{self.get_log_header()} - Thread started")
        while self and self.current_state != self.final:
            logger.info(f"{self.get_log_header()} - Thread running")
            self.do_state()
        if self:
            self.do_stop()
        logger.info(f"{self.get_log_header()} - Thread finished")

    def on_message(self, topic: str, payload: bytes):
        '''
        Callback method to handle incoming MQTT messages. It is called by the MQTT connection when a message is received.
        Args:
            topic (str): The topic of the incoming MQTT message.
            payload (bytes): The payload of the incoming MQTT message.
        '''
        # Handle message only if the FSM is in the running state
        if self.current_state != self.running:
            return
        self.msg_dispatcher.handle_incoming_message(topic, payload)
