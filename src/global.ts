import { MqttClient } from "mqtt";
import protobuf from 'protobufjs'

export type Configuration = {
  mqtt_url: string,
  mqtt_port: number
}

export type Global = {
  configuration: Configuration,
  connection: MqttClient,
  deviceVersions: { [k: string]: string }
  versionDescriptors: { [version: string]: { [network: string]: protobuf.Type } }
}

const _global = global as typeof globalThis & Global

if (!_global.deviceVersions) {
  _global.deviceVersions = {}
}
if (!_global.versionDescriptors) {
  _global.versionDescriptors = {}
}

export default _global

