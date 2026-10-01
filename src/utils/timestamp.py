"""
Timestamp utility module for InfluxDB interactions.
"""
from enum import Enum


class TimestampPrecision(Enum):
    """
    Enum representing the precision of timestamps.
    """
    NANOSECONDS: int = 1
    '''Nanoseconds'''
    MICROSECONDS: int = 1_000
    '''Microseconds'''
    MILLISECONDS: int = 1_000_000
    '''Milliseconds'''
    SECONDS: int = 1_000_000_000
    '''Seconds'''

    @staticmethod
    def get_factor(precision: str) -> int:
        """
        Returns the factor corresponding to the specified timestamp precision.
        Args:
            precision (str): The precision of the timestamp, which can be "ns", "us", "ms", or "s".
        Returns:
            int: The factor corresponding to the specified precision.
        """
        if precision == "ns":
            return TimestampPrecision.NANOSECONDS.value
        if precision == "us":
            return TimestampPrecision.MICROSECONDS.value
        if precision == "ms":
            return TimestampPrecision.MILLISECONDS.value
        if precision == "s":
            return TimestampPrecision.SECONDS.value
        return None

    @staticmethod
    def get_name(precision: int) -> str:
        """
        Returns the name of the timestamp precision corresponding to the specified factor.
        Args:
            precision (int): The factor of the timestamp precision.
        Returns:
            str: The name of the timestamp precision, which can be "ns", "us", "ms", or "s".
        """
        if precision == TimestampPrecision.NANOSECONDS.value:
            return "ns"
        if precision == TimestampPrecision.MICROSECONDS.value:
            return "us"
        if precision == TimestampPrecision.MILLISECONDS.value:
            return "ms"
        if precision == TimestampPrecision.SECONDS.value:
            return "s"
        return None


INFLUX_INT64_MAX: int = 2**63 - 1
'''
InfluxDB's maximum value for a 64-bit signed integer.
This constant is used to ensure that timestamp values do not exceed
the maximum limit that InfluxDB can handle.
'''

TIMESTAMP_KEYS: list[str] = [
    "inner_timestamp",
    "_inner_timestamp",
    "time",
    "timestamp",
    "_timestamp",
    "innerTimestamp",
    "_innerTimestamp",
]
'''
List of keys that are commonly used to represent timestamps in data structures.
This list is used to identify and extract timestamp values from various data formats.
'''
