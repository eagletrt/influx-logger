from statemachine import StateMachine, State
from threading import Thread

from configuration import Configuration
from parser import Parser
from influx_logger import InfluxLogger

class HandlerFSM(StateMachine, Thread):
    start: State = State('start', initial=True)
    idle: State = State('idle')
    run: State = State('run')
    stop: State = State('stop', final=True)

    fsm = (
        start.to(idle)
        | idle.to(run)
        | run.to(idle)
        | run.to(stop)
    )

    #TODO: https://github.com/fgmacedo/python-statemachine

    def __init__(self, config: Configuration):
        super().__init__(name='HandlerFSM')
        self.parser: Parser = Parser()
        self.influx_logger: InfluxLogger = InfluxLogger(config)

    def __on_connection(self):
        raise NotImplementedError("Method not implemented yet")
    
    def __on_disconnection(self):
        raise NotImplementedError("Method not implemented yet")
    
    def __on_both_connected(self):
        raise NotImplementedError("Method not implemented yet")

    def on_stop(self):
        raise NotImplementedError("Method not implemented yet")
    
    def __do_start(self):
        raise NotImplementedError("Method not implemented yet")
    
    def __do_idle(self):
        raise NotImplementedError("Method not implemented yet")
    
    def do_run(self):
        raise NotImplementedError("Method not implemented yet")
    
    def do_stop(self):
        raise NotImplementedError("Method not implemented yet")    
