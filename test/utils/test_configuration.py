"""Tests for application configuration loading."""

from unittest import TestCase

from src.utils.configuration import Configuration, InfluxConfig, MQTTConfig


class TestConfiguration(TestCase):
    """Test the current nested configuration API."""

    def setUp(self):
        """Create a representative configuration."""
        self.config = Configuration(
            mqtt=MQTTConfig(url="mqtt://localhost", port=1883),
            influx=InfluxConfig(
                url="http://localhost",
                port=8086,
                token="token",
                org="org",
                buckets={"default": "bucket"},
            ),
            excluded_networks=["192.168.1.0/24"],
        )

    def test_configuration_initialization(self):
        """Preserve values supplied to the configuration objects."""
        self.assertEqual(self.config.mqtt.url, "mqtt://localhost")
        self.assertEqual(self.config.mqtt.port, 1883)
        self.assertEqual(self.config.influx.url, "http://localhost")
        self.assertEqual(self.config.influx.port, 8086)
        self.assertEqual(self.config.influx.token, "token")
        self.assertEqual(self.config.influx.org, "org")
        self.assertEqual(self.config.influx.buckets, {"default": "bucket"})
        self.assertEqual(self.config.excluded_networks, ["192.168.1.0/24"])

    def test_load_from_file(self):
        """Load the repository configuration file."""
        # Assuming a valid config.json file exists in the current directory
        config = Configuration.load_from_file("config.json")
        self.assertIsInstance(config, Configuration)
        self.assertIsNotNone(config.mqtt)
        self.assertIsNotNone(config.mqtt.url)
        self.assertIsNotNone(config.mqtt.port)
        self.assertIsNotNone(config.influx)
        self.assertIsNotNone(config.influx.url)
        self.assertIsNotNone(config.influx.port)
        self.assertIsNotNone(config.influx.token)
        self.assertIsNotNone(config.influx.org)
        self.assertIsNotNone(config.influx.buckets)
