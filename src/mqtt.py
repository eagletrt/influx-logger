import time
import re
from typing import Callable, Dict

import paho.mqtt.client as mqtt

from src.logger_utils import logger
from src.handlers import handle_data_message, handle_version_message

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, _userdata, _flags, reason_code, properties=None):
    print(f"Connected with result code {reason_code}")
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("$SYS/#")

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    handle_incoming_message(msg.topic, msg.payload)

def on_log(client, userdata, level, buf):
    logger.debug(f"MQTT: {buf}")

def estabilish_mqtt_connection(url: str, port: int = 1883) -> mqtt.Client:
    mqttc = mqtt.Client()
    mqttc.on_log = on_log
    mqttc.on_connect = on_connect
    mqttc.on_message = on_message
    mqttc.enable_logger(logger)
    retries = 5
    delay = 5  # seconds

    for attempt in range(1, retries + 1):
        try:
            logger.info(f"Connecting to MQTT broker at {url}:{port} (Attempt {attempt}/{retries})...")
            mqttc.connect(host=url, port=port)
            return mqttc
        except Exception as e:
            logger.warning(f"Connection attempt {attempt} failed: {e}")
            if attempt < retries:
                time.sleep(delay)
            else:
                logger.fatal(f"Failed to connect to MQTT server at {url}:{port} after {retries} attempts.")
                raise Exception(f"Cannot connect to MQTT server at {url}:{port}") from e
    return mqttc


def build_topic_regex(topic: str) -> re.Pattern:
    pattern = topic.replace("/", "\\/").replace("+", "([^\\/]+)").replace("#", ".*")
    return re.compile(pattern)


topic_handlers: Dict[str, Callable] = {
    "+/+/version": handle_version_message,
    "+/+/data/+": handle_data_message,
}


def handle_incoming_message(topic: str, payload: bytes) -> None:
    logger.info(f"Received message on topic {topic}")
    for handler_topic, handler_function in topic_handlers.items():
        matches = list(build_topic_regex(handler_topic).finditer(topic))
        if matches:
            logger.debug(f"Topic has matched {handler_topic}")
            groups = list(matches[0].groups())
            handler_function(topic, payload, groups)


__all__ = ["estabilish_mqtt_connection", "handle_incoming_message", "topic_handlers", "build_topic_regex"]
