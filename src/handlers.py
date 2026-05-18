from typing import List

from src.logger_utils import logger
from src.http_client import check_commit_existence
from src.proto import get_proto_descriptor
from src.influx import Line
from src.global_influx import global_state


def handle_version_message(_topic: str, payload: bytes, ids: List[str]) -> None:
    vehicle_id, device_id = ids
    payload_str = payload.decode()
    logger.info(f"Checking existance of commit {payload_str}, requested by device '{vehicle_id}/{device_id}'")
    check = check_commit_existence(payload_str)
    if check:
        logger.info(f"Subscribing to data topics for the new device ({vehicle_id}/{device_id})")
        if global_state.connection:
            global_state.connection.subscribe(f"{vehicle_id}/{device_id}/data/+")
            logger.info(f"Commit {payload_str} exists, device '{vehicle_id}/{device_id}' will be considered")
        global_state.device_versions[f"{vehicle_id}/{device_id}"] = payload_str
        global_state.version_descriptors[payload_str] = {}
        logger.info(f"Device '{vehicle_id}/{device_id}' is now subscribed to data topics")
    else:
        logger.error(f"Device '{vehicle_id}/{device_id}' uses a CAN commit that apparently doesn't exists. This device will not be considered")


def handle_data_message(_topic: str, payload: bytes, ids: List[str]) -> None:
    vehicle_id, device_id, network = ids
    key = f"{vehicle_id}/{device_id}"
    if key not in global_state.device_versions:
        logger.error(f"Device '{key}' started streaming data before sending version. Skipping")
        return

    if global_state.configuration and "excludedNetworks" in global_state.configuration and network in global_state.configuration["excludedNetworks"]:
        logger.debug(f"Network '{network}' is in the exclusion list. Skipping message")
        return

    version = global_state.device_versions[key]

    if network not in global_state.version_descriptors.get(version, {}):
        logger.info(f"Network '{network}' with version {version} never seen before. Downloading .proto descriptor")
        try:
            get_proto_descriptor(version, network)
        except Exception:
            logger.error("Error while getting proto, skipping message")
            return

    try:
        decoder = global_state.version_descriptors[version][network]
        # Expect decoder to provide a `decode` method returning a dict-like object
        message_content = decoder.decode(payload)
    except Exception as e:
        logger.error("Cannot deserialize payload with saved descriptor")
        return

    tags = {
        "vehicle-id": vehicle_id,
        "device-id": device_id,
        "network": network,
    }

    for measurement, records in message_content.items():
        for record in records:
            valid_object = all(
                isinstance(v, (str, int, float, bool)) for v in record.values()
            )
            if not valid_object:
                logger.warn("Invalid object received from device")
                break

            line = Line.from_object(record, measurement, tags)
            if global_state.line_repository:
                global_state.line_repository.push(line)


__all__ = ["handle_version_message", "handle_data_message"]
