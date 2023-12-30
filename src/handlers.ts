import logger from "./logger";
import global from './global'

export async function handleVersionMessage(topic: string, payload: Buffer, [vehicleId, deviceId]: string[]) {
  logger.info(`Subscribing to data topics for the new device (${vehicleId}/${deviceId})`)
  global.connection.subscribe(`${vehicleId}/${deviceId}/data/+`)
  global.deviceVersions[`${vehicleId}/${deviceId}`] = payload.toString()
}
