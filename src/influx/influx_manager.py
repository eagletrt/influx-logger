from abc import ABC
from threading import Thread

from src.utils.timestamp import TimestampPrecision
from src.connections.influx_connection import InfluxConnection


class InfluxManager(Thread, ABC):
    """
    A base class for managing interactions with InfluxDB.
    This class provides common functionality for both reading and writing to InfluxDB, such as managing
    the connection and handling timestamp precision. It is intended to be extended by specific reader and writer classes that implement the actual reading and writing logic.
    
    Attributes:
        client (InfluxConnection): The connection to the InfluxDB service.
        timestamp_precision (TimestampPrecision): The precision of timestamps used in interactions with InfluxDB.
    """
    def __init__(self, client:InfluxConnection, timestamp_precision:TimestampPrecision = TimestampPrecision.ns, name:str = "InfluxManager") -> None:
        super().__init__(name=name, daemon=True)
        self.client:InfluxConnection = client
        self.timestamp_precision:TimestampPrecision = timestamp_precision
        self._stop:bool = False

    def stop(self):
        """
        Stops the InfluxManager thread by setting the stop flag to True.
        This method can be called to gracefully stop the thread's execution.
        """
        self.stop = True

__all__ = ["InfluxManager"]
