from src.global_influx import global_state
from src.http_client import download_proto_version
from src.logger_utils import logger
import os
import tempfile


class _DecoderWrapper:
    def __init__(self, message_class, json_format_module):
        self._message_class = message_class
        self._json_format = json_format_module

    def decode(self, payload: bytes):
        message = self._message_class()
        message.ParseFromString(payload)
        return self._json_format.MessageToDict(message, preserving_proto_field_name=True)


def _build_decoder(descriptor_raw: str, network: str):
    try:
        from google.protobuf import descriptor_pb2, descriptor_pool, json_format, message_factory
        from grpc_tools import protoc
    except Exception as e:
        raise RuntimeError(
            "Missing protobuf runtime/compiler dependencies. Install 'protobuf' and 'grpcio-tools'."
        ) from e

    with tempfile.TemporaryDirectory(prefix="influx_proto_") as tmp_dir:
        proto_file = os.path.join(tmp_dir, f"{network}.proto")
        descriptor_set_file = os.path.join(tmp_dir, "descriptor_set.pb")

        with open(proto_file, "w", encoding="utf-8") as fh:
            fh.write(descriptor_raw)

        result = protoc.main(
            [
                "protoc",
                f"-I{tmp_dir}",
                f"--descriptor_set_out={descriptor_set_file}",
                "--include_imports",
                proto_file,
            ]
        )
        if result != 0:
            raise RuntimeError("Failed to compile downloaded .proto descriptor")

        file_set = descriptor_pb2.FileDescriptorSet()
        with open(descriptor_set_file, "rb") as fh:
            file_set.ParseFromString(fh.read())

    pool = descriptor_pool.DescriptorPool()
    for file_proto in file_set.file:
        pool.Add(file_proto)

    # Keep parity with the original TypeScript implementation, which expects
    # the top-level message type `${network}.Pack`.
    full_name = f"{network}.Pack"
    try:
        message_descriptor = pool.FindMessageTypeByName(full_name)
    except KeyError:
        candidates = [
            desc.full_name
            for file_proto in file_set.file
            for desc in file_proto.message_type
            if desc.name == "Pack"
        ]
        if not candidates:
            raise RuntimeError(f"Cannot find protobuf message type '{full_name}'")
        message_descriptor = pool.FindMessageTypeByName(candidates[0])

    try:
        message_class = message_factory.GetMessageClass(message_descriptor)
    except AttributeError:
        message_class = message_factory.MessageFactory(pool).GetPrototype(message_descriptor)

    return _DecoderWrapper(message_class, json_format)


def get_proto_descriptor(version: str, network: str) -> None:
    try:
        descriptor_raw = download_proto_version(version, network)
    except Exception as c:
        logger.trace(c)
        logger.error(f"Proto descriptor for network '{network}' (version {version}) cannot be downloaded")
        return

    logger.info("Descriptor successfully downloaded")

    try:
        decoder = _build_decoder(descriptor_raw, network)

        if version not in global_state.version_descriptors:
            global_state.version_descriptors[version] = {}
        global_state.version_descriptors[version][network] = decoder
    except Exception as e:
        logger.trace(e)
        logger.error(f"Downloaded proto descriptor for network '{network}' (version {version}) is not a valid proto file")
        return

    logger.info("Descriptor successfully parsed and is now ready for deserialize data")


__all__ = ["get_proto_descriptor"]
