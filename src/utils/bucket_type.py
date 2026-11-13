"""
Enum-like class for InfluxDB bucket types.
"""

from enum import Enum


class BucketType(Enum):
    """
    Enum-like class for InfluxDB bucket types.
    """
    ADR: str = "adr"
    LOG: str = "log"


__all__ = ["BucketType"]
