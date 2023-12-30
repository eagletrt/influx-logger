import { Configuration } from "./configuration";
import logger from "./logger";
import { estabilishMqttConnection } from "./mqtt";
import mqtt from 'mqtt'

if (Bun.argv.length < 3) {
  logger.fatal(`Configuration file path not provided`)
  process.exit(1)
}

const configurationFile = Bun.file(Bun.argv[2])
let configuration: Configuration 
try {
  configuration = await configurationFile.json()
} catch {
  logger.fatal('Given configuration file doesn\'t exists or doesn\'t contain a valid json')
  process.exit(0)
} finally {
  logger.info('Configuration succesfully loaded')
}

let connection: mqtt.MqttClient
logger.info(`Trying connecting to ${configuration.mqtt_url}:${configuration.mqtt_port}`)
try {
  connection = await estabilishMqttConnection(configuration.mqtt_url, configuration.mqtt_port)
}
catch {
  logger.fatal('Cannot estabilish connection with MQTT server')
  process.exit(1)
}
finally {
  logger.info('MQTT connection successfully estabilished')
}

logger.info('Subscribing to the version topic')
connection.subscribe('+/+/version')

