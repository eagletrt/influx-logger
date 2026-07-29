import json
import os
from typing import Dict, List, Optional


class InfluxConfig:
    """
    Configuration for a single InfluxDB connection.

    Attributes:
        url (str): The URL of the InfluxDB instance.
        port (int): The port number of the InfluxDB instance.
        token (str): The authentication token for InfluxDB.
        org (str): The organization name in InfluxDB.
        bucket (str): The bucket name in InfluxDB.
    """

    def __init__(
        self,
        url: str,
        port: int,
        token: str,
        org: str,
        bucket: str
    ):
        self.url: str = url
        self.port: int = int(port)
        self.token: str = token
        self.org: str = org
        self.bucket: str = bucket

    @staticmethod
    def from_dict(data: dict) -> "InfluxConfig":
        '''
        Creates an InfluxConfig instance from a dictionary.
        Args:
            data (dict): A dictionary containing InfluxDB configuration.
        Returns:
            InfluxConfig: An instance of InfluxConfig populated with data from the dictionary.
        '''
        return InfluxConfig(
            url=data.get("url"),
            port=data.get("port", 8086),
            token=data.get("token"),
            org=data.get("org"),
            bucket=data.get("bucket")
        )

    def to_dict(self) -> dict:
        '''
        Converts the InfluxConfig instance to a dictionary.
        Returns:
            dict: A dictionary representation of the InfluxConfig instance.
        '''
        return {
            "url": self.url,
            "port": self.port,
            "token": self.token,
            "org": self.org,
            "bucket": self.bucket,
        }

    def __str__(self):
        return json.dumps(self.to_dict(), indent=4)

class MQTTConfig:
    """
    Configuration for an MQTT connection.

    Attributes:
        url (str): The URL of the MQTT broker.
        port (int): The port number of the MQTT broker.
    """

    def __init__(self, url: str, port: int):
        self.url: str = url
        self.port: int = int(port)

    @staticmethod
    def from_dict(data: dict) -> "MQTTConfig":
        '''
        Creates an MQTTConfig instance from a dictionary.
        Args:
            data (dict): A dictionary containing MQTT configuration.
        Returns:
            MQTTConfig: An instance of MQTTConfig populated with data from the dictionary.
        '''
        return MQTTConfig(
            url=data.get("url"),
            port=data.get("port", 1883),
        )

    def to_dict(self) -> dict:
        '''
        Converts the MQTTConfig instance to a dictionary.
        Returns:
            dict: A dictionary representation of the MQTTConfig instance.
        '''
        return {
            "url": self.url,
            "port": self.port,
        }

    def __str__(self):
        return json.dumps(self.to_dict(), indent=4)

class Configuration:
    """
    Holds MQTT connection info plus an arbitrary number of named InfluxDB
    connections (e.g. "adr", "logs", ...), mirroring the structure of
    config.json:

        {
            "mqtt": {"url": ..., "port": ...},
            "influx": {
                "<name>": {"url": ..., "port": ..., "token": ..., "org": ..., "bucket": ...},
                ...
            }
        }
    """

    def __init__(
        self,
        mqtt: MQTTConfig = None,
        influx: Dict[str, InfluxConfig] = None,
        excluded_networks: list = None,
        github_token: str = None,
    ):
        self.mqtt: MQTTConfig = mqtt
        self.influx: Dict[str, InfluxConfig] = influx or {}
        self.excluded_networks: list = excluded_networks or []
        self.github_token: str = github_token

    def get_influx(self, name: str) -> Optional[InfluxConfig]:
        """Returns the InfluxConfig registered under `name`, or None."""
        return self.influx.get(name)

    def influx_names(self) -> List[str]:
        """Returns the list of configured Influx connection names."""
        return list(self.influx.keys())

    @staticmethod
    def load_from_file(file_path: str = "config.json") -> "Configuration":
        """
        Loads configuration from a JSON file structured as:
            {"mqtt": {...}, "influx": {"<name>": {...}, ...}}
        Args:
            file_path (str): Path to the JSON configuration file.
        Returns:
            Configuration: An instance populated with data from the file.
        """
        with open(file_path, "r") as file:
            data = json.load(file)

        mqtt_data = data.get("mqtt", {})
        influx_data = data.get("influx", {})
        github_token = data.get("github_token", "")

        mqtt = MQTTConfig.from_dict(mqtt_data) if mqtt_data else None

        influx = {
            name: InfluxConfig.from_dict(cfg) for name, cfg in influx_data.items()
        }

        return Configuration(
            mqtt=mqtt,
            influx=influx,
            excluded_networks=data.get("excluded_networks", None),
            github_token=github_token
        )

    @staticmethod
    def load_from_env() -> "Configuration":
        """
        Loads configuration from environment variables.

        MQTT_URL, MQTT_PORT, EXCLUDED_NETWORKS behave as before.

        Influx connections are provided as a JSON object via INFLUX, e.g.:
            INFLUX='{"adr": {"url": "...", "port": 8086, "token": "...",
                              "org": "...", "bucket": "..."},
                     "logs": {...}}'
        Returns:
            Configuration: An instance populated with data from environment variables.
        """
        influx_raw = json.loads(os.getenv("INFLUX", "{}"))
        influx = {
            name: InfluxConfig.from_dict(cfg) for name, cfg in influx_raw.items()
        }
        mqtt = MQTTConfig(
            url=os.getenv("MQTT_URL", "localhost"),
            port=int(os.getenv("MQTT_PORT", 1883)),
        )
        github_token = os.getenv("GITHUB_TOKEN", "")

        return Configuration(
            mqtt=mqtt,
            influx=influx,
            excluded_networks=json.loads(os.getenv("EXCLUDED_NETWORKS", "[]")),
            github_token=github_token
        )

    def __str__(self):
        conf = {
            "mqtt": self.mqtt.to_dict() if self.mqtt else None,
            "influx": {name: cfg.to_dict() for name, cfg in self.influx.items()},
            "excluded_networks": self.excluded_networks,
            "github_token": self.github_token
        }
        return json.dumps(conf, indent=4)
