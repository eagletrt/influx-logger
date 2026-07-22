import sys
from types import ModuleType
from unittest import TestCase


def _install_import_stubs() -> None:
    requests_module = ModuleType("requests")
    requests_module.get = lambda *args, **kwargs: None
    sys.modules.setdefault("requests", requests_module)

    grpc_tools_module = ModuleType("grpc_tools")
    protoc_module = ModuleType("grpc_tools.protoc")
    protoc_module.main = lambda *args, **kwargs: 0
    grpc_tools_module.protoc = protoc_module
    sys.modules.setdefault("grpc_tools", grpc_tools_module)
    sys.modules.setdefault("grpc_tools.protoc", protoc_module)

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

    sys.modules.setdefault("google", google_module)
    sys.modules.setdefault("google.protobuf", protobuf_module)
    sys.modules.setdefault("google.protobuf.json_format", json_format_module)
    sys.modules.setdefault("google.protobuf.descriptor_pool", descriptor_pool_module)
    sys.modules.setdefault("google.protobuf.descriptor_pb2", descriptor_pb2_module)
    sys.modules.setdefault("google.protobuf.message_factory", message_factory_module)


_install_import_stubs()

from src.parser.protobuf_manager import _DecoderWrapper


class DummyMessage:
    def __init__(self) -> None:
        self.payload = None

    def ParseFromString(self, payload: bytes) -> None:
        self.payload = payload


class FakeJsonFormat:
    def __init__(self) -> None:
        self.calls = []

    def MessageToDict(self, message, **kwargs):
        self.calls.append((message, kwargs))
        return {"status": 1}


class TestDecoderWrapper(TestCase):
    def test_decode_forces_integer_enums(self):
        fake_json_format = FakeJsonFormat()
        wrapper = _DecoderWrapper(DummyMessage, fake_json_format)

        result = wrapper.decode(b"abc")

        self.assertEqual(result, {"status": 1})
        self.assertEqual(len(fake_json_format.calls), 1)
        message, kwargs = fake_json_format.calls[0]
        self.assertEqual(message.payload, b"abc")
        self.assertTrue(kwargs["preserving_proto_field_name"])
        self.assertTrue(kwargs["use_integers_for_enums"])
