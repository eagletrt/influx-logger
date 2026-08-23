# Query protocol

Reference for the messages added to [telemetry-serializers](https://github.com/eagletrt/telemetry-serializers)
in `proto/influxlogger/query.proto` (package `InfluxLogger`), and for how the influx-logger
answers a data query over MQTT.

The `.proto` file itself is kept free of comments, in line with the rest of that repository:
this document is the annotated version of it.

## Where the code comes from

| Artifact | Branch of telemetry-serializers | How it reaches the influx-logger |
| --- | --- | --- |
| `proto/influxlogger/query.proto` | `dev` / `main` (hand written) | source of truth, edited there |
| `py/influxlogger/query.py` (dataclasses) | `dev-build` / `build` (CI generated) | shipped by the `external/serializer` submodule |
| `influxlogger/query_pb2.py` | not shipped | generated locally by `make proto` into `.generated/` |

`.generated/` and `external/serializer/py` both contribute to the `influxlogger` namespace
package, so `influxlogger.query` and `influxlogger.query_pb2` resolve even though they live
in different trees. `src/serializer/__init__.py` puts both on `sys.path`.

## Topics

`{vehicle}` and `{device}` identify the logger the request is addressed to, `{tx}` is the
transaction id chosen by the requester.

| Topic | Direction | Payload | QoS |
| --- | --- | --- | --- |
| `{vehicle}/{device}/query/{tx}/data/get` | requester to logger | `QueryRequest`, or the legacy JSON | 0 |
| `{vehicle}/{device}/query/{tx}/status` | logger to requester | `QueryStatus` | 1 |
| `{vehicle}/{device}/query/{tx}/data/content/{network}--{measurement}` | logger to requester | gzip compressed CSV | 0 |
| `{vehicle}/{device}/query/{tx}/data/content/eof` | logger to requester | empty, legacy only | 0 |
| `{vehicle}/{device}/query/{tx}/data/content/error` | logger to requester | JSON, legacy only | 0 |

Statuses travel at QoS 1 on their own topic: losing the message that reports a failure would
leave the requester waiting for data that is never coming, which is what the status channel
exists to prevent. The chunks stay at QoS 0, and the manifest published on completion lets
the requester detect a missing one.

The status topic sits outside `data/content/` on purpose. The chunk names are built from the
data itself, so a measurement called `error` or `eof` would otherwise collide with the
control messages.

## Message flow

1. The requester publishes a `QueryRequest` on `.../data/get`.
2. The logger answers `QUERY_STATE_ACCEPTED` as soon as the request is queued, or
   `QUERY_STATE_FAILED` if it is refused (unknown vehicle, reader down, queue full).
3. `QUERY_STATE_RUNNING` is published when the query starts.
4. One message per measurement is published on its content topic.
5. `QUERY_STATE_COMPLETED` carries the number of chunks and rows, plus the manifest of every
   chunk that was published.

A failure at any point produces a single `QUERY_STATE_FAILED`. Chunks already received before
a failure are incomplete by definition and must be discarded.

## Messages

### QueryRequest

| Field | Type | Meaning |
| --- | --- | --- |
| `start` | `uint64` | Start of the interval, microseconds since epoch. Mandatory. |
| `stop` | `uint64` | End of the interval, microseconds since epoch. Must be greater than `start`. |
| `transactionId` | `string` | Redundant with the topic, useful in logs and when replaying traffic. |
| `networks` | `repeated string` | Only export these networks. Empty means all of them. |
| `measurements` | `repeated string` | Only export these measurements. Empty means all of them. |
| `format` | `QueryFormat` | Serialization of the chunks. Only CSV is implemented. |
| `compression` | `QueryCompression` | Compression of the chunks. Only gzip is implemented. |
| `maxRows` | `uint64` | Cap on the rows returned per measurement. `0` uses the logger default. |
| `protocolVersion` | `uint32` | Version of this protocol. Current version is `1`. |

### QueryChunkInfo

Describes one published chunk. The payload is not carried here: it stays the raw body of its
own content topic, so the CSV is not paid for twice.

| Field | Type | Meaning |
| --- | --- | --- |
| `transactionId` | `string` | Transaction the chunk belongs to. |
| `network` | `string` | Network the measurement belongs to. |
| `measurement` | `string` | Measurement exported in the chunk. |
| `topic` | `string` | Topic the payload was published on. |
| `chunkNumber` | `uint64` | Position in the transaction, starting from 1. |
| `rows` | `uint64` | Data rows, the CSV header excluded. |
| `sizeBytes` | `uint64` | Size of the published payload. |
| `hash` | `string` | Hexadecimal sha256 of the payload, for integrity checks. |
| `format` | `QueryFormat` | Format the payload was serialized with. |
| `compression` | `QueryCompression` | Compression applied to the payload. |

### QueryStatus

| Field | Type | Meaning |
| --- | --- | --- |
| `transactionId` | `string` | Transaction the status refers to. |
| `timestamp` | `uint64` | When the status was produced, microseconds since epoch. |
| `state` | `QueryState` | Current state of the query. |
| `error` | `QueryError` | Failure cause, `QUERY_ERROR_NONE` when the query did not fail. |
| `stage` | `string` | Stage the failure belongs to: `request`, `query`, `serialization`, `publish`. |
| `description` | `string` | Human readable detail. Never meant to drive client logic. |
| `totalChunks` | `uint64` | Chunks published, meaningful on `QUERY_STATE_COMPLETED`. |
| `totalRows` | `uint64` | Rows published, meaningful on `QUERY_STATE_COMPLETED`. |
| `protocolVersion` | `uint32` | Version of this protocol. Current version is `1`. |
| `chunks` | `repeated QueryChunkInfo` | Manifest sent with `QUERY_STATE_COMPLETED`. |
| `details` | `map<string, string>` | Diagnostic fields that can be added without changing the schema. |

`details` currently carries `truncated: "true"` when at least one measurement hit `maxRows`.

## Enums

`QueryState` is `QUERY_STATE_ACCEPTED`, `QUERY_STATE_RUNNING`, `QUERY_STATE_COMPLETED`,
`QUERY_STATE_FAILED`. `QueryFormat` only has `QUERY_FORMAT_CSV`; `QueryCompression` has
`QUERY_COMPRESSION_GZIP` and `QUERY_COMPRESSION_NONE`.

`QueryError` tells a request that must be fixed from an outage that can be retried:

| Code | Stage | Cause |
| --- | --- | --- |
| `QUERY_ERROR_NONE` | | The query did not fail. |
| `QUERY_ERROR_BAD_REQUEST` | `request` | Payload is neither a `QueryRequest` nor valid JSON, or `start`/`stop` are missing. |
| `QUERY_ERROR_INVALID_RANGE` | `request` | `stop` is not greater than `start`, or the range exceeds the configured maximum. |
| `QUERY_ERROR_NOT_AUTHORIZED` | `request` | The vehicle is not in the whitelist. |
| `QUERY_ERROR_UNAVAILABLE` | `request` | The reader is not running, is shutting down, or its queue is full. |
| `QUERY_ERROR_DB_UNAVAILABLE` | `query` | InfluxDB is unreachable or answered with a server error. Retry. |
| `QUERY_ERROR_QUERY_FAILED` | `query` | InfluxDB rejected the query. Do not retry unchanged. |
| `QUERY_ERROR_SERIALIZATION_FAILED` | `serialization` | The records could not be turned into a CSV chunk. |
| `QUERY_ERROR_PUBLISH_FAILED` | `publish` | The broker refused a chunk, or the connection was gone. |
| `QUERY_ERROR_TIMEOUT` | `query` | Reserved: the query exceeded its time budget. |
| `QUERY_ERROR_TOO_MUCH_DATA` | `query` | Reserved: the result exceeded the memory budget. |
| `QUERY_ERROR_INTERNAL` | any | Unclassified exception. |

Enum values are prefixed because in proto3 they live in the scope of the package, not of the
enum: two enums of `InfluxLogger` cannot both declare a bare `NONE`.

## Backward compatibility

The logger still publishes the pre-protocol topics: an empty message on `.../data/content/eof`
on completion, and `{"error": ..., "code": ..., "stage": ...}` on `.../data/content/error` on
failure. Requests are still accepted as `{"start": <us>, "stop": <us>}` JSON. Existing clients
keep working untouched; once they move to the status topic, `legacy_topics=False` on
`InfluxReader` turns the old topics off.

## Caveats of the generated code

The dataclasses generated from this file default enum fields to `None` and dereference
`.value` while serializing, so `state`, `error`, `format` and `compression` must always be
set explicitly. `src.serializer.query_protocol.build_status` guarantees it for statuses.

The generator resolves types file by file, and the generated `.proto` files are compiled
individually, so a message must not reference a type declared in another file. Everything the
query protocol needs is therefore declared in `query.proto`.
