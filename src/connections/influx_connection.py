import influxdb_client

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
    def __init__(self, url: str, token: str, org: str, bucket: str, port: int = 8086):
        super().__init__(url=url, port=port)
        self.token: str = token
        self.org: str = org
        self.bucket: str = bucket

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
            self.connection = influxdb_client.InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org,
                port=self.port
            )
            logger.info(f"influx-connection: Successfully connected to InfluxDB at {self.url}:{self.port}")
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

    def ping(self):
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
            return None

        # Prefer a direct ping() method if available
        ping_fn = getattr(self.connection, 'ping', None)
        try:
            if callable(ping_fn):
                ping_fn()
                return True

            # Fall back to a health() method if present
            health_fn = getattr(self.connection, 'health', None)
            if callable(health_fn):
                health_fn()
                return True
        except Exception:
            return None
