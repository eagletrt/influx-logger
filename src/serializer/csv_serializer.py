import csv
import gzip
import hashlib
import io

from src.serializer.query_protocol import QueryCompression, QueryFormat

EXCLUDED_COLUMNS: tuple[str, ...] = (
    "result",
    "table",
    "network",
    "antenna_name",
    "vehicle-id",
    "device-id",
    "vehicle_id",
    "device_id",
)
'''Columns carried by the Flux result that must not end up in the CSV.'''

TIMESTAMP_COLUMN: str = "_timestamp"
'''Name of the timestamp column written as the first field of every CSV.'''

class SerializedChunk:
    '''
    The outcome of serializing one Flux table.

    Attributes:
        payload (bytes): The chunk body, ready to be published.
        rows (int): Number of data rows, the header excluded.
        digest (str): Hexadecimal sha256 of the payload, published in the chunk manifest.
    '''
    def __init__(self, payload: bytes, rows: int) -> None:
        self.payload: bytes = payload
        self.rows: int = rows
        self.digest: str = hashlib.sha256(payload).hexdigest()

class CsvSerializer:
    '''
    Turns a Flux table into a gzip compressed CSV chunk.

    Serialization is kept separate from both the query and the transport so a different
    format can be added later by implementing the same two methods, without touching
    the reader: only 'describe' and 'serialize' are used by InfluxReader.
    '''
    format: QueryFormat = QueryFormat.QUERY_FORMAT_CSV
    '''Format advertised in the chunk manifest.'''
    compression: QueryCompression = QueryCompression.QUERY_COMPRESSION_GZIP
    '''Compression advertised in the chunk manifest.'''

    @staticmethod
    def describe(records: list) -> tuple[str, str]:
        '''
        Extracts the network and measurement names identifying a table.

        Args:
            records (list): The records of a single Flux table, never empty.
        Returns:
            tuple[str, str]: The network name and the measurement name.
        '''
        network_name = records[0].values.get("network", "unknown")
        measurement_name = records[0].values.get("_measurement", "unknown")
        antenna = records[0].values.get("antenna_name")
        if antenna:
            network_name = antenna
            measurement_name = f"{antenna}_{measurement_name}"
        return network_name, measurement_name

    @staticmethod
    def _columns(records: list) -> list[str]:
        '''
        Collects the data columns of a table, in a stable order so the header does not
        depend on the iteration order of the records.

        Args:
            records (list): The records of a single Flux table.
        Returns:
            list[str]: The column names, with the timestamp column first.
        '''
        columns: set[str] = set()
        for record in records:
            for key in record.values.keys():
                clean_key = key.strip().lower()
                if not clean_key.startswith("_") and clean_key not in EXCLUDED_COLUMNS:
                    columns.add(clean_key)
        columns.discard("timestamp")
        return [TIMESTAMP_COLUMN] + sorted(columns)

    @staticmethod
    def _timestamp_of(record) -> int:
        '''
        Normalizes the timestamp of a record to microseconds.

        Args:
            record: A single Flux record.
        Returns:
            int: The timestamp in microseconds, or None when the record carries none.
        '''
        value = record.values.get("timestamp")
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return int(value / 1000)
        if hasattr(value, "timestamp"):
            return int(value.timestamp()) * 1_000_000 + value.microsecond
        return 0

    def serialize(self, records: list) -> SerializedChunk:
        '''
        Serializes a whole Flux table into a compressed CSV chunk.

        Args:
            records (list): The records of a single Flux table.
        Returns:
            SerializedChunk: The compressed payload, its row count and its digest.
        '''
        columns = self._columns(records)
        data_columns = set(columns[1:])
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        rows = 0
        for record in records:
            row = {}
            timestamp = self._timestamp_of(record)
            if timestamp is not None:
                row[TIMESTAMP_COLUMN] = timestamp
            for key, value in record.values.items():
                clean_key = key.strip().lower()
                if clean_key in data_columns and value is not None and value != "":
                    row[clean_key] = value
            writer.writerow(row)
            rows += 1
        # mtime is pinned so the same records always produce the same bytes, which keeps
        # the digest published in the manifest comparable across retries.
        payload = gzip.compress(buffer.getvalue().encode("utf-8"), mtime=0)
        return SerializedChunk(payload=payload, rows=rows)

__all__ = ["CsvSerializer", "SerializedChunk", "EXCLUDED_COLUMNS", "TIMESTAMP_COLUMN"]
