from requests import post
from threading import Thread, Event
from influxdb_client import InfluxDBClient

from src.utils.logger_utils import logger
from src.connections.connection import Connection

class InfluxConnection(Connection):
    """
    This class manages the connection to an InfluxDB service.
    It extends the abstract Connection class and implements the connect method to establish a connection to InfluxDB using the provided URL, token, organization, and bucket.
    Attributes:
        token: The authentication token for the InfluxDB service.
        org: The organization name for the InfluxDB service.
        bucket: The bucket name for the InfluxDB service.
    """
    def __init__(self, url: str, token: str, org: str, bucket: str, port: int = 8086, on_state_change=None):
        """
        Initializes the InfluxConnection instance with the provided URL, token, organization, bucket, and port.
        Args:
            url (str): The URL of the InfluxDB service.
            token (str): The authentication token for the InfluxDB service.
            org (str): The organization name for the InfluxDB service.
            bucket (str): The bucket name for the InfluxDB service.
            port (int, optional): The port of the InfluxDB service. Defaults to 8086.
            on_state_change (callable, optional): A callback function to be called when the connection state changes. Defaults to None.
        """
        super().__init__(url=url, port=port)
        self.token: str = token
        self.org: str = org
        self.bucket: str = bucket
        self.connection_checker: ConnectionChecker = ConnectionChecker(self, check_interval=10)
        self.on_state_change = on_state_change

    def __notify_state_change(self) -> None:
        if callable(self.on_state_change):
            self.on_state_change()

    def on_connect(self):
        logger.info(f"influx-connection: Successfully connected to InfluxDB at {self.url}:{self.port}")
        self.__notify_state_change()

    def on_disconnect(self):
        logger.info(f"influx-connection: Disconnected from InfluxDB at {self.url}:{self.port}")
        self.__notify_state_change()

    def disconnect(self) -> bool:
        """
        Disconnects from the InfluxDB service.
        Logs the success or failure of the disconnection attempt.
        Returns:
            bool: True if the disconnection was successful, False otherwise.
        """
        try:
            if self.connection:
                self.connection.close()
                self.connection = None
                self.connection_checker.stop()  # Stop the connection checker thread
                logger.info(f"influx-connection: Successfully disconnected from InfluxDB at {self.url}:{self.port}")
                return True
            else:
                logger.warning(f"influx-connection: No active connection to disconnect from InfluxDB at {self.url}:{self.port}")
                return False
        except Exception as e:
            logger.error(f"influx-connection: Failed to disconnect from InfluxDB at {self.url}:{self.port}: {e}")
            return False

    def connect(self) -> bool:
        """
        Establishes a connection to the InfluxDB service using the provided URL, token, organization, and bucket.
        Logs the success or failure of the connection attempt.
        Returns:
            bool: True if the connection was successful, False otherwise.
        """
        try:
            self.connection = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org,
                port=self.port
            )
            logger.info(f"influx-connection: Successfully connected to InfluxDB at {self.url}:{self.port}")
            if not self.connection_checker.is_alive():
                self.connection_checker.start()  # Start the connection checker thread
            return True
        except Exception as e:
            logger.error(f"influx-connection: Failed to connect to InfluxDB at {self.url}:{self.port}: {e}")
            return False
        
    def is_connected(self) -> bool:
        """
        Checks if the connection to the InfluxDB service is established.
        Returns:
            bool: True if the connection is established, False otherwise.
        """
        # Ensure base connection object exists first
        if not super().is_connected():
            return False

        # Use the safe ping helper which normalizes client behavior.
        try:
            return bool(self.ping())
        except Exception:
            return False

    def ping(self) -> bool:
        """
        Perform a safe ping/health check against the underlying client.

        Many InfluxDB client implementations either return a truthy value,
        return None on success, or raise on failure. Normalize that behavior
        so callers can rely on a boolean-like result (or non-None when used
        directly in tests).

        Returns:
            Any: The raw client response when available, True when the client
                 returned None but the call succeeded, or None on failure/no
                 connection.
        """
        if not self.connection:
            return False
        try:
            response = post(url=f'{self.url}:{self.port}/')
            if response.ok:
                return True
            else:
                return False
        except Exception:
            return False

class ConnectionChecker(Thread):
    """
    A thread that periodically checks the connection status of the InfluxDB service.
    It runs in the background and logs the connection status at regular intervals.
    """
    def __init__(self, influx_connection: 'InfluxConnection', check_interval: int = 10):
        """
        Initializes the ConnectionChecker thread with a specified check interval.
        Args:
            influx_connection (InfluxConnection): The InfluxConnection instance to check.
            check_interval (int, optional): The interval (in seconds) between connection checks. Defaults to 10 seconds.
        """
        super().__init__(name="ConnectionChecker", daemon=True)
        self.influx_connection = influx_connection
        self.check_interval = check_interval
        self._stop_event = Event()

    def run(self):
        """
        The main loop of the ConnectionChecker thread.
        It checks the connection status at regular intervals and logs the result.
        """
        if self.influx_connection.is_connected():
            self.influx_connection.on_connect()
        while not self._stop_event.is_set():
            if not self.influx_connection.is_connected():
                self._stop_event.set()
            self._stop_event.wait(self.check_interval)
        self.influx_connection.on_disconnect()

    def stop(self):
        """
        Stops the ConnectionChecker thread gracefully.
        """
        self._stop_event.set()
