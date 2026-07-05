from threading import Condition, Thread, Lock
from influxdb_client import Point
from typing import Any

class Parser(Thread):
    def __init__(self):
        self.row_messages: list = []
        self.__row_message_lock: Lock = Lock()
        self.destination_list: list[Point] = []
        self.__destination_list_lock: Lock = Lock()
        self.stop: bool = False

    def add_to_queue(self, message: str) -> None:
        with self.__row_message_lock:
            self.row_messages.append(message)
        #TODO: Trigger the parsing process if not already running
    
    def __parse_next_message(self) -> None:
        while len(self.row_messages) == 0:
            Condition.wait()
        with self.__row_message_lock:
            message = self.row_messages.pop(0)
            parsed_message = self.parse_msg(message)
        with self.__destination_list_lock:
            self.destination_list.append(parsed_message)
    
    def parse_msg(msg: Any) -> Point:
        """
        Parses a message and returns an InfluxDB Point object.
        Args:
            msg (Any): The message to be parsed.
        Returns:
            influxdb_client.Point: The parsed InfluxDB Point object.
        """
        # TODO: Implement the parsing logic here
        raise NotImplementedError("The parse_msg method is not implemented yet. Please implement the parsing logic.")
    
    def graceful_stop(self) -> None:
        """
        Method to gracefully stop the parser. It sets the stop flag to True, which will signal the run method to exit its loop and stop the thread.
        """
        cond: Condition = Condition(lock=self.__row_message_lock)
        while len(self.row_messages) > 0:
            cond.wait()
        self.stop = True
    
    def stop_parser(self) -> None:
        self.stop = True
    
    def run(self) -> None:
        while not self.stop:
            self.__parse_next_message()

parser: Parser = Parser()
