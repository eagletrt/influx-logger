from connections.influx_connection import InfluxConnection
from connections.mqtt_connection import MQTTConnection

class ConnectionHandler:
    """
    This class handles the connections to InfluxDB and MQTT broker.
    It provides methods to start and stop the connections, as well as to check their status.
    """
    def __init__(self, config):
        self.influx_connection = InfluxConnection(
            url=config.influx_url,
            token=config.influx_token,
            org=config.influx_org,
            bucket=config.influx_bucket,
            port=config.influx_port
        )
        self.mqtt_connection = MQTTConnection(
            broker=config.mqtt_url,
            port=config.mqtt_port
        )

    def start_connections(self):
        self.influx_connection.connect()
        self.mqtt_connection.connect()

    def stop_connections(self):
        self.influx_connection.disconnect()
        self.mqtt_connection.disconnect()

    def are_both_connected(self) -> bool:
        """
        Check if both connections are established.
        Returns:
            bool: True if both connections are established, False otherwise.
        """
        return self.influx_connection.is_connected() and self.mqtt_connection.is_connected()