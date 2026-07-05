from enum import Enum

class TimestampPrecision(Enum):
    """
    Enum representing the precision of timestamps.
    """
    ns : int =                1
    us : int =            1_000
    ms : int =        1_000_000
    s  : int =    1_000_000_000

INFLUX_INT64_MAX: int = 2**63 - 1
'''InfluxDB's maximum value for a 64-bit signed integer. This constant is used to ensure that timestamp values do not exceed the maximum limit that InfluxDB can handle.'''

TIMESTAMP_KEYS: list[str] = [
    "_inner_timestamp", 
    "_innerTimestamp", 
    "_timestamp", 
    "timestamp", 
    "innerTimestamp"
]
