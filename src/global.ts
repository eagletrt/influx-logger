import { MqttClient } from "mqtt";
import { Configuration } from "./configuration";

export type Global = {
  configuration: Configuration,
  connection: MqttClient
}

const _global = global as typeof globalThis & Global

export default _global
