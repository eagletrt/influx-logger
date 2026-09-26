"""
This module contains the ConnectionHandler class, which is responsible for managing
connections to InfluxDB and MQTT broker. It provides methods to start and stop
connections, as well as to check the connection status of both InfluxDB and MQTT broker.
The ConnectionHandler class is implemented as a singleton to ensure that only one
instance of the connection handler exists throughout the application.
Classes:
    ConnectionHandler: A singleton class to manage InfluxDB and MQTT connections.
"""
from src.connections.influx_connection import InfluxConnection
from src.connections.mqtt_connection import MQTTConnection
from src.utils.configuration import Configuration
from src.utils.logger_utils import logger


class ConnectionHandler:
    """
    Singleton class to manage InfluxDB and MQTT connections.
    This class ensures that only one instance of the connection
    handler exists throughout the application.
    It provides methods to start and stop connections,
    as well as to check the connection status of both InfluxDB
    and MQTT broker.
    Attributes:
        influx_connection: An instance of the InfluxConnection class.
        mqtt_connection: An instance of the MQTTConnection class.
    """
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self,
                 config: Configuration = None,
                 on_state_change=None,
                 on_message=None):
        if self._initialized:
            return
        self.on_state_change = on_state_change
        if config:
            self.set(config,
                     on_state_change=on_state_change,
                     on_message=on_message)
        self._initialized = True

    def set(self,
            config: Configuration = None,
            on_state_change=None,
            on_message=None) -> None:
        """
        Set the configuration for InfluxDB and MQTT connections.
        This method allows updating the connection settings after
        the ConnectionHandler instance has been created.
        Args:
            config (Configuration): Configuration to set.
        """
        if on_state_change is not None:
            self.on_state_change = on_state_change
        if on_message is not None:
            self.on_message = on_message
        self.influx_adr = InfluxConnection(
            url=config.influx.url,
            token=config.influx.token,
            org=config.influx.org,
            port=config.influx.port,
            on_state_change=self.on_state_change,
            buckets=list(config.influx.buckets.values()
                         )) if config and config.influx else None
        self.mqtt = MQTTConnection(
            url=config.mqtt.url,
            port=config.mqtt.port,
            username=config.mqtt.username,
            password=config.mqtt.password,
            on_state_change=self.on_state_change,
            on_message=on_message,
        ) if config and config.mqtt else None

    def start_connections(self) -> None:
        """
        Start both InfluxDB and MQTT connections.
        If either connection is not configured,
        it will log an error message and return without attempting
        to connect.
        """
        if not self.influx_adr or not self.mqtt:
            logger.error(
                "No connections to start. " \
                    "Please provide a valid configuration."
            )
            return
        if not self.influx_adr.is_connected():
            self.influx_adr.connect()
        if not self.mqtt.is_connected():
            self.mqtt.connect()
        self.__notify_state_change()

    def stop_connections(self) -> None:
        """
        Stop both InfluxDB and MQTT connections.
        If either connection is not configured,
        it will log an error message and return without attempting
        to disconnect.
        """
        if not self.influx_adr and not self.mqtt:
            logger.error(
                "No connections to stop. " \
                    "Please provide a valid configuration."
            )
            return
        self.influx_adr.disconnect()
        self.mqtt.disconnect()
        self.__notify_state_change()

    def are_both_connected(self) -> bool:
        """
        Check if both connections are established.
        Returns:
            bool: True if both connections are established, False otherwise.
        """
        return bool(self.influx_adr and self.mqtt
                    and self.influx_adr.is_connected()
                    and self.mqtt.is_connected())

    def __notify_state_change(self) -> None:
        if callable(self.on_state_change):
            self.on_state_change()
