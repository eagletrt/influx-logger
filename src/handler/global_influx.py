"""Global shared state for the influx-logger application.

This module provides a simple singleton-like container to store
shared objects such as configuration, MQTT connection and parsed
protobuf descriptors across the application.

Usage:
    from .global import get_global
    g = get_global()
    g.configuration = {...}

The module avoids complex runtime dependencies in the global
initialization to keep imports lightweight.
"""

from typing import Any, Dict, Optional, List, TypedDict

try:
    from ..influx import LineRepository
except Exception:  # pragma: no cover - keep import optional for static checks
    LineRepository = Any  # type: ignore


class Configuration(TypedDict):
    mqtt_url: str
    mqtt_port: int
    influx_url: str
    influx_bucket: str
    influx_token: str
    influx_org: str
    excludedNetworks: List[str]

class Line(TypedDict):
    measurement: str
    tags: Dict[str, str]
    fields: Dict[str, Any]
    timestamp: int


class GlobalState:
    configuration: Optional[Configuration]
    connection: Any
    device_versions: Dict[str, str]
    # version_descriptors maps version -> network -> protobuf type/object
    version_descriptors: Dict[str, Dict[str, Any]]
    line_repository: Optional[LineRepository]

    def __init__(self) -> None:
        self.configuration = None
        self.connection = None
        self.device_versions = {}
        self.version_descriptors = {}
        self.line_repository = None


# Use a module-level singleton stored under a stable name so re-imports
# across the application share the same object.
_GLOBAL_STATE_NAME = "_INFLUX_LOGGER_GLOBAL_STATE"
_global = globals().get(_GLOBAL_STATE_NAME)
if _global is None:
    _global = GlobalState()
    globals()[_GLOBAL_STATE_NAME] = _global


def get_global() -> GlobalState:
    """Return the global shared state object."""

    return _global  # type: ignore


# Convenience alias for callers that prefer a module variable
global_state = get_global()


__all__ = ["Configuration", "Line", "GlobalState", "get_global", "global_state"]
