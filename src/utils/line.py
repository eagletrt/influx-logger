import influxdb_client
from pydot import Any
from influxdb_client import Point, InfluxDBClient

from src.utils.logger_utils import logger
from src.utils.timestamp import TimestampPrecision, INFLUX_INT64_MAX, TIMESTAMP_KEYS

class Line:
    '''
    Represents a single measurement line for InfluxDB.
    Attributes:
        measurement (str): The name of the measurement's signal.
        tags (dict[str, str]): Tags associated with the measurement.
        fields (dict[str, Any]): Fields containing the actual data values.
        timestamp (int): Timestamp of the measurement in nanoseconds since epoch.
    '''
    def __init__(self, measurement: str, tags: dict[str, str], fields: dict[str, Any], timestamp: int) -> None:
        self.measurement = measurement
        '''Name of the measurement's signal'''
        self.tags = tags
        '''Tags associated with the measurement'''
        self.fields = fields
        '''Fields containing the actual data values'''
        self.timestamp = timestamp
        '''Timestamp of the measurement in nanoseconds since epoch'''

    @staticmethod
    def obj_to_str( obj: dict[str, Any]) -> str:
        '''
        Converts a dictionary object to a string representation.
        Args:
            obj (dict[str, Any]): The dictionary object to convert.
        Returns:
            str: A string representation of the dictionary in the format "key1=value1, key2=value2, ...".
        '''
        return ", ".join(f"{k}={v}" for k, v in obj.items())

    @staticmethod
    def from_object(obj: dict[str, Any], measurement: str, tags: dict[str, str]) -> "Line":
        '''
        Creates a Line object from a dictionary representation of a measurement.
        Args:
            obj (dict[str, Any]): The dictionary containing the measurement data.
            measurement (str): The name of the measurement.
            tags (dict[str, str]): A dictionary of tags associated with the measurement.
        Returns:
            Line: A Line object representing the measurement.
        Raises:
            ValueError: If the timestamp is missing or invalid in the input object.
        '''
        #logger.debug(f"Creating Line from object: {Line.obj_to_str(obj)} with measurement: {measurement} and tags: {tags}")
        timestamp = obj.get("_innerTimestamp")
        # Check for timestamp in the possible keys defined in TIMESTAMP_KEYS
        for key in TIMESTAMP_KEYS:
            if timestamp is not None:
                break
            timestamp = obj.get(key)
        # If no valid timestamp is found, raise an error
        if timestamp is None:
            #logger.error(f"Handler: Missing timestamp in object: {Line.obj_to_str(obj)}")
            raise ValueError("Missing timestamp")
        # Convert the timestamp to an integer if it's a string or float
        if isinstance(timestamp, str):
            timestamp_value: int = int(timestamp)
        elif isinstance(timestamp, (int, float)):
            timestamp_value: int = int(timestamp)
        else:
            raise ValueError("Invalid timestamp")
        # Extract fields from the object, excluding any keys that are considered timestamp keys
        fields: dict[str, Any] = {
            k: v
            for k, v in obj.items()
            if k not in TIMESTAMP_KEYS
        }
        #logger.info(f"Influx Connection: Measurement '{measurement}' and timestamp {timestamp_value}")
        return Line(measurement, tags, {k: v for k, v in fields.items()}, timestamp_value)

    @staticmethod
    def _normalize_timestamp(timestamp: int, timestamp_precision: str) -> int:
        '''
        Normalizes a timestamp based on the specified precision.
        Args:
            timestamp (int): The original timestamp to normalize.
            timestamp_precision (str): The precision of the timestamp, which can be "ns", "us", "ms", or "s".
        Returns:
            int: The normalized timestamp.
        Raises:
            ValueError: If the normalized timestamp exceeds InfluxDB's maximum value for a 64-bit signed integer.
        '''
        factor: int = TimestampPrecision.get_factor(timestamp_precision)
        if factor is None:
            return timestamp
        # Normalize the timestamp by dividing it by the factor corresponding to the specified precision
        normalized: int = timestamp // factor
        # Check if the normalized timestamp exceeds InfluxDB's maximum value for a 64-bit signed integer
        if normalized > INFLUX_INT64_MAX:
            raise ValueError(f"Timestamp {timestamp} is out of range for InfluxDB")
        return normalized
    
    def to_point(self, timestamp_precision: str = "ns") -> Point:
        '''
        Converts the Line object to an InfluxDB Point object.
        Args:
            timestamp_precision (str): The precision of the timestamp for the InfluxDB Point, which can be "ns", "us", "ms", or "s". Default is "ns".
        Returns:
            influxdb_client.Point: The converted InfluxDB Point object.
        '''
        point: Point = Point(self.measurement)
        for k, v in self.tags.items():
            point.tag(k, v)
        for k, v in self.fields.items():
            if isinstance(v, bytes):
                point.field(k, v.decode("utf-8", errors="replace"))
            else:
                point.field(k, str(v))
        point.time(self.timestamp, write_precision=timestamp_precision)
        return point

    def __str__(self) -> str:
        def field_to_str(k, v):
            if isinstance(v, str):
                return f'{k}="{v}"'
            else:
                return f"{k}={v}"
        # Create a string representation of the fields in the format "key1=value1, key2=value2, ..."
        fields_str = ",".join(field_to_str(k, v) for k, v in self.fields.items())
        tags_str = ",".join(f"{k}={v}" for k, v in self.tags.items())
        tags_part = f",{tags_str}" if self.tags else ""
        prefix = f"{self.measurement}{tags_part}"
        return f"{prefix} {fields_str} {self.timestamp}"


class LineRepository:
    def __init__(self, url: str, bucket: str, org: str, token: str, timestamp_precision: str = "us", limit: int = 5_000) -> None:
        self.points: list[Point] = []
        self.limit = limit
        self.url = url
        self.bucket = bucket
        self.token = token
        self.org = org
        self.timestamp_precision = timestamp_precision
        self.pending_commits_count = 0
        
        self.client = InfluxDBClient(url=url, token=token, org=org)
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
    def pack_lines(lines: list[Point]) -> str:
        return "\n".join(str(line) for line in lines)
