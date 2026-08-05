from re import Pattern, compile
from typing import Callable

from src.utils.logger_utils import logger
from src.influx.influx_writer import InfluxWriter
from src.influx.influx_reader import InfluxReader
from src.parser.protobuf_manager import LibcanManager, LibgpsManager
from src.connections.mqtt_connection import MQTTConnection

class MsgDispatcher:
    def __init__(self, influx_writer: InfluxWriter = None, influx_reader: InfluxReader = None, mqtt: MQTTConnection = None) -> None:
        self.topic_callbacks: dict[str, Callable] = {
            "+/+/version":  self.handle_libcan_version_message,
            "+/+/data/+":   self.handle_data_message,
            "+/+/info/version/gpslib":   self.handle_libgps_version_message,
        }
        self.influx_writer: InfluxWriter = influx_writer
        self.influx_reader: InfluxReader = influx_reader
        self.mqtt: MQTTConnection = mqtt
        self.__run_if_set()

    def set(self, influx_writer: InfluxWriter=None, influx_reader: InfluxReader=None, mqtt: MQTTConnection=None) -> None:
        '''
        Sets the InfluxWriter instance for the MsgDispatcher.
        Args:
            influx_writer (InfluxWriter): The InfluxWriter instance to be used for writing data to InfluxDB.
        '''
        if influx_writer is not None:
            self.influx_writer = influx_writer
        if influx_reader is not None:
            self.influx_reader = influx_reader
        if mqtt is not None:
            self.mqtt = mqtt
        self.__run_if_set()

    def __run_if_set(self) -> None:
        '''
        Starts the InfluxWriter and InfluxReader threads if they are set.
        '''
        if self.influx_writer:
            try:
                self.influx_writer.start()
            except Exception as e:
                pass
        if self.influx_reader:
            try:
                self.influx_reader.start()
            except Exception as e:
                pass

    def handle_existing_messages(self) -> None:
        '''
        Handles any existing messages on the MQTT broker by subscribing to the relevant topics and processing the messages.
        '''
        if not self.mqtt:
            logger.warning("msg_dispatcher: MQTTConnection is not set. Cannot handle existing messages.")
            return
        logger.info("msg_dispatcher: Handling existing messages on the MQTT broker")
        # Subscribe to the relevant topics to receive existing messages
        for topic in self.topic_callbacks.keys():
            self.mqtt.connection.subscribe(topic)
            logger.info(f"msg_dispatcher: Subscribed to topic '{topic}' for existing messages")
        
    def handle_incoming_message(self, topic: str, payload: bytes) -> None:
        '''
        Handles incoming MQTT messages by dispatching them to the appropriate handler based on the topic.
        Args:
            topic (str): The topic of the incoming MQTT message.
            payload (bytes): The payload of the incoming MQTT message.
        '''
        logger.debug(f"MQTT Connection: Handling incoming message on topic: {topic}")
        # Iterate through the registered topic handlers and invoke the appropriate handler for the incoming message
        for handler_topic, handler_function in self.topic_callbacks.items():
            # Check if the incoming topic matches the handler topic pattern
            matches = list(self.build_topic_regex(handler_topic).finditer(topic))
            # If a match is found, extract the groups and call the handler function with the topic, payload, and extracted groups
            if matches:
                groups = list(matches[0].groups())
                handler_function(topic, payload, groups)

    @staticmethod
    def build_topic_regex(topic: str) -> Pattern:
        '''
        Converts an MQTT topic with wildcards into a regex pattern for matching incoming topics.
        Args:
            topic (str): The MQTT topic with wildcards.
        Returns:
            Pattern: A compiled regex pattern for matching incoming topics.
        '''
        pattern = topic.replace("/", "\\/").replace("+", "([^\\/]+)").replace("#", ".*")
        return compile(pattern)

    def handle_version_message(self, library, version: str, ids: list[str]) -> None:
        if not self.mqtt:
            logger.warning("msg_dispatcher: MQTTConnection is not set. Cannot handle version message.")
            return
        if not self.influx_writer:
            logger.warning("msg_dispatcher: InfluxWriter is not set. Cannot handle version message.")
            return
        vehicle_id, device_id = ids
        logger.info(f"msg_dispatcher: Checking existance of commit {version}, requested by device '{vehicle_id}/{device_id}'")
        check = library.check_commit_existence(version)
        if check:
            logger.info(f"msg_dispatcher: Subscribing to data topics for the new device ({vehicle_id}/{device_id})")
            if self.mqtt.connection:
                self.mqtt.connection.subscribe(f"{vehicle_id}/{device_id}/data/+")
                logger.info(f"Commit {version} exists, device '{vehicle_id}/{device_id}' will be considered")
            try:
                self.influx_writer.parser.device_versions[f"{vehicle_id}/{device_id}"] = version
                self.influx_writer.parser.protobuf_manager.version_descriptors[version] = {}
                logger.info(f"Device '{vehicle_id}/{device_id}' is now subscribed to data topics")
            except Exception as e:
                logger.error(f"msg_dispatcher: Error while subscribing device '{vehicle_id}/{device_id}' to data topics: {e}")
        else:
            logger.error(f"msg_dispatcher: Device '{vehicle_id}/{device_id}' uses a libcan commit that apparently doesn't exists. This device will not be considered")

    
    def handle_libcan_version_message(self, _topic: str, payload: bytes, ids: list[str]) -> None:
        '''
        Handles incoming version messages by checking the existence of the commit and subscribing to data topics if the commit exists.
        Args:
            _topic (str): The topic of the incoming version message.
            payload (bytes): The payload of the incoming version message.
            ids (list[str]): A list containing the vehicle ID and device ID extracted from the topic.
        '''
        self.handle_version_message(self, LibcanManager, payload.decode(), ids)

    def handle_libgps_version_message(self, _topic: str, payload: bytes, ids: list[str]) -> None:
        '''
        Handles incoming GPS library version messages by checking the existence of the commit and subscribing to data topics if the commit exists.
        Args:
            _topic (str): The topic of the incoming GPS library version message.
            payload (bytes): The payload of the incoming GPS library version message.
            ids (list[str]): A list containing the vehicle ID and device ID extracted from the topic.
        '''
        self.handle_version_message(self, LibgpsManager, payload.decode(), ids)

    def handle_data_message(self, _topic: str, payload: bytes, ids: list[str]) -> None:
        '''
        Handles incoming data messages by deserializing the payload and pushing the records to the line repository.
        Args:
            _topic (str): The topic of the incoming data message.
            payload (bytes): The payload of the incoming data message.
            ids (list[str]): A list containing the vehicle ID, device ID, and network extracted from the topic.
        '''
        if not self.influx_writer:
            logger.warning("msg_dispatcher: InfluxWriter is not set. Cannot handle data message.")
            return
        row_msg: tuple[list[str], bytes] = (ids, payload)
        self.influx_writer.parser.add_to_queue(row_msg)

    def stop(self) -> None:
        '''
        Stops the MsgDispatcher by stopping the InfluxWriter and InfluxReader if they are set.
        '''
        if self.influx_writer:
            self.influx_writer.stop()
            self.influx_writer.join()
            self.influx_writer = None  # Clear the reference to the InfluxWriter instance
        if self.influx_reader:
            self.influx_reader.stop()
            self.influx_reader.join()
            self.influx_reader = None  # Clear the reference to the InfluxReader instance

    def graceful_stop(self) -> None:
        '''
        Gracefully stops the MsgDispatcher by stopping the InfluxWriter and InfluxReader if they are set, and waiting for their threads to finish.
        '''
        if self.influx_writer:
            self.influx_writer.graceful_stop()
            self.influx_writer.join()
        if self.influx_reader:
            self.influx_reader.stop() # TODO: Implement graceful stop for InfluxReader if needed
            self.influx_reader.join()
        
__all__ = ["MsgDispatcher"]
