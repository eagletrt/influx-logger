"""
Module managing the logging state
of a session.
"""

from threading import Lock


class LoggingState:  # pylint: disable=too-few-public-methods
    """
    Class representing the logging state of a session.
    It contains the timestamps for when logging started and stopped.
    """

    def __init__(self,
                 started_timestamp: int,
                 stopped_timestamp: int = None) -> None:
        """
        Initializes the LoggingState with the provided timestamps.
        
        Args:
            started_timestamp (int): The timestamp when logging started.
            stopped_timestamp (int, optional): The timestamp when logging stopped. Defaults to None.
        """
        self.started_timestamp: int = started_timestamp
        '''Timestamp when logging started.'''
        self.stopped_timestamp: int = stopped_timestamp
        '''Timestamp when logging stopped.'''
        self._lock: Lock = Lock()
        '''Lock to ensure thread-safe access to the LoggingState object.'''

    def set_stopped_timestamp(self, stopped_timestamp: int) -> bool:
        """
        Sets the timestamp when logging stopped if it hasn't been set already.

        Args:
            stopped_timestamp (int): The timestamp when logging stopped.

        Returns:
            bool: True if the timestamp was set, False otherwise.
        """
        set_result: bool = False
        with self._lock:
            if self.stopped_timestamp is None:
                self.stopped_timestamp = stopped_timestamp
                set_result = True
        return set_result
