from src.connections.influx_connection import InfluxConnection
from src.connections.mqtt_connection import MQTTConnection
from src.utils.configuration import Configuration
from src.utils.logger_utils import logger


class ConnectionHandler:
    """
    Singleton class to manage InfluxDB and MQTT connections.
    This class ensures that only one instance of the connection handler exists throughout the application.
    It provides methods to start and stop connections, as well as to check the connection status of both InfluxDB and MQTT broker.
    Attributes:
        influx_connection: An instance of the InfluxConnection class to manage the InfluxDB connection
        mqtt_connection: An instance of the MQTTConnection class to manage the MQTT broker connection
    """
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ConnectionHandler, cls).__new__(cls)
        return cls._instance

    def __init__(self, config: Configuration = None):
        if self._initialized:
            return
        self.set(config) if config else None
        self._initialized = True

    def set(self, config: Configuration = None) -> None:
        """
        Set the configuration for InfluxDB and MQTT connections.
        This method allows updating the connection settings after the ConnectionHandler instance has been created.
        Args:
            config (Configuration): An instance of the Configuration class containing the new connection settings.
        """
        self.influx_connection = InfluxConnection(
            url=config.influx_url,
            token=config.influx_token,
            org=config.influx_org,
            bucket=config.influx_bucket,
            port=config.influx_port
        ) if config else None
        self.mqtt_connection = MQTTConnection(
            url=config.mqtt_url,
            port=config.mqtt_port
        ) if config else None

    def start_connections(self) -> None:
        """
        Start both InfluxDB and MQTT connections.
        If either connection is not configured, it will log an error message and return without attempting to connect.
        """
        if not self.influx_connection and not self.mqtt_connection:
            logger.error("No connections to start. Please provide a valid configuration.")
            return
        self.influx_connection.connect()
        self.mqtt_connection.connect()

    def stop_connections(self) -> None:
        """
        Stop both InfluxDB and MQTT connections.
        If either connection is not configured, it will log an error message and return without attempting to disconnect.
        """
        if not self.influx_connection and not self.mqtt_connection:
            logger.error("No connections to stop. Please provide a valid configuration.")
            return
        self.influx_connection.disconnect()
        self.mqtt_connection.disconnect()

    def are_both_connected(self) -> bool:
        """
        Check if both connections are established.
        Returns:
            bool: True if both connections are established, False otherwise.
        """
        return self.influx_connection and self.mqtt_connection and self.influx_connection.is_connected() and self.mqtt_connection.is_connected()
