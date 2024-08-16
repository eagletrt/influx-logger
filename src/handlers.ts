import logger from "./logger";
import global from "./global";
import { checkCommitExistance } from "./http";
import { getProtoDescriptor } from "./proto";
import { Line } from "./influx";

export async function handleVersionMessage(
  _topic: string,
  payload: Buffer,
  [vehicleId, deviceId]: string[],
) {
  logger.info(
    `Checking existance of commit ${payload.toString()}, requested by device '${vehicleId}/${deviceId}'`,
  );
  const check = await checkCommitExistance(payload.toString());
  if (check) {
    logger.info(
      `Subscribing to data topics for the new device (${vehicleId}/${deviceId})`,
    );
    global.connection.subscribe(`${vehicleId}/${deviceId}/data/+`);
    global.deviceVersions[`${vehicleId}/${deviceId}`] = payload.toString();
    global.versionDescriptors[payload.toString()] = {};
  } else {
    logger.error(
      `Device '${vehicleId}/${deviceId}' uses a CAN commit that apparently doesn't exists. This device will not be considered`,
    );
  }
}

export async function handleDataMessage(
  _topic: string,
  payload: Buffer,
  [vehicleId, deviceId, network]: string[],
) {
  if (!(`${vehicleId}/${deviceId}` in global.deviceVersions)) {
    logger.error(
      `Device '${vehicleId}/${deviceId}' started streaming data before sending version. Skipping`,
    );
    return;
  }

  const version = global.deviceVersions[`${vehicleId}/${deviceId}`];

  if (!(network in global.versionDescriptors[version])) {
    logger.info(
      `Network '${network}' with version ${version} never seen before. Downloading .proto descriptor`,
    );
    try {
      await getProtoDescriptor(version, network);
    } catch {
      logger.error("Error while getting proto, skipping message");
    }
  }

  let messageContent: {
    [key: string]: { [key: string]: string | number | boolean }[];
  };
  try {
    messageContent = global.versionDescriptors[version][network].decode(payload)
      .toJSON();
  } catch (e) {
    logger.trace(e);
    logger.error("Cannot deserialized payload with saved descriptor");
    return;
  }

  const tags: { [key: string]: string } = {
    "vehicle-id": vehicleId,
    "device-id": deviceId,
    "network": network,
  };

  for (const measurement in messageContent) {
    for (const record in messageContent[measurement]) {
      const validObject = Object.values(
        messageContent[measurement][record],
      ).every(
        (field) =>
          typeof field === "string" ||
          typeof field === "number" ||
          typeof field === "boolean",
      );

      if (!validObject) {
        logger.warn("Invalid object received from device");
        break;
      }

      const line = Line.fromObject(
        messageContent[measurement][record],
        measurement,
        tags,
      );

      await global.lineRepository.push(line);
    }
  }
}
