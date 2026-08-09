from threading import Thread, Condition
from statemachine import StateMachine, State
from statemachine.contrib.diagram import DotGraphMachine

# Info about FSM at https://github.com/fgmacedo/python-statemachine

from src.utils.logger_utils import logger
from src.utils.configuration import Configuration
from src.influx.influx_writer import InfluxWriter
from src.influx.influx_reader import InfluxReader
from src.handler.msg_dispatcher import MsgDispatcher
from src.parser.protobuf_manager import LibcanManager
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

    def __init__(self, config: Configuration, name: str = "HandlerFSM") -> None:
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
        self.log_status("Connection state changed, notifying FSM")
        with self.__connection_condition:
            self.__connection_condition.notify_all()

    @staticmethod
    def draw(filename: str = 'handler_fsm.png'):
        """
        Draws the FSM structure and saves it to a file.
        Args:
            filename (str): The name of the file to save the FSM diagram. Defaults to 'handler_fsm.png'.
        """
        DotGraphMachine(HandlerFSM).get_graph().write_png(filename)

    def log_status(self, message: str):
        """
        Logs a message with the FSM name and current state.
        Args:
            message (str): The message to log.
        """
        logger.info(f"{self.get_log_header()} - {message}")
        topic = "lorenzo/onboard/info/status/influx-logger"
        msg = f"{self.current_state}"
        if self.config.log_on_mqtt:
            try:
                result = self.handler.mqtt.connection.publish(
                    topic=self.config.log_on_mqtt,
                    payload=msg,
                )
                if result.rc != 0:
                    logger.error(f"{self.get_log_header()} - Failed to publish log message to MQTT, return code: {result.rc}")
            except Exception as e:
                logger.error(f"{self.get_log_header()} - Failed to publish log message to MQTT: {e}")

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
        self.log_status(f"on_connection event triggered")

    def on_disconnection(self):
        """
        Event triggered when a disconnection occurs. It checks if both connections are still established and transitions to the appropriate state.
        If both connections are still established, it remains in the running state. If one or both connections are lost, it transitions to the idle state and continues to check for both connections.
        """
        self.log_status(f"on_disconnection event triggered")
        self.msg_dispatcher.stop()
    
    def on_finish(self):
        """
        Event triggered when the finish event is called. It transitions to the final state and performs any necessary cleanup operations.
        """
        self.log_status(f"on_finish event triggered")
    
    def on_enter_starting(self):
        """
        Method called when entering the start state. It initializes the connections and prepares the handler for operation.
        """
        self.log_status(f"Entering start state")
        
    def on_enter_idling(self):
        """
        Method called when entering the idle state. It starts the connections and waits for both connections to be established before transitioning to the running state.
        If both connections are not established, it remains in the idle state and continues to check for both connections.
        """
        self.log_status(f"Entering idle state")
        self.do_idle()
    
    def on_enter_running(self):
        """
        Method called when entering the running state. It starts the handler's main operation, which involves processing incoming data and logging it to InfluxDB.
        If either connection is lost while in the running state, it transitions back to the idle state and continues to check for both connections.
        """
        self.log_status(f"Entering running state")
        # Set the InfluxWriter and MQTT connection in the MsgDispatcher
        self.msg_dispatcher.set(
            influx_writer=InfluxWriter(
                client=self.handler.influx_adr, 
                adr_bucket=self.config.influx.buckets["adr"], 
                log_bucket=self.config.influx.buckets["logs"],
                excluded_networks=self.config.excluded_networks
            ),
            influx_reader=InfluxReader(
                client=self.handler.influx_adr,
                mqtt_client=self.handler.mqtt,
                log_bucket=self.config.influx.buckets["adr"]
            ),
            mqtt=self.handler.mqtt,
        )
        # Check if there are already messages on the MQTT broker and handle them before starting the main operation
        self.msg_dispatcher.handle_existing_messages()
        self.do_run()

    def on_enter_final(self):
        """
        Method called when entering the stop state. It performs any necessary cleanup operations, such as stopping the connections and releasing resources.
        """
        self.log_status(f"Entering stop state")
        self.do_stop()

    def do_start(self):
        """
        Method to start the FSM. It triggers the init event to transition from the start state to the idle state and begins the FSM operation.
        """
        if self.config.github_token and self.config.github_token != "":
            LibcanManager.TOKEN = self.config.github_token
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
        self.handler.start_connections()
        while not self.__event and not self.are_both_connected():
            with self.__connection_condition:
                self.__connection_condition.wait(timeout=1.0)
            self.log_status("trying connection")
            self.handler.start_connections()
        if self.are_both_connected():
            self.log_status("Both connections established, transitioning to running state")
            self.send('connection')

    def do_run(self):
        """
        Method to handle the running state. It performs the main operation of the handler, which involves processing incoming data and logging it to InfluxDB.
        If either connection is lost while in the running state, it triggers the disconnection event to transition back to the idle state and continues to check for both connections.
        """
        self.__event = False
        while not self.__event and self.are_both_connected():
            self.log_status("Running")
            with self.__connection_condition:
                self.__connection_condition.wait(timeout=60)
        if not self.are_both_connected():
            self.log_status("Connection lost, transitioning to idle state")
            self.send('disconnection')

    def do_stop(self):
        """
        Method to handle the stop state. It performs any necessary cleanup operations, such as stopping the connections and releasing resources.
        """
        self.msg_dispatcher.graceful_stop()
        self.handler.stop_connections()
        self.log_status("Connections stopped, handler in finale state")

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
        self.log_status("Thread started")
        while self and self.current_state != self.final:
            self.log_status(f"Current state: {self.current_state}")
            self.do_state()
        if self:
            self.do_stop()
        self.log_status("Thread finished")

    def on_message(self, topic: str, payload: bytes):
        '''
        Callback method to handle incoming MQTT messages. It is called by the MQTT connection when a message is received.
        Args:
            topic (str): The topic of the incoming MQTT message.
            payload (bytes): The payload of the incoming MQTT message.
        '''
        # Handle message only if the FSM is in the running state
        logger.debug(f"{self.get_log_header()} - Received message on topic: {topic}")
        if self.current_state == self.running:
            self.msg_dispatcher.handle_incoming_message(topic, payload)
