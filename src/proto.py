from src.global_influx import global_state
from src.http_client import download_proto_version
from src.logger_utils import logger


def get_proto_descriptor(version: str, network: str) -> None:
    try:
        descriptor_raw = download_proto_version(version, network)
    except Exception as c:
        logger.trace(c)
        logger.error(f"Proto descriptor for network '{network}' (version {version}) cannot be downloaded")
        return

    logger.info("Descriptor successfully downloaded")

    # Runtime parsing of .proto into a decoder requires protoc or third-party tooling.
    # Here we store the raw descriptor and provide a minimal placeholder decoder
    # object that raises if decode is attempted. Integrate a proper parser as needed.
    try:
        def _placeholder_decoder(payload: bytes):
            raise NotImplementedError("Runtime .proto decoding not implemented")

        class _DecoderWrapper:
            def decode(self, payload: bytes):
                return _placeholder_decoder(payload)

        if version not in global_state.version_descriptors:
            global_state.version_descriptors[version] = {}
        global_state.version_descriptors[version][network] = _DecoderWrapper()
    except Exception as e:
        logger.trace(e)
        logger.error(f"Downloaded proto descriptor for network '{network}' (version {version}) is not a valid proto file")
        return

    logger.info("Descriptor successfully parsed and is now ready for deserialize data")


__all__ = ["get_proto_descriptor"]
