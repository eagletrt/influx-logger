from pydot import Any
from influxdb_client import Point

from src.utils.logger_utils import logger
from src.utils.timestamp import TimestampPrecision, INFLUX_INT64_MAX, TIMESTAMP_KEYS

class Line:
    '''
    Represents a single measurement line for InfluxDB.
    Attributes:
        measurement (Any): The name of the measurement's signal.
        tags (dict[str, str]): Tags associated with the measurement.
        fields (dict[str, Any]): Fields containing the actual data values.
        timestamp (int): Timestamp of the measurement in nanoseconds since epoch.
    '''
    def __init__(self, measurement: Any, tags: dict[str, str], fields: dict[str, Any], timestamp: int) -> None:
        self.measurement:Any = measurement
        '''Name of the measurement's signal'''
        self.tags:dict[str, str] = tags
        '''Tags associated with the measurement'''
        self.fields:dict[str, Any] = fields
        '''Fields containing the actual data values'''
        self.timestamp:int = timestamp
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
    def from_object(obj: dict[str, Any], measurement: Any, tags: dict[str, str]) -> "Line":
        '''
        Creates a Line object from a dictionary representation of a measurement.
        Args:
            obj (dict[str, Any]): The dictionary containing the measurement data.
            measurement (Any): The name of the measurement.
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
        if len(fields) == 0:
            raise ValueError("Missing fields")
        #logger.info(f"Influx Connection: Measurement '{measurement}' and timestamp {timestamp_value}")
        return Line(measurement, tags, {k: v for k, v in fields.items()}, timestamp_value)

    @staticmethod
    def _normalize_timestamp(timestamp: int, timestamp_precision: str = "ns") -> int:
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
        for key, value in self.tags.items():
            point.tag(key, value)
        type_of_v: type  = None
        type_of_f: type  = None
        for field, value in self.fields.items():
            if type_of_v is None:
                type_of_v = type(value)
                logger.info(f"Line: Type of value for vaule '{value}' is {type_of_v}")
            if type_of_f is None:
                type_of_f = type(field)
                logger.info(f"Line: Type of field for field '{field}' is {type_of_f}")
            if not isinstance(value, type_of_v):
                # Cast it to it
                value = type_of_v(value)
            if not isinstance(field, type_of_f):
                # Cast it to it
                field = type_of_f(field)
            point.field(field, value)
        point.time(self.timestamp, write_precision=timestamp_precision)
        return point

    def __str__(self) -> str:
        def field_to_str(k, v):
            if isinstance(v, bytes):
                return f'{k}="{v.decode("utf-8", errors="replace")}"'
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
