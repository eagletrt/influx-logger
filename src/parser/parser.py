"""
A parser for processing incoming messages and converting them into InfluxDB points.
"""
from queue import Empty, Queue
from threading import Condition, Lock, RLock, Thread, Timer
from typing import Any

from influxdb_client import Point

from src.parser.libmanager import LibcanManager, LibgpsManager
from src.parser.parserfsm import ParserFSM
from src.parser.protobuf_manager import ProtobufManager
from src.utils.line import Line
from src.utils.logger_utils import logger
from src.utils.timestamp import TIMESTAMP_KEYS


class Parser(Thread):  # pylint: disable=too-many-instance-attributes
    '''
    A parser for processing incoming messages and converting them into InfluxDB points.

    Attributes:
        excluded_networks (list[str]): A list of network identifiers to be excluded from parsing
        protobuf_manager (ProtobufManager): .proto descriptor handler
        device_versions (dict[str, dict[type, str]]): vehicle_id/device_id -> {lib_type: version}
        row_messages (Queue[tuple[list[str], bytes]]): queue of unprocessed messages
        destination_list (Queue[Point]): Queue of parsed InfluxDB Point objects
        stop (bool): A flag to indicate whether the parser should stop processing messages
        row_queue_not_empty (Condition): Condition to signal that the queue is not empty
        __new_points_event_lock__ (Lock): Lock to new points event
        points_increased (Condition): Event to signal the addition of new points to the destination
        last_parse_timer (Timer): Timer to track the last time a message was parsed
    '''
    TIMER_TIMEOUT: int = 5
    '''Timeout in seconds indicating how long to wait before the system is considered inactive.'''

    def __init__(self,
                 excluded_networks: list[str] = None,
                 log_callback: callable = None) -> None:
        '''
        Initialize the parser.
        Args:
            excluded_networks (list[str], optional): A list of network identifiers to be excluded.
            log_callback (callable, optional): A callback function for logging messages.
        '''
        self.parserfsm: ParserFSM = ParserFSM()
        '''Finite State Machine for the parser.'''
        if log_callback:
            self.parserfsm.set_log_callback(log_callback)
        super().__init__(name="Parser")
        self.excluded_networks: list[
            str] = excluded_networks if excluded_networks is not None else []
        '''List of network identifiers to be excluded from parsing.'''
        self.protobuf_manager: ProtobufManager = ProtobufManager()
        '''ProtobufManager instance to handle .proto descriptor management and message decoding.'''
        self.device_versions: dict[str, dict[type, str]] = {}
        '''vehicle_id/device_id -> {lib_type: version} '''
        self.row_messages: Queue[tuple[list[str], bytes]] = Queue()
        '''Queue of unprocessed messages'''
        self.destination_list: Queue[Point] = Queue()
        '''Queue to store parsed InfluxDB Point objects'''
        self.stop: bool = False
        '''Flag to indicate whether the parser should stop processing messages.'''
        self.__row_message_lock = Lock()
        '''Lock to synchronize access to the row_messages queue'''
        self.row_queue_not_empty: Condition = Condition(
            lock=self.__row_message_lock)
        '''Condition variable to signal when the row_messages queue is not empty'''
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
        self.__timer_lock = Lock()
        '''Lock to synchronize access to the last_parse_timer and timer_expired flag'''
        self.__parser_state_lock = RLock()
        '''
        Lock to synchronize access to the parser state,
        including device_versions and protobuf_manager
        '''
        self.network_blacklisting: dict[tuple[str, str], int] = {}
        '''
        Counter to track the number of times a network has
        failed to download its .proto descriptor.
        If a network fails to download its .proto descriptor
        blacklist_threshold times,
        it will be blacklisted and skipped in future parsing attempts.
        '''
        self.network_blacklist: set[tuple[str, str]] = set()
        '''
        Set of blacklisted networks that have failed to 
        download their .proto descriptor.
        '''
        self.blacklist_threshold: int = 3
        '''
        Threshold for blacklisting a network after consecutive
        failures to download its .proto descriptor.
        '''
        self.parserfsm.send('initialization')

    def set_log_callback(self, callback: callable) -> None:
        """
        Sets the log callback function for the parser's finite state machine.
        Args:
            callback (callable): The callback function to be set for logging.
        """
        self.parserfsm.set_log_callback(callback)

    def _handle_inactivity(self) -> None:
        """
        Handles inactivity by logging a warning message when the
        parser has not processed any messages for a specified timeout period.
        This method is called when the last_parse_timer expires,
        indicating that no messages have been parsed within the defined timeout.
        """
        if self.row_messages.empty():
            with self.__timer_lock:
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
            with self.__timer_lock:
                self.timer_expired = False
            self.timer_touch(
            )  # Reset the timer if there are still messages in the queue

    def add_to_queue(self, message: tuple[list[str], bytes]) -> None:
        '''
        Adds a new message to the row_messages queue in a thread-safe manner.
        Args:
            message (tuple[list[str], bytes]): The message to be added
        '''
        with self.row_queue_not_empty:
            self.row_messages.put(message)
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
            while self.row_messages.empty() and not self.stop:
                self.row_queue_not_empty.wait()
            if self.stop:
                return
            message: tuple[list[str], bytes] = self.row_messages.get()
            self.row_queue_not_empty.notify_all()
        try:
            self.parse_msg(message)
        finally:
            self.row_messages.task_done()
            with self.row_queue_not_empty:
                self.row_queue_not_empty.notify_all()

    def parse_msg(self, msg: tuple[list[str], bytes]) -> None:  # pylint: disable=too-many-return-statements,too-many-locals
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
        with self.__parser_state_lock:
            version = self.device_versions.get(key, {}).get(library)
        if version is None:
            logger.error(
                "parser: Device '%s' started streaming data before sending version. Skipping",
                key)
            return
        if network in self.excluded_networks:
            logger.debug(
                "parser: Network '%s' is in the exclusion list. Skipping message",
                network)
            return
        with self.__parser_state_lock:
            blacklisted = (network, version) in self.network_blacklist
        if blacklisted:
            logger.debug(
                "parser: Network '%s' with version %s is blacklisted due " \
                "to repeated failures to download its .proto descriptor. " \
                "Skipping message.",
                network,
                version
            )
            return
        # Check if the network is already registered for the given version, if not,
        # download the .proto descriptor
        with self.__parser_state_lock:
            descriptor = self.protobuf_manager.version_descriptors.get(
                version, {}).get(network)
        if descriptor is None:
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
                with self.__parser_state_lock:
                    if not self.protobuf_manager.download_proto_descriptor(
                            version, network):
                        self.network_blacklisting[(
                            network, version)] = self.network_blacklisting.get(
                                (network, version), 0) + 1
                        if self.network_blacklisting[(
                                network, version)] >= self.blacklist_threshold:
                            logger.warning(
                                "parser: Network '%s' with version %s has failed to " \
                                "download its .proto descriptor %d times. Blacklisting.",
                                network,
                                version,
                                self.blacklist_threshold
                            )
                            self.network_blacklist.add((network, version))
                        return
            except Exception:  # pylint: disable=broad-exception-caught
                logger.error(
                    "parser: Error while getting proto, skipping message")
                return
        # Deserialize the payload using the appropriate decoder for the given version and network
        try:
            # Use the appropriate decoder for the given version and network
            # to deserialize the payload
            with self.__parser_state_lock:
                decoder = self.protobuf_manager.version_descriptors[version][
                    network]
            # Expect decoder to provide a `decode` method returning a dict-like object
            message_content = decoder.decode(payload)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(
                "parser: Cannot deserialize payload with saved descriptor: %s",
                str(e))
            with self.__parser_state_lock:
                descriptors = dict(self.protobuf_manager.version_descriptors)
            logger.error("parser: version descriptors: %s", descriptors)
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
        with self.__timer_lock:
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
        # Reset the timer_expired flag to indicate that the parser is active
        with self.__timer_lock:
            self.timer_expired = False
            if self.last_parse_timer is not None:
                self.last_parse_timer.cancel()  # Cancel the existing timer

    def __append_to_destination_list(self, line: Line) -> None:
        """
        Appends a Line object to the destination list in a thread-safe manner.
        Args:
            line (Line): The Line object to be appended to the destination list.
        """
        #logger.info("parser: Appending line to destination list: %s", line)
        self.destination_list.put(line)
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
                    except Exception:  # pylint: disable=broad-exception-caught
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
            else:
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
        #logger.info("parser: Pushing record for measurement '%s': %s",
        #            measurement, record)
        # Check if the record is a dictionary; if not, log a warning and return early
        if isinstance(record, dict):
            #logger.info("parser: Received record for measurement '%s': %s",
            #            measurement, record)
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
                            #logger.info("parser: Line: %s", line)
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
                    #logger.warning(
                    #    "parser: Skipping record for measurement '%s' due to missing fields: %s",
                    #    measurement, record)
                    return
                logger.error(
                    "parser: Error creating Line from record for measurement '%s': %s",
                    measurement, str(e))
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(
                    "parser: Error creating Line from record for measurement '%s': %s",
                    measurement, str(e))
                return
            #logger.info("parser: Line: %s", line)
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
        timestamp_values = None
        for timestamp_key in TIMESTAMP_KEYS:
            if timestamp_key in record:
                timestamp_values = record[timestamp_key]
                break
        timestamps = Parser._unwrap_values(timestamp_values)
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
        self.row_messages.join()
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
        with self.row_queue_not_empty:
            self.stop = True
            self.row_queue_not_empty.notify_all(
            )  # Notify the parser thread to wake up and check the stop condition
        with self.__new_points_event_lock__:
            # Notify any waiting threads that the parser is stopping,
            # allowing them to exit their wait state
            self.points_increased.notify_all()

    def run(self) -> None:
        while True:
            self.__parse_next_message()
            with self.row_queue_not_empty:
                if self.stop:
                    return

    def get_points_count(self) -> int:
        '''
        Returns the number of points currently stored in the destination list.
        Returns:
            int: The number of points in the destination list.
        '''
        return self.destination_list.qsize()

    def is_timer_expired(self) -> bool:
        """
        Returns whether the inactivity timer has expired.
        Returns:
            bool: True if the inactivity timer has expired, False otherwise.
        """
        with self.__timer_lock:
            return self.timer_expired

    def register_device_version(self, vehicle_id: str, device_id: str,
                                library: type, version: str) -> None:
        """
        Registers a device decoder version while holding the parser state lock.
        
        Args:
            vehicle_id (str): The unique identifier for the vehicle.
            device_id (str): The unique identifier for the device.
            library (type): The library type (e.g., LibcanManager or LibgpsManager).
            version (str): The version of the decoder to be registered.
        """
        key = f"{vehicle_id}/{device_id}"
        with self.__parser_state_lock:
            self.device_versions.setdefault(key, {})[library] = version
            self.protobuf_manager.version_descriptors.setdefault(version, {})

    def pop_points(self, max_points_to_pop: int = -1) -> list[Point]:
        '''
        Pops a specified number of points from the destination list and returns them.
        Args:
            max_points_to_pop (int): The maximum number of points to pop
        Returns:
            list[Point]: A list of popped InfluxDB Point objects
        '''
        point_count = self.destination_list.qsize()
        target_count = (point_count if max_points_to_pop <= 0 or
                        max_points_to_pop > point_count else max_points_to_pop)
        points: list[Point] = []
        for _ in range(target_count):
            try:
                points.append(self.destination_list.get_nowait())
            except Empty:
                break
        return points

    def log_session_start(self, timestamp: int) -> None:
        """
        Logs the start of a session with the provided timestamp.
        Args:
            timestamp (int): The timestamp indicating when the session started.
        """
        logger.info("parser: Session started at timestamp %d", timestamp)
        raise NotImplementedError(
            "log_session_start method is not implemented.")

    def log_session_end(self, timestamp: int) -> None:
        """
        Logs the end of a session with the provided timestamp.
        Args:
            timestamp (int): The timestamp indicating when the session ended.
        """
        logger.info("parser: Session ended at timestamp %d", timestamp)
        raise NotImplementedError("log_session_end method is not implemented.")


__all__ = ["Parser"]
