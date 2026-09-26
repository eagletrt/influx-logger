"""
A parser for processing incoming messages and converting them into InfluxDB points.
"""
from threading import Condition, Lock, Thread, Timer
from typing import Any

from influxdb_client import Point

from src.parser.protobuf_manager import LibcanManager, LibgpsManager, ProtobufManager
from src.utils.line import Line
from src.utils.logger_utils import logger
from src.utils.timestamp import TIMESTAMP_KEYS


class Parser(Thread):
    '''
    A parser for processing incoming messages and converting them into InfluxDB points.

    Attributes:
        excluded_networks (list[str]): A list of network identifiers to be excluded from parsing
        protobuf_manager (ProtobufManager): .proto descriptor handler
        device_versions (dict[str, dict[type, str]]): vehicle_id/device_id -> {lib_type: version}
        row_messages (list[tuple[list[str], bytes]]): list of unprocessed messages
        __row_message_lock (Lock): row_messages lock
        destination_list (list[Point]): List of parsed InfluxDB Point objects
        __destination_list_lock (Lock): destination_list lock
        stop (bool): A flag to indicate whether the parser should stop processing messages
        row_queue_not_empty (Condition): Condition to signal that the list is not empty
        __new_points_event_lock__ (Lock): Lock to new points event
        points_increased (Condition): Event to signal the addition of new points to the destination
        last_parse_timer (Timer): Timer to track the last time a message was parsed
    '''
    TIMER_TIMEOUT: int = 5
    '''Timeout in seconds indicating how long to wait before the system is considered inactive.'''

    def __init__(self, excluded_networks: list[str] = None) -> None:
        super().__init__(name="Parser")
        self.excluded_networks: list[
            str] = excluded_networks if excluded_networks is not None else []
        '''List of network identifiers to be excluded from parsing.'''
        self.protobuf_manager: ProtobufManager = ProtobufManager()
        '''ProtobufManager instance to handle .proto descriptor management and message decoding.'''
        self.device_versions: dict[str, dict[type, str]] = {}
        '''vehicle_id/device_id -> {lib_type: version} '''
        self.row_messages: list[tuple[list[str], bytes]] = []
        '''List of unprocessed messages'''
        self.__row_message_lock: Lock = Lock()
        '''Lock to synchronize access to the row_messages list'''
        self.destination_list: list[Point] = []
        '''List to store parsed InfluxDB Point objects'''
        self.__destination_list_lock: Lock = Lock()
        '''Lock to synchronize access to the destination_list'''
        self.stop: bool = False
        '''Flag to indicate whether the parser should stop processing messages.'''
        self.row_queue_not_empty: Condition = Condition(
            lock=self.__row_message_lock)
        '''Condition variable to signal when the row_messages list is not empty'''
        self.__new_points_event_lock__: Lock = Lock()
        '''Lock to synchronize access to the new points event'''
        self.points_increased: Condition = Condition(
            lock=self.__new_points_event_lock__)
        '''Event to signal when new points have been added to the destination_list'''
        self.last_parse_timer: Timer = Timer(Parser.TIMER_TIMEOUT,
                                             self._handle_inactivity)
        '''A timer to track the last time a message was parsed'''
        self.timer_expired: bool = False
        '''Flag to indicate whether the last_parse_timer has expired'''

    def _handle_inactivity(self) -> None:
        """
        Handles inactivity by logging a warning message when the
        parser has not processed any messages for a specified timeout period.
        This method is called when the last_parse_timer expires,
        indicating that no messages have been parsed within the defined timeout.
        """
        with self.__row_message_lock:
            if len(self.row_messages) <= 0:
                with self.__destination_list_lock:
                    self.timer_expired = True
                logger.warning(
                    "parser: No messages have been parsed for %d seconds.",
                    Parser.TIMER_TIMEOUT)
                with self.__new_points_event_lock__:
                    self.points_increased.notify_all(
                    )  # Notify any waiting threads that new points have been added
            else:
                logger.warning(
                    "parser: Messages are still being processed." \
                    "Resetting the inactivity timer for %d seconds.",
                    Parser.TIMER_TIMEOUT
                )
                with self.__destination_list_lock:
                    self.timer_expired = False
                self.timer_touch(
                )  # Reset the timer if there are still messages in the queue

    def add_to_queue(self, message: tuple[list[str], bytes]) -> None:
        '''
        Adds a new message to the row_messages queue in a thread-safe manner.
        Args:
            message (tuple[list[str], bytes]): The message to be added
        '''
        with self.__row_message_lock:
            self.row_messages.append(message)
            # Notify the parser thread that a new message has been added to the queue
            self.row_queue_not_empty.notify_all()

    def __parse_next_message(self) -> None:
        '''
        Parses the next message from the row_messages queue.
        This method waits for a message to be available in the queue,
        retrieves it,
        and then processes it by calling the parse_msg method.
        If the parser is stopped while waiting for a message,
        it will exit without processing.
        '''
        with self.row_queue_not_empty:
            while len(self.row_messages) == 0 and not self.stop:
                self.row_queue_not_empty.wait()
        if self.stop:
            return
        with self.__row_message_lock:
            message: tuple[list[str], bytes] = self.row_messages.pop(0)
            self.parse_msg(message)

    def parse_msg(self, msg: tuple[list[str], bytes]) -> None:
        """
        Parses a message and appends it to the destination list.
        Args:
            msg (Any): The message to be parsed.
        """
        # List of identifiers extracted from the message,
        # typically containing vehicle_id, device_id, and network.
        ids: list[str] = msg[0]
        # The payload of the message
        payload: bytes = msg[1]
        # Extracted identifiers from the message,
        # where vehicle_id is the unique identifier for the vehicle,
        # device_id is the unique identifier for the device, and network is the network identifier
        # indicating the source of the message.
        vehicle_id, device_id, network = ids
        # Key used to uniquely identify a device based on its vehicle_id and device_id,
        # formatted as "vehicle_id/device_id".
        key = f"{vehicle_id}/{device_id}"
        # Library type to be used for decoding the message,
        # determined based on the network identifier.
        library: type = LibcanManager if network != "gps" else LibgpsManager
        if key not in self.device_versions:
            logger.error(
                "parser: Device '%s' started streaming data before sending version. Skipping",
                key)
            return
        if network in self.excluded_networks:
            logger.debug(
                "parser: Network '%s' is in the exclusion list. Skipping message",
                network)
            return
        try:
            version = self.device_versions[key][library]
        except KeyError:
            logger.error(
                "parser:" \
                    "Device '%s' with library '%s' not found in device versions." \
                    "Skipping.",
                    key,
                    library.__name__
            )
            return
        # Check if the network is already registered for the given version, if not,
        # download the .proto descriptor
        if network not in self.protobuf_manager.version_descriptors.get(
                version, {}):
            # If the proto descriptor
            # is not already downloaded for the given version and network,
            # download it
            logger.info(
                "parser: Network '%s' with version %s never seen before." \
                    "Downloading .proto descriptor",
                network,
                version
            )
            try:
                if not self.protobuf_manager.download_proto_descriptor(
                        version, network):
                    return
            except Exception:
                logger.error(
                    "parser: Error while getting proto, skipping message")
                return
        # Deserialize the payload using the appropriate decoder for the given version and network
        try:
            # Use the appropriate decoder for the given version and network
            # to deserialize the payload
            decoder = self.protobuf_manager.version_descriptors[version][
                network]
            # Expect decoder to provide a `decode` method returning a dict-like object
            message_content = decoder.decode(payload)
        except Exception as e:
            logger.error(
                "parser: Cannot deserialize payload with saved descriptor: %s",
                str(e))
            logger.error("parser: version descriptors: %s",
                         self.protobuf_manager.version_descriptors)
            return
        tags = {
            "vehicle-id": vehicle_id,
            "device-id": device_id,
            "network": network,
        }
        # If the message content contains a "valuesPack" key and its value is a dictionary,
        # extract the inner dictionary for processing
        if "valuesPack" in message_content and isinstance(
                message_content["valuesPack"], dict):
            message_content = message_content["valuesPack"]
            logger.info(
                "parser: Unpacked valuesPack for network '%s' with version %s: %s",
                network, version, message_content)
        #logger.info(
        #    "parser: Committing message content for network '%s' with version %s: %s",
        #    network, version, message_content)
        self.commit_to_destination_list(message_content, tags)

    def timer_touch(self) -> None:
        """
        Resets the last_parse_timer to prevent it from expiring due to inactivity.
        This method should be called whenever a new message is parsed, 
        indicating that the parser is active.
        """
        if self.last_parse_timer is not None:
            self.last_parse_timer.cancel()  # Cancel the existing timer
        self.last_parse_timer = Timer(
            Parser.TIMER_TIMEOUT,
            self._handle_inactivity)  # Create a new timer instance
        self.last_parse_timer.start(
        )  # Start or restart the timer whenever a new message is parsed

    def reset_timer(self) -> None:
        """
        Resets the last_parse_timer to prevent it from expiring due to inactivity.
        This method should be called whenever a new message is parsed,
        indicating that the parser is active.
        """
        with self.__row_message_lock:
            # Reset the timer_expired flag to indicate that the parser is active
            self.timer_expired = False
            if self.last_parse_timer is not None:
                self.last_parse_timer.cancel()  # Cancel the existing timer

    def __append_to_destination_list(self, line: Line) -> None:
        """
        Appends a Line object to the destination list in a thread-safe manner.
        Args:
            line (Line): The Line object to be appended to the destination list.
        """
        with self.__destination_list_lock:
            #logger.info(f"parser: Appending line to destination list: {line}")
            self.destination_list.append(line)
            self.timer_touch()
        with self.__new_points_event_lock__:
            # Notify any waiting threads that new points
            # have been added to the destination list
            self.points_increased.notify_all()

    def commit_to_destination_list(self, message_content: dict[str, Any],
                                   tags: dict[str, str]) -> None:
        """
        Commits a record to the line repository by creating a Line object and 
        adding it to the destination list.
        Args:
            message_content (dict[str, Any]): Message content
            tags (dict[str, str]): Tags to commit with the record
        """
        additional_signals: dict[str, str] = {}
        if 'antenna_name' in message_content:
            additional_signals['antenna_name'] = message_content[
                'antenna_name']
        # Iterate through the measurements and their corresponding records in
        # the message content, pushing each record to the line repository
        for measurement, record_list in message_content.items():
            if isinstance(record_list, list):
                for record in record_list:
                    try:
                        if additional_signals and isinstance(record, dict):
                            record.update(additional_signals)
                    except Exception:
                        #logger.warning(
                        #    "parser: Failed to update record with additional" \
                        #        "signals for measurement" \
                        #        "'%s': %s",
                        #        measurement, record
                        #        )
                        pass
                    try:
                        #logger.info("parser: Measurement '%s': %s",
                        #            measurement, record
                        #            )
                        self.push(measurement, record, tags)
                    except ValueError as e:
                        logger.error(
                            "parser: Skipping invalid record for measurement '%s': %s",
                            measurement, str(e))
                continue
            try:
                #logger.info("parser: Non List Measurement '%s': %s",
                #            measurement, records
                #            )
                self.push(measurement, record_list, tags)
            except ValueError:
                #logger.error("parser: Skipping invalid record for measurement '%s': %s",
                #             measurement, e)
                pass

    def push(self, measurement: str, record: Any, tags: dict[str,
                                                             str]) -> None:
        '''
        Pushes a record to the line repository by creating a Line object and
        adding it to the destination list.
        Args:
            measurement (str): The name of the measurement associated with the record.
            record (Any): The record to be pushed, which can be a dictionary or any other type.
            tags (dict[str, str]): A dictionary of tags associated with the record.
        '''
        #logger.info(f"parser: Pushing record for measurement '{measurement}': {record}")
        # Check if the record is a dictionary; if not, log a warning and return early
        if isinstance(record, dict):
            #logger.info(f"parser: Received record for measurement '{measurement}': {record}")
            # Check if the record contains a "valuesMap" key, indicating a columnar format.
            if "valuesMap" in record:
                #logger.info(
                #    "parser: Received columnar record for measurement '%s': %s",
                #    measurement,
                #    record
                #)
                for timestamp_key in TIMESTAMP_KEYS:
                    if timestamp_key in record:
                        # Expand the columnar record into row-wise records
                        for row in Parser._expand_columnar_record(record):
                            # Push each row-wise record to the line repository
                            line: Line = Line.from_object(
                                row, measurement, tags)
                            #logger.info(f"parser: Line: {line}")
                            self.__append_to_destination_list(line)
                        return
            #logger.info(
            #    "parser: Received row-wise record for measurement '%s': %s",
            #    measurement,
            #    record
            #    )
            # Create a Line object from the record and add it to the destination list
            try:
                line: Line = Line.from_object(record, measurement, tags)
            except ValueError as e:
                if str(e) == "Missing fields":
                    logger.warning(
                        "parser: Skipping record for measurement '%s' due to missing fields: %s",
                        measurement, record)
                    return
                logger.error(
                    "parser: Error creating Line from record for measurement '%s': %s",
                    measurement, str(e))
            except Exception as e:
                logger.error(
                    "parser: Error creating Line from record for measurement '%s': %s",
                    measurement, str(e))
                return
            #logger.info(f"parser: Line: {line}")
            self.__append_to_destination_list(line)
        elif isinstance(record, str):
            #logger.warning(
            #    "Handler: Received a string record for measurement '%s': %s. Skipping.",
            #    measurement, record)
            return
        else:
            logger.warning(
                "Handler: Invalid record received from device for measurement '%s', type: %s.",
                measurement, type(record))
            return

    @staticmethod
    def _expand_columnar_record(
            record: dict[str, Any]) -> list[dict[str, Any]]:
        '''
        Expands a columnar record into a list of row-wise records.
        Args:
            record (dict[str, Any]): Columnar record containing "timestamp" and "valuesMap" keys.
        Returns:
            list[dict[str, Any]]: List with timestamps and corresponding field values
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
        # Iterate through the timestamps and corresponding field values,
        # creating a row-wise record for each timestamp
        for index, timestamp in enumerate(timestamps):
            row: dict[str, Any] = {"timestamp": timestamp}
            # Iterate through the field names and their corresponding values in the values_map,
            # unwrapping the values and adding them to the row if they exist for the current index
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
        Unwraps the "values" key from a dictionary if it exists,
        otherwise returns the original value.
        Args:
            values (Any): Value to be unwrapped, which can be a dictionary or any other type.
        Returns:
            Any: Unwrapped value
        '''
        if isinstance(values, dict):
            return values.get("values")
        return values

    def graceful_stop(self) -> None:
        """
        Method to gracefully stop the parser.
        It sets the stop flag to True,
        which will signal the run method to exit its loop and stop the thread.
        """
        cond: Condition = Condition(lock=self.__row_message_lock)
        while len(self.row_messages) > 0:
            cond.wait()
        self.stop_parser()

    def stop_parser(self) -> None:
        '''
        Method to stop the parser thread.
        It sets the stop flag to True and notifies the parser thread
        to wake up and check the stop condition. This allows the parser to
        exit its loop and stop processing messages.
        If you want to stop the parser gracefully, use the `graceful_stop` method instead,
        which will wait for the message queue to be empty before stopping.
        '''
        self.stop = True
        with self.row_queue_not_empty:
            self.row_queue_not_empty.notify_all(
            )  # Notify the parser thread to wake up and check the stop condition
        with self.__new_points_event_lock__:
            # Notify any waiting threads that the parser is stopping,
            # allowing them to exit their wait state
            self.points_increased.notify_all()

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

    def pop_points(self, max_points_to_pop: int = -1) -> list[Point]:
        '''
        Pops a specified number of points from the destination list and returns them.
        Args:
            max_points_to_pop (int): The maximum number of points to pop
        Returns:
            list[Point]: A list of popped InfluxDB Point objects
        '''
        with self.__destination_list_lock:
            if max_points_to_pop <= 0 or max_points_to_pop > len(
                    self.destination_list):
                # Get all points
                points: list[Point] = [
                    self.destination_list.pop(0)
                    for _ in range(len(self.destination_list))
                ]
            else:
                # Get the specified number of points
                points: list[Point] = [
                    self.destination_list.pop(0)
                    for _ in range(max_points_to_pop)
                ]
        return points


__all__ = ["Parser"]
