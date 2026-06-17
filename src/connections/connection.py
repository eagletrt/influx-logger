from abc import ABC, abstractmethod

class Connection(ABC):
    def __init__(self, url: str = None, port: int = None):
        self.connection = None
        self.url = url
        self.port = port
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establishes a connection to the specified service.
        This method should be implemented by subclasses to handle the specific connection logic for different services.
        Returns:
            bool: True if the connection was successful, False otherwise.
        """
        raise NotImplementedError("Subclasses must implement the connect method.")
    
    def is_connected(self) -> bool:
        """
        Checks if the connection to the specified service is established.
        Returns:
            bool: True if the connection is established, False otherwise.
        """
        return self.connection is not None
