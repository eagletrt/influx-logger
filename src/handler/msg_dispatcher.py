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
        #vehicle_id, device_id, network = ids
        #key = f"{vehicle_id}/{device_id}"
        #if key not in self.device_versions:
        #    logger.error(f"msg_dispatcher: Device '{key}' started streaming data before sending version. Skipping")
        #    return
        #if network in self.excluded_networks:
        #    logger.debug(f"msg_dispatcher: Network '{network}' is in the exclusion list. Skipping message")
        #    return
        #version = self.device_versions[key]
        ## Check if the network is already registered for the given version, if not, download the .proto descriptor
        #if network not in self.protobuff_manager.version_descriptors.get(version, {}):
        #    logger.info(f"msg_dispatcher: Network '{network}' with version {version} never seen before. Downloading .proto descriptor")
        #    protobuf_manager = ProtobufManager()
        #    try:
        #        protobuf_manager.download_proto_descriptor(version, network)
        #    except Exception:
        #        logger.error(f"msg_dispatcher: Error while getting proto, skipping message")
        #        return
        ## Deserialize the payload using the appropriate decoder for the given version and network
        #try:
        #    # Use the appropriate decoder for the given version and network to deserialize the payload
        #    decoder = self.protobuff_manager.version_descriptors[version][network]
        #    # Expect decoder to provide a `decode` method returning a dict-like object
        #    message_content = decoder.decode(payload)
        #except Exception as e:
        #    logger.error(f"msg_dispatcher: Cannot deserialize payload with saved descriptor: {e}")
        #    return
        #tags = {
        #    "vehicle-id": vehicle_id,
        #    "device-id": device_id,
        #    "network": network,
        #}
        ## If the message content contains a "valuesPack" key and its value is a dictionary, extract the inner dictionary for processing
        #if "valuesPack" in message_content and isinstance(message_content["valuesPack"], dict):
        #    message_content = message_content["valuesPack"]
        ## Iterate through the measurements and their corresponding records in the message content, pushing each record to the line repository
        #for measurement, records in message_content.items():
        #    if isinstance(records, list):
        #        for record in records:
        #            try:
        #                self._push_record(measurement, record, tags)
        #            except ValueError as e:
        #                #logger.error(f"msg_dispatcher: Skipping invalid record for measurement '{measurement}': {e}")
        #                pass
        #        continue
        #    else:
        #        try:
        #            self._push_record(measurement, records, tags)
        #        except ValueError as e:
        #            #logger.error(f"msg_dispatcher: Skipping invalid record for measurement '{measurement}': {e}")
        #            pass

    #def _push_record(self, measurement: str, record: Any, tags: dict[str, str]) -> None:
    #    # If the record is a dictionary containing "valuesMap" and "timestamp", expand it into multiple rows and push each row to the line repository
    #    if isinstance(record, dict) and "valuesMap" in record and "timestamp" in record:
    #        for row in MsgDispatcher._expand_columnar_record(record):
    #            line = Line.from_object(row, measurement, tags)
    #            if self.line_repository:
    #                self.line_repository.push(line)
    #        return
    #    # If the record is not a dictionary, log a warning and return without pushing it to the line repository
    #    if not isinstance(record, dict):
    #        logger.warning(f"msg_dispatcher: Invalid object received from device for measurement '{measurement}'")
    #        return
    #    # Create a Line object from the record and push it to the line repository if it exists
    #    line = Line.from_object(record, measurement, tags)
    #    if self.line_repository:
    #        self.line_repository.push(line)
#
#
    #def _expand_columnar_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    #    '''
    #    Expands a columnar record into a list of row-wise records.
    #    Args:
    #        record (dict[str, Any]): The columnar record containing "timestamp" and "valuesMap" keys.
    #    Returns:
    #        list[dict[str, Any]]: A list of row-wise records, where each record is a dictionary containing a "timestamp" and corresponding field values.
    #    '''
    #    timestamps = MsgDispatcher._unwrap_values(record.get("timestamp"))
    #    values_map = record.get("valuesMap", {})
    #    # Validate that the timestamps and values_map are of the expected types
    #    if not isinstance(timestamps, list):
    #        raise ValueError("Missing or invalid timestamp")
    #    if not isinstance(values_map, dict):
    #        raise ValueError("Missing or invalid values map")
    #    # Expand the columnar record into a list of row-wise records
    #    rows: list[dict[str, Any]] = []
    #    # Iterate through the timestamps and corresponding field values, creating a row-wise record for each timestamp
    #    for index, timestamp in enumerate(timestamps):
    #        row: dict[str, Any] = {"timestamp": timestamp}
    #        # Iterate through the field names and their corresponding values in the values_map, unwrapping the values and adding them to the row if they exist for the current index
    #        for field_name, field_values in values_map.items():
    #            values = MsgDispatcher._unwrap_values(field_values)
    #            if isinstance(values, list) and index < len(values):
    #                row[field_name] = values[index]
    #        # Append the constructed row to the list of rows
    #        rows.append(row)
    #    return rows
#
    #def _unwrap_values(values: Any) -> Any:
    #    '''
    #    Unwraps the "values" key from a dictionary if it exists, otherwise returns the original value.
    #    Args:
    #        values (Any): The value to be unwrapped, which can be a dictionary or any other type.
    #    Returns:
    #        Any: The unwrapped value if it was a dictionary with a "values" key, otherwise the original value.
    #    '''
    #    if isinstance(values, dict):
    #        return values.get("values")
    #    return values
