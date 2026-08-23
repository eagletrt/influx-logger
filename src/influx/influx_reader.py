from queue import Queue, Empty, Full

from src.utils.logger_utils import logger
from src.utils.timestamp import TimestampPrecision
from src.influx.influx_manager import InfluxManager
from src.connections.influx_connection import InfluxConnection
from src.connections.mqtt_connection import MQTTConnection
from src.serializer.csv_serializer import CsvSerializer
from src.serializer.query_publisher import QueryPublisher
from src.serializer.query_protocol import (
    STAGE_PUBLISH,
    STAGE_QUERY,
    STAGE_REQUEST,
    STAGE_SERIALIZATION,
    QueryChunkInfo,
    QueryError,
    QueryRequest,
    QueryRequestError,
    classify_influx_error,
    escape_flux_string,
    parse_query_request,
)

class InfluxReader(InfluxManager):
    """
    A reader for interacting with InfluxDB. Handles incoming query requests,
    fetches data, formats it as CSV, and publishes it back over MQTT.

    Every request is answered on the status topic of its transaction: accepted when it is
    queued, running when it starts, and either completed with the manifest of the published
    chunks or failed with the error code and the stage the failure belongs to. A request
    that is refused before reaching the queue is answered too, so a requester never has to
    rely on a timeout to notice that nothing is coming.

    Attributes:
        mqtt (MQTTConnection): The connection used to publish results and statuses.
        log_bucket (str): The bucket queries are run against.
        query_queue (Queue): Pending requests, bounded to push back instead of growing forever.
        serializer (CsvSerializer): Turns Flux tables into chunk payloads.
        max_range_us (int): Maximum accepted time range in microseconds, 0 to disable the check.
        max_rows (int): Maximum rows returned per measurement, 0 to disable the limit.
        legacy_topics (bool): Whether to also publish the pre-protocol eof and error topics.
    """
    def __init__(
        self,
        client: InfluxConnection,
        mqtt_client: MQTTConnection,
        log_bucket: str,
        timestamp_precision: str = TimestampPrecision.us.name,
        max_queue_size: int = 32,
        max_range_us: int = 0,
        max_rows: int = 0,
        legacy_topics: bool = True,
    ) -> None:
        super().__init__(client, timestamp_precision, name="InfluxReader")
        self.query_api = self.client.connection.query_api()
        self.mqtt: MQTTConnection = mqtt_client
        self.log_bucket: str = log_bucket
        self.query_queue: Queue = Queue(maxsize=max_queue_size)
        self.serializer: CsvSerializer = CsvSerializer()
        self.max_range_us: int = max_range_us
        self.max_rows: int = max_rows
        self.legacy_topics: bool = legacy_topics

    def publisher(self, vehicle_id: str, device_id: str, transaction_id: str) -> QueryPublisher:
        '''
        Builds the publisher answering a given transaction.

        Args:
            vehicle_id (str): The vehicle the request came from.
            device_id (str): The device the request came from.
            transaction_id (str): The transaction to answer.
        Returns:
            QueryPublisher: The publisher bound to that transaction.
        '''
        return QueryPublisher(
            self.mqtt, vehicle_id, device_id, transaction_id, legacy_topics=self.legacy_topics
        )

    def add_query_to_queue(self, vehicle_id: str, device_id: str, transaction_id: str, payload: bytes) -> bool:
        '''
        Enqueues a query request for asynchronous processing, telling the requester whether
        it was taken in charge.

        Args:
            vehicle_id (str): The vehicle the request came from.
            device_id (str): The device the request came from.
            transaction_id (str): The transaction the request belongs to.
            payload (bytes): The raw request payload.
        Returns:
            bool: True if the request was queued, False if it was refused.
        '''
        publisher = self.publisher(vehicle_id, device_id, transaction_id)
        if self.stopped():
            publisher.publish_failure(
                QueryError.QUERY_ERROR_UNAVAILABLE, STAGE_REQUEST, "InfluxReader is shutting down"
            )
            return False
        try:
            self.query_queue.put_nowait((vehicle_id, device_id, transaction_id, payload))
        except Full:
            publisher.publish_failure(
                QueryError.QUERY_ERROR_UNAVAILABLE,
                STAGE_REQUEST,
                f"query queue is full ({self.query_queue.maxsize} requests pending)",
            )
            return False
        publisher.publish_accepted()
        return True

    def run(self) -> None:
        logger.info("InfluxReader: Thread started for query processing.")
        while not self.stopped():
            try:
                # Timeout di 1 secondo per non bloccare il controllo di self.stopped()
                vehicle_id, device_id, transaction_id, payload = self.query_queue.get(timeout=1.0)
            except Empty:
                continue
            try:
                self._process_query(vehicle_id, device_id, transaction_id, payload)
            except Exception as e:
                # _process_query reports its own failures: reaching this point means the
                # reporting itself failed, so there is nothing left to publish.
                logger.error(f"InfluxReader: Error in main loop: {e}", exc_info=True)
        self._drain_queue()

    def graceful_stop(self) -> None:
        '''
        Stops the reader letting the in flight query finish. The requests still queued are
        refused explicitly by run(), so nobody is left waiting for a result that will never come.
        '''
        self.stop()

    def _drain_queue(self) -> None:
        '''Refuses every request still queued when the reader stops.'''
        while True:
            try:
                vehicle_id, device_id, transaction_id, _payload = self.query_queue.get_nowait()
            except Empty:
                return
            logger.warning(f"InfluxReader: Query {transaction_id} dropped, the reader is stopping.")
            self.publisher(vehicle_id, device_id, transaction_id).publish_failure(
                QueryError.QUERY_ERROR_UNAVAILABLE, STAGE_REQUEST, "InfluxReader stopped before running the query"
            )

    def _build_flux_query(self, vehicle_id: str, device_id: str, request: QueryRequest) -> str:
        '''
        Builds the Flux query for a request. Every interpolated value is escaped: vehicle and
        device ids come straight from the MQTT topic and are not trusted input.

        Args:
            vehicle_id (str): The vehicle to filter on.
            device_id (str): The device to filter on.
            request (QueryRequest): The validated request.
        Returns:
            str: The Flux query to run.
        '''
        start_ns = request.start * 1000
        stop_ns = request.stop * 1000
        filters = ""
        if request.networks:
            networks = " or ".join(f'r["network"] == "{escape_flux_string(network)}"' for network in request.networks)
            filters += f"\n                |> filter(fn: (r) => {networks})"
        if request.measurements:
            measurements = " or ".join(
                f'r["_measurement"] == "{escape_flux_string(measurement)}"' for measurement in request.measurements
            )
            filters += f"\n                |> filter(fn: (r) => {measurements})"
        max_rows = request.maxRows if request.maxRows > 0 else self.max_rows
        limit = f"\n                |> limit(n: {int(max_rows)})" if max_rows > 0 else ""
        return f'''
                from(bucket: "{escape_flux_string(self.log_bucket)}")
                |> range(start: time(v: {start_ns}), stop: time(v: {stop_ns}))
                |> filter(fn: (r) => r["vehicle-id"] == "{escape_flux_string(vehicle_id)}")
                |> filter(fn: (r) => r["device-id"] == "{escape_flux_string(device_id)}"){filters}
                |> rename(columns: {{_time: "timestamp"}})
                |> pivot(rowKey:["timestamp"], columnKey: ["_field"], valueColumn: "_value")
                |> group(columns: ["network", "_measurement"]){limit}
        '''

    def _process_query(self, vehicle_id: str, device_id: str, transaction_id: str, payload: bytes) -> None:
        '''
        Runs a query and publishes its result, reporting on the status topic at every stage.

        Args:
            vehicle_id (str): The vehicle the request came from.
            device_id (str): The device the request came from.
            transaction_id (str): The transaction the request belongs to.
            payload (bytes): The raw request payload.
        '''
        logger.info(f"InfluxReader: Inizio elaborazione query {transaction_id} per {vehicle_id}/{device_id}")
        publisher = self.publisher(vehicle_id, device_id, transaction_id)

        try:
            request = parse_query_request(payload, transaction_id=transaction_id, max_range_us=self.max_range_us)
        except QueryRequestError as error:
            publisher.publish_failure(error.code, error.stage, str(error))
            return
        except Exception as error:
            publisher.publish_failure(QueryError.QUERY_ERROR_INTERNAL, STAGE_REQUEST, str(error))
            return

        publisher.publish_running()

        try:
            tables = self.query_api.query(self._build_flux_query(vehicle_id, device_id, request), org=self.client.org)
        except Exception as error:
            publisher.publish_failure(classify_influx_error(error), STAGE_QUERY, str(error))
            return

        chunks: list[QueryChunkInfo] = []
        total_rows: int = 0
        max_rows = request.maxRows if request.maxRows > 0 else self.max_rows
        truncated: bool = False

        for table in tables:
            records = table.records
            if not records:
                continue

            try:
                network_name, measurement_name = self.serializer.describe(records)
                chunk = self.serializer.serialize(records)
            except Exception as error:
                publisher.publish_failure(QueryError.QUERY_ERROR_SERIALIZATION_FAILED, STAGE_SERIALIZATION, str(error))
                return

            name = f"{network_name}--{measurement_name.lower()}"
            if not publisher.publish_chunk(name, chunk.payload):
                publisher.publish_failure(
                    QueryError.QUERY_ERROR_PUBLISH_FAILED,
                    STAGE_PUBLISH,
                    f"failed to publish the chunk '{name}'",
                )
                return

            total_rows += chunk.rows
            if max_rows > 0 and chunk.rows >= max_rows:
                truncated = True
            chunks.append(
                QueryChunkInfo(
                    transactionId=transaction_id,
                    network=network_name,
                    measurement=measurement_name,
                    topic=publisher.chunk_topic(name),
                    chunkNumber=len(chunks) + 1,
                    rows=chunk.rows,
                    sizeBytes=len(chunk.payload),
                    hash=chunk.digest,
                    format=self.serializer.format,
                    compression=self.serializer.compression,
                )
            )
            logger.info(f"InfluxReader: Inviato CSV compresso per '{name}' ({chunk.rows} righe).")

        details = {"truncated": "true"} if truncated else None
        publisher.publish_completed(chunks, total_rows, details=details)
        logger.info(
            f"InfluxReader: Query {transaction_id} completata ({len(chunks)} chunk, {total_rows} righe)."
        )

__all__ = ["InfluxReader"]
