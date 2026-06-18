import sys
import json
from utils.logger_utils import logger
from src.mqtt import estabilish_mqtt_connection, handle_incoming_message
from global_influx import global_state
from src.influx import LineRepository


def main(argv=None):
    argv = argv or sys.argv
    if len(argv) < 2:
        logger.fatal("Configuration file path not provided")
        sys.exit(1)

    config_path = argv[1]
    try:
        with open(config_path, "r") as fh:
            global_state.configuration = json.load(fh)
    except Exception:
        logger.fatal("Given configuration file doesn't exists or doesn't contain a valid json")
        sys.exit(1)

    logger.info("Configuration succesfully loaded")

    cfg = global_state.configuration
    try:
        global_state.line_repository = LineRepository(
            url=cfg["influx_url"],
            bucket=cfg["influx_bucket"],
            org=cfg["influx_org"],
            token=cfg["influx_token"]
        )
    except Exception as e:
        logger.fatal("Cannot estabilish connection with InfluxDB")
        logger.fatal("Current configuration: " + str(cfg))
        logger.fatal("Error: " + str(e))
        logger.fatal("Traceback: " + str(e.with_traceback()))
        sys.exit(1)

    logger.debug(f"Configuration: {cfg}")

    logger.info(f"Trying connecting to {cfg['mqtt_url']}:{cfg['mqtt_port']}")
    try:
        client = estabilish_mqtt_connection(cfg["mqtt_url"], cfg["mqtt_port"])
        global_state.connection = client
    except Exception as e:
        logger.fatal("Cannot estabilish connection with MQTT server with configuration: " + str(cfg))
        sys.exit(1)

    logger.info("MQTT connection successfully estabilished")

    try:
        client.subscribe("+/+/version")
    except Exception as e:
        logger.fatal("Cannot subscribe to MQTT topic with configuration: " + str(cfg))
        logger.fatal("Error: " + str(e))
        sys.exit(1)
    try:
        client.loop_forever()
    except Exception as e:
        logger.fatal("MQTT loop interrupted")
        logger.info("Configuration: " + str(cfg))
        sys.exit(1)

if __name__ == "__main__":
    main()


__all__ = ["main"]
