import requests

class ProtobuffManager:
    def __init__(self, cache_folder: str = ".cache"):
        pass


class LibCANManager:
    CAN_PROTO_URL = (
    "https://raw.githubusercontent.com/eagletrt/can/hash/proto/network/network.proto"
    )
    CAN_COMMIT_URL = "https://github.com/eagletrt/can/tree/hash"
    def __init__(self):
        pass
        
    def check_commit_existence(hash: str) -> bool:
        url = LibCANManager.CAN_COMMIT_URL.replace("hash", hash)
        resp = requests.get(url)
        return resp.ok
    
    def download_proto_version(hash: str, network: str) -> str:
        url = LibCANManager.CAN_PROTO_URL.replace("hash", hash).replace("network", network)
        resp = requests.get(url)
        if not resp.ok:
            raise RuntimeError("Failed to download proto")
        return resp.text
    
class _DecoderWrapper:
    def __init__(self, message_class, json_format_module):
        self._message_class = message_class
        self._json_format = json_format_module

    def decode(self, payload: bytes):
        message = self._message_class()
        message.ParseFromString(payload)
        return self._json_format.MessageToDict(message, preserving_proto_field_name=True)