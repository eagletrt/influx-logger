"""
This module provides a logger instance that can be used throughout
the application.
The logger is configured to log messages to the standard
output (stdout) and supports a custom TRACE log level for
detailed debugging information.
"""

import logging
import os
import sys


class _TraceLevel:
    TRACE = 5


logging.addLevelName(_TraceLevel.TRACE, "TRACE")


def _trace(self, message, *args, **kws):
    if self.isEnabledFor(_TraceLevel.TRACE):
        self._log(_TraceLevel.TRACE, message, args, **kws)


logging.Logger.trace = _trace

LEVEL_NAME = "TRACE" if os.getenv("NODE_ENV") == "development" else "INFO"
level = logging.getLevelName(LEVEL_NAME)

logger = logging.getLogger("influx_logger")
logger.setLevel(level)

handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    "%(asctime)s %(levelname)s %(name)s - %(message)s", )
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)

__all__ = ["logger"]
