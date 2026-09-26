"""
This module defines the MQTTConnection class, 
which manages the connection to an MQTT broker.
"""

import threading

import paho.mqtt.client as mqtt

from src.connections.connection import Connection
from src.utils.logger_utils import logger


class MQTTConnection(Connection):
    """
    This class manages the connection to an MQTT broker.
    It extends the abstract Connection class and implements 
    the connect method to establish a connection to the MQTT 
    broker using the provided URL and port.
    Attributes:
        broker: The URL of the MQTT broker to connect to.
        port: The port of the MQTT broker to connect to.
    """

    def __init__(self,
                 url: str,
                 port: int = 1883,
                 username: str = None,
                 password: str = None,
                 on_state_change=None,
                 on_message=None):
        super().__init__(url=url, port=port)
        self.username = username
        self.password = password
        self.on_state_change = on_state_change
        self.message_callback = on_message
        self._connected = False
        self._connecting = False
        # Lock to synchronize access to the connection state and the underlying MQTT client.
        self._lock = threading.RLock()

    def __notify_state_change(self) -> None:
        if callable(self.on_state_change):
            self.on_state_change()

    def on_connect(self,
                   client,
                   _userdata,
                   _flags,
                   reason_code,
                   properties=None) -> None:
        """
        Callback function that is called when the
        client receives a CONNACK response from the server.
        It checks the reason code to determine if
        the connection was successful or not.
        If the connection was successful, it sets
        the _connected flag to True and subscribes to the necessary topics.
        If the connection was not successful, it
        logs an error message and sets the _connected flag to False.
        """
        with self._lock:
            # Ignore callbacks from a client instance we've already replaced/torn down.
            if client is not self.connection:
                logger.debug(
                    "mqtt-connection: Ignoring on_connect from stale client at %s:%d",
                    self.url, self.port)
                return
            try:
                success = int(reason_code) == 0
            except Exception:  # pylint: disable=broad-except
                success = not reason_code

            if not success:
                self._connecting = False
                self._connected = False
                logger.error(
                    "mqtt-connection: MQTT broker at %s:%d rejected the " \
                        "connection with reason code %d",
                    self.url,
                    self.port,
                    reason_code
                )
                self.__notify_state_change()
                return

            logger.info(
                "mqtt-connection: Successfully connected to MQTT broker at %s:%d",
                self.url, self.port)
            self._connected = True
            self._connecting = False
            self.__subscribe_topics()
        self.__notify_state_change()

    def on_disconnect(self,
                      client,
                      _userdata,
                      reason_code,
                      properties=None) -> None:
        """
        Callback function that is called when the client disconnects from the server.
        It logs the disconnection event and sets the _connected flag to False.
        """
        with self._lock:
            # Ignore callbacks from a client instance we've already replaced/torn down.
            if client is not self.connection:
                logger.debug(
                    "mqtt-connection: Ignoring on_disconnect from stale client at %s:%d",
                    self.url, self.port)
                return
            logger.info(
                "mqtt-connection: Disconnected from MQTT broker at %s:%d with reason code %d",
                self.url, self.port, reason_code)
            self.connection = None
            self._connecting = False
            self._connected = False
        self.__notify_state_change()

    def __subscribe_topics(self) -> None:
        if not self.connection:
            return
        #self.connection.subscribe("+/+/version")
        self.connection.subscribe("+/+/info/version/libcan")
        self.connection.subscribe("+/+/info/version/gpslib")

    def on_message(self, client, _userdata, msg) -> None:
        """
        Callback function that is called when a message is received from the server.
        It logs the received message and invokes the message callback if provided.
        """
        logger.debug(
            "mqtt-connection: Received message on topic %s with payload %s",
            msg.topic, msg.payload)
        try:
            if callable(self.message_callback):
                self.message_callback(msg.topic, msg.payload)
        except Exception as e:  # pylint: disable=broad-except
            logger.error(
                "mqtt-connection: Error while handling incoming message on topic %s: %s",
                msg.topic, e)

    def connect(self) -> bool:
        """
        Establishes a connection to the MQTT broker using the provided URL and port.
        Logs the success or failure of the connection attempt.
        Returns:
            bool: True if the connection was successful, False otherwise.
        """
        with self._lock:
            if self._connected or self._connecting:
                # A connection attempt is already live/settling - never spin up
                # a second client on top of it.
                return True
            # Defensively tear down any leftover client before creating a new one.
            if self.connection is not None:
                try:
                    self.connection.loop_stop()
                    self.connection.disconnect()
                except Exception:  # pylint: disable=broad-except
                    pass
                self.connection = None
            try:
                self.connection = mqtt.Client()
                self._connecting = True
                self.connection.enable_logger(logger)
                if self.username and self.password:
                    self.connection.username_pw_set(self.username,
                                                    self.password)
                    self.connection.tls_set(
                    )  # Enable TLS for secure connection
                self.connection.on_connect = self.on_connect
                self.connection.on_disconnect = self.on_disconnect
                self.connection.on_message = self.on_message
                logger.info(
                    "mqtt-connection: Attempting to connect to MQTT broker at %s:%d",
                    self.url, self.port)
                self.connection.connect(host=self.url, port=self.port)
                self.connection.loop_start()
                logger.info(
                    "mqtt-connection: Connection attempt to MQTT broker at %s:%d initiated",
                    self.url, self.port)
            except Exception as e:  # pylint: disable=broad-except
                self.connection = None
                self._connecting = False
                self._connected = False
                logger.error(
                    "mqtt-connection: Failed to connect to MQTT broker at %s:%d: %s",
                    self.url, self.port, e)
                return False
        return self.is_connected()

    def disconnect(self) -> bool:
        """
        Disconnects from the MQTT broker.
        Logs the success or failure of the disconnection attempt.
        Returns:
            bool: True if the disconnection was successful, False otherwise.
        """
        with self._lock:
            try:
                if self.connection:
                    self._connecting = False
                    self.connection.loop_stop()
                    self._connected = False
                    self.connection.disconnect()
                    self.connection = None
                return True
            except Exception as e:  # pylint: disable=broad-except
                logger.error(
                    "mqtt-connection: Failed to disconnect from MQTT broker at %s:%d: %s",
                    self.url, self.port, e)
                return False

    def is_connected(self) -> bool:
        """
        Checks if the connection to the MQTT broker is established.
        Returns:
            bool: True if the connection is established, False otherwise.
        """
        with self._lock:
            connected: bool = super().is_connected() and self._connected
            if not connected or self.connection is None:
                return False
            # Ping the broker to check if the connection is still alive. Do this
            # outside the lock: is_connected() on the paho client is cheap/local,
            # but we avoid holding our lock while calling into paho at all.
            try:
                return bool(self.connection.is_connected())
            except Exception as e:  # pylint: disable=broad-except
                logger.warning(
                    "mqtt-connection: Connection to MQTT broker at %s:%d is not alive: %s",
                    self.url, self.port, str(e))
                return False
