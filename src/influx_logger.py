from connections.connection import ConnectionHandler
from configuration import Configuration

class InfluxLogger:
    def __init__(self, config: Configuration):
        self.config: Configuration = config
        self.connection_handler: ConnectionHandler = ConnectionHandler(config)
