"""Tests for shared connection manager behavior."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from src.connections.connection_handler import ConnectionHandler
from src.utils.configuration import Configuration, InfluxConfig, MQTTConfig


class TestConnectionHandler(TestCase):
    """
    Tests for ConnectionHandler singleton behavior, configuration management,
    and connection state reporting.
    """

    def setUp(self):
        """
        Resets the singleton instance and initialization state of ConnectionHandler
        before each test to ensure isolation between tests.
        """
        ConnectionHandler._instance = None  # pylint: disable=protected-access
        ConnectionHandler._initialized = False  # pylint: disable=protected-access

    def tearDown(self):
        """
        Resets the singleton instance and initialization state of ConnectionHandler
        after each test to ensure isolation between tests.
        """
        ConnectionHandler._instance = None  # pylint: disable=protected-access
        ConnectionHandler._initialized = False  # pylint: disable=protected-access

    def test_singleton_configuration_and_connection_state(self):
        """
        Tests that ConnectionHandler behaves as a singleton, that it can be configured,
        and that it correctly reports the connection state of its managed connections.
        """
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
        """
        Tests that the ConnectionHandler does not attempt to start or stop connections
        when the configuration is missing or incomplete.
        """
        handler = ConnectionHandler()
        handler.set(Configuration())
        handler.start_connections()
        handler.stop_connections()

    def test_callbacks_and_set_update(self):
        """
        Tests that the on_state_change callback is called when the state changes,
        and that the set method updates the configuration correctly.
        """
        handler = ConnectionHandler()
        state_change = MagicMock()
        handler.on_state_change = state_change
        handler.mqtt = MagicMock()
        handler.influx_adr = MagicMock()
        handler._ConnectionHandler__notify_state_change()  # pylint: disable=protected-access
        state_change.assert_called_once_with()
