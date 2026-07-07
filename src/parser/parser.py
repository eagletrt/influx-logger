from typing import Any
from influxdb_client import Point
from threading import Condition, Event, Thread, Lock

from src.utils.line import Line
from src.utils.logger_utils import logger
from src.utils.timestamp import TIMESTAMP_KEYS
from src.parser.protobuf_manager import ProtobufManager

class Parser(Thread):
    def __init__(self, excluded_networks: list[str] = []) -> None:
        super().__init__(name="Parser", daemon=False)
        self.excluded_networks: list[str] = excluded_networks
        '''List of network identifiers to be excluded from parsing. Messages from these networks will be ignored.'''
        self.protobuf_manager: ProtobufManager = ProtobufManager()
        '''ProtobufManager instance to handle .proto descriptor management and message decoding.'''
        self.device_versions: dict = {}
        '''Dictionary to store device versions, where the key is a combination of vehicle_id and device_id, and the value is the version.'''
        self.row_messages: list[tuple[list[str], bytes]] = []
        '''List to store incoming messages, where each message is a tuple containing a list of identifiers and a bytes payload.'''
        self.__row_message_lock: Lock = Lock()
        '''Lock to synchronize access to the row_messages list, ensuring thread safety when adding or removing messages.'''
        self.destination_list: list[Point] = []
        '''List to store parsed InfluxDB Point objects, which are the result of parsing incoming messages.'''
        self.__destination_list_lock: Lock = Lock()
        '''Lock to synchronize access to the destination_list, ensuring thread safety when adding parsed points.'''
        self.stop: bool = False
        '''Flag to indicate whether the parser should stop processing messages.'''
        self.row_queue_not_empty: Condition = Condition(lock=self.__row_message_lock)
        '''Condition variable to signal when the row_messages list is not empty, allowing the parser to start processing messages.'''
        self.__new_points_event_lock__: Lock = Lock()
        '''Lock to synchronize access to the new points event, ensuring thread safety when signaling that new points have been added to the destination_list.'''
        self.points_increased: Condition = Condition(lock=self.__new_points_event_lock__)
        '''Event to signal when new points have been added to the destination_list, allowing other threads to wait for new points to be available.'''

    def add_to_queue(self, message: tuple[list[str], bytes]) -> None:
        with self.__row_message_lock:
            self.row_messages.append(message)
            self.row_queue_not_empty.notify_all()  # Notify the parser thread that a new message has been added to the queue
    
    def __parse_next_message(self) -> None:
        with self.row_queue_not_empty:
            while len(self.row_messages) == 0 and not self.stop:
                self.row_queue_not_empty.wait()
        if self.stop:
            return
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
            Point: The parsed InfluxDB Point object.
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
                        self.push_record(measurement, record, tags)
                    except ValueError as e:
                        #logger.error(f"msg_dispatcher: Skipping invalid record for measurement '{measurement}': {e}")
                        pass
                continue
            else:
                try:
                    self.push_record(measurement, records, tags)
                except ValueError as e:
                    #logger.error(f"msg_dispatcher: Skipping invalid record for measurement '{measurement}': {e}")
                    pass

    def __append_to_destination_list(self, line: Line) -> None:
        """
        Appends a Line object to the destination list in a thread-safe manner.
        Args:
            line (Line): The Line object to be appended to the destination list.
        """
        with self.__destination_list_lock:
            self.destination_list.append(line)
        with self.__new_points_event_lock__:
            self.points_increased.notify_all()  # Notify any waiting threads that new points have been added to the destination list
    
    def push_record(self, measurement: str, record: Any, tags: dict[str, str]) -> None:
        '''
        Pushes a record to the line repository by creating a Line object and adding it to the destination list.
        Args:
            measurement (str): The name of the measurement associated with the record.
            record (Any): The record to be pushed, which can be a dictionary or any other type. If it's a dictionary, it will be processed to create a Line object.
            tags (dict[str, str]): A dictionary of tags associated with the record, where the keys are tag names and the values are tag values.
        '''
        # Check if the record is a dictionary; if not, log a warning and return early
        if not isinstance(record, dict):
            logger.warning(f"Handler: Invalid object received from device for measurement '{measurement}'")
            return
        # Check if the record contains a "valuesMap" key, indicating a columnar format.
        if "valuesMap" in record:
            for timestamp_key in TIMESTAMP_KEYS:
                if timestamp_key in record:
                    # Expand the columnar record into row-wise records
                    for row in Parser._expand_columnar_record(record):
                        # Push each row-wise record to the line repository
                        line: Line = Line.from_object(row, measurement, tags)
                        self.__append_to_destination_list(line)
                    return
        # Create a Line object from the record and add it to the destination list
        line: Line = Line.from_object(record, measurement, tags)
        self.__append_to_destination_list(line)

    @staticmethod
    def _expand_columnar_record(record: dict[str, Any]) -> list[dict[str, Any]]:
        '''
        Expands a columnar record into a list of row-wise records.
        Args:
            record (dict[str, Any]): The columnar record containing "timestamp" and "valuesMap" keys.
        Returns:
            list[dict[str, Any]]: A list of row-wise records, where each record is a dictionary containing a "timestamp" and corresponding field values.
        '''
        timestamps = Parser._unwrap_values(record.get("timestamp"))
        values_map = record.get("valuesMap", {})
        # Validate that the timestamps and values_map are of the expected types
        if not isinstance(timestamps, list):
            raise ValueError("Missing or invalid timestamp")
        if not isinstance(values_map, dict):
            raise ValueError("Missing or invalid values map")
        # Expand the columnar record into a list of row-wise records
        rows: list[dict[str, Any]] = []
        # Iterate through the timestamps and corresponding field values, creating a row-wise record for each timestamp
        for index, timestamp in enumerate(timestamps):
            row: dict[str, Any] = {"timestamp": timestamp}
            # Iterate through the field names and their corresponding values in the values_map, unwrapping the values and adding them to the row if they exist for the current index
            for field_name, field_values in values_map.items():
                values = Parser._unwrap_values(field_values)
                if isinstance(values, list) and index < len(values):
                    row[field_name] = values[index]
            # Append the constructed row to the list of rows
            rows.append(row)
        return rows

    @staticmethod
    def _unwrap_values(values: Any) -> Any:
        '''
        Unwraps the "values" key from a dictionary if it exists, otherwise returns the original value.
        Args:
            values (Any): The value to be unwrapped, which can be a dictionary or any other type.
        Returns:
            Any: The unwrapped value if it was a dictionary with a "values" key, otherwise the original value.
        '''
        if isinstance(values, dict):
            return values.get("values")
        return values

    def graceful_stop(self) -> None:
        """
        Method to gracefully stop the parser. It sets the stop flag to True, which will signal the run method to exit its loop and stop the thread.
        """
        cond: Condition = Condition(lock=self.__row_message_lock)
        while len(self.row_messages) > 0:
            cond.wait()
        self.stop_parser()
    
    def stop_parser(self) -> None:
        '''
        Method to stop the parser thread. It sets the stop flag to True and notifies the parser thread to wake up and check the stop condition. This allows the parser to exit its loop and stop processing messages.
        If you want to stop the parser gracefully, use the `graceful_stop` method instead, which will wait for the message queue to be empty before stopping.
        '''
        self.stop = True
        with self.row_queue_not_empty:
            self.row_queue_not_empty.notify_all()  # Notify the parser thread to wake up and check the stop condition
        with self.__new_points_event_lock__:
            self.points_increased.notify_all()  # Notify any waiting threads that the parser is stopping, allowing them to exit their wait state

    def run(self) -> None:
        while not self.stop:
            self.__parse_next_message()

    def get_points_count(self) -> int:
        '''
        Returns the number of points currently stored in the destination list.
        Returns:
            int: The number of points in the destination list.
        '''
        with self.__destination_list_lock:
            return len(self.destination_list)

    def pop_points(self, max: int = -1) -> list[Point]:
        '''
        Pops a specified number of points from the destination list and returns them.
        Args:
            max (int): The maximum number of points to pop. If max is less than or equal to 0 or greater than the length of the destination list, all points will be popped.
        Returns:
            list[Point]: A list of popped InfluxDB Point objects.
        '''
        with self.__destination_list_lock:
            if max <= 0 or max > len(self.destination_list):
                points: list[Point] = self.destination_list.pop(0, len(self.destination_list))
            else:
                points: list[Point] = self.destination_list.pop(0, max)
        return points

__all__ = ["parser", "Parser"]
