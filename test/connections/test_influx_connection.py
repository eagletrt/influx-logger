import unittest

from time import sleep
from src.connections.influx_connection import InfluxConnection
from src.utils.configuration import Configuration

class TestInfluxConnection(unittest.TestCase):

    def setUp(self):
        config: Configuration = Configuration.load_from_file()
        self.connection = InfluxConnection(
            url=config.influx_url,
            port=config.influx_port,
            token=config.influx_token,
            org=config.influx_org,
            bucket=config.influx_bucket
        )

    def test_connect(self):
        if not self.connection.connect():
            self.skipTest("Could not establish connection to InfluxDB. Skipping test.")
        assert self.connection.is_connected()  # Verify that the connection is established after connecting

    def test_disconnect(self):
        self.connection.connect()  # Establish a connection first
        if self.connection.is_connected():
            self.connection.disconnect()
        sleep(2)
        assert not self.connection.is_connected()  # Verify that the connection is no longer active after disconnecting

    def test_is_connected(self):
        if self.connection.connect():
            assert self.connection.is_connected()
        self.connection.disconnect()  # Clean up by disconnecting
        sleep(2)
        assert not self.connection.is_connected()  # Verify that the connection is no longer active after disconnecting
