import logger from "./logger";
import global, { Line } from './global'
import { checkCommitExistance, downloadProtoVersion } from "./http";
import protobufjs from 'protobufjs'

export async function handleVersionMessage(topic: string, payload: Buffer, [vehicleId, deviceId]: string[]) {
  logger.info(`Checking existance of commit ${payload.toString()}, requested by device '${vehicleId}/${deviceId}'`)
  const check = await checkCommitExistance(payload.toString())
  if (check) {
    logger.info(`Subscribing to data topics for the new device (${vehicleId}/${deviceId})`)
    global.connection.subscribe(`${vehicleId}/${deviceId}/data/+`)
    global.deviceVersions[`${vehicleId}/${deviceId}`] = payload.toString()
    global.versionDescriptors[payload.toString()] = {}
  }
  else {
    logger.error(`Device '${vehicleId}/${deviceId}' uses a CAN commit that apparently doesn't exists. This device will not be considered`)
  }
}

export async function handleDataMessage(topic: string, payload: Buffer, [vehicleId, deviceId, network]: string[]) {

  if (!(`${vehicleId}/${deviceId}` in global.deviceVersions)) {
    logger.error(`Device '${vehicleId}/${deviceId}' started streaming data before sending version. Skipping`)
    return
  }

  const version = global.deviceVersions[`${vehicleId}/${deviceId}`]

  if (!(network in global.versionDescriptors[version])) {
    logger.info(`Network '${network}' with version ${version} never seen before. Downloading .proto descriptor`)

    let descriptorRaw: string
    try {
      descriptorRaw = await downloadProtoVersion(version, network)
    } catch {
      logger.error(`Proto descriptor for network '${network}' (version ${version}) cannot be downloaded`)
      return
    }
    logger.info('Descriptor successfully downloaded')

    try {
      global.versionDescriptors[version][network] = protobufjs.parse(descriptorRaw)
        .root.lookupType(`${network}.Pack`)
    } catch (e) {
      logger.trace(e)
      logger.error(`Downloaded proto descriptor for network '${network}' (version ${version}) is not a valid proto file`)
      return
    }
    logger.info('Descriptor successfully parsed and is now ready for deserialize data')
  } 

  let messageContent: { [key: string]: { [key: string]: string | number | boolean }[] }
  try {
    messageContent = global.versionDescriptors[version][network].decode(payload).toJSON()
  } catch (e) {
    logger.trace(e)
    logger.error('Cannot deserialized payload with saved descriptor')
    return
  }

  for (const measurement in messageContent) {
    for (const rawLine of messageContent[measurement]) {
      let timestamp: number
      let tags: { [key: string]: string }
      let fields: { [key: string]: string | number | boolean }

      for (const field in rawLine) {
        logger.trace(`${field}: ${rawLine[field]}`)
      }
    }     
  }
}
