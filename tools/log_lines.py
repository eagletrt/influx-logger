"""
This module provides a utility function for logging lines for debugging purposes.
"""
import os
from datetime import datetime

from influxdb_client.client.write_api import Point

from src.utils.line import Line
from src.utils.logger_utils import logger

DEBUG_LOGS_DIR = "debug_logs"
DEBUG_LOGS_FILE = os.path.join(DEBUG_LOGS_DIR, "lines.log")


@staticmethod
def log_lines(list_of_lines: list[Point | Line]) -> None:
    """
    Logs the provided list of lines for debugging purposes.

    Args:
        list_of_lines (list): A list of lines to be logged.
    """
    # mkdir debug_logs if it doesn't exist
    if not os.path.exists(DEBUG_LOGS_DIR):
        os.makedirs(DEBUG_LOGS_DIR)
    with open(DEBUG_LOGS_FILE, "a", encoding="utf-8") as log_file:
        for point in list_of_lines:
            if isinstance(point, Line):
                time = point.timestamp
            else:
                time = point._time  # pylint: disable=protected-access
            # Redable timestamp in microseconds
            readable_time = datetime.fromtimestamp(
                time / 1_000_000).strftime("%Y-%m-%d %H:%M:%S.%f")
            record = point
            log: str = f"influx_writer: _time={readable_time}, {record}"
            logger.debug(log)
            log_file.write(log + "\n")


def extract_lines(measurement: str, field: str) -> None:
    """
    Extracts lines from the debug logs that match the specified measurement and field.

    Args:
        measurement (str): The measurement to filter lines by.
        field (str): The field to filter lines by.
    """
    output: str = ""
    with open(DEBUG_LOGS_FILE, encoding="utf-8") as log_file:
        lines = log_file.readlines()
        for line in lines:
            if measurement in line and field in line:
                output += line
    if output:
        output_file_name = f"{measurement}_{field}.log"
        output_file_path = os.path.join(DEBUG_LOGS_DIR, output_file_name)
        with open(output_file_path, "w", encoding="utf-8") as output_file:
            output_file.write(output)
