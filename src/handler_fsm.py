from statemachine import StateMachine, State
from threading import Thread

from src.logger_utils import logger
from utils.configuration import Configuration
from parser.parser import Parser
from src.influx_logger import InfluxLogger

class HandlerFSM(StateMachine, Thread):
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
    start: State = State('start', initial=True)
    idle: State = State('idle')
    run: State = State('run')
    stop: State = State('stop', final=True)

    # Events
    init = start.to(idle)
    connection = (
        idle.to(idle, unless=['are_both_connected'])
        | idle.to(run, cond=['are_both_connected'])
    )
    disconnection = (
        run.to(idle)
        | idle.to(idle)
    )
    finish = (
        run.to(stop)
        | idle.to(stop)
    )

    #TODO: https://github.com/fgmacedo/python-statemachine

    def __init__(self, config: Configuration):
        super().__init__()
        super(Thread, self).__init__()
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
        logger.info(f"HandlerFSM {self.name} {self.state_field} - Entering run state")
        #TODO: implement method

    def on_enter_stop(self):
        logger.info(f"HandlerFSM {self.name} {self.state_field} - Entering stop state")
        #TODO: implement method
