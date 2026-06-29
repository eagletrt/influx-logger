import os
import sys
from typing import Any
from requests import get
from types import ModuleType
from tempfile import TemporaryDirectory
from importlib.util import spec_from_loader, spec_from_file_location, module_from_spec

from src.utils.logger_utils import logger

# TODO: Comments and documentation
# TODO: improve readability
def _register_generated_proto_package(package_name: str):
    package_path = os.path.join(generated_proto_root, package_name)
    if not os.path.isdir(package_path):
        return

    module = ModuleType(package_name)
    module.__path__ = [package_path]
    module.__package__ = package_name
    module.__file__ = os.path.join(package_path, "__init__.py")
    module.__spec__ = spec_from_loader(package_name, loader=None, is_package=True)
    if module.__spec__ is not None:
        module.__spec__.submodule_search_locations = [package_path]

    sys.modules[package_name] = module

def _load_generated_proto_module(package_name: str, module_name: str):
    package_path = os.path.join(generated_proto_root, package_name)
    module_path = os.path.join(package_path, f"{module_name}.py")
    if not os.path.isfile(module_path):
        return

    full_name = f"{package_name}.{module_name}"
    if full_name in sys.modules:
        return

    spec = spec_from_file_location(full_name, module_path)
    if spec is None or spec.loader is None:
        return

    module = module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    setattr(sys.modules[package_name], module_name, module)

for package_name in [
    "actions",
    "app",
    "can",
    "configs",
    "data",
    "handcart",
    "influxlogger",
    "lapcounter",
    "mongodb",
    "sessions",
    "telemetry",
    "tpms",
]:
    _register_generated_proto_package(package_name)
    package_path = os.path.join(generated_proto_root, package_name)
    if os.path.isdir(package_path):
        for file_name in os.listdir(package_path):
            if file_name.endswith(".py") and file_name != "__init__.py":
                _load_generated_proto_module(package_name, file_name[:-3])

# TODO: documentation
class ProtobuffManager:
    def __init__(self, cache_folder: str = ".cache"):
        self.version_descriptors: dict[str, dict[str, Any]]
        ''' Version descriptors maps version -> network -> protobuf type/object'''
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.generated_proto_root = os.path.join(project_root, cache_folder, ".generated/external/serializers/proto")

        sys.path.insert(0, self.project_root)
        sys.path.insert(0, self.generated_proto_root)

    def get_proto_descriptor(self, version: str, network: str) -> None:
        try:
            descriptor_raw = LibCANManager.download_proto_version(version, network)
        except Exception as c:
            logger.trace(c)
            logger.error(f"Proto: descriptor for network '{network}' (version {version}) cannot be downloaded")
            return

        logger.info("Proto: Descriptor successfully downloaded")

        try:
            decoder = _DecoderWrapper._build_decoder(descriptor_raw, network)

            if version not in self.version_descriptors:
                self.version_descriptors[version] = {}
            self.version_descriptors[version][network] = decoder
        except Exception as e:
            logger.trace(e)
            logger.error(f"Proto: Downloaded proto descriptor for network '{network}' (version {version}) is not a valid proto file")
            return

        logger.info("Proto: Descriptor successfully parsed and is now ready for deserialize data")

class LibCANManager:
    CAN_PROTO_URL = (
    "https://raw.githubusercontent.com/eagletrt/can/hash/proto/network/network.proto"
    )
    CAN_COMMIT_URL = "https://github.com/eagletrt/can/tree/hash"
    def __init__(self):
        pass
    
    @staticmethod
    def check_commit_existence(hash: str) -> bool:
        url = LibCANManager.CAN_COMMIT_URL.replace("hash", hash)
        resp = get(url)
        return resp.ok
    
    @staticmethod
    def download_proto_version(hash: str, network: str) -> str:
        url = LibCANManager.CAN_PROTO_URL.replace("hash", hash).replace("network", network)
        resp = get(url)
        if not resp.ok:
            raise RuntimeError("Failed to download proto")
        return resp.text
    
class _DecoderWrapper:
    def __init__(self, message_class, json_format_module):
        self._message_class = message_class
        self._json_format = json_format_module

    def decode(self, payload: bytes):
        message = self._message_class()
        message.ParseFromString(payload)
        return self._json_format.MessageToDict(message, preserving_proto_field_name=True)
    
    @staticmethod
    def _build_decoder(descriptor_raw: str, network: str) -> _DecoderWrapper:
        # TODO: Improve readability
        try:
            from google.protobuf import descriptor_pb2, descriptor_pool, json_format, message_factory
            from grpc_tools import protoc
        except Exception as e:
            raise RuntimeError(
                "Missing protobuf runtime/compiler dependencies. Install 'protobuf' and 'grpcio-tools'."
            ) from e

        with TemporaryDirectory(prefix="influx_proto_") as tmp_dir:
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
