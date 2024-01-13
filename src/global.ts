import { MqttClient } from "mqtt";
import protobuf from 'protobufjs'

export type Configuration = {
  mqtt_url: string,
  mqtt_port: number
}

export type Line = {
  measurement: string,
  tags: { [key: string]: string },
  fields: { [key: string]: string | number | boolean },
  timestamp: number
}

export type Global = {
  configuration: Configuration,
  connection: MqttClient,
  deviceVersions: { [k: string]: string }
  versionDescriptors: { [version: string]: { [network: string]: protobuf.Type } }
  linesBuffer: Line[]
}

const _global = global as typeof globalThis & Global

if (!_global.deviceVersions) {
  _global.deviceVersions = {}
}
if (!_global.versionDescriptors) {
  _global.versionDescriptors = {}
}
if (!_global.linesBuffer) {
  _global.linesBuffer = []
}

export default _global

