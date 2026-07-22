from influxdb_client.client.write_api import WriteOptions, WriteApi
from threading import Condition, Lock

from src.parser.parser import Parser
from src.utils.line import Line
from src.utils.logger_utils import logger
from src.utils.timestamp import TimestampPrecision
from src.influx.influx_manager import InfluxManager
from connections.influx_connection import InfluxConnection

class InfluxWriter(InfluxManager):
    """
    A writer for interacting with InfluxDB.

    Attributes:
        client (InfluxConnection): The connection to the InfluxDB service.
        timestamp_precision (TimestampPrecision): The precision of timestamps used in interactions with InfluxDB.
        write_options (WriteOptions): The options for writing data to InfluxDB, including batch size, flush interval, retry interval, and maximum retries.
        write_api (WriteApi): The API for writing data to InfluxDB, initialized with the specified write options.
        points (list[Point]): A list of points to be written to InfluxDB, which will be prepared and committed in batches based on the specified batch size.
        ready_to_flush_list (list[str]): A list of identifiers for points that are ready to be flushed to InfluxDB, which can be used
    """
    def __init__(self, client:InfluxConnection, batch_size:int = 5_000, timestamp_precision: str = TimestampPrecision.us.name) -> None:
        super().__init__(client, timestamp_precision, name="InfluxWriter")
        self.write_options:WriteOptions = WriteOptions(
            batch_size=batch_size, # The maximum number of points to be written in a single batch. When this limit is reached, the points will be flushed to InfluxDB.
            flush_interval=10_000,  # Flush every 10 seconds
            retry_interval=5_000,  # Retry every 5 seconds if the write fails
            max_retries=3,  # Maximum number of retries
        )
        self.write_api:WriteApi = self.client.connection.write_api(
            write_options=self.write_options
        )
        self.parser: Parser = Parser()
        '''Parser instance for processing incoming data and converting it into InfluxDB points. The parser will handle the parsing of messages and the creation of Point objects.'''
        self.__lock__: Lock = Lock()
        '''Lock for synchronizing access to shared resources, ensuring thread safety when preparing and committing points to InfluxDB.'''
        self.cond_to_push: Condition = Condition(lock=self.__lock__)
        '''Condition variable for signaling when the batch size limit is reached and points are ready to be pushed to InfluxDB. This allows for efficient waiting and notification between threads.'''

    def is_list_limit_reached(self, count:int) -> bool:
        '''
        Checks if the number of points in the list has reached the specified batch size limit.
        
        Args:
            count (int): The current number of points in the list.
        Returns:
            bool: True if the count is greater than or equal to the batch size limit, False otherwise.
        '''
        return count >= self.write_options.batch_size
    
    def prepare_for_commit(self) -> str:
        '''
        Prepares the points for committing to InfluxDB by popping a batch of points from the parser and packing them into a string representation.
        Returns:
            str: A string representation of the packed points, ready to be committed to InfluxDB.
        '''
        points: list[Line] = []
        with self.__lock__:
            lines: list[Line] = self.parser.pop_points(self.write_options.batch_size)
        for line in lines:
            points.append(line.to_point(timestamp_precision=self.timestamp_precision))
        # pack: str = self.__pack_lines(self.points, self.timestamp_precision)
        return points
    
    def commit(self) -> bool:
        '''
        Commits the prepared points to InfluxDB using the write API.
        Returns:
            bool: True if the commit was successful, False otherwise.
        '''
        points: str = self.prepare_for_commit()
        if len(points) == 0:
            logger.debug("influx_writer: No points available to commit")
            return False
        logger.info(f"influx_writer: Committing {len(points)} lines to InfluxDB")
        #logger.info(f"influx_writer: Lines to commit:\n{points}")
        try:
            #logger.info(f"influx_writer: bucket: {self.client.bucket}, org: {self.client.org}, write_precision: {self.timestamp_precision}")
            result = self.write_api.write(
                bucket=self.client.bucket,
                org=self.client.org,
                record=points,
                write_precision=self.timestamp_precision,
            )
            if result is None:
                logger.info(f"influx_writer: Successfully committed {len(points)} lines")
            else:
                logger.warning(f"influx_writer: Commit returned unexpected result: {result}")
            return result is None
        except Exception as e:
            pack: str = InfluxWriter.__pack_lines(self.points, self.timestamp_precision)
            logger.error(f"influx_writer: Failed to commit lines: {e}", exc_info=True)
            logger.debug(f"influx_writer: Lines that failed to commit: {pack}")

    @staticmethod
    def __pack_lines(lines: list[Line], timestamp_precision: str) -> str:
        """
        Packs a list of InfluxDB points into a single string representation.

        Args:
            lines (list[Point]): A list of InfluxDB Point objects to be packed.

        Returns:
            str: A string representation of the packed points, where each point is converted to its line protocol format and separated by newlines.
        """
        valid_lines = [line for line in lines if line is not None]
        return "\n".join([
            line.to_point(timestamp_precision=timestamp_precision).to_line_protocol()
            for line in valid_lines
        ])
    
    def check_to_commit(self) -> bool:
        '''
        Checks if the number of points in the parser has reached the batch size limit for pushing to InfluxDB.
        Returns:
            bool: True if the number of points in the parser has reached or exceeded the batch size limit, False otherwise.
        '''
        return self.is_list_limit_reached(
            self.parser.get_points_count()
            )
    
    def run(self) -> None:
        try:
            self.parser.start()
        except Exception:
            pass
        while self.stopped() is False:
            with self.parser.__new_points_event_lock__:
                self.parser.points_increased.wait()
            if self.check_to_commit():
                self.commit()
        self.parser.graceful_stop()

    def graceful_stop(self) -> None:
        '''
        Gracefully stops the InfluxWriter and its associated parser, ensuring that any remaining points are processed and committed before termination.
        '''
        super().stop()
        self.parser.graceful_stop()
        self.parser.join()

    def stop(self) -> None:
        '''
        Stops the InfluxWriter and its associated parser, ensuring that any remaining points are processed and committed before termination.
        '''
        super().stop()
        self.parser.stop_parser()
        self.parser.join()

__all__ = ["InfluxWriter"]
