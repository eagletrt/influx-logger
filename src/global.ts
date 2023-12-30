import { MqttClient } from "mqtt";

export type Configuration = {
  mqtt_url: string,
  mqtt_port: number
}

export type Global = {
  configuration: Configuration,
  connection: MqttClient,
  deviceVersions: { [k: string]: string }
}

const _global = global as typeof globalThis & Global

if (!_global.deviceVersions) {
  _global.deviceVersions = {}
}

export default _global

