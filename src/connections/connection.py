from abc import ABC, abstractmethod

class Connection(ABC):
    """
    Abstract base class for managing connections to different services.
    This class provides a common interface for establishing and checking the status of connections.
    Subclasses should implement the connect method to handle specific connection logic for different services.
    Attributes:
        connection: The actual connection object to the service.
        url: The URL of the service to connect to.
        port: The port of the service to connect to.
    """
    def __init__(self, url: str = None, port: int = None):
        self.connection = None
        self.url: str = url
        self.port: int = port
    
    def __str__(self) -> str:
        return self.get_full_link()
    
    def get_full_link(self) -> str:
        """
        Get the full link, comprehensive of port.
        Returns:
            str: full link
        """
        full_link = f"{self.url}:{self.port}"
        if "http" not in full_link:
            return full_link
        return f"http://{full_link}"

    @abstractmethod
    def connect(self) -> bool:
        """
        Establishes a connection to the specified service.
        This method should be implemented by subclasses to handle the specific connection logic for different services.
        Returns:
            bool: True if the connection was successful, False otherwise.
        """
        raise NotImplementedError("Subclasses must implement the connect method.")
    
    @abstractmethod
    def disconnect(self) -> bool:
        """
        Disconnects from the specified service.
        This method should be implemented by subclasses to handle the specific disconnection logic for different services.
        Returns:
            bool: True if the disconnection was successful, False otherwise.
        """
        raise NotImplementedError("Subclasses must implement the disconnect method.")
    
    def is_connected(self) -> bool:
        """
        Checks if the connection to the specified service is established.
        Returns:
            bool: True if the connection is established, False otherwise.
        """
        return self.connection is not None
