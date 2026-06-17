import influxdb_client
from logger_utils import logger

from connections.connection import Connection

class InfluxConnection(Connection):
    def __init__(self, url, token, org, bucket, port:int = 8086):
        super().__init__(url=url, port=port)
        self.token: str = token
        self.org: str = org
        self.bucket: str = bucket

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
