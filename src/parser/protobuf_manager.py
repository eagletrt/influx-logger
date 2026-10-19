'''
    Manages the retrieval and caching of protobuf descriptors for different versions and networks.
'''

import os
from typing import Any

from google.protobuf import json_format
from google.protobuf.descriptor import FieldDescriptor
from google.protobuf.descriptor_pb2 import FileDescriptorSet  # pylint: disable=no-name-in-module
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message_factory import GetMessageClass, MessageFactory
from grpc_tools import protoc

from src.parser.libmanager import LibcanManager, LibgpsManager, LibManager
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
            except Exception as e:  # pylint: disable=broad-exception-caught
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
        except Exception:  # pylint: disable=broad-exception-caught
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
        decoded = self._json_format.MessageToDict(
            message,
            preserving_proto_field_name=True,
            use_integers_for_enums=True,
        )
        return self._restore_descriptor_types(
            decoded, getattr(message, "DESCRIPTOR", None))

    @staticmethod
    def _restore_descriptor_types(value: Any, descriptor: Any) -> Any:
        """Restore protobuf scalar types after converting a message to a dict.

        The JSON representation is intentionally generic, while InfluxDB
        distinguishes integer and floating-point field types. Use the
        descriptor as the source of truth before creating ``Line`` objects.
        """
        if not isinstance(value, dict) or descriptor is None:
            return value

        fields_by_name = {
            field.json_name: field
            for field in descriptor.fields
        }
        fields_by_name.update(
            {field.name: field
             for field in descriptor.fields})

        restored: dict[str, Any] = {}
        for key, field_value in value.items():
            field = fields_by_name.get(key)
            if field is None:
                restored[key] = field_value
                continue
            restored[key] = _DecoderWrapper._restore_field_type(
                field_value, field)
        return restored

    @staticmethod
    def _restore_field_type(value: Any, field: Any) -> Any:
        """Restore a decoded field according to its protobuf descriptor."""
        if field.is_repeated:
            if field.message_type is not None and field.message_type.GetOptions(
            ).map_entry:
                value_field = field.message_type.fields_by_name["value"]
                return {
                    key:
                    _DecoderWrapper._restore_scalar_or_message(
                        item, value_field)
                    for key, item in value.items()
                }
            return [
                _DecoderWrapper._restore_scalar_or_message(item, field)
                for item in value
            ]
        return _DecoderWrapper._restore_scalar_or_message(value, field)

    @staticmethod
    def _restore_scalar_or_message(value: Any, field: Any) -> Any:
        """Restore a scalar or recursively restore a nested message."""
        if field.message_type is not None:
            return _DecoderWrapper._restore_descriptor_types(
                value, field.message_type)
        if field.type in (FieldDescriptor.TYPE_FLOAT,
                          FieldDescriptor.TYPE_DOUBLE):
            return float(value)
        if field.type in (
                FieldDescriptor.TYPE_INT32, FieldDescriptor.TYPE_SINT32,
                FieldDescriptor.TYPE_SFIXED32, FieldDescriptor.TYPE_INT64,
                FieldDescriptor.TYPE_SINT64, FieldDescriptor.TYPE_SFIXED64,
                FieldDescriptor.TYPE_UINT32, FieldDescriptor.TYPE_FIXED32,
                FieldDescriptor.TYPE_UINT64, FieldDescriptor.TYPE_FIXED64,
                FieldDescriptor.TYPE_ENUM):
            return int(value)
        return value

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
        except Exception:  # pylint: disable=broad-exception-caught
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
            #message_class = MessageFactory(pool).GetPrototype(
            #    message_descriptor)
            get_prototype = getattr(MessageFactory(pool), "GetPrototype")
            message_class = get_prototype(message_descriptor)
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
        LibManager.create_cache_directories(cache, version_dir)
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
        except Exception:  # pylint: disable=broad-exception-caught
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
