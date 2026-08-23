import json
import time

import src.serializer  # noqa: F401  (registers the generated code on sys.path)

try:
    from influxlogger.query import (
        QueryChunkInfo,
        QueryCompression,
        QueryError,
        QueryFormat,
        QueryRequest,
        QueryState,
        QueryStatus,
    )
except ImportError as error:  # pragma: no cover - depends on the build step
    raise ImportError(
        "Generated query protocol not found. Initialize the submodule with "
        "'git submodule update --init --recursive' and generate the protobuf "
        "modules with 'make proto'."
    ) from error

PROTOCOL_VERSION: int = 1
'''Version of the query protocol implemented by this module. Published in every message.'''

STAGE_REQUEST: str = "request"
'''The failure happened while accepting or decoding the request.'''
STAGE_QUERY: str = "query"
'''The failure happened while querying InfluxDB.'''
STAGE_SERIALIZATION: str = "serialization"
'''The failure happened while turning records into a chunk payload.'''
STAGE_PUBLISH: str = "publish"
'''The failure happened while publishing a message on MQTT.'''

class QueryRequestError(Exception):
    '''
    Raised when a query request cannot be accepted. Carries the protocol error code
    and the stage to report back to the requester.

    Attributes:
        code (QueryError): The protocol error code to publish.
        stage (str): The stage of the pipeline the failure belongs to.
    '''
    def __init__(self, code: QueryError, stage: str, description: str) -> None:
        super().__init__(description)
        self.code: QueryError = code
        self.stage: str = stage

def now_us() -> int:
    '''
    Returns:
        int: The current time in microseconds since epoch, the unit used by the protocol.
    '''
    return int(time.time() * 1_000_000)

def status_topic(vehicle_id: str, device_id: str, transaction_id: str) -> str:
    '''Topic carrying the QueryStatus messages of a transaction.'''
    return f"{vehicle_id}/{device_id}/query/{transaction_id}/status"

def content_topic(vehicle_id: str, device_id: str, transaction_id: str, name: str) -> str:
    '''Topic carrying the payload of a single chunk.'''
    return f"{vehicle_id}/{device_id}/query/{transaction_id}/data/content/{name}"

def legacy_eof_topic(vehicle_id: str, device_id: str, transaction_id: str) -> str:
    '''Topic used before the protocol existed to signal the end of a transaction.'''
    return content_topic(vehicle_id, device_id, transaction_id, "eof")

def legacy_error_topic(vehicle_id: str, device_id: str, transaction_id: str) -> str:
    '''Topic used before the protocol existed to signal a failure.'''
    return content_topic(vehicle_id, device_id, transaction_id, "error")

def build_status(
    transaction_id: str,
    state: QueryState,
    error: QueryError = QueryError.QUERY_ERROR_NONE,
    stage: str = "",
    description: str = "",
    total_chunks: int = 0,
    total_rows: int = 0,
    chunks: list[QueryChunkInfo] = None,
    details: dict[str, str] = None,
) -> QueryStatus:
    '''
    Builds a QueryStatus with every field the generated code requires.

    The generated dataclass defaults enum fields to None and dereferences them while
    serializing, so 'state' and 'error' must always be set: this helper guarantees it.

    Args:
        transaction_id (str): The transaction the status refers to.
        state (QueryState): The state of the query.
        error (QueryError): The failure cause, QUERY_ERROR_NONE when the query did not fail.
        stage (str): The stage the failure belongs to, empty when the query did not fail.
        description (str): Human readable detail, never meant to drive client logic.
        total_chunks (int): Number of chunks published, meaningful on QUERY_STATE_COMPLETED.
        total_rows (int): Number of data rows published, meaningful on QUERY_STATE_COMPLETED.
        chunks (list[QueryChunkInfo]): Manifest of the published chunks, for integrity checks.
        details (dict[str, str]): Extra diagnostic fields.
    Returns:
        QueryStatus: The status message, ready to be serialized.
    '''
    return QueryStatus(
        transactionId=transaction_id,
        timestamp=now_us(),
        state=state,
        error=error,
        stage=stage,
        description=description,
        totalChunks=total_chunks,
        totalRows=total_rows,
        protocolVersion=PROTOCOL_VERSION,
        chunks=chunks if chunks else [],
        details=details if details else {},
    )

def classify_influx_error(error: Exception) -> QueryError:
    '''
    Maps an exception raised by the InfluxDB client to a protocol error code, so the
    requester can tell a transient outage from a request it should not retry.

    Args:
        error (Exception): The exception raised while querying InfluxDB.
    Returns:
        QueryError: QUERY_ERROR_DB_UNAVAILABLE for transport or server side failures,
            QUERY_ERROR_QUERY_FAILED otherwise.
    '''
    if isinstance(error, (ConnectionError, TimeoutError, OSError)):
        return QueryError.QUERY_ERROR_DB_UNAVAILABLE
    # The influxdb-client exceptions are not imported on purpose: the module must stay
    # importable when the client is stubbed, so they are matched by name and status code.
    status = getattr(error, "status", None)
    if isinstance(status, int) and status >= 500:
        return QueryError.QUERY_ERROR_DB_UNAVAILABLE
    if type(error).__name__ in (
        "NewConnectionError",
        "MaxRetryError",
        "ConnectTimeoutError",
        "ReadTimeoutError",
        "ProtocolError",
        "ServiceException",
    ):
        return QueryError.QUERY_ERROR_DB_UNAVAILABLE
    return QueryError.QUERY_ERROR_QUERY_FAILED

def escape_flux_string(value: str) -> str:
    '''
    Escapes a value interpolated inside a Flux string literal. Vehicle and device ids come
    from the MQTT topic, so without escaping a quote in an id would break, or extend, the query.

    Args:
        value (str): The raw value to interpolate.
    Returns:
        str: The value with backslashes and double quotes escaped.
    '''
    return str(value).replace("\\", "\\\\").replace('"', '\\"')

def _request_from_json(payload: bytes) -> QueryRequest:
    '''
    Decodes the legacy JSON request '{"start": <us>, "stop": <us>}' still sent by older clients.

    Args:
        payload (bytes): The raw MQTT payload.
    Returns:
        QueryRequest: The decoded request.
    Raises:
        QueryRequestError: If the payload is not a JSON object with usable 'start' and 'stop'.
    '''
    try:
        data = json.loads(payload.decode("utf-8"))
    except Exception as error:
        raise QueryRequestError(
            QueryError.QUERY_ERROR_BAD_REQUEST, STAGE_REQUEST, f"invalid JSON payload: {error}"
        ) from error
    if not isinstance(data, dict):
        raise QueryRequestError(
            QueryError.QUERY_ERROR_BAD_REQUEST, STAGE_REQUEST, "invalid JSON payload: expected an object"
        )
    if data.get("start") is None or data.get("stop") is None:
        raise QueryRequestError(
            QueryError.QUERY_ERROR_BAD_REQUEST, STAGE_REQUEST, "invalid JSON payload: 'start' and 'stop' are mandatory"
        )
    try:
        start = int(data["start"])
        stop = int(data["stop"])
        max_rows = int(data.get("maxRows", 0))
    except (TypeError, ValueError) as error:
        raise QueryRequestError(
            QueryError.QUERY_ERROR_BAD_REQUEST, STAGE_REQUEST, f"invalid JSON payload: {error}"
        ) from error
    return QueryRequest(
        start=start,
        stop=stop,
        transactionId=str(data.get("transactionId", "")),
        networks=[str(network) for network in data.get("networks", [])],
        measurements=[str(measurement) for measurement in data.get("measurements", [])],
        format=QueryFormat.QUERY_FORMAT_CSV,
        compression=QueryCompression.QUERY_COMPRESSION_GZIP,
        maxRows=max_rows,
        protocolVersion=0,
    )

def parse_query_request(payload: bytes, transaction_id: str = "", max_range_us: int = 0) -> QueryRequest:
    '''
    Decodes and validates a query request. Accepts both a serialized QueryRequest and the
    legacy JSON payload, so clients can migrate without a flag day.

    Args:
        payload (bytes): The raw MQTT payload.
        transaction_id (str): The transaction id taken from the topic, used when the payload omits it.
        max_range_us (int): Maximum accepted time range in microseconds, 0 to disable the check.
    Returns:
        QueryRequest: The validated request, with the optional fields defaulted.
    Raises:
        QueryRequestError: If the payload cannot be decoded or the time range is not usable.
    '''
    if not payload:
        raise QueryRequestError(QueryError.QUERY_ERROR_BAD_REQUEST, STAGE_REQUEST, "empty payload")
    if payload.lstrip().startswith(b"{"):
        request = _request_from_json(payload)
    else:
        try:
            request = QueryRequest.deserializeFromProtobufString(payload)
        except Exception as error:
            raise QueryRequestError(
                QueryError.QUERY_ERROR_BAD_REQUEST,
                STAGE_REQUEST,
                f"payload is neither a JSON object nor a QueryRequest: {error}",
            ) from error
    if not request.transactionId:
        request.transactionId = transaction_id
    if request.start <= 0 or request.stop <= 0:
        raise QueryRequestError(
            QueryError.QUERY_ERROR_BAD_REQUEST, STAGE_REQUEST, "'start' and 'stop' are mandatory and must be positive"
        )
    if request.stop <= request.start:
        raise QueryRequestError(
            QueryError.QUERY_ERROR_INVALID_RANGE,
            STAGE_REQUEST,
            f"'stop' ({request.stop}) must be greater than 'start' ({request.start})",
        )
    if max_range_us > 0 and (request.stop - request.start) > max_range_us:
        raise QueryRequestError(
            QueryError.QUERY_ERROR_INVALID_RANGE,
            STAGE_REQUEST,
            f"requested range of {request.stop - request.start} us exceeds the maximum of {max_range_us} us",
        )
    if request.format is None:
        request.format = QueryFormat.QUERY_FORMAT_CSV
    if request.compression is None:
        request.compression = QueryCompression.QUERY_COMPRESSION_GZIP
    if request.format != QueryFormat.QUERY_FORMAT_CSV:
        raise QueryRequestError(
            QueryError.QUERY_ERROR_BAD_REQUEST, STAGE_REQUEST, f"unsupported format: {request.format}"
        )
    if request.compression != QueryCompression.QUERY_COMPRESSION_GZIP:
        raise QueryRequestError(
            QueryError.QUERY_ERROR_BAD_REQUEST, STAGE_REQUEST, f"unsupported compression: {request.compression}"
        )
    return request

__all__ = [
    "PROTOCOL_VERSION",
    "STAGE_REQUEST",
    "STAGE_QUERY",
    "STAGE_SERIALIZATION",
    "STAGE_PUBLISH",
    "QueryChunkInfo",
    "QueryCompression",
    "QueryError",
    "QueryFormat",
    "QueryRequest",
    "QueryRequestError",
    "QueryState",
    "QueryStatus",
    "build_status",
    "classify_influx_error",
    "content_topic",
    "escape_flux_string",
    "legacy_eof_topic",
    "legacy_error_topic",
    "now_us",
    "parse_query_request",
    "status_topic",
]
