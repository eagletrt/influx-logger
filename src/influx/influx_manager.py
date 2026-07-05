from abc import ABC

from src.connections.influx_connection import InfluxConnection
from utils.timestamp import TimestampPrecision


class InfluxManager(ABC):
    """
    A base class for managing interactions with InfluxDB.
    This class provides common functionality for both reading and writing to InfluxDB, such as managing
    the connection and handling timestamp precision. It is intended to be extended by specific reader and writer classes that implement the actual reading and writing logic.
    
    Attributes:
        client (InfluxConnection): The connection to the InfluxDB service.
        timestamp_precision (TimestampPrecision): The precision of timestamps used in interactions with InfluxDB.
    """
    def __init__(self, client:InfluxConnection, timestamp_precision:TimestampPrecision = TimestampPrecision.NANOSECONDS):
        self.client:InfluxConnection = client
        self.timestamp_precision:TimestampPrecision = timestamp_precision
