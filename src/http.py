import requests
from typing import Optional


CAN_PROTO_URL = (
    "https://raw.githubusercontent.com/eagletrt/can/hash/proto/network/network.proto"
)
CAN_COMMIT_URL = "https://github.com/eagletrt/can/tree/hash"


def check_commit_existence(hash: str) -> bool:
    url = CAN_COMMIT_URL.replace("hash", hash)
    resp = requests.get(url)
    return resp.ok


def download_proto_version(hash: str, network: str) -> str:
    url = CAN_PROTO_URL.replace("hash", hash).replace("network", network)
    resp = requests.get(url)
    if not resp.ok:
        raise RuntimeError("Failed to download proto")
    return resp.text


__all__ = ["check_commit_existence", "download_proto_version"]
