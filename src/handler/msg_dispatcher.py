from re import Pattern, compile
from influx import LineRepository
from typing import Callable, Any, Optional

from src.utils.logger_utils import logger
from src.connections.mqtt_connection import MQTTConnection
from src.parser.protobuf_manager import LibCANManager, ProtobufManager

class MsgDispatcher:
    def __init__(self, connection: MQTTConnection):
        self.topic_callbacks: dict[str, Callable] = {
            "+/+/version":  self.handle_version_message,
            "+/+/data/+":   self.handle_data_message,
        }
        self.protobuff_manager: ProtobufManager = ProtobufManager()
        self.mqtt: MQTTConnection = connection
        self.device_versions: dict = {}
        # TODO: Remove
        self.line_repository: Optional[LineRepository]

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
        vehicle_id, device_id = ids
        payload_str = payload.decode()
        logger.info(f"Handler: Checking existance of commit {payload_str}, requested by device '{vehicle_id}/{device_id}'")
        check = LibCANManager.check_commit_existence(payload_str)
        if check:
            logger.info(f"Handler: Subscribing to data topics for the new device ({vehicle_id}/{device_id})")
            if self.mqtt.connection:
                self.mqtt.connection.subscribe(f"{vehicle_id}/{device_id}/data/+")
                logger.info(f"Commit {payload_str} exists, device '{vehicle_id}/{device_id}' will be considered")
            self.device_versions[f"{vehicle_id}/{device_id}"] = payload_str
            self.protobuff_manager.version_descriptors[payload_str] = {}
            logger.info(f"Device '{vehicle_id}/{device_id}' is now subscribed to data topics")
        else:
            logger.error(f"Handler: Device '{vehicle_id}/{device_id}' uses a CAN commit that apparently doesn't exists. This device will not be considered")


    def handle_data_message(self, _topic: str, payload: bytes, ids: list[str]) -> None:
            vehicle_id, device_id, network = ids
            key = f"{vehicle_id}/{device_id}"
            if key not in self.device_versions:
                logger.error(f"Handler: Device '{key}' started streaming data before sending version. Skipping")
                return

            if network in self.excluded_networks:
                logger.debug(f"Handler: Network '{network}' is in the exclusion list. Skipping message")
                return

            version = self.device_versions[key]

            if network not in self.protobuff_manager.version_descriptors.get(version, {}):
                logger.info(f"Handler: Network '{network}' with version {version} never seen before. Downloading .proto descriptor")
                try:
                    ProtobufManager.get_proto_descriptor(version, network)
                except Exception:
                    logger.error(f"Handler: Error while getting proto, skipping message")
                    return

            try:
                decoder = self.protobuff_manager.version_descriptors[version][network]
                # Expect decoder to provide a `decode` method returning a dict-like object
                message_content = decoder.decode(payload)
            except Exception as e:
                logger.error(f"Handler: Cannot deserialize payload with saved descriptor: {e}")
                return

            tags = {
                "vehicle-id": vehicle_id,
                "device-id": device_id,
                "network": network,
            }

            if "valuesPack" in message_content and isinstance(message_content["valuesPack"], dict):
                message_content = message_content["valuesPack"]

            for measurement, records in message_content.items():
                if isinstance(records, list):
                    for record in records:
                        try:
                            self._push_record(measurement, record, tags)
                        except ValueError as e:
                            #logger.error(f"Handler: Skipping invalid record for measurement '{measurement}': {e}")
                            pass
                    continue
                else:
                    try:
                        self._push_record(measurement, records, tags)
                    except ValueError as e:
                        #logger.error(f"Handler: Skipping invalid record for measurement '{measurement}': {e}")
                        pass

    def _push_record(self, measurement: str, record: Any, tags: dict[str, str]) -> None:
        if isinstance(record, dict) and "valuesMap" in record and "timestamp" in record:
            for row in _expand_columnar_record(record):
                line = Line.from_object(row, measurement, tags)
                if self.line_repository:
                    self.line_repository.push(line)
            return

        if not isinstance(record, dict):
            logger.warning(f"Handler: Invalid object received from device for measurement '{measurement}'")
            return

        line = Line.from_object(record, measurement, tags)
        if self.line_repository:
            self.line_repository.push(line)


    def _expand_columnar_record(record: dict[str, Any]) -> list[dict[str, Any]]:
        timestamps = _unwrap_values(record.get("timestamp"))
        values_map = record.get("valuesMap", {})

        if not isinstance(timestamps, list):
            raise ValueError("Missing or invalid timestamp")
        if not isinstance(values_map, dict):
            raise ValueError("Missing or invalid values map")

        rows: List[Dict[str, Any]] = []
        for index, timestamp in enumerate(timestamps):
            row: Dict[str, Any] = {"timestamp": timestamp}

            for field_name, field_values in values_map.items():
                values = _unwrap_values(field_values)
                if isinstance(values, list) and index < len(values):
                    row[field_name] = values[index]

            rows.append(row)

        return rows

