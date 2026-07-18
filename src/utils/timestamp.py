from enum import Enum

class TimestampPrecision(Enum):
    """
    Enum representing the precision of timestamps.
    """
    ns : int =                1
    '''Nanoseconds'''
    us : int =            1_000
    '''Microseconds'''
    ms : int =        1_000_000
    '''Milliseconds'''
    s  : int =    1_000_000_000
    '''Seconds'''

    @staticmethod
    def get_factor(precision: str) -> int:
        """
        Returns the factor corresponding to the specified timestamp precision.
        Args:
            precision (str): The precision of the timestamp, which can be "ns", "us", "ms", or "s".
        Returns:
            int: The factor corresponding to the specified precision, or None if the precision is invalid.
        """
        if precision == "ns":
            return TimestampPrecision.ns.value
        elif precision == "us":
            return TimestampPrecision.us.value
        elif precision == "ms":
            return TimestampPrecision.ms.value
        elif precision == "s":
            return TimestampPrecision.s.value
        else:
            return None

INFLUX_INT64_MAX: int = 2**63 - 1
'''InfluxDB's maximum value for a 64-bit signed integer. This constant is used to ensure that timestamp values do not exceed the maximum limit that InfluxDB can handle.'''

TIMESTAMP_KEYS: list[str] = [
    "_inner_timestamp", 
    "_innerTimestamp", 
    "_timestamp", 
    "timestamp", 
    "innerTimestamp"
]
