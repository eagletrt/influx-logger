import sys
import types
import unittest
from unittest.mock import MagicMock, patch


if "influxdb_client" not in sys.modules:
    influx_mod = types.ModuleType("influxdb_client")

    class _InfluxDBClient:
        def __init__(self, *args, **kwargs):
            pass

    influx_mod.InfluxDBClient = _InfluxDBClient
    sys.modules["influxdb_client"] = influx_mod

if "paho.mqtt.client" not in sys.modules:
    paho_mod = types.ModuleType("paho")
    mqtt_pkg = types.ModuleType("paho.mqtt")
    mqtt_client_mod = types.ModuleType("paho.mqtt.client")

    class _Client:
        def __init__(self, *args, **kwargs):
            self.on_connect = None
            self.on_disconnect = None

        def connect(self, *args, **kwargs):
            return None

        def loop_start(self):
            return None

        def loop_stop(self):
            return None

        def disconnect(self):
            return None

        def loop_read(self):
            return None

    mqtt_client_mod.Client = _Client
    paho_mod.mqtt = mqtt_pkg
    mqtt_pkg.client = mqtt_client_mod
    sys.modules["paho"] = paho_mod
    sys.modules["paho.mqtt"] = mqtt_pkg
    sys.modules["paho.mqtt.client"] = mqtt_client_mod

from src.connections.connection_handler import ConnectionHandler


class TestConnectionHandler(unittest.TestCase):
    def setUp(self):
        ConnectionHandler._instance = None
        ConnectionHandler._initialized = False

    def tearDown(self):
        ConnectionHandler._instance = None
        ConnectionHandler._initialized = False

    def test_set_wires_state_change_callback_to_both_connections(self):
        config = MagicMock(
            influx_url="http://influx",
            influx_token="token",
            influx_org="org",
            influx_bucket="bucket",
            influx_port=8086,
            mqtt_url="mqtt://broker",
            mqtt_port=1883,
        )
        on_state_change = MagicMock()

        with patch("src.connections.connection_handler.InfluxConnection") as influx_cls, patch(
            "src.connections.connection_handler.MQTTConnection"
        ) as mqtt_cls:
            ConnectionHandler(config, on_state_change=on_state_change)

        influx_cls.assert_called_once_with(
            url="http://influx",
            token="token",
            org="org",
            bucket="bucket",
            port=8086,
            on_state_change=on_state_change,
        )
        mqtt_cls.assert_called_once_with(
            url="mqtt://broker",
            port=1883,
            on_state_change=on_state_change,
        )
