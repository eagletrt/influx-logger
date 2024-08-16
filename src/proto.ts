import global from "./global";
import { downloadProtoVersion } from "./http";
import logger from "./logger";
import protobufjs from "protobufjs";

export async function getProtoDescriptor(version: string, network: string) {
  let descriptorRaw: string;
  try {
    descriptorRaw = await downloadProtoVersion(version, network);
  } catch (c) {
    logger.trace(c);
    logger.error(
      `Proto descriptor for network '${network}' (version ${version}) cannot be downloaded`,
    );
    return;
  }
  logger.info("Descriptor successfully downloaded");

  try {
    global.versionDescriptors[version][network] = protobufjs.parse(
      descriptorRaw,
    )
      .root.lookupType(`${network}.Pack`);
  } catch (e) {
    logger.trace(e);
    logger.error(
      `Downloaded proto descriptor for network '${network}' (version ${version}) is not a valid proto file`,
    );
    return;
  }
  logger.info(
    "Descriptor successfully parsed and is now ready for deserialize data",
  );
}
