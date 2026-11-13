"""Tests for descriptor caching and protobuf decoding helpers."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from google.protobuf.descriptor_pb2 import FileDescriptorSet  # pylint: disable=no-name-in-module

from src.parser.libmanager import LibcanManager, LibgpsManager
from src.parser.protobuf_manager import ProtobufManager, _DecoderWrapper


class TestProtobufManager(TestCase):
    """
    Tests for ProtobufManager descriptor caching and decoding helpers.
    """

    def test_descriptor_cache_lookup_and_download_failure(self):
        """
        Tests that proto_version_downloaded returns True when the expected descriptor file exists,
        and that download_proto_descriptor returns False when the download fails.
        """
        manager = ProtobufManager()
        with TemporaryDirectory() as temp, patch.object(
                LibcanManager, "CACHE_DIR", temp):
            target = Path(temp) / "v1" / "proto" / "can.proto"
            target.parent.mkdir(parents=True)
            target.write_text("syntax = 'proto3';", encoding="utf-8")
            self.assertTrue(
                manager.proto_version_downloaded("v1", "proto/can",
                                                 LibcanManager))
            self.assertFalse(
                manager.proto_version_downloaded("absent", "can",
                                                 LibcanManager))
        with patch.object(LibcanManager,
                          "download_proto_version",
                          return_value=False):
            self.assertFalse(
                manager.download_proto_descriptor("v", "can", LibcanManager))

    def test_download_builds_and_registers_decoder(self):
        """
        Tests that download_proto_descriptor calls build_decoder and registers
        the resulting _DecoderWrapper in version_descriptors.
        """
        manager = ProtobufManager()
        decoder = MagicMock()
        with patch.object(manager, "proto_version_downloaded", return_value=True), \
                patch(
                    "src.parser.protobuf_manager._DecoderWrapper.build_decoder",
                    return_value=decoder
                    ):
            self.assertTrue(
                manager.download_proto_descriptor("v", "can", LibcanManager))
        self.assertIs(manager.version_descriptors["v"]["can"], decoder)

    def test_decode_message_and_restore_numeric_descriptor_types(self):
        """
        Tests that _DecoderWrapper.decode calls ParseFromString and MessageToDict,
        and that _restore_descriptor_types converts numeric strings to numbers.
        """
        field_int = SimpleNamespace(json_name="count",
                                    name="count",
                                    is_repeated=False,
                                    message_type=None,
                                    type=5)
        field_float = SimpleNamespace(json_name="ratio",
                                      name="ratio",
                                      is_repeated=True,
                                      message_type=None,
                                      type=2)
        descriptor = SimpleNamespace(fields=[field_int, field_float])
        message = SimpleNamespace(DESCRIPTOR=descriptor,
                                  ParseFromString=MagicMock())
        message_class = MagicMock(return_value=message)
        format_module = MagicMock()
        format_module.MessageToDict.return_value = {
            "count": "8",
            "ratio": ["1.25"]
        }
        wrapper = _DecoderWrapper(message_class, format_module)
        result = wrapper.decode(b"bytes")
        message.ParseFromString.assert_called_once_with(b"bytes")
        self.assertEqual(result, {"count": 8, "ratio": [1.25]})

    def test_restore_nested_map_and_unknown_values(self):
        """
        Tests that _restore_descriptor_types and _restore_field_type handle
        scalar values, unknown types, and map fields correctly.
        """
        self.assertEqual(
            _DecoderWrapper._restore_descriptor_types("scalar", None),  # pylint: disable=protected-access
            "scalar")
        unknown = _DecoderWrapper._restore_descriptor_types(  # pylint: disable=protected-access
            {"x": 1}, SimpleNamespace(fields=[]))
        self.assertEqual(unknown, {"x": 1})
        value_field = SimpleNamespace(message_type=None,
                                      type=5,
                                      is_repeated=False)
        entry_type = SimpleNamespace(
            GetOptions=lambda: SimpleNamespace(map_entry=True),
            fields_by_name={"value": value_field})
        map_field = SimpleNamespace(is_repeated=True, message_type=entry_type)
        self.assertEqual(
            _DecoderWrapper._restore_field_type({"a": "2"}, map_field),  # pylint: disable=protected-access
            {"a": 2})
        names = _DecoderWrapper._message_names(FileDescriptorSet())  # pylint: disable=protected-access
        self.assertEqual(names, [])

    def test_build_decoder_reads_descriptor_set_and_formats(self):
        """
        Tests that build_decoder reads a FileDescriptorSet and returns a _DecoderWrapper.
        """
        with TemporaryDirectory() as temp:
            descriptor = Path(temp) / "schema.pb"
            descriptor.write_bytes(FileDescriptorSet().SerializeToString())
            with patch("src.parser.protobuf_manager._DecoderWrapper.compile_proto_files",
                       return_value=str(descriptor)), \
                    patch("src.parser.protobuf_manager._DecoderWrapper.build_message_prototype",
                          return_value="decoder") as build:
                self.assertEqual(
                    _DecoderWrapper.build_decoder("v", "can", LibcanManager),
                    "decoder")
        build.assert_called_once()
        wrapper = _DecoderWrapper(object, object)
        self.assertIn("_DecoderWrapper", str(wrapper))

    def test_build_prototype_finds_pack_or_status_message(self):
        """
        Tests that build_message_prototype finds the Pack or TelemetryStatus message
        in the provided FileDescriptorSet and returns a _DecoderWrapper instance.
        """
        file_set = FileDescriptorSet()
        file_proto = file_set.file.add(name="sample.proto",
                                       package="can",
                                       syntax="proto3")
        pack = file_proto.message_type.add(name="Pack")
        pack.field.add(name="value", number=1, label=1, type=5)
        status = file_proto.message_type.add(name="TelemetryStatus")
        status.field.add(name="state", number=1, label=1, type=5)
        self.assertEqual(
            _DecoderWrapper._message_names(file_set),  # pylint: disable=protected-access
            ["can.Pack", "can.TelemetryStatus"])
        self.assertIsInstance(
            _DecoderWrapper.build_message_prototype("can", LibcanManager,
                                                    file_set), _DecoderWrapper)
        self.assertIsInstance(
            _DecoderWrapper.build_message_prototype("telemetry",
                                                    LibgpsManager,
                                                    file_set,
                                                    message_field="state"),
            _DecoderWrapper)

    def test_compile_proto_files_uses_protoc_and_rejects_failure(self):
        """
        Tests that compile_proto_files calls protoc and raises an error on failure.
        """
        with TemporaryDirectory() as temp:
            with patch("src.parser.protobuf_manager.LibManager.create_cache_directories",
                       side_effect=lambda _cache, version: str(Path(version) / "proto")), \
                    patch("src.parser.protobuf_manager.os.makedirs"), \
                    patch("src.parser.protobuf_manager.protoc.main", return_value=0) as protoc:
                result = _DecoderWrapper.compile_proto_files("v", "can", temp)
            self.assertTrue(result.endswith("can.pb"))
            protoc.assert_called_once()
            with patch("src.parser.protobuf_manager.LibManager.create_cache_directories",
                       side_effect=lambda _cache, version: str(Path(version) / "proto")), \
                    patch("src.parser.protobuf_manager.os.makedirs"), \
                    patch("src.parser.protobuf_manager.protoc.main", return_value=1):
                with self.assertRaisesRegex(RuntimeError, "Failed to compile"):
                    _DecoderWrapper.compile_proto_files("v", "can", temp)
