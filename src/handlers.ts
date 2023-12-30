import logger from "./logger";
import global from './global'
import { checkCommitExistance } from "./http";

export async function handleVersionMessage(topic: string, payload: Buffer, [vehicleId, deviceId]: string[]) {
  logger.info(`Checking existance of commit ${payload.toString()}, requested by device '${vehicleId}/${deviceId}'`)
  const check = await checkCommitExistance(payload.toString())
  if (check) {
    logger.info(`Subscribing to data topics for the new device (${vehicleId}/${deviceId})`)
    global.connection.subscribe(`${vehicleId}/${deviceId}/data/+`)
    global.deviceVersions[`${vehicleId}/${deviceId}`] = payload.toString()
  }
  else {
    logger.error(`Device '${vehicleId}/${deviceId}' uses a CAN commit that apparently doesn't exists. This device will not be considered`)
  }
}
