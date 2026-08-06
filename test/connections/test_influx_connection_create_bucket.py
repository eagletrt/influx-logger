import sys
import types
import unittest
from unittest.mock import MagicMock


if "influxdb_client" not in sys.modules:
    influx_mod = types.ModuleType("influxdb_client")

    class _InfluxDBClient:
        def __init__(self, *args, **kwargs):
            pass

    influx_mod.InfluxDBClient = _InfluxDBClient
    sys.modules["influxdb_client"] = influx_mod


from src.connections.influx_connection import InfluxConnection


class TestInfluxConnectionCreateBucket(unittest.TestCase):
    def test_create_bucket_sends_bucket_payload(self):
        connection = InfluxConnection.__new__(InfluxConnection)
        connection.org = "org"
        bucket_api = MagicMock()
        connection.connection = MagicMock()
        connection.connection.buckets_api.return_value = bucket_api

        result = InfluxConnection.create_bucket(
            connection,
            bucket_name="telemetry_adr",
            retention_rules={"type": "expire", "everySeconds": 86400},
        )

        self.assertTrue(result)
        bucket_api.create_bucket.assert_called_once_with(
            bucket_name="telemetry_adr",
            retention_rules={"type": "expire", "everySeconds": 86400},
            org="org",
        )