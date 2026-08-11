import paho.mqtt.client as mqtt

from src.utils.logger_utils import logger
from src.connections.connection import Connection

class MQTTConnection(Connection):
    """
    This class manages the connection to an MQTT broker.
    It extends the abstract Connection class and implements the connect method to establish a connection to the MQTT broker using the provided URL and port.
    Attributes:
        broker: The URL of the MQTT broker to connect to.
        port: The port of the MQTT broker to connect to.
    """
    def __init__(self, url: str, port: int = 1883, username: str = None, password: str = None, on_state_change=None, on_message=None):
        super().__init__(url=url, port=port)
        self.username = username
        self.password = password
        self.on_state_change = on_state_change
        self.message_callback = on_message

    def __notify_state_change(self) -> None:
        if callable(self.on_state_change):
            self.on_state_change()

    def on_connect(self, client, _userdata, _flags, reason_code, properties=None) -> None:
        logger.info(f"mqtt-connection: Successfully connected to MQTT broker at {self.url}:{self.port}")
        self.__notify_state_change()

    def on_disconnect(self, client, _userdata, reason_code, properties=None) -> None:
        logger.info(f"mqtt-connection: Disconnected from MQTT broker at {self.url}:{self.port} with reason code {reason_code}")
        self.connection = None
        self.__notify_state_change()

    def on_message(self, client, _userdata, msg) -> None:
        logger.debug(f"mqtt-connection: Received message on topic {msg.topic} with payload {msg.payload}")
        try:
            if callable(self.message_callback):
                self.message_callback(msg.topic, msg.payload)
        except Exception as e:
            logger.error(f"mqtt-connection: Error while handling incoming message on topic {msg.topic}: {e}")

    def connect(self) -> bool:
        """
        Establishes a connection to the MQTT broker using the provided URL and port.
        Logs the success or failure of the connection attempt.
        Returns:
            bool: True if the connection was successful, False otherwise.
        """
        try:
            self.connection = mqtt.Client()
            if self.username and self.password:
                self.connection.username_pw_set(self.username, self.password)
                self.connection.tls_set()  # Enable TLS for secure connection
            self.connection.on_connect = self.on_connect
            self.connection.on_disconnect = self.on_disconnect
            self.connection.on_message = self.on_message
            self.connection.connect(host=self.url, port=self.port)
            #self.connection.subscribe("+/+/version")
            self.connection.subscribe("+/+/info/version/libcan")
            self.connection.subscribe("+/+/info/version/gpslib")
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
            logger.warning(f"mqtt-connection: Connection to MQTT broker at {self.url}:{self.port} is not alive: {e}")
            return False
