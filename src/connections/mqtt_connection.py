from src.connections.connection import Connection

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
            return True
        except Exception as e:
            print(f"mqtt-connection: Failed to connect to MQTT broker at {self.url}:{self.port}: {e}")
            return False
