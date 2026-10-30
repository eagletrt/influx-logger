"""
Hanlder for serializers.
"""


class SerializersManager:
    """
    Class that manages the serializers.
    """

    @staticmethod
    def compile_protobuf() -> bool:
        raise NotImplementedError(
            "This method should be implemented in a subclass.")
