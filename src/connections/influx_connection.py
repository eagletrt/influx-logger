from threading import Thread, Event
from influxdb_client import InfluxDBClient

from src.utils.logger_utils import logger
from src.connections.connection import Connection

class InfluxConnection(Connection):
    """
    This class manages the connection to an InfluxDB service.
    It extends the abstract Connection class and implements the connect method to establish a connection to InfluxDB using the provided URL, token, organizationb.
    Attributes:
        token: The authentication token for the InfluxDB service.
        org: The organization name for the InfluxDB service.
    """
    def __init__(self, url: str, token: str, org: str, port: int = 8086, on_state_change=None, buckets: list = None):
        """
        Initializes the InfluxConnection instance with the provided URL, token, organization, and port.
        Args:
            url (str): The URL of the InfluxDB service.
            token (str): The authentication token for the InfluxDB service.
            org (str): The organization name for the InfluxDB service.
            port (int, optional): The port of the InfluxDB service. Defaults to 8086.
            on_state_change (callable, optional): A callback function to be called when the connection state changes. Defaults to None.
            buckets (list, optional): A list of bucket names to be managed by the connection. Defaults to None.
        """
        super().__init__(url=url, port=port)
        self.token: str = token
        self.org: str = org
        self.connection_checker: ConnectionChecker = ConnectionChecker(self, check_interval=10)
        self.on_state_change = on_state_change
        self.buckets: list = buckets

    def __str__(self):
        return f"InfluxConnection(url={self.url}, port={self.port}, org={self.org})"

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
        Establishes a connection to the InfluxDB service using the provided URL, token and organization.
        Logs the success or failure of the connection attempt.
        Returns:
            bool: True if the connection was successful, False otherwise.
        """
        try:
            self.connection_checker.stop()  # Stop the connection checker thread if it's already running
            self.connection = InfluxDBClient(
                url=self.get_full_link(),
                token=self.token,
                org=self.org
            )
            self.connection_checker = ConnectionChecker(self, check_interval=10)  # Create a new connection checker thread
            self.connection_checker.start()  # Start the connection checker thread
            if self.is_connected():
                logger.info(f"influx-connection: Successfully connected to InfluxDB at {self.url}:{self.port}")
                return True
            else:
                logger.warning(f"influx-connection: Connection to InfluxDB at {self.connection.url} Connection not established.")
                return False
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
        return self.ping()
    
    def create_missing_bucket(self, buckets: list, needed_buckets: list = []) -> bool:
        '''
        Creates any missing buckets from the needed_buckets list that are not present in the buckets list.
        Args:
            buckets (list): A list of existing bucket names.
            needed_buckets (list, optional): A list of bucket names that are required. Defaults to [].
        Returns:
            bool: True if all needed buckets are present or created successfully, False otherwise.
        '''
        if needed_buckets is None:
            needed_buckets = []
        ok: bool = True
        for bucket in needed_buckets:
            if bucket not in buckets:
                ok = ok and self.create_bucket(bucket)
        return ok

    def create_bucket(self, bucket_name: str, retention_rules=None) -> bool:
        """
        Creates a new bucket in the InfluxDB service.
        Args:
            bucket_name (str): The name of the bucket to create.
            retention_rules (dict, optional): The retention rules for the bucket. Defaults to None.
        Returns:
            bool: True if the bucket was created successfully, False otherwise.
        """
        try:
            self.connection.buckets_api().create_bucket(
                bucket_name=bucket_name,
                retention_rules=retention_rules,
                org=self.org,
            )
            logger.info(f"influx-connection: Bucket created successfully: {bucket_name}")
            return True
        except Exception as e:
            logger.error(f"influx-connection: Failed to create bucket named {bucket_name}: {e}")
            return False

    def ping(self) -> bool:
        """
        Perform a safe ping/health check against the underlying client.

        Many InfluxDB client implementations either return a truthy value,
        return None on success, or raise on failure. Normalize that behavior
        so callers can rely on a boolean-like result (or non-None when used
        directly in tests).

        Returns:
            bool: check weather ther connection is up
        """
        try:
            # List buckets (lightweight operation)
            result = self.connection.buckets_api().find_buckets()
            # Connection is active and authenticated
            if result is not None:
                Thread(
                    target=self.create_missing_bucket,
                    kwargs={
                        "buckets": [bucket.name for bucket in result.buckets],
                        "needed_buckets": self.buckets,
                    },
                    daemon=True,
                ).start()
                return True
            else:
                logger.warning("influx-connection: Ping returned None, indicating a potential issue with the connection.")
                return False
        except Exception as e:
            # Check weather InfluxDB is up
            health_api = self.connection.health()
            if health_api.status == "pass":
                logger.warning("influx-connection: InfluxDB up, but not connected. Check your token and permissions.")
            return False

class ConnectionChecker(Thread):
    """
    A thread that periodically checks the connection status of the InfluxDB service.
    It runs in the background and logs the connection status at regular intervals.
    """
    def __init__(self, influx_connection: 'InfluxConnection', check_interval: int = 2):
        """
        Initializes the ConnectionChecker thread with a specified check interval.
        Args:
            influx_connection (InfluxConnection): The InfluxConnection instance to check.
            check_interval (int, optional): The interval (in seconds) between connection checks. Defaults to 2 seconds.
        """
        super().__init__(name="ConnectionChecker")
        self.influx_connection: InfluxConnection = influx_connection
        self.check_interval: int = check_interval
        self._stop_event: Event = Event()

    def run(self):
        """
        The main loop of the ConnectionChecker thread.
        It checks the connection status at regular intervals and logs the result.
        """
        self._stop_event.clear()
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
        try:
            self.join()  # Wait for the thread to finish
        except Exception as e:
            pass
