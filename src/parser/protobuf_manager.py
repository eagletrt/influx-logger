import os
import sys

from typing import Any
from requests import get
from types import ModuleType
from grpc_tools import protoc
from google.protobuf import json_format
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.descriptor_pb2 import FileDescriptorSet
from google.protobuf.message_factory import MessageFactory, GetMessageClass
from importlib.util import spec_from_loader, spec_from_file_location, module_from_spec

from src.utils.logger_utils import logger

class ProtobufManager:
    '''
    Manages the retrieval and caching of protobuf descriptors for different versions and networks.
    '''
    def __init__(self, cache_folder: str = ".cache"):
        self.version_descriptors: dict[str, dict[str, Any]] = {}
        ''' Version descriptors maps version -> network -> protobuf type/object'''
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.generated_proto_root = os.path.join(self.project_root, cache_folder, "proto")
        sys.path.insert(0, self.project_root)
        sys.path.insert(0, self.generated_proto_root)

    def proto_version_downloaded(self, version: str, network: str) -> bool:
        '''
        Checks if the protobuf descriptor for the current version is already downloaded and cached.
        Returns:
            bool: True if the protobuf descriptor is already downloaded, False otherwise.
        '''
        version_dir = os.path.join(LibCANManager.CACHE_DIR, version)
        '''Directory in the cache where the .proto file for the specified version will be stored'''
        proto_file_path = os.path.join(version_dir, "proto", f"{network}.proto")
        '''Path to the .proto file for the specified version and network'''
        if os.path.exists(proto_file_path):
            logger.info(f"protobuf_manager: Descriptor for network '{network}' (version {version}) already downloaded")
            return True
        return False

    def download_proto_descriptor(self, version: str, network: str) -> None:
        '''
        Retrieves the protobuf descriptor for a given version and network.
        If the descriptor is not already cached, it will be downloaded and parsed.
        Args:
            version (str): The version of the protobuf descriptor.
            network (str): The network for which the protobuf descriptor is needed.
        '''
        if not self.proto_version_downloaded(version, network):
            download_result: bool = LibCANManager.download_proto_version(version, network)
            '''Descriptor raw is the raw content of the downloaded protobuf descriptor'''
            if not download_result:
                logger.error(f"protobuf_manager: descriptor for network '{network}' (version {version}) cannot be downloaded")
                return
            logger.info(f"protobuf_manager: Descriptor successfully downloaded: {network} (version {version})")
        try:
            decoder = _DecoderWrapper.build_decoder(version, network)
            '''Decoder is an instance of _DecoderWrapper that can decode messages for the given network'''
            # Ensure the version exists in the version_descriptors dictionary
            if version not in self.version_descriptors:
                self.version_descriptors[version] = {}
            # Store the decoder in the version_descriptors dictionary for the given version and network
            self.version_descriptors[version][network] = decoder
        except Exception as e:
            logger.error(f"protobuf_manager: Downloaded proto descriptor for network '{network}' (version {version}) is not a valid proto file")
            logger.error(e.__traceback__)
            return
        logger.info(f"protobuf_manager: Descriptor {network} (version {version}) successfully parsed and is now ready for deserialize data")
    
    @staticmethod
    def register_generated_proto_package(package_name: str) -> None:
        '''
        Registers a generated protobuf package in sys.modules to allow for dynamic imports of generated modules.
        Args:
            package_name (str): The name of the generated protobuf package to register.
        '''
        protobuf_manager = ProtobufManager()
        '''ProtobufManager instance used for managing protobuf descriptors and decoders'''
        package_path = os.path.join(protobuf_manager.generated_proto_root, package_name)
        '''Path to the generated protobuf package directory'''
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

    @staticmethod
    def load_generated_proto_module(package_name: str, module_name: str) -> None:
        '''
        Loads a generated protobuf module from the specified package and module name.
        Args:
            package_name (str): The name of the generated protobuf package.
            module_name (str): The name of the generated protobuf module to load.
        '''
        protobuf_manager = ProtobufManager()
        '''ProtobufManager instance used for managing protobuf descriptors and decoders'''
        package_path = os.path.join(protobuf_manager.generated_proto_root, package_name)
        '''Path to the generated protobuf package directory'''
        module_path = os.path.join(package_path, f"{module_name}.py")
        '''Path to the generated protobuf module file'''
        if not os.path.isfile(module_path):
            return
        full_name = f"{package_name}.{module_name}"
        '''Fully qualified name of the generated protobuf module'''
        if full_name in sys.modules:
            return
        spec = spec_from_file_location(full_name, module_path)
        '''Module spec for the generated protobuf module'''
        if spec is None or spec.loader is None:
            return
        module = module_from_spec(spec)
        '''Module object for the generated protobuf module'''
        # Set the module in sys.modules and execute it to load the generated protobuf module
        sys.modules[full_name] = module
        # Execute the module to load its contents
        spec.loader.exec_module(module)
        # Set the module as an attribute of the package module to allow for dynamic imports
        setattr(sys.modules[package_name], module_name, module)

class LibCANManager:
    '''
    A utility class for interacting with the CAN repository to check commit existence and download protobuf descriptors.
    '''
    CAN_PROTO_URL:str = (
        "https://raw.githubusercontent.com/eagletrt/can/hash/proto/network/network.proto"
    ) 
    '''URL to the raw .proto file in the CAN repository, where 'hash' and 'network' are placeholders for the commit hash and network name, respectively.'''
    CAN_COMMIT_URL:str = "https://github.com/eagletrt/can/tree/hash"
    '''URL to the commit page in the CAN repository, where 'hash' is a placeholder for the commit hash.'''
    CACHE_DIR: str = "cache"
    '''Cache directory used for storing .proto files and descriptor sets.'''
    
    def __init__(self):
        pass
    
    @staticmethod
    def check_commit_existence(hash: str) -> bool:
        '''
        Checks if a given commit hash exists in the CAN repository.
        Args:
            hash (str): The commit hash to check.
        Returns:
            bool: True if the commit exists, False otherwise.
        '''
        url = LibCANManager.CAN_COMMIT_URL.replace("hash", hash)
        try:
            resp = get(url)
            return resp.ok
        except Exception as e:
            logger.trace(e)
            logger.error(f"protobuf_manager: Failed to check commit existence for hash '{hash}'")
            return False

    @staticmethod
    def download_proto_version(hash: str, network: str) -> bool:
        '''
        Downloads the protobuf descriptor for a given commit hash and network from the CAN repository.
        Args:
            hash (str): The commit hash for which to download the protobuf descriptor.
            network (str): The network for which to download the protobuf descriptor.
        Returns:
            bool: True if the download is successful, False otherwise.
        '''
        url = LibCANManager.CAN_PROTO_URL.replace("hash", hash).replace("network", network)
        '''URL to the raw .proto file in the CAN repository for the specified commit hash and network.'''
        version_dir: str = os.path.join(LibCANManager.CACHE_DIR, hash)
        '''Directory in the cache where the .proto file for the specified commit hash will be stored'''
        try:
            resp = get(url)
            if not resp.ok:
                raise RuntimeError("Failed to download proto")
            if not os.path.exists(LibCANManager.CACHE_DIR):
                os.makedirs(LibCANManager.CACHE_DIR)
            if not os.path.exists(version_dir):
                os.makedirs(version_dir)
            proto_dir = os.path.join(version_dir, "proto")
            if not os.path.exists(proto_dir):
                os.makedirs(proto_dir)
            with open(os.path.join(proto_dir, f"{network}.proto"), "w", encoding="utf-8") as fh:
                fh.write(resp.text)
                return True
        except Exception as e:
            logger.trace(e)
            logger.error(f"protobuf_manager: Failed to download proto for network '{network}' (version {hash})")
            return False

class _DecoderWrapper:
    '''
    A wrapper class for decoding protobuf messages using a specific message class and JSON format module.
    '''
    def __init__(self, message_class, json_format_module, cache_dir: str = LibCANManager.CACHE_DIR):
        '''
        Initializes the _DecoderWrapper with the given message class and JSON format module.
        Args:
            message_class: The protobuf message class used for decoding messages.
            json_format_module: The module used for converting protobuf messages to dictionaries.
        '''
        self._message_class = message_class
        self._json_format = json_format_module
        LibCANManager.CACHE_DIR = cache_dir

    def decode(self, payload: bytes) -> dict:
        '''
        Decodes a protobuf message from the given payload using the stored message class and converts it to a dictionary.
        Args:
            payload (bytes): The raw bytes of the protobuf message to decode.
        Returns:
            dict: A dictionary representation of the decoded protobuf message.
        '''
        message = self._message_class()
        '''Creates an instance of the message class to hold the decoded data'''
        # Parse the payload into the message instance
        message.ParseFromString(payload)
        return self._json_format.MessageToDict(
            message,
            preserving_proto_field_name=True,
            use_integers_for_enums=True,
        )
    
    @staticmethod
    def build_decoder(version: str, network: str) -> '_DecoderWrapper':
        '''
        Builds a decoder for the given protobuf descriptor and network.
        Args:
            version (str): The version for which the decoder is being built.
            network (str): The network for which the decoder is being built.
        Returns:
            _DecoderWrapper: An instance of _DecoderWrapper that can decode messages for the given network.
        '''
        version_dir = os.path.join(LibCANManager.CACHE_DIR, version)
        '''Directory in the cache where the .proto file for the specified version will be stored'''
        # If cache directory does not exist, create it
        if not os.path.exists(LibCANManager.CACHE_DIR):
            os.makedirs(LibCANManager.CACHE_DIR)
        if not os.path.exists(version_dir):
            os.makedirs(version_dir)
        if not os.path.exists(os.path.join(version_dir, "proto")):
            os.makedirs(os.path.join(version_dir, "proto"))
        pb_dir: str = os.path.join(version_dir, "pb")
        '''Directory in the cache where the compiled descriptor set for the specified version will be stored'''
        if not os.path.exists(pb_dir):
            os.makedirs(pb_dir)
        # Create files for the .proto descriptor and the compiled descriptor set
        proto_file: str = os.path.join(version_dir, "proto", f"{network}.proto")
        '''Path to the .proto file for the specified version and network'''
        '''List of .proto file names to be passed to protoc'''
        descriptor_set_file: str = os.path.join(version_dir, "pb", f"{network}.pb")
        '''File that will store the compiled descriptor set'''
        # Compile the .proto file into a descriptor set using protoc
        logger.info(f"protobuf_manager: protoc -I{version_dir} --descriptor_set_out={descriptor_set_file} --include_imports {proto_file}")
        try:
            result = protoc.main(
                [
                    "protoc",
                    f"-I{version_dir}",
                    f"--descriptor_set_out={descriptor_set_file}",
                    "--include_imports",
                    proto_file
                ]
            )
        except Exception as e:
            logger.error(f"protobuf_manager: Failed to compile downloaded .proto descriptor for network '{network}'")
            result = 1
        # Check if the compilation was successful
        if result != 0:
            logger.error(f"protobuf_manager: Failed to compile downloaded .proto descriptor for network '{network}' (version {version})")
            raise RuntimeError("Failed to compile downloaded .proto descriptor")
        file_set: FileDescriptorSet = FileDescriptorSet()
        '''protobuf descriptor set that will be populated with the compiled descriptor data'''
        # Read the compiled descriptor set from the file and parse it into a FileDescriptorSet object
        with open(descriptor_set_file, "rb") as fh:
            file_set.ParseFromString(fh.read())
        # Create a DescriptorPool to register the compiled file descriptors
        pool: DescriptorPool = DescriptorPool()
        '''DescriptorPool that will be used to register the compiled file descriptors'''
        # Add the compiled file descriptors to the DescriptorPool
        for file_proto in file_set.file:
            pool.Add(file_proto)
        # Keep parity with the original TypeScript implementation, which expects
        # the top-level message type `${network}.Pack`.
        full_name = f"{network}.Pack"
        '''Fully qualified name of the top-level message type expected in the DescriptorPool'''
        message_descriptor = None
        '''Descriptor for the top-level message type in the DescriptorPool'''
        try:
            # Find the message descriptor for the top-level message type in the DescriptorPool
            message_descriptor = pool.FindMessageTypeByName(full_name)
        except KeyError:
            # If the message type is not found, search for candidates with the name "Pack"
            candidates = [
                desc.full_name
                for file_proto in file_set.file
                for desc in file_proto.message_type
                if desc.name == "Pack"
            ]
            '''Fully qualified names of message types named "Pack" found in the descriptor set'''
            # If no candidates are found, raise an error indicating that the protobuf message type cannot be found
            if not candidates:
                logger.error(f"protobuf_manager: Cannot find protobuf message type '{full_name}'")
                raise RuntimeError(f"Cannot find protobuf message type '{full_name}'")
            # If candidates are found, log a warning and use the first candidate as the message type
            message_descriptor = pool.FindMessageTypeByName(candidates[0])
            '''Log a warning indicating that the expected message type was not found and that a candidate will be used instead'''
            logger.warning(f"protobuf_manager: Cannot find protobuf message type '{full_name}', using '{candidates[0]}' instead")
        message_class = None
        '''Class corresponding to the found message descriptor, used for decoding protobuf messages'''
        try:
            # Get the message class for the found message descriptor using GetMessageClass
            message_class = GetMessageClass(message_descriptor)
        except AttributeError:
            # If GetMessageClass is not available, use MessageFactory to get the message class
            message_class = MessageFactory(pool).GetPrototype(message_descriptor)
        return _DecoderWrapper(message_class, json_format)

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
    ProtobufManager.register_generated_proto_package(package_name)
    protobuf_manager = ProtobufManager()
    '''ProtobufManager instance used for managing protobuf descriptors and decoders'''
    package_path = os.path.join(protobuf_manager.generated_proto_root, package_name)
    '''Path to the generated protobuf package directory'''
    if os.path.isdir(package_path):
        for file_name in os.listdir(package_path):
            if file_name.endswith(".py") and file_name != "__init__.py":
                ProtobufManager.load_generated_proto_module(package_name, file_name[:-3])
