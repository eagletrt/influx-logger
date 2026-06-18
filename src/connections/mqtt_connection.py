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

    def connect(self) -> bool:
        """
        Establishes a connection to the MQTT broker using the provided URL and port.
        Logs the success or failure of the connection attempt.
        Returns:
            bool: True if the connection was successful, False otherwise.
        """
        try:
            import paho.mqtt.client as mqtt
            self.connection = mqtt.Client()
            self.connection.connect(self.url, self.port)
            logger.info(f"mqtt-connection: Successfully connected to MQTT broker at {self.url}:{self.port}")
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
                logger.info(f"mqtt-connection: Successfully disconnected from MQTT broker at {self.url}:{self.port}")
                return True
            else:
                logger.warning(f"mqtt-connection: No active connection to disconnect from MQTT broker at {self.url}:{self.port}")
                return False
        except Exception as e:
            logger.error(f"mqtt-connection: Failed to disconnect from MQTT broker at {self.url}:{self.port}: {e}")
            return False
        
    def is_connected(self) -> bool:
        """
        Checks if the connection to the MQTT broker is established.
        Returns:
            bool: True if the connection is established, False otherwise.
        """
        return super().is_connected() and self.connection.is_connected()
