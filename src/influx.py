from typing import Dict, Any, List

from .logger_utils import logger
import requests
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS


LineFieldType = (str, int, float, bool)


class Line:
    possible_timestamp_keys = ["_inner_timestamp", "_innerTimestamp", "_timestamp", "timestamp", "innerTimestamp"]
    def __init__(self, measurement: str, tags: Dict[str, str], fields: Dict[str, Any], timestamp: int) -> None:
        self.measurement = measurement
        self.tags = tags
        self.fields = fields
        self.timestamp = timestamp

    @staticmethod
    def obj_to_str( obj: Dict[str, Any]) -> str:
        return ", ".join(f"{k}={v}" for k, v in obj.items())

    @staticmethod
    def from_object(obj: Dict[str, Any], measurement: str, tags: Dict[str, str]) -> "Line":
        #logger.debug(f"Creating Line from object: {Line.obj_to_str(obj)} with measurement: {measurement} and tags: {tags}")
        timestamp = obj.get("_innerTimestamp")

        for key in Line.possible_timestamp_keys:
            if timestamp is not None:
                break
            timestamp = obj.get(key)

        if timestamp is None:
            logger.error(f"Handler: Missing timestamp in object: {Line.obj_to_str(obj)}")
            raise ValueError("Missing timestamp")

        if isinstance(timestamp, str):
            timestamp_value = int(timestamp)
        elif isinstance(timestamp, (int, float)):
            timestamp_value = int(timestamp)
        else:
            raise ValueError("Invalid timestamp")

        fields = {
            k: v
            for k, v in obj.items()
            if k not in {"_innerTimestamp", "_timestamp", "timestamp", "innerTimestamp"}
        }
        #logger.info(f"Influx Connection: Measurement '{measurement}' and timestamp {timestamp_value}")
        return Line(measurement, tags, {k: v for k, v in fields.items()}, timestamp_value)

    def __str__(self) -> str:
        def field_to_str(k, v):
            if isinstance(v, str):
                return f'{k}="{v}"'
            else:
                return f"{k}={v}"

        fields_str = ",".join(field_to_str(k, v) for k, v in self.fields.items())
        tags_str = ",".join(f"{k}={v}" for k, v in self.tags.items())
        tags_part = f",{tags_str}" if self.tags else ""
        prefix = f"{self.measurement}{tags_part}"
        return f"{prefix} {fields_str} {self.timestamp}"


class LineRepository:
    def __init__(self, url: str, bucket: str, org: str, token: str, timestamp_precision: str = "us", limit: int = 5000) -> None:
        self.lines: List[Line] = []
        self.limit = limit
        self.url = url
        self.bucket = bucket
        self.token = token
        self.org = org
        self.timestamp_precision = timestamp_precision
        self.pending_commits_count = 0
        self.client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    def push(self, line: Line) -> None:
        #logger.debug(f"Influx Connection: Lines {len(self.lines)}/{self.limit}: {line}")
        self.lines.append(line)
        if len(self.lines) >= self.limit:
            self.commit()
            self.lines = []

    def commit(self) -> None:
        lines_count = len(self.lines)
        logger.info(f"Committing {lines_count} lines")
        logger.info(f"Pending commits: {self.pending_commits_count}")
        self.pending_commits_count += 1

        pack = LineRepository.pack_lines(self.lines)
        #url = f"{self.url}/api/v2/write?org={self.org}&bucket={self.bucket}&precision={self.timestamp_precision}"
        url: str = f"{self.url}/api/v2/write?org={self.org}&bucket={self.bucket}&precision={self.timestamp_precision}"
        try:
            self.write_api.write(bucket=self.bucket, org=self.org, record=pack, write_precision=self.timestamp_precision)
        except Exception as e:
            logger.error(f"Influx Connection: Failed to commit lines: {e}")
            logger.debug(f"Influx Connection: Lines that failed to commit: {pack}")
        else:
            logger.info(f"Influx Connection: Successfully committed {lines_count} lines")

        self.pending_commits_count -= 1

    @staticmethod
    def pack_lines(lines: List[Line]) -> str:
        return "\n".join(str(line) for line in lines)


__all__ = ["Line", "LineRepository"]
