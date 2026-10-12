"""
This module provides a utility function for logging lines for debugging purposes.
"""

from influxdb_client.client.write_api import Point
from src.utils.line import Line
from src.utils.logger_utils import logger

@staticmethod
def log_lines(list_of_lines: list[Point | Line]) -> None:
    """
    Logs the provided list of lines for debugging purposes.

    Args:
        list_of_lines (list): A list of lines to be logged.
    """
    with open("debug_logs/lines.log", "a") as log_file:
        for point in list_of_lines:
            if isinstance(point, Line):
                time = point.timestamp
            else:
                time = point._time
            # Redable timestamp in microseconds
            from datetime import datetime
            readable_time = datetime.fromtimestamp(time / 1_000_000).strftime("%Y-%m-%d %H:%M:%S.%f")   
            record = point
            log: str = f"influx_writer: _time={readable_time}, {record}"
            logger.debug(log)
            log_file.write(log + "\n")
