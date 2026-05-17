import sys
import json
from .logger import logger
from .mqtt import estabilish_mqtt_connection, handle_incoming_message
from .global import global_state
from .influx import LineRepository


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
    global_state.line_repository = LineRepository(
        cfg["influx_url"], cfg["influx_bucket"], cfg["influx_org"], cfg["influx_token"], "us", 5000
    )

    logger.debug(f"Configuration: {cfg}")

    logger.info(f"Trying connecting to {cfg['mqtt_url']}:{cfg['mqtt_port']}")
    try:
        client = estabilish_mqtt_connection(cfg["mqtt_url"], cfg["mqtt_port"])
        global_state.connection = client
    except Exception:
        logger.fatal("Cannot estabilish connection with MQTT server")
        sys.exit(1)

    logger.info("MQTT connection successfully estabilished")

    logger.info("Subscribing to the version topic")
    client.subscribe("+/+/version")

    # wire the message handler
    client.on_message = lambda client, userdata, msg: handle_incoming_message(msg.topic, msg.payload)
    client.loop_start()


if __name__ == "__main__":
    main()


__all__ = ["main"]
