"""Tests for InfluxDB line conversion."""

import sys
from types import ModuleType
from unittest import TestCase

if "influxdb_client" not in sys.modules:
    influxdb_client_module = ModuleType("influxdb_client")

    class Point:
        """Minimal Point double used when the dependency is unavailable."""

        def __init__(self, measurement):
            self.measurement = measurement
            self.tags = {}
            self.fields = {}
            self.timestamp = None
            self.write_precision = None

        def tag(self, key, value):
            """Store a tag and return this point."""
            self.tags[key] = value
            return self

        def field(self, key, value):
            """Store a field and return this point."""
            self.fields[key] = value
            return self

        def time(self, timestamp, write_precision="us"):
            """Store the timestamp and precision and return this point."""
            self.timestamp = timestamp
            self.write_precision = write_precision
            return self

    influxdb_client_module.Point = Point
    sys.modules["influxdb_client"] = influxdb_client_module

from src.utils.line import Line  # pylint: disable=wrong-import-position


class TestLine(TestCase):
    """Test conversion between measurement dictionaries and points."""

    def test_from_object_treats_time_as_timestamp(self):
        """Treat the time field as the line timestamp."""
        line = Line.from_object(
            {
                "time": 123,
                "lap_time": 42.5
            },
            measurement="bestlap",
            tags={},
        )

        self.assertEqual(line.timestamp, 123)
        self.assertEqual(line.fields, {"lap_time": 42.5})

    def test_to_point_preserves_each_field_type(self):
        """Preserve scalar field types when creating a point."""
        line = Line(
            measurement="sample",
            tags={"vehicle-id": "vehicle-1"},
            fields={
                "int_field": 3,
                "float_field": 3.5,
                "bool_field": True
            },
            timestamp=123,
        )

        point = line.to_point()
        fields = getattr(point, "fields", None)
        if fields is None:
            fields = getattr(point, "_fields")

        self.assertEqual(fields["int_field"], 3)
        self.assertIsInstance(fields["int_field"], int)
        self.assertEqual(fields["float_field"], 3.5)
        self.assertIsInstance(fields["float_field"], float)
        self.assertTrue(fields["bool_field"])
        self.assertIsInstance(fields["bool_field"], bool)

    def test_to_point_serializes_nested_field_values(self):
        """Serialize nested field values as compact JSON."""
        line = Line(
            measurement="sample",
            tags={},
            fields={"group_mux1": {
                "channel": 2,
                "enabled": True
            }},
            timestamp=123,
        )

        point = line.to_point()
        fields = getattr(point, "fields", None)
        if fields is None:
            fields = getattr(point, "_fields")

        self.assertEqual(fields["group_mux1"], '{"channel":2,"enabled":true}')
