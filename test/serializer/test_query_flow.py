import sys

from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from unittest import TestCase

# The heavy clients are stubbed so the query flow can be exercised without a broker or a
# database. google.protobuf is deliberately not stubbed: the protocol serializes real
# protobuf messages generated from the telemetry-serializers submodule.
if "influxdb_client" not in sys.modules:
    influxdb_client_module = ModuleType("influxdb_client")

    class InfluxDBClient:
        def __init__(self, *args, **kwargs):
            self.connection = self

        def write_api(self, *args, **kwargs):
            return self

        def query_api(self, *args, **kwargs):
            return self

        def close(self):
            return None

    influxdb_client_module.InfluxDBClient = InfluxDBClient

    client_module = ModuleType("influxdb_client.client")
    write_api_module = ModuleType("influxdb_client.client.write_api")

    class WriteOptions:
        def __init__(self, *args, **kwargs):
            self.batch_size = kwargs.get("batch_size", 0)

    class WriteApi:
        pass

    class Point:
        pass

    write_api_module.WriteOptions = WriteOptions
    write_api_module.WriteApi = WriteApi
    write_api_module.Point = Point
    write_api_module.SYNCHRONOUS = object()
    influxdb_client_module.Point = Point
    client_module.write_api = write_api_module

    sys.modules["influxdb_client"] = influxdb_client_module
    sys.modules["influxdb_client.client"] = client_module
    sys.modules["influxdb_client.client.write_api"] = write_api_module

if "paho.mqtt.client" not in sys.modules:
    paho_module = ModuleType("paho")
    mqtt_module = ModuleType("paho.mqtt")
    mqtt_client_module = ModuleType("paho.mqtt.client")

    class Client:
        def __init__(self, *args, **kwargs):
            self.on_connect = None
            self.on_disconnect = None
            self.on_message = None

    mqtt_client_module.Client = Client
    paho_module.mqtt = mqtt_module
    mqtt_module.client = mqtt_client_module
    sys.modules["paho"] = paho_module
    sys.modules["paho.mqtt"] = mqtt_module
    sys.modules["paho.mqtt.client"] = mqtt_client_module

if "requests" not in sys.modules:
    requests_module = ModuleType("requests")
    requests_module.get = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_module

if "grpc_tools" not in sys.modules:
    grpc_tools_module = ModuleType("grpc_tools")
    protoc_module = ModuleType("grpc_tools.protoc")
    protoc_module.main = lambda *args, **kwargs: 0
    grpc_tools_module.protoc = protoc_module
    sys.modules["grpc_tools"] = grpc_tools_module
    sys.modules["grpc_tools.protoc"] = protoc_module

import gzip
import hashlib
import json

from src.handler.msg_dispatcher import MsgDispatcher
from src.influx.influx_reader import InfluxReader
from src.serializer.query_protocol import (
    QueryCompression,
    QueryError,
    QueryFormat,
    QueryRequest,
    QueryState,
    QueryStatus,
)

VEHICLE = "kraken"
DEVICE = "onboard"
TRANSACTION = "tx-1"
STATUS_TOPIC = f"{VEHICLE}/{DEVICE}/query/{TRANSACTION}/status"


class FakeRecord:
    def __init__(self, values: dict) -> None:
        self.values = values


class FakeTable:
    def __init__(self, records: list) -> None:
        self.records = records


class FakeQueryApi:
    def __init__(self, tables: list = None, error: Exception = None) -> None:
        self.tables = tables if tables is not None else []
        self.error = error
        self.last_query = None

    def query(self, query, org=None):
        self.last_query = query
        if self.error:
            raise self.error
        return self.tables


class FakeInfluxConnection:
    def __init__(self, query_api: FakeQueryApi) -> None:
        self.connection = SimpleNamespace(query_api=lambda: query_api)
        self.org = "eagletrt"


class FakeMqttClient:
    def __init__(self, return_code: int = 0) -> None:
        self.published: list = []
        self.return_code = return_code

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, payload, qos))
        return SimpleNamespace(rc=self.return_code)


class FakeMqttConnection:
    def __init__(self, client=None) -> None:
        self.connection = client


def make_records(network: str = "primary", measurement: str = "hv_current", rows: int = 2) -> list:
    return [
        FakeRecord(
            {
                "result": "_result",
                "table": 0,
                "network": network,
                "_measurement": measurement,
                "vehicle-id": VEHICLE,
                "device-id": DEVICE,
                "timestamp": datetime(2026, 1, 1, 0, 0, index, tzinfo=timezone.utc),
                "value": float(index),
            }
        )
        for index in range(rows)
    ]


def make_reader(tables: list = None, error: Exception = None, client: FakeMqttClient = None) -> InfluxReader:
    query_api = FakeQueryApi(tables=tables, error=error)
    return InfluxReader(
        client=FakeInfluxConnection(query_api),
        mqtt_client=FakeMqttConnection(client if client is not None else FakeMqttClient()),
        log_bucket="telemetry_adr",
    )


def statuses(client: FakeMqttClient) -> list:
    return [
        QueryStatus.deserializeFromProtobufString(payload)
        for topic, payload, _qos in client.published
        if topic == STATUS_TOPIC
    ]


def json_request(start: int = 1_000, stop: int = 2_000) -> bytes:
    return json.dumps({"start": start, "stop": stop}).encode("utf-8")


class TestQuerySuccess(TestCase):
    def test_chunks_and_manifest_are_published(self):
        client = FakeMqttClient()
        reader = make_reader(tables=[FakeTable(make_records())], client=client)

        reader._process_query(VEHICLE, DEVICE, TRANSACTION, json_request())

        chunk_topic = f"{VEHICLE}/{DEVICE}/query/{TRANSACTION}/data/content/primary--hv_current"
        chunks = [entry for entry in client.published if entry[0] == chunk_topic]
        self.assertEqual(len(chunks), 1)

        published = statuses(client)
        self.assertEqual([status.state for status in published], [QueryState.QUERY_STATE_RUNNING, QueryState.QUERY_STATE_COMPLETED])

        completed = published[-1]
        self.assertEqual(completed.error, QueryError.QUERY_ERROR_NONE)
        self.assertEqual(completed.totalChunks, 1)
        self.assertEqual(completed.totalRows, 2)
        self.assertEqual(len(completed.chunks), 1)

        manifest = completed.chunks[0]
        payload = chunks[0][1]
        self.assertEqual(manifest.topic, chunk_topic)
        self.assertEqual(manifest.sizeBytes, len(payload))
        self.assertEqual(manifest.hash, hashlib.sha256(payload).hexdigest())
        self.assertEqual(manifest.rows, 2)
        self.assertEqual(manifest.format, QueryFormat.QUERY_FORMAT_CSV)
        self.assertEqual(manifest.compression, QueryCompression.QUERY_COMPRESSION_GZIP)

    def test_csv_payload_keeps_its_format(self):
        client = FakeMqttClient()
        reader = make_reader(tables=[FakeTable(make_records())], client=client)

        reader._process_query(VEHICLE, DEVICE, TRANSACTION, json_request())

        payload = next(entry[1] for entry in client.published if entry[0].endswith("primary--hv_current"))
        content = gzip.decompress(payload).decode("utf-8")
        self.assertEqual(content.splitlines()[0], "_timestamp,value")
        self.assertEqual(len(content.splitlines()), 3)

    def test_protobuf_request_is_accepted(self):
        client = FakeMqttClient()
        reader = make_reader(tables=[FakeTable(make_records())], client=client)
        request = QueryRequest(
            start=1_000,
            stop=2_000,
            transactionId=TRANSACTION,
            format=QueryFormat.QUERY_FORMAT_CSV,
            compression=QueryCompression.QUERY_COMPRESSION_GZIP,
            protocolVersion=1,
        )

        reader._process_query(VEHICLE, DEVICE, TRANSACTION, request.serializeAsProtobufString())

        self.assertEqual(statuses(client)[-1].state, QueryState.QUERY_STATE_COMPLETED)

    def test_legacy_eof_is_still_published(self):
        client = FakeMqttClient()
        reader = make_reader(tables=[FakeTable(make_records())], client=client)

        reader._process_query(VEHICLE, DEVICE, TRANSACTION, json_request())

        eof_topic = f"{VEHICLE}/{DEVICE}/query/{TRANSACTION}/data/content/eof"
        self.assertIn(eof_topic, [entry[0] for entry in client.published])

    def test_accepted_is_published_on_enqueue(self):
        client = FakeMqttClient()
        reader = make_reader(client=client)

        self.assertTrue(reader.add_query_to_queue(VEHICLE, DEVICE, TRANSACTION, json_request()))
        self.assertEqual(statuses(client)[0].state, QueryState.QUERY_STATE_ACCEPTED)


class TestQueryFailures(TestCase):
    def failure(self, client: FakeMqttClient) -> QueryStatus:
        failed = [status for status in statuses(client) if status.state == QueryState.QUERY_STATE_FAILED]
        self.assertEqual(len(failed), 1, "exactly one failure must be reported")
        return failed[0]

    def test_missing_fields_are_reported_as_bad_request(self):
        client = FakeMqttClient()
        reader = make_reader(client=client)

        reader._process_query(VEHICLE, DEVICE, TRANSACTION, b"{}")

        status = self.failure(client)
        self.assertEqual(status.error, QueryError.QUERY_ERROR_BAD_REQUEST)
        self.assertEqual(status.stage, "request")

    def test_undecodable_payload_is_reported(self):
        client = FakeMqttClient()
        reader = make_reader(client=client)

        reader._process_query(VEHICLE, DEVICE, TRANSACTION, b"{not json")

        self.assertEqual(self.failure(client).error, QueryError.QUERY_ERROR_BAD_REQUEST)

    def test_inverted_range_is_reported(self):
        client = FakeMqttClient()
        reader = make_reader(client=client)

        reader._process_query(VEHICLE, DEVICE, TRANSACTION, json_request(start=2_000, stop=1_000))

        self.assertEqual(self.failure(client).error, QueryError.QUERY_ERROR_INVALID_RANGE)

    def test_range_over_the_limit_is_reported(self):
        client = FakeMqttClient()
        reader = make_reader(client=client)
        reader.max_range_us = 100

        reader._process_query(VEHICLE, DEVICE, TRANSACTION, json_request(start=1_000, stop=2_000))

        self.assertEqual(self.failure(client).error, QueryError.QUERY_ERROR_INVALID_RANGE)

    def test_unreachable_database_is_reported_as_db_unavailable(self):
        client = FakeMqttClient()
        reader = make_reader(error=ConnectionError("connection refused"), client=client)

        reader._process_query(VEHICLE, DEVICE, TRANSACTION, json_request())

        status = self.failure(client)
        self.assertEqual(status.error, QueryError.QUERY_ERROR_DB_UNAVAILABLE)
        self.assertEqual(status.stage, "query")

    def test_rejected_query_is_reported_as_query_failed(self):
        client = FakeMqttClient()
        reader = make_reader(error=ValueError("compilation failed"), client=client)

        reader._process_query(VEHICLE, DEVICE, TRANSACTION, json_request())

        self.assertEqual(self.failure(client).error, QueryError.QUERY_ERROR_QUERY_FAILED)

    def test_serialization_error_is_reported(self):
        client = FakeMqttClient()
        reader = make_reader(tables=[FakeTable([FakeRecord({"_measurement": "hv"})])], client=client)
        reader.serializer.serialize = lambda records: (_ for _ in ()).throw(RuntimeError("boom"))

        reader._process_query(VEHICLE, DEVICE, TRANSACTION, json_request())

        status = self.failure(client)
        self.assertEqual(status.error, QueryError.QUERY_ERROR_SERIALIZATION_FAILED)
        self.assertEqual(status.stage, "serialization")

    def test_refused_publish_is_reported(self):
        client = FakeMqttClient(return_code=1)
        reader = make_reader(tables=[FakeTable(make_records())], client=client)

        reader._process_query(VEHICLE, DEVICE, TRANSACTION, json_request())

        status = self.failure(client)
        self.assertEqual(status.error, QueryError.QUERY_ERROR_PUBLISH_FAILED)
        self.assertEqual(status.stage, "publish")

    def test_a_dropped_broker_never_raises(self):
        reader = make_reader(tables=[FakeTable(make_records())], client=None)

        # The MQTT connection is torn down on disconnect: the failure path must survive it.
        reader._process_query(VEHICLE, DEVICE, TRANSACTION, json_request())

    def test_queued_requests_are_refused_on_shutdown(self):
        client = FakeMqttClient()
        reader = make_reader(client=client)
        reader.add_query_to_queue(VEHICLE, DEVICE, TRANSACTION, json_request())
        client.published.clear()

        reader._drain_queue()

        status = self.failure(client)
        self.assertEqual(status.error, QueryError.QUERY_ERROR_UNAVAILABLE)

    def test_a_full_queue_is_refused(self):
        client = FakeMqttClient()
        query_api = FakeQueryApi()
        reader = InfluxReader(
            client=FakeInfluxConnection(query_api),
            mqtt_client=FakeMqttConnection(client),
            log_bucket="telemetry_adr",
            max_queue_size=1,
        )
        reader.add_query_to_queue(VEHICLE, DEVICE, TRANSACTION, json_request())
        client.published.clear()

        self.assertFalse(reader.add_query_to_queue(VEHICLE, DEVICE, TRANSACTION, json_request()))
        self.assertEqual(self.failure(client).error, QueryError.QUERY_ERROR_UNAVAILABLE)


class TestFluxQuery(TestCase):
    def test_ids_are_escaped(self):
        reader = make_reader(tables=[])
        query_api = reader.query_api

        reader._process_query('kra"ken', DEVICE, TRANSACTION, json_request())

        self.assertIn('r["vehicle-id"] == "kra\\"ken"', query_api.last_query)

    def test_filters_and_limit_are_applied(self):
        reader = make_reader(tables=[])
        query_api = reader.query_api
        payload = json.dumps(
            {"start": 1_000, "stop": 2_000, "networks": ["primary"], "measurements": ["hv_current"], "maxRows": 10}
        ).encode("utf-8")

        reader._process_query(VEHICLE, DEVICE, TRANSACTION, payload)

        self.assertIn('r["network"] == "primary"', query_api.last_query)
        self.assertIn('r["_measurement"] == "hv_current"', query_api.last_query)
        self.assertIn("limit(n: 10)", query_api.last_query)


class TestDispatcherRefusals(TestCase):
    def test_vehicle_out_of_whitelist_is_refused(self):
        client = FakeMqttClient()
        dispatcher = MsgDispatcher(mqtt=FakeMqttConnection(client), vehicle_whitelist=["another"])

        dispatcher.handle_query_request("", json_request(), [VEHICLE, DEVICE, TRANSACTION])

        status = statuses(client)[-1]
        self.assertEqual(status.state, QueryState.QUERY_STATE_FAILED)
        self.assertEqual(status.error, QueryError.QUERY_ERROR_NOT_AUTHORIZED)

    def test_missing_reader_is_refused(self):
        client = FakeMqttClient()
        dispatcher = MsgDispatcher(mqtt=FakeMqttConnection(client))

        dispatcher.handle_query_request("", json_request(), [VEHICLE, DEVICE, TRANSACTION])

        status = statuses(client)[-1]
        self.assertEqual(status.state, QueryState.QUERY_STATE_FAILED)
        self.assertEqual(status.error, QueryError.QUERY_ERROR_UNAVAILABLE)
