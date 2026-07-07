from influxdb_client import Point
from influxdb_client.client.write_api import WriteOptions, WriteApi
from threading import Condition

from src.parser.parser import Parser
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
    def __init__(self, client:InfluxConnection, batch_size:int = 5_000, timestamp_precision:TimestampPrecision = TimestampPrecision.ns) -> None:
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
        self.points:list[Point] = None
        self.ready_to_flush_list:list[str] = None
        self.parser: Parser = Parser()
        self.cond_to_push: Condition = Condition()

    def is_list_limit_reached(self, count:int) -> bool:
        return count >= self.write_options.batch_size
    
    def prepare_for_commit(self, point:Point) -> None:
        raise NotImplementedError("This method should be implemented by subclasses to prepare the point for commit, e.g. by adding it to the points list and checking if the batch size limit is reached.")
    
    def push(self, point:Point) -> None:
        points: list[Point] = self.parser.pop_points(self.write_options.batch_size)
    
    def commit(self) -> None:
        points: list[Point] = self.parser.pop_points(self.write_options.batch_size)
        try:
            result = self.write_api.write(
                bucket=self.client.bucket,
                org=self.client.org,
                record=points,
                write_precision=self.timestamp_precision,
            )
        except Exception as e:
            pack: str = InfluxWriter.__pack_lines(points)
            logger.error(f"Influx Connection: Failed to commit lines: {e}", exc_info=True)
            logger.debug(f"Influx Connection: Lines that failed to commit: {pack}")
        else:
            logger.info(f"Influx Connection: Successfully committed {len(points)} lines")
            logger.debug(f"Influx Connection: Write API returned: {result}")

    @staticmethod
    def __pack_lines(lines: list[Point]) -> str:
        """
        Packs a list of InfluxDB points into a single string representation.

        Args:
            lines (list[Point]): A list of InfluxDB Point objects to be packed.

        Returns:
            str: A string representation of the packed points, where each point is converted to its line protocol format and separated by newlines.
        """
        # TODO: probably change it in order to not use str(line) but line.to_line_protocol() or something like that
        return "\n".join([str(line) for line in lines])
    
    def check_to_push(self) -> None:
        return self.is_list_limit_reached(
            self.parser.get_points_count()
            )
    
    def run(self) -> None:
        try:
            self.parser.start()
        except Exception:
            pass
        while not super()._stop():
            self.cond_to_push.wait(lambda: self.check_to_push() or super()._stop())
            if self.check_to_push():
                self.push(self.parser.pop_points(self.write_options.batch_size))
        self.parser.graceful_stop()

    def graceful_stop(self) -> None:
        super().stop()
        self.parser.graceful_stop()
        self.parser.join()
        self.cond_to_push.notify_all()

    def stop(self) -> None:
        super().stop()
        self.parser.stop_parser()
        self.parser.join()
        self.cond_to_push.notify_all()

__all__ = ["InfluxWriter"]
