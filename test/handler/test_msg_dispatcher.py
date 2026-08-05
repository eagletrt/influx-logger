import sys
from types import ModuleType
from unittest import TestCase


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

        def connect(self, *args, **kwargs):
            return None

        def subscribe(self, *args, **kwargs):
            return None

        def loop_start(self):
            return None

        def loop_stop(self):
            return None

        def disconnect(self):
            return None

        def loop_read(self):
            return None

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

if "google.protobuf" not in sys.modules:
    google_module = ModuleType("google")
    protobuf_module = ModuleType("google.protobuf")

    json_format_module = ModuleType("google.protobuf.json_format")

    descriptor_pool_module = ModuleType("google.protobuf.descriptor_pool")

    class DescriptorPool:
        def Add(self, file_proto):
            return None

        def FindMessageTypeByName(self, name):
            return object()

    descriptor_pool_module.DescriptorPool = DescriptorPool

    descriptor_pb2_module = ModuleType("google.protobuf.descriptor_pb2")

    class FileDescriptorSet:
        def __init__(self) -> None:
            self.file = []

        def ParseFromString(self, payload: bytes) -> None:
            return None

    descriptor_pb2_module.FileDescriptorSet = FileDescriptorSet

    message_factory_module = ModuleType("google.protobuf.message_factory")

    class MessageFactory:
        def __init__(self, pool):
            self.pool = pool

        def GetPrototype(self, message_descriptor):
            return object()

    def GetMessageClass(message_descriptor):
        return object()

    message_factory_module.MessageFactory = MessageFactory
    message_factory_module.GetMessageClass = GetMessageClass

    protobuf_module.json_format = json_format_module
    protobuf_module.descriptor_pool = descriptor_pool_module
    protobuf_module.descriptor_pb2 = descriptor_pb2_module
    protobuf_module.message_factory = message_factory_module
    google_module.protobuf = protobuf_module

    sys.modules["google"] = google_module
    sys.modules["google.protobuf"] = protobuf_module
    sys.modules["google.protobuf.json_format"] = json_format_module
    sys.modules["google.protobuf.descriptor_pool"] = descriptor_pool_module
    sys.modules["google.protobuf.descriptor_pb2"] = descriptor_pb2_module
    sys.modules["google.protobuf.message_factory"] = message_factory_module

from src.handler.msg_dispatcher import MsgDispatcher
from src.connections.mqtt_connection import MQTTConnection


class TestMsgDispatcher(TestCase):
    def test_version_topics_keep_legacy_and_new_paths(self):
        dispatcher = MsgDispatcher()

        self.assertIn("+/+/version", dispatcher.topic_callbacks)
        self.assertIn("+/+/info/version/libcan", dispatcher.topic_callbacks)
        self.assertIn("+/+/info/version/gpslib", dispatcher.topic_callbacks)

    def test_legacy_version_topic_keeps_vehicle_and_device_ids(self):
        dispatcher = MsgDispatcher()
        regex = dispatcher.build_topic_regex("+/+/version")

        match = regex.fullmatch("vehicle/onboard/version")

        self.assertIsNotNone(match)
        self.assertEqual(list(match.groups()), ["vehicle", "onboard"])

    def test_new_version_topic_keeps_vehicle_and_device_ids(self):
        dispatcher = MsgDispatcher()
        regex = dispatcher.build_topic_regex("+/+/info/version/libcan")

        match = regex.fullmatch("vehicle/onboard/info/version/libcan")

        self.assertIsNotNone(match)
        self.assertEqual(list(match.groups()), ["vehicle", "onboard"])

    def test_legacy_version_topic_does_not_partially_match_new_topic(self):
        dispatcher = MsgDispatcher()
        regex = dispatcher.build_topic_regex("+/+/version")

        self.assertIsNone(regex.fullmatch("vehicle/onboard/info/version/libcan"))

    def test_mqtt_connection_subscribes_to_legacy_and_new_version_topics(self):
        import src.connections.mqtt_connection as mqtt_module

        subscribe_calls = []
        original_client = mqtt_module.mqtt.Client

        class Client:
            def __init__(self, *args, **kwargs):
                self.on_connect = None
                self.on_disconnect = None
                self.on_message = None

            def connect(self, *args, **kwargs):
                return None

            def subscribe(self, topic, *args, **kwargs):
                subscribe_calls.append(topic)
                return None

            def loop_start(self):
                return None

        mqtt_module.mqtt.Client = Client
        try:
            self.assertTrue(MQTTConnection(url="broker", port=1883).connect())
        finally:
            mqtt_module.mqtt.Client = original_client

        self.assertEqual(
            subscribe_calls,
            [
                "+/+/version",
                "+/+/info/version/libcan",
                "+/+/info/version/gpslib",
            ],
        )