from influxdb_client import Point
from influxdb_client.client.write_api import WriteOptions, WriteApi

from connections.influx_connection import InfluxConnection
from src.influx.influx_manager import InfluxManager
from utils.timestamp_precision import TimestampPrecision

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
    def __init__(self, client:InfluxConnection, batch_size:int = 5_000, timestamp_precision:TimestampPrecision = TimestampPrecision.NANOSECONDS):
        super().__init__(client, timestamp_precision)
        self.write_options:WriteOptions = WriteOptions(
            batch_size=batch_size,
            flush_interval=10_000,  # Flush every 10 seconds
            retry_interval=5_000,  # Retry every 5 seconds if the write fails
            max_retries=3,  # Maximum number of retries
        )
        self.write_api:WriteApi = self.client.connection.write_api(
            write_options=self.write_options
        )
        self.points:list[Point] = None
        self.ready_to_flush_list:list[str] = None

    def is_list_limit_reached(self, list:list) -> bool:
        return len(list) >= self.write_options.batch_size
    
    def prepare_for_commit(self, point:Point) -> None:
        raise NotImplementedError("This method should be implemented by subclasses to prepare the point for commit, e.g. by adding it to the points list and checking if the batch size limit is reached.")
    
    def push(self, point:Point) -> None:
        raise NotImplementedError("This method should be implemented by subclasses to push a point to the InfluxDB, e.g. by preparing it for commit and committing if the batch size limit is reached.")
    
    def commit(self) -> None:
        raise NotImplementedError("This method should be implemented by subclasses to commit the points to the InfluxDB, e.g. by writing the points using the write API and clearing the points list.")
    
    def __pack_lines(self) -> None:
        raise NotImplementedError("This method should be implemented by subclasses to pack the points into a format suitable for writing to InfluxDB, e.g. by converting the points to a string representation.")
