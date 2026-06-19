from enum import Enum

class TimestampPrecision(Enum):
    """
    Enum representing the precision of timestamps.
    """
    ns =                1
    us =            1_000
    ms =        1_000_000
    s  =    1_000_000_000