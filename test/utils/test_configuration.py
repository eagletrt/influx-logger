from unittest import TestCase

from src.utils.configuration import Configuration

class TestConfiguration(TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def setUp(self):
        self.config = Configuration(
            mqtt_url="mqtt://localhost",
            mqtt_port=1883,
            influx_url="http://localhost",
            influx_port=8086,
            influx_token="token",
            influx_org="org",
            influx_bucket="bucket",
            excluded_networks=["192.168.1.0/24"]
        )

    def test_configuration_initialization(self):
        self.assertEqual(self.config.mqtt_url, "mqtt://localhost")
        self.assertEqual(self.config.mqtt_port, 1883)
        self.assertEqual(self.config.influx_url, "http://localhost")
        self.assertEqual(self.config.influx_port, 8086)
        self.assertEqual(self.config.influx_token, "token")
        self.assertEqual(self.config.influx_org, "org")
        self.assertEqual(self.config.influx_bucket, "bucket")
        self.assertEqual(self.config.excluded_networks, ["192.168.1.0/24"])

    def test_load_from_file(self):
        # Assuming a valid config.json file exists in the current directory
        config = Configuration.load_from_file("config.json")
        self.assertIsInstance(config, Configuration)
        self.assertIsNotNone(config.mqtt_url)
        self.assertIsNotNone(config.mqtt_port)
        self.assertIsNotNone(config.influx_url)
        self.assertIsNotNone(config.influx_port)
        self.assertIsNotNone(config.influx_token)
        self.assertIsNotNone(config.influx_org)
        self.assertIsNotNone(config.influx_bucket)
