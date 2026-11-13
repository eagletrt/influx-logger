"""Tests for configuration conversion and loading."""

import json
import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

from src.utils.configuration import Configuration, InfluxConfig, MQTTConfig


class TestConfiguration(TestCase):
    """
    Test configuration conversion, normalization, and loading from file or environment.
    """

    def test_influx_config_round_trip_and_string(self):
        """
        Test that InfluxConfig can be converted to/from dict and string representations.
        """
        config = InfluxConfig.from_dict({
            "url": "localhost",
            "port": "8086",
            "token": "secret",
            "org": "team",
            "buckets": {
                "adr": "a"
            },
        })
        self.assertEqual(config.port, 8086)
        self.assertEqual(
            InfluxConfig.from_dict(config.to_dict()).to_dict(),
            config.to_dict())
        self.assertEqual(json.loads(str(config)), config.to_dict())
        self.assertEqual(InfluxConfig("u", 1, "t", "o").buckets, {})

    def test_mqtt_config_defaults_and_round_trip(self):
        """
        Test that MQTTConfig defaults are applied and round-trip conversion works.
        """
        with patch("src.utils.configuration.random.randint", return_value=9):
            config = MQTTConfig.from_dict({"url": "broker"})
        self.assertEqual(config.port, 1883)
        self.assertEqual(config.client_id, "influx-logger-000009")
        restored = MQTTConfig.from_dict(config.to_dict())
        self.assertEqual(restored.to_dict(), config.to_dict())
        self.assertEqual(json.loads(str(config)), config.to_dict())

    def test_configuration_normalizes_optional_values(self):
        """
        Test that optional values are normalized to None when empty.
        """
        config = Configuration(excluded_networks=[],
                               vehicle_whitelist=[],
                               github_token="",
                               log_on_mqtt="")
        self.assertEqual(config.excluded_networks, [])
        self.assertIsNone(config.vehicle_whitelist)
        self.assertIsNone(config.github_token)
        self.assertIsNone(config.log_on_mqtt)
        self.assertEqual(json.loads(str(config))["mqtt"], None)

    def test_load_from_file(self):
        """
        Test loading configuration from a JSON file and default values.
        """
        source = {
            "mqtt": {
                "url": "broker"
            },
            "influx": {
                "url": "db",
                "token": "t",
                "org": "o"
            },
            "excluded_networks": ["gps"],
            "vehicle_whitelist": ["v1"],
            "github_token": "gh",
            "log_on_mqtt": "logs"
        }
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as file:
            json.dump(source, file)
            file.flush()
            config = Configuration.load_from_file(file.name)
        self.assertEqual(config.mqtt.port, 1883)
        self.assertEqual(config.influx.port, 8086)
        self.assertEqual(config.excluded_networks, ["gps"])
        self.assertEqual(config.vehicle_whitelist, ["v1"])
        self.assertEqual(config.github_token, "gh")
        self.assertEqual(config.log_on_mqtt, "logs")

    def test_load_from_env_and_invalid_mqtt_port(self):
        """
        Test loading configuration from environment variables and handling invalid MQTT port.
        """
        env = {
            "INFLUX": '{"logs":{"url":"db","token":"t","org":"o"}}',
            "MQTT_URL": "broker",
            "MQTT_PORT": "1884",
            "VEHICLE_WHITELIST": '["v"]',
            "EXCLUDED_NETWORKS": '["gps"]',
            "GITHUB_TOKEN": "gh",
            "LOG_ON_MQTT": "topic"
        }
        with patch.dict(os.environ, env, clear=True):
            config = Configuration.load_from_env()
        self.assertEqual(config.mqtt.port, 1884)
        self.assertEqual(config.influx["logs"].url, "db")
        self.assertEqual(config.vehicle_whitelist, ["v"])
        self.assertEqual(config.excluded_networks, ["gps"])
        with patch.dict(os.environ, {"MQTT_PORT": "bad"}, clear=True):
            with self.assertRaisesRegex(ValueError,
                                        "MQTT_PORT must be an integer"):
                Configuration.load_from_env()
