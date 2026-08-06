from abc import ABC, abstractmethod
import json
import os
import sys

from typing import Any
from requests import get
from types import ModuleType
from grpc_tools import protoc
from google.protobuf import json_format
from importlib.util import spec_from_loader
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.descriptor_pb2 import FileDescriptorSet
from google.protobuf.message_factory import MessageFactory, GetMessageClass

from src.utils.logger_utils import logger

class ProtobufManager:
    '''
    Manages the retrieval and caching of protobuf descriptors for different versions and networks.
    '''
    def __init__(self):
        self.version_descriptors: dict[str, dict[str, Any]] = {}
        ''' Version descriptors maps version -> network -> protobuf type/object'''

    def proto_version_downloaded(self, version: str, network: str) -> bool:
        '''
        Checks if the protobuf descriptor for the current version is already downloaded and cached.
        Returns:
            bool: True if the protobuf descriptor is already downloaded, False otherwise.
        '''
        version_dir = os.path.join(LibcanManager.CACHE_DIR, version)
        '''Directory in the cache where the .proto file for the specified version will be stored'''
        proto_file_path = os.path.join(version_dir, "proto", f"{network}.proto")
        '''Path to the .proto file for the specified version and network'''
        if os.path.exists(proto_file_path):
            logger.info(f"protobuf_manager: Descriptor for network '{network}' (version {version}) already downloaded")
            return True
        return False

    def download_proto_descriptor(self, version: str, network: str) -> bool:
        '''
        Retrieves the protobuf descriptor for a given version and network.
        If the descriptor is not already cached, it will be downloaded and parsed.
        Args:
            version (str): The version of the protobuf descriptor.
            network (str): The network for which the protobuf descriptor is needed.
        '''
        lib_manager = LibcanManager if network != "gps" else LibgpsManager
        '''Library manager class to use based on the network type'''
        if not self.proto_version_downloaded(version, network):
            download_result: bool = lib_manager.download_proto_version(version, network)
            '''Descriptor raw is the raw content of the downloaded protobuf descriptor'''
            if not download_result:
                return False
            logger.info(f"protobuf_manager: Descriptor successfully downloaded: {network} (version {version})")
        try:
            decoder = _DecoderWrapper.build_decoder(version, network, cache=lib_manager)
            '''Decoder is an instance of _DecoderWrapper that can decode messages for the given network'''
            # Ensure the version exists in the version_descriptors dictionary
            if version not in self.version_descriptors:
                self.version_descriptors[version] = {}
            # Store the decoder in the version_descriptors dictionary for the given version and network
            self.version_descriptors[version][network] = decoder
            logger.info(f"protobuf_manager: Descriptor {network} (version {version}) is now ready for deserialize data")
        except Exception as e:
            logger.error(f"protobuf_manager: Downloaded proto descriptor for network '{network}' (version {version}) is not a valid proto file")
            return False
        logger.info(f"protobuf_manager: Descriptor {network} (version {version}) successfully parsed and is now ready for deserialize data")
        return True

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

class LibManager(ABC):
    '''
    A utility class for interacting with the CAN and GPS repositories to check commit existence and download protobuf descriptors.
    '''
    CACHE_DIR: str = "cache"
    '''Base cache directory used for storing .proto files and descriptor sets.'''
    @staticmethod
    def check(hash: str, url: str|list[str], token: str = None) -> bool:
        '''
        Checks if a given commit hash exists in the repository.
        Args:
            hash (str): The commit hash to check.
            url (str|list[str]): The URL or list of URLs to check.
            token (str): The GitHub personal access token for authentication.
        Returns:
            bool: True if the commit exists, False otherwise.
        '''
        headers:json = {}
        # If a GitHub token is provided, include it in the request headers for authentication
        if token and token != "":
            headers:json = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                }
        # Check the existence of the commit hash in the CAN repository by sending a GET request to the commit URLs
        for url in url if isinstance(url, list) else [url]:
            check_url = url.replace("hash", hash)
            try:
                resp = get(check_url, headers=headers)
                logger.info(f"protobuf_manager: url: {check_url}, headers: {headers}")
                if resp.ok:
                    return True
                else:
                    logger.error(f"protobuf_manager: Response: {resp.status_code} - {resp.text}")
            except Exception as e:
                logger.error(f"protobuf_manager: Failed to check commit existence for hash '{hash}' at URL '{check_url}'")
                logger.error(f"protobuf_manager: {e}")
        return False
    @staticmethod
    @abstractmethod
    def check_commit_existence(hash: str) -> bool:
        '''
        Checks if a given commit hash exists in the repository.
        Args:
            hash (str): The commit hash to check.
        Returns:
            bool: True if the commit exists, False otherwise.
        '''
        raise NotImplementedError("Subclasses must implement the check_commit_existence method.")
    @staticmethod
    def download(hash: str, network: str, in_url: str|list[str], cache: str, token: str = None) -> bool:
        '''
        Downloads the protobuf descriptor for a given commit hash and network from the repository.
        Args:
            hash (str): The commit hash for which to download the protobuf descriptor.
            network (str): The network for which to download the protobuf descriptor.
            url (str|list[str]): The URL or list of URLs from which to download the protobuf descriptor.
            cache (str): The path to the cache directory where the downloaded proto file will be stored.
            token (str): The GitHub personal access token for authentication.
        Returns:
            bool: True if the download is successful, False otherwise.
        '''
        headers:json = {}
        # If a GitHub token is provided, include it in the request headers for authentication
        if token and token != "":
            headers:json = {
                "Authorization": f"Bearer {token}",
                }
        version_dir: str = os.path.join(cache, hash)
        '''Directory in the cache where the .proto file for the specified commit hash will be stored'''
        urls: list[str] = []
        '''List of URLs to check for the protobuf descriptor'''
        # If in_url is a list, use it directly; if it's a string, convert it to a list
        if isinstance(in_url, list):
            urls = in_url
        elif isinstance(in_url, str):
            urls.append(in_url)
        for url_sample in urls:
            try:
                url:str = url_sample.replace("hash", hash).replace("network", network)
                logger.info(f"protobuf_manager: URL: {url}")
                resp = get(url, headers=headers)
                if resp and resp.ok:
                    break
            except Exception:
                logger.error(f"protobuf_manager: Error while downloading proto for network '{network}' (version {hash})")
        if not resp or not resp.ok:
            logger.error(f"protobuf_manager: Proto for network '{network}' (version {hash}) not downloaded")
            if resp:
                logger.error(f"protobuf_manager: Response: {resp.status_code} - {resp.text}")
            else:
                logger.error(f"protobuf_manager: No response received for network '{network}' (version {hash})")
            return False
        try:
            if not os.path.exists(LibManager.CACHE_DIR):
                os.makedirs(LibManager.CACHE_DIR)
            if not os.path.exists(cache):
                os.makedirs(cache)
            if not os.path.exists(version_dir):
                os.makedirs(version_dir)
            proto_dir = os.path.join(version_dir, "proto")
            if not os.path.exists(proto_dir):
                os.makedirs(proto_dir)
            with open(os.path.join(proto_dir, f"{network}.proto"), "w", encoding="utf-8") as fh:
                fh.write(resp.text)
                return True
        except Exception:
            logger.error(f"protobuf_manager: Failed to save downloaded proto for network '{network}' (version {hash})")
            return False
        return False
    @staticmethod
    @abstractmethod
    def download_proto_version(hash: str, network: str) -> bool:
        '''
        Downloads the protobuf descriptor for a given commit hash and network from the repository.
        Args:
            hash (str): The commit hash for which to download the protobuf descriptor.
            network (str): The network for which to download the protobuf descriptor.
        Returns:
            bool: True if the download is successful, False otherwise.
        '''
        raise NotImplementedError("Subclasses must implement the download_proto_version method.")

class LibcanManager(LibManager):
    '''
    A utility class for interacting with the CAN repository to check commit existence and download protobuf descriptors.
    '''
    token: str = None
    '''GitHub personal access token used for authentication when accessing the CAN repository.'''

    CAN_COMMIT_URL:str = "https://api.github.com/repos/eagletrt/can/commits/hash"
    '''URL to the commit page in the can repository, where 'hash' is a placeholder for the commit hash.'''
    LIBCAN_COMMIT_URL:str = CAN_COMMIT_URL.replace("can", "libcan-sw")
    '''URL to the commit page in the libcan-sw repository, where 'hash' is a placeholder for the commit hash.'''
    CAN_COMMIT_URLS:list[str] = [
        CAN_COMMIT_URL,
        LIBCAN_COMMIT_URL,
    ]
    '''URLs to the commit pages in the can and libcan-sw repositories, where 'hash' is a placeholder for the commit hash.'''

    CAN_PROTO_URL:str = "https://raw.githubusercontent.com/eagletrt/can/hash/proto/network/network.proto"
    '''URL to the raw .proto file in the can repository, where 'hash' and 'network' are placeholders for the commit hash and network name, respectively.'''
    LIBCAN_PROTO_URL:str = CAN_PROTO_URL.replace("can", "libcan-sw")
    '''URL to the raw .proto file in the libcan-sw repository, where 'hash' and 'network' are placeholders for the commit hash and network name, respectively.'''
    CAN_PROTO_URLS:list[str] = [
        CAN_PROTO_URL,
        LIBCAN_PROTO_URL,
    ]
    '''URLs to the raw .proto files in the can and libcan-sw repositories, where 'hash' and 'network' are placeholders for the commit hash and network name, respectively.'''

    CACHE_DIR:str = os.path.join(LibManager.CACHE_DIR, "can")
    '''Cache directory used for storing .proto files and descriptor sets for CAN.'''
    
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
        return LibManager.check(hash, LibcanManager.CAN_COMMIT_URLS, token=LibcanManager.token)
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
        return LibManager.download(hash, network, LibcanManager.CAN_PROTO_URLS, cache=LibcanManager.CACHE_DIR, token=LibcanManager.token)
class LibgpsManager(LibManager):
    '''
    A utility class for interacting with the GPS repository to check commit existence.
    '''
    GPS_COMMIT_URL:str = "https://api.github.com/repos/eagletrt/gpslib/commits/hash"
    '''URL to the commit page in the gps repository, where 'hash' is a placeholder for the commit hash.'''
    GPS_PROTO_URL:str = "https://raw.githubusercontent.com/eagletrt/gpslib/hash/network.proto"
    '''URL to the raw .proto file in the gps repository, where 'hash' and 'network' are placeholders for the commit hash and network name, respectively.'''

    CACHE_DIR:str = os.path.join(LibManager.CACHE_DIR, "gps")
    '''Cache directory used for storing .proto files and descriptor sets for GPS.'''

    @staticmethod
    def check_commit_existence(hash: str) -> bool:
        '''
        Checks if a given commit hash exists in the GPS repository.
        Args:
            hash (str): The commit hash to check.
        Returns:
            bool: True if the commit exists, False otherwise.
        '''
        return LibManager.check(hash, LibgpsManager.GPS_COMMIT_URL)
    @staticmethod
    def download_proto_version(hash: str, network: str) -> bool:
        '''
        Downloads the protobuf descriptor for a given commit hash and network from the GPS repository.
        Args:
            hash (str): The commit hash for which to download the protobuf descriptor.
            network (str): The network for which to download the protobuf descriptor.
        Returns:
            bool: True if the download is successful, False otherwise.
        '''
        return LibManager.download(hash, network, LibgpsManager.GPS_PROTO_URL, cache=LibgpsManager.CACHE_DIR)

class _DecoderWrapper:
    '''
    A wrapper class for decoding protobuf messages using a specific message class and JSON format module.
    '''
    def __init__(self, message_class, json_format_module):
        '''
        Initializes the _DecoderWrapper with the given message class and JSON format module.
        Args:
            message_class: The protobuf message class used for decoding messages.
            json_format_module: The module used for converting protobuf messages to dictionaries.
        '''
        self._message_class = message_class
        self._json_format = json_format_module

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
    def build_decoder(version: str, network: str, lib_manager: type = LibManager) -> '_DecoderWrapper':
        '''
        Builds a decoder for the given protobuf descriptor and network.
        Args:
            version (str): The version for which the decoder is being built.
            network (str): The network for which the decoder is being built.
        Returns:
            _DecoderWrapper: An instance of _DecoderWrapper that can decode messages for the given network.
        '''
        version_dir = os.path.join(cache, version)
        '''Directory in the cache where the .proto file for the specified version will be stored'''
        cache: str = lib_manager.CACHE_DIR
        '''Cache directory used for storing .proto files and descriptor sets for the specified library'''
        # If cache directory does not exist, create it
        if not os.path.exists(cache):
            os.makedirs(cache)
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
        pack_name: str = "Pack"
        if lib_manager == LibgpsManager:
            pack_name = "GpsPack"
        full_name = f"{network}.{pack_name}"
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

    def __str__(self):
        return f"_DecoderWrapper(message_class={self._message_class}, json_format_module={self._json_format})"
