from typing import Dict, Any, List

from .logger_utils import logger
import requests


LineFieldType = (str, int, float, bool)


class Line:
    def __init__(self, measurement: str, tags: Dict[str, str], fields: Dict[str, Any], timestamp: int) -> None:
        self.measurement = measurement
        self.tags = tags
        self.fields = fields
        self.timestamp = timestamp

    @staticmethod
    def from_object(obj: Dict[str, Any], measurement: str, tags: Dict[str, str]) -> "Line":
        timestamp = obj.get("_innerTimestamp")
        if timestamp is None:
            timestamp = obj.get("_timestamp")
        if timestamp is None:
            timestamp = obj.get("timestamp")
        if timestamp is None:
            timestamp = obj.get("innerTimestamp")

        if timestamp is None:
            raise ValueError("Missing or invalid timestamp")

        if isinstance(timestamp, str):
            timestamp_value = int(timestamp)
        elif isinstance(timestamp, (int, float)):
            timestamp_value = int(timestamp)
        else:
            raise ValueError("Missing or invalid timestamp")

        fields = {
            k: v
            for k, v in obj.items()
            if k not in {"_innerTimestamp", "_timestamp", "timestamp", "innerTimestamp"}
        }

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

    def push(self, line: Line) -> None:
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
        url = f"{self.url}/api/v2/write?org={self.org}&bucket={self.bucket}&precision={self.timestamp_precision}"

        resp = requests.post(url, data=pack, headers={"Authorization": f"Token {self.token}"})
        if not resp.ok:
            logger.error(f"Failed to commit lines: {resp.text}")
        else:
            logger.info(f"Committed {lines_count} lines")

        self.pending_commits_count -= 1

    @staticmethod
    def pack_lines(lines: List[Line]) -> str:
        return "\n".join(str(line) for line in lines)


__all__ = ["Line", "LineRepository"]
