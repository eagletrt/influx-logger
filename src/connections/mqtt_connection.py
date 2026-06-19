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
    def __init__(self, url: str, port: int = 1883):
        super().__init__(url=url, port=port)
        self.connected = False

    def on_connect(self, client, _userdata, _flags, reason_code, properties=None):
        logger.info(f"mqtt-connection: Successfully connected to MQTT broker at {self.url}:{self.port}")
        self.connected = True

    def on_disconnect(self, client, _userdata, reason_code, properties=None):
        logger.info(f"mqtt-connection: Disconnected from MQTT broker at {self.url}:{self.port} with reason code {reason_code}")
        self.connected = False

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
            self.on_connect(self.connection, None, None, 0)  # Manually trigger the on_connect callback to update the connection state
            return True
        except Exception as e:
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
                self.connection.disconnect()
                self.connection = None
                self.on_disconnect(None, None, 0)  # Manually trigger the on_disconnect callback to update the connection state
                logger.info(f"mqtt-connection: Successfully disconnected from MQTT broker at {self.url}:{self.port}")
                return True
        except Exception as e:
            logger.error(f"mqtt-connection: Failed to disconnect from MQTT broker at {self.url}:{self.port}: {e}")
            self.connected = False
            return False
        
    def is_connected(self) -> bool:
        """
        Checks if the connection to the MQTT broker is established.
        Returns:
            bool: True if the connection is established, False otherwise.
        """
        print(f"[{self.connected}]")
        return super().is_connected() and self.connected
