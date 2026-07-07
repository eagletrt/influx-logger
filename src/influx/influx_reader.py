from src.influx.influx_manager import InfluxManager

class InfluxReader(InfluxManager):
    """
    A reader for interacting with InfluxDB.
    """
    def __init__(self, client:InfluxConnection, timestamp_precision:TimestampPrecision = TimestampPrecision.ns) -> None:
        super().__init__(client, timestamp_precision)
        self.query_api = self.client.connection.query_api()