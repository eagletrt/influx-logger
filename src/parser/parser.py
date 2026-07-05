from threading import Condition, Thread, Lock
from influxdb_client import Point
from typing import Any

from src.parser.protobuf_manager import ProtobufManager
from src.utils.logger_utils import logger

class Parser(Thread):
    def __init__(self):
        self.protobuf_manager: ProtobufManager = ProtobufManager()
        self.device_versions: dict = {}
        self.row_messages: list[tuple[list[str], bytes]] = []
        self.__row_message_lock: Lock = Lock()
        self.destination_list: list[Point] = []
        self.__destination_list_lock: Lock = Lock()
        self.stop: bool = False

    def add_to_queue(self, message: tuple[list[str], bytes]) -> None:
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
    
    def parse_msg(self, msg: tuple[list[str], bytes]) -> Point:
        """
        Parses a message and returns an InfluxDB Point object.
        Args:
            msg (Any): The message to be parsed.
        Returns:
            influxdb_client.Point: The parsed InfluxDB Point object.
        """
        ids:list[str] = msg[0]
        payload:bytes = msg[1]
        vehicle_id, device_id, network = ids
        key = f"{vehicle_id}/{device_id}"
        if key not in self.device_versions:
            logger.error(f"msg_dispatcher: Device '{key}' started streaming data before sending version. Skipping")
            return
        if network in self.excluded_networks:
            logger.debug(f"msg_dispatcher: Network '{network}' is in the exclusion list. Skipping message")
            return
        version = self.device_versions[key]
        # Check if the network is already registered for the given version, if not, download the .proto descriptor
        if network not in self.protobuf_manager.version_descriptors.get(version, {}):
            logger.info(f"msg_dispatcher: Network '{network}' with version {version} never seen before. Downloading .proto descriptor")
            protobuf_manager = ProtobufManager()
            try:
                protobuf_manager.download_proto_descriptor(version, network)
            except Exception:
                logger.error(f"msg_dispatcher: Error while getting proto, skipping message")
                return
        # Deserialize the payload using the appropriate decoder for the given version and network
        try:
            # Use the appropriate decoder for the given version and network to deserialize the payload
            decoder = self.protobuf_manager.version_descriptors[version][network]
            # Expect decoder to provide a `decode` method returning a dict-like object
            message_content = decoder.decode(payload)
        except Exception as e:
            logger.error(f"msg_dispatcher: Cannot deserialize payload with saved descriptor: {e}")
            return
        tags = {
            "vehicle-id": vehicle_id,
            "device-id": device_id,
            "network": network,
        }
        # If the message content contains a "valuesPack" key and its value is a dictionary, extract the inner dictionary for processing
        if "valuesPack" in message_content and isinstance(message_content["valuesPack"], dict):
            message_content = message_content["valuesPack"]
        # Iterate through the measurements and their corresponding records in the message content, pushing each record to the line repository
        for measurement, records in message_content.items():
            if isinstance(records, list):
                for record in records:
                    try:
                        self._push_record(measurement, record, tags)
                    except ValueError as e:
                        #logger.error(f"msg_dispatcher: Skipping invalid record for measurement '{measurement}': {e}")
                        pass
                continue
            else:
                try:
                    self._push_record(measurement, records, tags)
                except ValueError as e:
                    #logger.error(f"msg_dispatcher: Skipping invalid record for measurement '{measurement}': {e}")
                    pass


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

__all__ = ["parser", "Parser"]
