import paho.mqtt.client as mqtt

from src.connections.connection import Connection
from src.utils.logger_utils import logger

class MQTTConnection(Connection):
    """
    This class manages the connection to an MQTT broker.
    It extends the abstract Connection class and implements the connect method to establish a connection to the MQTT broker using the provided URL and port.
    Attributes:
        broker: The URL of the MQTT broker to connect to.
        port: The port of the MQTT broker to connect to.
    """
    def __init__(self, url: str, port: int = 1883, on_state_change=None):
        super().__init__(url=url, port=port)
        self.on_state_change = on_state_change

    def __notify_state_change(self) -> None:
        if callable(self.on_state_change):
            self.on_state_change()

    def on_connect(self, client, _userdata, _flags, reason_code, properties=None):
        logger.info(f"mqtt-connection: Successfully connected to MQTT broker at {self.url}:{self.port}")
        self.__notify_state_change()

    def on_disconnect(self, client, _userdata, reason_code, properties=None):
        logger.info(f"mqtt-connection: Disconnected from MQTT broker at {self.url}:{self.port} with reason code {reason_code}")
        self.__notify_state_change()

    def connect(self) -> bool:
        """
        Establishes a connection to the MQTT broker using the provided URL and port.
        Logs the success or failure of the connection attempt.
        Returns:
            bool: True if the connection was successful, False otherwise.
        """
        try:
            self.connection = mqtt.Client()
            self.connection.on_connect = self.on_connect
            self.connection.on_disconnect = self.on_disconnect
            self.connection.connect(self.url, self.port)
            self.connection.loop_start()
            logger.info(f"mqtt-connection: Successfully connected to MQTT broker at {self.url}:{self.port}")
            return True
        except Exception as e:
            self.connection = None
            logger.error(f"mqtt-connection: Failed to connect to MQTT broker at {self.url}:{self.port}: {e}")
            return False
        
    def disconnect(self) -> bool:
        """
        Disconnects from the MQTT broker.
        Logs the success or failure of the disconnection attempt.
        Returns:
            bool: True if the disconnection was successful, False otherwise.
        """
        try:
            if self.connection:
                self.connection.loop_stop()
                self.connection.disconnect()
                self.connection = None
                return True
        except Exception as e:
            logger.error(f"mqtt-connection: Failed to disconnect from MQTT broker at {self.url}:{self.port}: {e}")
            return False
        
    def is_connected(self) -> bool:
        """
        Checks if the connection to the MQTT broker is established.
        Returns:
            bool: True if the connection is established, False otherwise.
        """
        if not super().is_connected():
            return False
        # Ping the broker to check if the connection is still alive
        try:
            self.connection.loop_read()
            return True
        except Exception as e:
            logger.warn(f"mqtt-connection: Connection to MQTT broker at {self.url}:{self.port} is not alive: {e}")
            return False
