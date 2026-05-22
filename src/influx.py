from typing import Dict, Any, List

from .logger_utils import logger
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS


_INFLUX_INT64_MAX = 2**63 - 1
_TIMESTAMP_PRECISION_FACTORS = {
    "ns": 1,
    "us": 1_000,
    "ms": 1_000_000,
    "s": 1_000_000_000,
}


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
            #logger.error(f"Handler: Missing timestamp in object: {Line.obj_to_str(obj)}")
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
            if k not in Line.possible_timestamp_keys
        }
        #logger.info(f"Influx Connection: Measurement '{measurement}' and timestamp {timestamp_value}")
        return Line(measurement, tags, {k: v for k, v in fields.items()}, timestamp_value)

    @staticmethod
    def _normalize_timestamp(timestamp: int, timestamp_precision: str) -> int:
        factor = _TIMESTAMP_PRECISION_FACTORS.get(timestamp_precision)
        if factor is None:
            return timestamp

        normalized = timestamp // factor
        if normalized > _INFLUX_INT64_MAX:
            raise ValueError(f"Timestamp {timestamp} is out of range for InfluxDB")
        return normalized
    
    def to_point(self, timestamp_precision: str = "ns") -> influxdb_client.Point:
        p = influxdb_client.Point(self.measurement)
        for k, v in self.tags.items():
            p.tag(k, v)
        for k, v in self.fields.items():
            if isinstance(v, bytes):
                p.field(k, v.decode("utf-8", errors="replace"))
            else:
                p.field(k, str(v))
        p.time(self.timestamp, write_precision=timestamp_precision)
        return p

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
    def __init__(self, url: str, bucket: str, org: str, token: str, timestamp_precision: str = "us", limit: int = 5_000) -> None:
        self.points: List[influxdb_client.Point] = []
        self.limit = limit
        self.url = url
        self.bucket = bucket
        self.token = token
        self.org = org
        self.timestamp_precision = timestamp_precision
        self.pending_commits_count = 0
        
        self.client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)
        self.write_options = influxdb_client.client.write_api.WriteOptions(
            batch_size=limit,
            flush_interval=10_000,  # Flush every 10 seconds
            retry_interval=5_000,  # Retry every 5 seconds if the write fails
            max_retries=3,  # Maximum number of retries
        )
        self.write_api: influxdb_client.client.write_api.WriteApi = self.client.write_api(write_options=self.write_options)


    def push(self, line: Line) -> None:
        #logger.debug(f"Influx Connection: Lines {len(self.lines)}/{self.limit}: {line}")
        self.points.append(line.to_point(self.timestamp_precision))
        #logger.debug(f"Influx Connection: Lines {len(self.points)}/{self.limit}")
        if len(self.points) >= self.limit:
            logger.info(f"Influx Connection: Line limit reached ({self.limit}), committing lines")
            self.commit()
            self.points = []

    def commit(self) -> None:
        lines_count = len(self.points)
        #logger.info(f"Influx Connection: Committing {lines_count} lines")
        self.pending_commits_count += 1

        pack = LineRepository.pack_lines(self.points)
        #url = f"{self.url}/api/v2/write?org={self.org}&bucket={self.bucket}&precision={self.timestamp_precision}"
        #url: str = f"{self.url}/api/v2/write?org={self.org}&bucket={self.bucket}&precision={self.timestamp_precision}"
        #logger.debug(f"Influx Connection: Writing to {url} with precision={self.timestamp_precision}, lines={lines_count}")
        try:
            result = self.write_api.write(
                bucket=self.bucket,
                org=self.org,
                record=self.points,
                write_precision=self.timestamp_precision,
            )
        except Exception as e:
            logger.error(f"Influx Connection: Failed to commit lines: {e}", exc_info=True)
            logger.debug(f"Influx Connection: Lines that failed to commit: {pack}")
        else:
            logger.info(f"Influx Connection: Successfully committed {lines_count} lines")
            logger.debug(f"Influx Connection: Write API returned: {result}")

        self.pending_commits_count -= 1

    @staticmethod
    def pack_lines(lines: List[influxdb_client.Point]) -> str:
        return "\n".join(str(line) for line in lines)


__all__ = ["Line", "LineRepository"]
