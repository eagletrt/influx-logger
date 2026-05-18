import re
from typing import Callable, Dict

import paho.mqtt.client as mqtt

from src.logger_utils import logger
from src.handlers import handle_data_message, handle_version_message


def estabilish_mqtt_connection(url: str, port: int = 1883) -> mqtt.Client:
    client = mqtt.Client()
    client.connect(host=url, port=port)
    return client


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
