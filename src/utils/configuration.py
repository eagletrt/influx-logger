import json


class Configuration:
    def __init__(self, mqtt_url: str, mqtt_port: int, influx_url: str, influx_port: int, influx_token: str, influx_org: str, influx_bucket: str, excluded_networks: list = None):
        self.mqtt_url = mqtt_url
        self.mqtt_port = mqtt_port
        self.influx_url = influx_url
        self.influx_port = influx_port
        self.influx_token = influx_token
        self.influx_org = influx_org
        self.influx_bucket = influx_bucket
        self.excluded_networks = excluded_networks or []
    
    @staticmethod
    def load_from_file(file_path: str = "config.json") -> 'Configuration':
        """
        Loads configuration from a JSON file.
        Args:
            file_path (str): Path to the JSON configuration file.
        Returns:
            Configuration: An instance of the Configuration class populated with data from the file.
        """
        with open(file_path, 'r') as file:
            data = json.load(file)
            return Configuration(
                mqtt_url=data.get("mqtt_url"),
                mqtt_port=data.get("mqtt_port", 1883),
                influx_url=data.get("influx_url"),
                influx_port=data.get("influx_port", 8086),
                influx_token=data.get("influx_token"),
                influx_org=data.get("influx_org"),
                influx_bucket=data.get("influx_bucket"),
                excluded_networks=data.get("excluded_networks", None)
            )
        
    def load_from_env(self) -> 'Configuration':
        """
        Loads configuration from environment variables.
        Returns:
            Configuration: An instance of the Configuration class populated with data from environment variables.
        """
        import os
        return Configuration(
            mqtt_url=os.getenv("MQTT_URL"),
            mqtt_port=int(os.getenv("MQTT_PORT", 1883)),
            influx_url=os.getenv("INFLUX_URL"),
            influx_port=int(os.getenv("INFLUX_PORT", 8086)),
            influx_token=os.getenv("INFLUX_TOKEN"),
            influx_org=os.getenv("INFLUX_ORG"),
            influx_bucket=os.getenv("INFLUX_BUCKET"),
            excluded_networks=json.loads(os.getenv("EXCLUDED_NETWORKS", "[]"))
        )
    
    def __str__(self):
        conf:json = {
            "mqtt_url": self.mqtt_url,
            "mqtt_port": self.mqtt_port,
            "influx_url": self.influx_url,
            "influx_port": self.influx_port,
            "influx_token": self.influx_token,
            "influx_org": self.influx_org,
            "influx_bucket": self.influx_bucket,
            "excluded_networks": self.excluded_networks
        }
        return json.dumps(conf, indent=4)
