from unittest import TestCase
from src.connections.mqtt_connection import MQTTConnection
from src.utils.configuration import Configuration

class TestMQTTConnection(TestCase):
    def setUp(self):
        config: Configuration = Configuration.load_from_file()
        self.connection = MQTTConnection(
            url=config.mqtt_url,
            port=config.mqtt_port
        )

    def test_connect(self) -> bool:
        self.connection.connect()
        assert self.connection.is_connected()  # Verify that the connection is established after connecting
        
    def test_disconnect(self) -> bool:
        self.connection.connect()  # Establish a connection first
        if self.connection.is_connected():
            self.connection.disconnect()
        assert not self.connection.is_connected()  # Verify that the connection is no longer active after disconnecting
        
    def test_is_connected(self) -> bool:
        if self.connection.connect():
            assert self.connection.is_connected()
        self.connection.disconnect()  # Clean up by disconnecting
        assert not self.connection.is_connected()  # Verify that the connection is no longer active after disconnecting
