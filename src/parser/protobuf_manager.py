'''
    Manages the retrieval and caching of protobuf descriptors for different versions and networks.
'''

import json
import os
from abc import ABC, abstractmethod
from typing import Any

from google.protobuf import json_format
from google.protobuf.descriptor_pb2 import FileDescriptorSet
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message_factory import GetMessageClass, MessageFactory
from grpc_tools import protoc
from requests import get

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
        # Directory in the cache where the .proto file for the specified version will be stored
        version_dir = os.path.join(LibcanManager.CACHE_DIR, version)
        # Path to the .proto file for the specified version and network
        proto_file_path = os.path.join(version_dir, "proto",
                                       f"{network}.proto")
        if os.path.exists(proto_file_path):
            logger.info(
                "protobuf_manager: Descriptor for network '%s' (version %s) already downloaded",
                network, version)
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
        # Library manager class to use based on the network type
        lib_manager = LibcanManager if network != "gps" else LibgpsManager
        if not self.proto_version_downloaded(version, network):
            # Descriptor raw is the raw content of the downloaded protobuf descriptor
            download_result: bool = lib_manager.download_proto_version(
                version, network)
            if not download_result:
                return False
            logger.info(
                "protobuf_manager: Descriptor successfully downloaded: %s (version %s)",
                network, version)
        try:
            try:
                # Instance of _DecoderWrapper that can decode messages for the given network
                decoder = _DecoderWrapper.build_decoder(
                    version=version, network=network, lib_manager=lib_manager)
            except Exception as e:
                logger.error(
                    "protobuf_manager: Failed to build decoder for network '%s' (version %s): %s",
                    network, version, e)
                return False
            logger.info(
                "protobuf_manager: Descriptor successfully parsed: %s (version %s)",
                network, version)
            # Ensure the version exists in the version_descriptors dictionary
            if version not in self.version_descriptors:
                logger.info(
                    "protobuf_manager: Creating new entry for version %s in version_descriptors",
                    version)
                self.version_descriptors[version] = {}
            # Store decoder in version_descriptors dictionary for the given version and network
            self.version_descriptors[version][network] = decoder
            logger.info(
                "protobuf_manager: Descriptor %s (version %s) is now ready for deserialize data",
                network, version)
        except Exception:
            logger.error(
                "protobuf_manager: " \
                "Downloaded proto descriptor for network '%s' "
                "(version %s) is not a valid proto file",
                network,
                version
            )
            return False
        logger.info(
            "protobuf_manager: " \
            "Descriptor %s (version %s) successfully parsed and is now ready for deserialize data",
            network,
            version
        )
        return True


class LibManager(ABC):
    '''
    A utility class for interacting with the CAN and GPS repositories 
    to check commit existence and download protobuf descriptors.
    '''
    CACHE_DIR: str = "cache"
    '''Base cache directory used for storing .proto files and descriptor sets.'''

    @staticmethod
    def check(commit_hash: str,
              urls: str | list[str],
              token: str = None) -> bool:
        '''
        Checks if a given commit hash exists in the repository.
        Args:
            commit_hash (str): The commit hash to check.
            urls (str|list[str]): The URL or list of URLs to check.
            token (str): The GitHub personal access token for authentication.
        Returns:
            bool: True if the commit exists, False otherwise.
        '''
        headers: json = {}
        # If a GitHub token is provided, include it in the request headers for authentication
        if token and token != "":
            headers: json = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            }
        # Check the existence of the commit hash in the CAN repository
        # by sending a GET request to the commit URLs
        for repo_url in urls if isinstance(urls, list) else [urls]:
            check_url = repo_url.replace("hash", commit_hash)
            try:
                resp = get(check_url, headers=headers, timeout=10)
                logger.info("protobuf_manager: url: %s, headers: %s",
                            check_url, headers)
                if resp.ok:
                    return True
                # If the request fails, log a warning with the status code and response text
                logger.warning(
                    "protobuf_manager: Request to %s failed with status code %s: %s",
                    check_url, resp.status_code, resp.text)
            except Exception as e:
                logger.error(
                    "protobuf_manager: " \
                    "Failed to check commit existence for hash '%s' at URL '%s'",
                    commit_hash,
                    check_url
                )
                logger.error("protobuf_manager: %s", e)
        return False

    @staticmethod
    @abstractmethod
    def check_commit_existence(commit_hash: str) -> bool:
        '''
        Checks if a given commit hash exists in the repository.
        Args:
            commit_hash (str): The commit hash to check.
        Returns:
            bool: True if the commit exists, False otherwise.
        '''
        raise NotImplementedError(
            "Subclasses must implement the check_commit_existence method.")

    @staticmethod
    def download(commit_hash: str,
                 network: str,
                 in_url: str | list[str],
                 cache: str,
                 token: str = None) -> bool:
        '''
        Downloads the protobuf descriptor for a given commit hash and network from the repository.
        Args:
            commit_hash (str): The commit hash for which to download the protobuf descriptor
            network (str): The network for which to download the protobuf descriptor
            url (str|list[str]): URL or list of URLs from which to download the protobuf descriptor
            cache (str): Path to the cache directory where the downloaded proto file will be stored
            token (str): The GitHub personal access token for authentication
        Returns:
            bool: True if the download is successful, False otherwise
        '''
        headers: json = {}
        # If a GitHub token is provided, include it in the request headers for authentication
        if token and token != "":
            headers: json = {
                "Authorization": f"Bearer {token}",
            }
        # Directory in the cache where the .proto file for the specified commit hash will be stored
        version_dir: str = os.path.join(cache, commit_hash)
        # List of URLs to check for the protobuf descriptor
        urls: list[str] = []
        # If in_url is a list, use it directly; if it's a string, convert it to a list
        if isinstance(in_url, list):
            urls = in_url
        elif isinstance(in_url, str):
            urls.append(in_url)
        for url_sample in urls:
            try:
                url: str = url_sample.replace("hash", commit_hash).replace(
                    "network", network)
                logger.info("protobuf_manager: URL: %s", url)
                resp = get(url, headers=headers, timeout=10)
                if resp and resp.ok:
                    break
            except Exception:
                logger.error(
                    "protobuf_manager: "
                    "Error while downloading proto for network '%s' (version %s)",
                    network, commit_hash)
        if not resp or not resp.ok:
            logger.warning(
                "protobuf_manager: Proto for network '%s' (version %s) not downloaded %s",
                network, commit_hash,
                resp.status_code if resp else 'No response')
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
            with open(os.path.join(proto_dir, f"{network}.proto"),
                      "w",
                      encoding="utf-8") as fh:
                fh.write(resp.text)
                return True
        except Exception:
            logger.error(
                "protobuf_manager: "
                "Failed to save downloaded proto for network '%s' (version %s)",
                network, commit_hash)
            return False
        return False

    @staticmethod
    @abstractmethod
    def download_proto_version(commit_hash: str, network: str) -> bool:
        '''
        Downloads the protobuf descriptor for a given commit hash and network from the repository.
        Args:
            commit_hash (str): The commit hash for which to download the protobuf descriptor.
            network (str): The network for which to download the protobuf descriptor.
        Returns:
            bool: True if the download is successful, False otherwise.
        '''
        raise NotImplementedError(
            "Subclasses must implement the download_proto_version method.")


class LibcanManager(LibManager):
    '''
    A utility class for interacting with the CAN repository to 
    check commit existence and download protobuf descriptors.
    '''

    TOKEN: str = None
    '''GitHub personal access token used for authentication when accessing the CAN repository.'''
    CAN_COMMIT_URL: str = "https://api.github.com/repos/eagletrt/can/commits/hash"
    '''URL to the commit page in the can repository'''
    LIBCAN_COMMIT_URL: str = CAN_COMMIT_URL.replace("can", "libcan-sw")
    '''URL to the commit page in the libcan-sw repository'''
    CAN_COMMIT_URLS: list[str] = [
        CAN_COMMIT_URL,
        LIBCAN_COMMIT_URL,
    ]
    '''URLs to the commit pages in the can and libcan-sw repositories'''

    CAN_PROTO_URL: str = "https://raw.githubusercontent.com" \
    "/eagletrt/can/hash/proto/network/network.proto"
    '''URL to the raw .proto file in the can repository'''
    LIBCAN_PROTO_URL: str = CAN_PROTO_URL.replace("can", "libcan-sw")
    '''URL to the raw .proto file in the libcan-sw repository'''
    CAN_PROTO_URLS: list[str] = [
        CAN_PROTO_URL,
        LIBCAN_PROTO_URL,
    ]
    '''URLs to the raw .proto files in the can and libcan-sw repositories'''

    CACHE_DIR: str = os.path.join(LibManager.CACHE_DIR, "can")
    '''Cache directory used for storing .proto files and descriptor sets for CAN.'''

    @staticmethod
    def check_commit_existence(commit_hash: str) -> bool:
        '''
        Checks if a given commit hash exists in the CAN repository.
        Args:
            commit_hash (str): The commit hash to check.
        Returns:
            bool: True if the commit exists, False otherwise.
        '''
        return LibManager.check(commit_hash,
                                LibcanManager.CAN_COMMIT_URLS,
                                token=LibcanManager.TOKEN)

    @staticmethod
    def download_proto_version(commit_hash: str, network: str) -> bool:
        '''
        Downloads the protobuf descriptor for a given 
        commit hash and network from the CAN repository.
        Args:
            commit_hash (str): The commit hash for which to download the protobuf descriptor.
            network (str): The network for which to download the protobuf descriptor.
        Returns:
            bool: True if the download is successful, False otherwise.
        '''
        return LibManager.download(commit_hash,
                                   network,
                                   LibcanManager.CAN_PROTO_URLS,
                                   cache=LibcanManager.CACHE_DIR,
                                   token=LibcanManager.TOKEN)


class LibgpsManager(LibManager):
    '''
    A utility class for interacting with the GPS repository to check commit existence.
    '''
    GPS_COMMIT_URL: str = "https://api.github.com" \
        "/repos/eagletrt/gpslib/commits/hash"
    '''URL to the commit page in the gps repository'''
    GPS_PROTO_URL: str = "https://raw.githubusercontent.com" \
        "/eagletrt/gpslib/hash/network.proto"
    '''URL to the raw .proto file in the gps repository'''

    CACHE_DIR: str = os.path.join(LibManager.CACHE_DIR, "gps")
    '''Cache directory used for storing .proto files and descriptor sets for GPS.'''

    @staticmethod
    def check_commit_existence(commit_hash: str) -> bool:
        '''
        Checks if a given commit hash exists in the GPS repository.
        Args:
            commit_hash (str): The commit hash to check.
        Returns:
            bool: True if the commit exists, False otherwise.
        '''
        return LibManager.check(commit_hash, LibgpsManager.GPS_COMMIT_URL)

    @staticmethod
    def download_proto_version(commit_hash: str, network: str) -> bool:
        '''
        Downloads the protobuf descriptor for a given 
        commit hash and network from the GPS repository.
        Args:
            commit_hash (str): The commit hash for which to download the protobuf descriptor.
            network (str): The network for which to download the protobuf descriptor.
        Returns:
            bool: True if the download is successful, False otherwise.
        '''
        logger.info(
            "protobuf_manager: Downloading GPS proto for network '%s' (version %s),",
            network, commit_hash)
        return LibManager.download(commit_hash,
                                   network,
                                   LibgpsManager.GPS_PROTO_URL,
                                   cache=LibgpsManager.CACHE_DIR)


class _DecoderWrapper:
    '''
    A wrapper class for decoding protobuf messages using 
    a specific message class and JSON format module.
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
        Decodes a protobuf message from the given payload using 
        the stored message class and converts it to a dictionary.
        Args:
            payload (bytes): The raw bytes of the protobuf message to decode.
        Returns:
            dict: A dictionary representation of the decoded protobuf message.
        '''
        # Creates an instance of the message class to hold the decoded data
        message = self._message_class()
        # Parse the payload into the message instance
        message.ParseFromString(payload)
        return self._json_format.MessageToDict(
            message,
            preserving_proto_field_name=True,
            use_integers_for_enums=True,
        )

    @staticmethod
    def build_decoder(version: str,
                      network: str,
                      lib_manager: type = LibManager) -> '_DecoderWrapper':
        '''
        Builds a decoder for the given protobuf descriptor and network.
        Args:
            version (str): The version for which the decoder is being built.
            network (str): The network for which the decoder is being built.
        Returns:
            _DecoderWrapper: Message decoder for the given network.
        '''
        try:
            logger.info("protobuf_manager: Lib_manager '%s'",
                        lib_manager.__name__)
            # Cache directory used for storing .proto files and
            # descriptor sets for the specified library
            cache: str = lib_manager.CACHE_DIR
            logger.info("protobuf_manager: Using cache directory '%s'", cache)
        except Exception:
            logger.error(
                "protobuf_manager: Invalid lib_manager provided." \
                "It must have a CACHE_DIR attribute."
            )
            raise
        descriptor_set_file = _DecoderWrapper.compile_proto_files(
            version, network, cache)
        # protobuf descriptor set that will be populated with the compiled descriptor data
        file_set: FileDescriptorSet = FileDescriptorSet()
        # Read the compiled descriptor set from the file and
        # parse it into a FileDescriptorSet object
        with open(descriptor_set_file, "rb") as fh:
            file_set.ParseFromString(fh.read())
        return _DecoderWrapper.build_message_prototype(network, lib_manager,
                                                       file_set)

    @staticmethod
    def build_message_prototype(network: str, lib_manager: type,
                                file_set: FileDescriptorSet):
        '''
        Builds a message prototype for the given protobuf descriptor and network.
        Args:
            network (str): The network for which the message prototype is being built
            lib_manager (type): The library manager type
            file_set (FileDescriptorSet): file set containing the compiled protobuf descriptors
        Returns:
            _DecoderWrapper: Message decoder for the given network.
        '''
        # Create a DescriptorPool to register the compiled file descriptors
        # DescriptorPool that will be used to register the compiled file descriptors
        pool: DescriptorPool = DescriptorPool()
        # Add the compiled file descriptors to the DescriptorPool
        for file_proto in file_set.file:
            pool.Add(file_proto)
        # Keep parity with the original TypeScript implementation, which expects
        # the top-level message type `${network}.Pack`.
        pack_name: str = "Pack"
        if lib_manager == LibgpsManager:
            pack_name = "GpsPack"
        # Fully qualified name of the top-level message type expected in the DescriptorPool
        full_name = f"{network}.{pack_name}"
        # Descriptor for the top-level message type in the DescriptorPool
        message_descriptor = None
        try:
            # Find the message descriptor for the top-level message type in the DescriptorPool
            message_descriptor = pool.FindMessageTypeByName(full_name)
        except KeyError:
            # If the message type is not found, search for candidates with the name "Pack"
            # Fully qualified names of message types named "Pack" found in the descriptor set
            candidates = [
                desc.full_name for file_proto in file_set.file
                for desc in file_proto.message_type if desc.name == "Pack"
            ]
            # If no candidates are found,
            # raise an error indicating that the protobuf message type cannot be found
            if not candidates:
                logger.error(
                    "protobuf_manager: Cannot find protobuf message type '%s'",
                    full_name)
                raise RuntimeError(
                    "Cannot find protobuf message type '{full_name}'"
                ) from KeyError(full_name)
            # If candidates are found,
            # log a warning and use the first candidate as the message type
            # Log a warning indicating that the expected message
            # type was not found and that a candidate will be used instead
            message_descriptor = pool.FindMessageTypeByName(candidates[0])
            logger.warning(
                "protobuf_manager: Cannot find protobuf message type '%s', using '%s' instead",
                full_name, candidates[0])
        # Class corresponding to the found message descriptor,
        # used for decoding protobuf messages
        message_class = None
        try:
            # Get the message class for the found message descriptor using GetMessageClass
            message_class = GetMessageClass(message_descriptor)
        except AttributeError:
            # If GetMessageClass is not available, use MessageFactory to get the message class
            message_class = MessageFactory(pool).GetPrototype(
                message_descriptor)
        return _DecoderWrapper(message_class, json_format)

    @staticmethod
    def compile_proto_files(version: str, network: str, cache: str):
        '''
        Compiles the .proto files for the specified version and network into a descriptor set.
        Args:
            version (str): The version for which the .proto files are being compiled.
            network (str): The network for which the .proto files are being compiled.
            cache (str): The cache directory where the .proto files and descriptor sets are stored.
        Returns:
            str: The path to the compiled descriptor set file.
        '''
        # Directory in the cache where the .proto file for the specified version will be stored
        version_dir: str = os.path.join(cache, version)
        # If cache directory does not exist, create it
        if not os.path.exists(cache):
            os.makedirs(cache)
        if not os.path.exists(version_dir):
            os.makedirs(version_dir)
        proto_dir = os.path.join(version_dir, "proto")
        if not os.path.exists(proto_dir):
            os.makedirs(proto_dir)
        version_pb_dir = os.path.join(version_dir, "pb")
        if not os.path.exists(version_pb_dir):
            os.makedirs(version_pb_dir)
        # Create files for the .proto descriptor and the compiled descriptor set
        # Path to the .proto file for the specified version and network
        proto_file: str = os.path.join(version_dir, "proto",
                                       f"{network}.proto")
        # File that will store the compiled descriptor set
        descriptor_set_file: str = os.path.join(version_dir, "pb",
                                                f"{network}.pb")
        # Compile the .proto file into a descriptor set using protoc
        logger.info(
            "protobuf_manager: protoc -I%s --descriptor_set_out=%s --include_imports %s",
            version_dir, descriptor_set_file, proto_file)
        try:
            result = protoc.main([
                "protoc", f"-I{version_dir}",
                f"--descriptor_set_out={descriptor_set_file}",
                "--include_imports", proto_file
            ])
        except Exception:
            logger.error(
                "protobuf_manager: " \
                    "Failed to compile downloaded .proto descriptor for network '%s'",
                network
            )
            result = 1
        # Check if the compilation was successful
        if result != 0:
            logger.error(
                "protobuf_manager: " \
                    "Failed to compile downloaded .proto descriptor for network '%s' (version %s)",
                network,
                version
            )
            raise RuntimeError(
                "Failed to compile downloaded .proto descriptor")
        return descriptor_set_file

    def __str__(self):
        return "_DecoderWrapper" \
            f"(message_class={self._message_class}, " \
            f"json_format_module={self._json_format})"
