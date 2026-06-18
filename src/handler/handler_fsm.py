from concurrent.futures import thread

from statemachine import StateMachine, State
from threading import Thread

from src.utils.logger_utils import logger
from src.utils.configuration import Configuration
from src.parser.parser import Parser
from src.influx_logger import InfluxLogger

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
        idling.to(idling, unless=['are_both_connected'])
        | idling.to(running, cond=['are_both_connected'])
    )
    disconnection = (
        running.to(idling)
        | idling.to(idling)
    )
    finish = (
        running.to(final)
        | idling.to(final)
    )

    #TODO: https://github.com/fgmacedo/python-statemachine

    def __init__(self, config: Configuration):
        StateMachine.__init__(self)
        Thread.__init__(self)
        self.name = "HandlerFSM"
        self.parser: Parser = Parser()
        self.influx_logger: InfluxLogger = InfluxLogger(config)

    @staticmethod
    def draw(filename: str = 'handler_fsm.png'):
        HandlerFSM(Configuration("localhost",1883,"localhost", 8086, "", "", ""))._graph().write_png(filename)

    def are_both_connected(self) -> bool:
        #return self.influx_logger.connection_handler.are_both_connected()
        return False

    def on_connection(self):
        logger.info(f"HandlerFSM {self.name} {self.state_field} -  on_connection event triggered")
        raise NotImplementedError("Method not implemented yet")
    
    def on_disconnection(self):
        logger.info(f"HandlerFSM {self.name} {self.state_field} - on_disconnection event triggered")
        raise NotImplementedError("Method not implemented yet")
    
    def on_finish(self):
        logger.info(f"HandlerFSM {self.name} {self.state_field} - on_finish event triggered")
        raise NotImplementedError("Method not implemented yet")
    
    def on_enter_start(self):
        logger.info(f"HandlerFSM {self.name} {self.state_field} - Entering start state")
        #TODO: implement method
    
    def on_enter_idle(self):
        logger.info(f"HandlerFSM {self.name} {self.state_field} - Entering idle state")
        #TODO: implement method
    
    def on_enter_run(self):
        logger.info(f"HandlerFSM {self.name} {self.state_field} - Entering running state")
        #TODO: implement method

    def on_enter_stop(self):
        logger.info(f"HandlerFSM {self.name} {self.state_field} - Entering stop state")
        #TODO: implement method

    def run(self):
        logger.info(f"HandlerFSM {self.name} {self.state_field} - Thread started")
        raise NotImplementedError("Method not implemented yet")
