"""
This module implements a message dispatcher that handles
incoming MQTT messages and dispatches them to the appropriate
handlers based on the topic.
"""

import json
from collections.abc import Callable
from re import Pattern
from re import compile as re_compile

from src.connections.mqtt_connection import MQTTConnection
from src.influx.influx_writer import InfluxWriter
from src.parser.libmanager import LibSerializersManager
from src.parser.protobuf_manager import LibcanManager, LibgpsManager
from src.utils.logger_utils import logger


class MsgDispatcher:
    """
    A class that dispatches incoming MQTT messages to the appropriate handlers
    based on the topic. It supports handling version messages, data messages,
    and query requests. It also manages the InfluxWriter instance
    for writing data to InfluxDB.

    Attributes:
        topic_callbacks: A dictionary mapping MQTT topics to their corresponding callback.
        influx_writer: An instance of the InfluxWriter class for writing data to InfluxDB.
        mqtt: An instance of the MQTTConnection class for handling MQTT connections.
        vehicle_whitelist: A list of allowed vehicle IDs.
    """

    def __init__(self,
                 influx_writer: InfluxWriter = None,
                 mqtt: MQTTConnection = None,
                 vehicle_whitelist: list = None) -> None:
        self.topic_callbacks: dict[str, Callable] = {
            "+/+/info/version/serializers":
            self.handle_serializers_version_message,
            #"+/+/version":              self.handle_canlib_version_message,
            "+/+/info/version/libcan": self.handle_libcan_version_message,
            "+/+/info/version/gpslib": self.handle_libgps_version_message,
            "+/+/data/+": self.handle_data_message,
            "+/+/status/info": self.handle_tlm_status_message,
        }
        self.influx_writer: InfluxWriter = influx_writer
        self.mqtt: MQTTConnection = mqtt
        self.vehicle_whitelist: list = None
        if vehicle_whitelist and vehicle_whitelist != []:
            self.vehicle_whitelist: list = vehicle_whitelist
        self.__run_if_set()

    def set(self,
            influx_writer: InfluxWriter = None,
            mqtt: MQTTConnection = None,
            vehicle_whitelist: list = None) -> None:
        '''
        Sets the InfluxWriter instance for the MsgDispatcher.
        Args:
            influx_writer (InfluxWriter): Instance to be used for writing data to InfluxDB.
        '''
        if influx_writer is not None:
            self.influx_writer = influx_writer
        if mqtt is not None:
            self.mqtt = mqtt
        if vehicle_whitelist is not None and vehicle_whitelist != []:
            self.vehicle_whitelist = vehicle_whitelist
        self.__run_if_set()

    def __run_if_set(self) -> None:
        '''
        Starts the InfluxWriter threads if they are set.
        '''
        if self.influx_writer:
            try:
                self.influx_writer.start()
            except Exception:  # pylint: disable=broad-except
                pass

    def handle_existing_messages(self) -> None:
        '''
        Handles any existing messages on the MQTT broker by
        subscribing to the relevant topics and processing the messages.
        '''
        if not self.mqtt:
            logger.warning(
                "msg_dispatcher: MQTTConnection is not set. Cannot handle existing messages."
            )
            return
        logger.info(
            "msg_dispatcher: Handling existing messages on the MQTT broker")
        if not self.mqtt.connection:
            logger.warning(
                "msg_dispatcher: MQTTConnection is not connected. Cannot handle existing messages."
            )
            return
        # Subscribe to the relevant topics to receive existing messages
        for topic in self.topic_callbacks:
            try:
                self.mqtt.connection.subscribe(topic)
                logger.info(
                    "msg_dispatcher: Subscribed to topic '%s' for existing messages",
                    topic)
            except Exception as e:  # pylint: disable=broad-except
                logger.error(
                    "msg_dispatcher: Failed to subscribe to topic '%s': %s",
                    topic, str(e))

    @staticmethod
    def payload_to_json(payload: bytes) -> json:
        """
        Converts a payload in bytes to a JSON dictionary.
        Args:
            payload (bytes): The payload to be converted.
        Returns:
            json: The converted JSON dictionary.
        """
        try:
            return json.loads(payload.decode())
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Error while converting payload to JSON: %s", str(e))
            return {}

    def handle_incoming_message(self, topic: str, payload: bytes) -> None:
        '''
        Handles incoming MQTT messages by dispatching them to the
        appropriate handler based on the topic.
        Args:
            topic (str): The topic of the incoming MQTT message.
            payload (bytes): The payload of the incoming MQTT message.
        '''
        logger.debug("MQTT Connection: Handling incoming message on topic: %s",
                     topic)
        # Iterate through the registered topic handlers and invoke
        # the appropriate handler for the incoming message
        for handler_topic, handler_function in self.topic_callbacks.items():
            # Check if the incoming topic matches the handler topic pattern
            match = self.build_topic_regex(handler_topic).fullmatch(topic)
            # If a match is found, extract the groups and call
            # the handler function with the topic, payload,
            # and extracted groups
            if match:
                groups = list(match.groups())
                handler_function(topic, payload, groups)
            else:
                logger.debug(
                    "MQTT Connection: No match for topic '%s' with handler topic '%s'",
                    topic, handler_topic)

    @staticmethod
    def build_topic_regex(topic: str) -> Pattern:
        '''
        Converts an MQTT topic with wildcards into a regex pattern for matching incoming topics.
        Args:
            topic (str): The MQTT topic with wildcards.
        Returns:
            Pattern: A compiled regex pattern for matching incoming topics.
        '''
        pattern = topic.replace("/",
                                "\\/").replace("+",
                                               "([^\\/]+)").replace("#", ".*")
        return re_compile(pattern)

    def handle_version_message(self, library: type[LibcanManager]
                               | type[LibgpsManager]
                               | type[LibSerializersManager], version: str,
                               ids: list[str]) -> None:
        """
        Handles incoming version messages by checking the existence of
        the commit and subscribing to data topics if the commit exists.
        Args:
            library (type): The library manager class (LibcanManager or LibgpsManager).
            version (str): The version string received in the message.
            ids (list[str]): A list containing the vehicle ID and device ID.
        """
        if not self.mqtt:
            logger.warning(
                "msg_dispatcher: MQTTConnection is not set. Cannot handle version message."
            )
            return
        if not self.influx_writer:
            logger.warning(
                "msg_dispatcher: InfluxWriter is not set. Cannot handle version message."
            )
            return
        sanitized_version: str = None
        # Regex pattern to sanitize the version string by extracting
        # the commit hash from the version string.
        version_sanitize_regex = re_compile(r"^(\w+)", )
        try:
            match = version_sanitize_regex.search(version)
            if match:
                sanitized_version = match.group(1)
        except Exception:  # pylint: disable=broad-except
            pass
        if sanitized_version:
            version = sanitized_version
        logger.info("msg_dispatcher: Received version message from %s",
                    str(ids))
        vehicle_id: str = ids[0] if len(ids) > 0 else "unknown_vehicle"
        device_id: str = ids[1] if len(ids) > 1 else "unknown_id"
        if self.vehicle_whitelist and vehicle_id not in self.vehicle_whitelist:
            #logger.debug(
            #    "msg_dispatcher: Vehicle '%s/%s' is not in the whitelist.",
            #    vehicle_id, device_id)
            return
        logger.info(
            "msg_dispatcher: Checking existance of commit %s, requested by device '%s/%s'",
            version, vehicle_id, device_id)
        check = library.check_commit_existence(version)
        if check:
            logger.info(
                "msg_dispatcher: Subscribing to data topics for the new device (%s/%s)",
                vehicle_id, device_id)
            if self.mqtt.connection:
                self.mqtt.connection.subscribe(
                    f"{vehicle_id}/{device_id}/data/+")
                logger.info(
                    "msg_dispatcher: Commit %s exists, device '%s/%s' will be considered",
                    version, vehicle_id, device_id)
            try:
                self.influx_writer.parser.register_device_version(
                    vehicle_id, device_id, library, version)
                logger.info(
                    "msg_dispatcher: Device '%s/%s' is now subscribed to data topics, " \
                    "version_descriptors: %s",
                    vehicle_id, device_id, self.influx_writer.parser.
                    protobuf_manager.version_descriptors)
            except Exception as e:  # pylint: disable=broad-except
                logger.error(
                    "msg_dispatcher: Error while subscribing device '%s/%s' to data topics: %s",
                    vehicle_id, device_id, e)
        else:
            logger.error(
                "msg_dispatcher: Device '%s/%s' uses a libcan commit that " \
                "apparently doesn't exists. " \
                "This device will not be considered",
                vehicle_id,
                device_id
            )

    def handle_serializers_version_message(self, _topic: str, payload: bytes,
                                           ids: list[str]) -> None:
        '''
        Handles incoming Serializers version messages by checking the existence of
        the commit and subscribing to data topics if the commit exists.
        Args:
            _topic (str): The topic of the incoming Serializers version message.
            payload (bytes): The payload of the incoming Serializers version message.
            ids (list[str]): A list containing the vehicle ID and device ID.
        '''
        self.handle_version_message(LibSerializersManager, payload.decode(),
                                    ids)

    def handle_libcan_version_message(self, _topic: str, payload: bytes,
                                      ids: list[str]) -> None:
        '''
        Handles incoming libcan version messages by checking the existence of
        the commit and subscribing to data topics if the commit exists.
        Args:
            _topic (str): The topic of the incoming libcan version message.
            payload (bytes): The payload of the incoming libcan version message.
            ids (list[str]): A list containing the vehicle ID and device ID.
        '''
        self.handle_version_message(LibcanManager, payload.decode(), ids)

    def handle_canlib_version_message(self, _topic: str, payload: bytes,
                                      ids: list[str]) -> None:
        '''
        Handles incoming CAN library version messages by checking
        the existence of the commit and subscribing to data topics
        if the commit exists.
        Args:
            _topic (str): The topic of the incoming CAN library version message.
            payload (bytes): The payload of the incoming CAN library version message.
            ids (list[str]): A list containing the vehicle ID and device ID.
        '''
        # We could think about moving this to a dedicated class
        self.handle_version_message(LibcanManager, payload.decode(), ids)

    def handle_libgps_version_message(self, _topic: str, payload: bytes,
                                      ids: list[str]) -> None:
        '''
        Handles incoming GPS library version messages by checking the existence
        of the commit and subscribing to data topics if the commit exists.
        Args:
            _topic (str): The topic of the incoming GPS library version message.
            payload (bytes): The payload of the incoming GPS library version message.
            ids (list[str]): A list containing the vehicle ID and device ID.
        '''
        self.handle_version_message(LibgpsManager, payload.decode(), ids)

    def handle_data_message(self, _topic: str, payload: bytes,
                            ids: list[str]) -> None:
        '''
        Handles incoming data messages by deserializing the payload and
        pushing the records to the line repository.
        Args:
            _topic (str): The topic of the incoming data message.
            payload (bytes): The payload of the incoming data message.
            ids (list[str]): A list containing the vehicle ID, device ID, and network.
        '''
        if not self.influx_writer:
            logger.warning(
                "msg_dispatcher: InfluxWriter is not set. Cannot handle data message."
            )
            return
        row_msg: tuple[list[str], bytes] = (ids, payload)
        vehicle_id: str = ids[0] if len(ids) > 0 else "unknown_vehicle"
        if self.vehicle_whitelist and vehicle_id not in self.vehicle_whitelist:
            #logger.debug(
            #    "msg_dispatcher: Vehicle '%s' is not in the whitelist.",
            #    vehicle_id)
            return
        self.influx_writer.parser.add_to_queue(row_msg)

    def handle_tlm_status_message(
            self, _topic: str, payload: bytes, ids: list[str]) -> None:  #pylint: disable=unused-argument
        """
        Handles incoming telemetry status messages by deserializing the payload
        and updating the Telemetry FSM accordingly.
        Args:
            _topic (str): The topic of the incoming telemetry status message.
            payload (bytes): The payload of the incoming telemetry status message.
            ids (list[str]): A list containing the vehicle ID, device ID, and network.
        """
        raise NotImplementedError(
            "Telemetry status message handling is not implemented yet.")

    def stop(self) -> None:
        '''
        Stops the MsgDispatcher by stopping the InfluxWriter 
        if it's set.
        '''
        if self.influx_writer:
            self.influx_writer.stop()
            self.influx_writer.join()
            self.influx_writer = None  # Clear the reference to the InfluxWriter instance

    def graceful_stop(self) -> None:
        '''
        Gracefully stops the MsgDispatcher by stopping the
        InfluxWriter and waiting
        for its thread to finish.
        '''
        if self.influx_writer:
            self.influx_writer.graceful_stop()
            self.influx_writer.join()


__all__ = ["MsgDispatcher"]
