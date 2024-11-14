import { MqttClient } from "mqtt";
import protobuf from "protobufjs";
import { LineRepository } from "./influx";

export type Configuration = {
  mqtt_url: string;
  mqtt_port: number;
  influx_url: string;
  influx_token: string;
  influx_org: string;
  excludedNetworks: string[];
};

export type Line = {
  measurement: string;
  tags: { [key: string]: string };
  fields: { [key: string]: string | number | boolean };
  timestamp: number;
};

export type Global = {
  configuration: Configuration;
  connection: MqttClient;
  deviceVersions: { [k: string]: string };
  current_bucket: string;
  versionDescriptors: {
    [version: string]: { [network: string]: protobuf.Type };
  };
  lineRepository: LineRepository;
};

const _global = global as typeof globalThis & Global;

if (!_global.deviceVersions) {
  _global.deviceVersions = {};
}
if (!_global.versionDescriptors) {
  _global.versionDescriptors = {};
}

export default _global;
