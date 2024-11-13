import logger from "./logger";
import { estabilishMqttConnection, handleIncomingMessage } from "./mqtt";
import global from "./global";
import { LineRepository } from "./influx";



if (Bun.argv.length < 3) {
  logger.fatal(`Configuration file path not provided`);
  process.exit(1);
}

const configurationFile = Bun.file(Bun.argv[2]);
try {
  global.configuration = await configurationFile.json();
} catch {
  logger.fatal(
    "Given configuration file doesn't exists or doesn't contain a valid json",
  );
  process.exit(0);
}
logger.info("Configuration succesfully loaded");

global.lineRepository = new LineRepository(
  global.configuration.influx_url,
  global.configuration.influx_bucket,
  global.configuration.influx_org,
  global.configuration.influx_token,
  "us",
  5000,
);

logger.debug(`Configuration: ${JSON.stringify(global.configuration)}`);

logger.info(
  `Trying connecting to ${global.configuration.mqtt_url}:${global.configuration.mqtt_port}`,
);
try {
  global.connection = await estabilishMqttConnection(
    global.configuration.mqtt_url,
    global.configuration.mqtt_port,
  );
} catch {
  logger.fatal("Cannot estabilish connection with MQTT server");
  process.exit(1);
}
logger.info("MQTT connection successfully estabilished");

logger.info("Subscribing to the version topic");
global.connection.subscribe("+/+/version");

global.connection.on("message", handleIncomingMessage);
