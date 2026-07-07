from re import Pattern, compile
from typing import Callable, Any

from src.utils.logger_utils import logger
from src.parser.parser import parser
from src.parser.protobuf_manager import LibCANManager

class MsgDispatcher:
    def __init__(self):
        self.topic_callbacks: dict[str, Callable] = {
            "+/+/version":  self.handle_version_message,
            "+/+/data/+":   self.handle_data_message,
        }
        #self.protobuff_manager: ProtobufManager = ProtobufManager()
        #self.mqtt: MQTTConnection = connection

    def handle_incoming_message(self, topic: str, payload: bytes) -> None:
        '''
        Handles incoming MQTT messages by dispatching them to the appropriate handler based on the topic.
        Args:
            topic (str): The topic of the incoming MQTT message.
            payload (bytes): The payload of the incoming MQTT message.
        '''
        #logger.debug(f"MQTT Connection: Handling incoming message on topic: {topic}")
        # Iterate through the registered topic handlers and invoke the appropriate handler for the incoming message
        for handler_topic, handler_function in self.topic_callbacks.items():
            # Check if the incoming topic matches the handler topic pattern
            matches = list(self.build_topic_regex(handler_topic).finditer(topic))
            # If a match is found, extract the groups and call the handler function with the topic, payload, and extracted groups
            if matches:
                groups = list(matches[0].groups())
                handler_function(topic, payload, groups)

    def build_topic_regex(self, topic: str) -> Pattern:
        '''
        Converts an MQTT topic with wildcards into a regex pattern for matching incoming topics.
        Args:
            topic (str): The MQTT topic with wildcards.
        Returns:
            Pattern: A compiled regex pattern for matching incoming topics.
        '''
        pattern = topic.replace("/", "\\/").replace("+", "([^\\/]+)").replace("#", ".*")
        return compile(pattern)
    
    def handle_version_message(self, _topic: str, payload: bytes, ids: list[str]) -> None:
        '''
        Handles incoming version messages by checking the existence of the commit and subscribing to data topics if the commit exists.
        Args:
            _topic (str): The topic of the incoming version message.
            payload (bytes): The payload of the incoming version message.
            ids (list[str]): A list containing the vehicle ID and device ID extracted from the topic.
        '''
        vehicle_id, device_id = ids
        payload_str = payload.decode()
        logger.info(f"msg_dispatcher: Checking existance of commit {payload_str}, requested by device '{vehicle_id}/{device_id}'")
        check = LibCANManager.check_commit_existence(payload_str)
        if check:
            logger.info(f"msg_dispatcher: Subscribing to data topics for the new device ({vehicle_id}/{device_id})")
            if self.mqtt.connection:
                self.mqtt.connection.subscribe(f"{vehicle_id}/{device_id}/data/+")
                logger.info(f"Commit {payload_str} exists, device '{vehicle_id}/{device_id}' will be considered")
            try:
                self.parser.device_versions[f"{vehicle_id}/{device_id}"] = payload_str
                parser.protobuf_manager.version_descriptors[payload_str] = {}
                logger.info(f"Device '{vehicle_id}/{device_id}' is now subscribed to data topics")
            except Exception as e:
                logger.error(f"msg_dispatcher: Error while subscribing device '{vehicle_id}/{device_id}' to data topics: {e}")
        else:
            logger.error(f"msg_dispatcher: Device '{vehicle_id}/{device_id}' uses a CAN commit that apparently doesn't exists. This device will not be considered")

    def handle_data_message(self, _topic: str, payload: bytes, ids: list[str]) -> None:
        '''
        Handles incoming data messages by deserializing the payload and pushing the records to the line repository.
        Args:
            _topic (str): The topic of the incoming data message.
            payload (bytes): The payload of the incoming data message.
            ids (list[str]): A list containing the vehicle ID, device ID, and network extracted from the topic.
        '''
        row_msg: tuple[list[str], bytes] = (ids, payload)
        parser.add_to_queue(row_msg)
        
__all__ = ["MsgDispatcher"]
