from typing import Any, Dict, List

from utils.logger_utils import logger
from src.http_client import check_commit_existence
from parser.proto import get_proto_descriptor
from src.influx import Line
from global_influx import global_state


def _unwrap_values(values: Any) -> Any:
    if isinstance(values, dict):
        return values.get("values")
    return values


def _expand_columnar_record(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    timestamps = _unwrap_values(record.get("timestamp"))
    values_map = record.get("valuesMap", {})

    if not isinstance(timestamps, list):
        raise ValueError("Missing or invalid timestamp")
    if not isinstance(values_map, dict):
        raise ValueError("Missing or invalid values map")

    rows: List[Dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps):
        row: Dict[str, Any] = {"timestamp": timestamp}

        for field_name, field_values in values_map.items():
            values = _unwrap_values(field_values)
            if isinstance(values, list) and index < len(values):
                row[field_name] = values[index]

        rows.append(row)

    return rows


def _push_record(measurement: str, record: Any, tags: Dict[str, str]) -> None:
    if isinstance(record, dict) and "valuesMap" in record and "timestamp" in record:
        for row in _expand_columnar_record(record):
            line = Line.from_object(row, measurement, tags)
            if global_state.line_repository:
                global_state.line_repository.push(line)
        return

    if not isinstance(record, dict):
        logger.warn(f"Handler: Invalid object received from device for measurement '{measurement}'")
        return

    line = Line.from_object(record, measurement, tags)
    if global_state.line_repository:
        global_state.line_repository.push(line)


def handle_version_message(_topic: str, payload: bytes, ids: List[str]) -> None:
    vehicle_id, device_id = ids
    payload_str = payload.decode()
    logger.info(f"Handler: Checking existance of commit {payload_str}, requested by device '{vehicle_id}/{device_id}'")
    check = check_commit_existence(payload_str)
    if check:
        logger.info(f"Handler: Subscribing to data topics for the new device ({vehicle_id}/{device_id})")
        if global_state.connection:
            global_state.connection.subscribe(f"{vehicle_id}/{device_id}/data/+")
            logger.info(f"Commit {payload_str} exists, device '{vehicle_id}/{device_id}' will be considered")
        global_state.device_versions[f"{vehicle_id}/{device_id}"] = payload_str
        global_state.version_descriptors[payload_str] = {}
        logger.info(f"Device '{vehicle_id}/{device_id}' is now subscribed to data topics")
    else:
        logger.error(f"Handler: Device '{vehicle_id}/{device_id}' uses a CAN commit that apparently doesn't exists. This device will not be considered")


def handle_data_message(_topic: str, payload: bytes, ids: List[str]) -> None:
    vehicle_id, device_id, network = ids
    key = f"{vehicle_id}/{device_id}"
    if key not in global_state.device_versions:
        logger.error(f"Handler: Device '{key}' started streaming data before sending version. Skipping")
        return

    if global_state.configuration and "excludedNetworks" in global_state.configuration and network in global_state.configuration["excludedNetworks"]:
        logger.debug(f"Handler: Network '{network}' is in the exclusion list. Skipping message")
        return

    version = global_state.device_versions[key]

    if network not in global_state.version_descriptors.get(version, {}):
        logger.info(f"Handler: Network '{network}' with version {version} never seen before. Downloading .proto descriptor")
        try:
            get_proto_descriptor(version, network)
        except Exception:
            logger.error(f"Handler: Error while getting proto, skipping message")
            return

    try:
        decoder = global_state.version_descriptors[version][network]
        # Expect decoder to provide a `decode` method returning a dict-like object
        message_content = decoder.decode(payload)
    except Exception as e:
        logger.error(f"Handler: Cannot deserialize payload with saved descriptor: {e}")
        return

    tags = {
        "vehicle-id": vehicle_id,
        "device-id": device_id,
        "network": network,
    }

    if "valuesPack" in message_content and isinstance(message_content["valuesPack"], dict):
        message_content = message_content["valuesPack"]

    for measurement, records in message_content.items():
        if isinstance(records, list):
            for record in records:
                try:
                    _push_record(measurement, record, tags)
                except ValueError as e:
                    #logger.error(f"Handler: Skipping invalid record for measurement '{measurement}': {e}")
                    pass
            continue
        else:
            try:
                _push_record(measurement, records, tags)
            except ValueError as e:
                #logger.error(f"Handler: Skipping invalid record for measurement '{measurement}': {e}")
                pass


__all__ = ["handle_version_message", "handle_data_message"]
