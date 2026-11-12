"""Tests for shared connection manager behavior."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from src.connections.connection_handler import ConnectionHandler
from src.utils.configuration import Configuration, InfluxConfig, MQTTConfig


class TestConnectionHandler(TestCase):

    def setUp(self):
        ConnectionHandler._instance = None
        ConnectionHandler._initialized = False

    def tearDown(self):
        ConnectionHandler._instance = None
        ConnectionHandler._initialized = False

    def test_singleton_configuration_and_connection_state(self):
        config = Configuration(mqtt=MQTTConfig("broker", 1883),
                               influx=InfluxConfig("db", 8086, "t", "o",
                                                   {"adr": "a"}))
        with patch("src.connections.connection_handler.InfluxConnection") as influx_cls, \
                patch("src.connections.connection_handler.MQTTConnection") as mqtt_cls:
            first = ConnectionHandler(config)
            second = ConnectionHandler()
        self.assertIs(first, second)
        influx, mqtt = influx_cls.return_value, mqtt_cls.return_value
        influx.is_connected.return_value = False
        mqtt.is_connected.return_value = False
        self.assertFalse(first.are_both_connected())
        influx.is_connected.return_value = True
        mqtt.is_connected.return_value = True
        self.assertTrue(first.are_both_connected())
        influx.is_connected.return_value = False
        mqtt.is_connected.return_value = False
        first.start_connections()
        influx.connect.assert_called_once_with()
        mqtt.connect.assert_called_once_with()
        first.stop_connections()
        influx.disconnect.assert_called_once_with()
        mqtt.disconnect.assert_called_once_with()

    def test_missing_configuration_returns_early(self):
        handler = ConnectionHandler()
        handler.set(Configuration())
        handler.start_connections()
        handler.stop_connections()

    def test_callbacks_and_set_update(self):
        handler = ConnectionHandler()
        state_change = MagicMock()
        handler.on_state_change = state_change
        handler.mqtt = MagicMock()
        handler.influx_adr = MagicMock()
        handler._ConnectionHandler__notify_state_change()
        state_change.assert_called_once_with()
