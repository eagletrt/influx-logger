import sys
from types import ModuleType
from unittest import TestCase


if "influxdb_client" not in sys.modules:
    influxdb_client_module = ModuleType("influxdb_client")

    class Point:
        def __init__(self, measurement):
            self.measurement = measurement
            self.tags = {}
            self.fields = {}
            self.timestamp = None
            self.write_precision = None

        def tag(self, key, value):
            self.tags[key] = value
            return self

        def field(self, key, value):
            self.fields[key] = value
            return self

        def time(self, timestamp, write_precision="ns"):
            self.timestamp = timestamp
            self.write_precision = write_precision
            return self

    influxdb_client_module.Point = Point
    sys.modules["influxdb_client"] = influxdb_client_module

from src.utils.line import Line


class TestLine(TestCase):
    def test_to_point_preserves_each_field_type(self):
        line = Line(
            measurement="sample",
            tags={"vehicle-id": "vehicle-1"},
            fields={"int_field": 3, "float_field": 3.5, "bool_field": True},
            timestamp=123,
        )

        point = line.to_point()

        self.assertEqual(point.fields["int_field"], 3)
        self.assertIsInstance(point.fields["int_field"], int)
        self.assertEqual(point.fields["float_field"], 3.5)
        self.assertIsInstance(point.fields["float_field"], float)
        self.assertTrue(point.fields["bool_field"])
        self.assertIsInstance(point.fields["bool_field"], bool)
