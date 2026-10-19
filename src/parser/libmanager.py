"""
Utility classes for interacting with the Library repositories 
to check commit existence and download protobuf descriptors.
"""

import json
import os
from abc import ABC, abstractmethod

# pylint: disable=no-name-in-module
from requests import get

from src.utils.logger_utils import logger


class LibManager(ABC):
    '''
    A utility class for interacting with the CAN and GPS repositories 
    to check commit existence and download protobuf descriptors.
    '''
    CACHE_DIR: str = "cache"
    '''Base cache directory used for storing .proto files and descriptor sets.'''

    @staticmethod
    def check(commit_hash: str,
              urls: str | list[str],
              token: str = None) -> bool:
        '''
        Checks if a given commit hash exists in the repository.
        Args:
            commit_hash (str): The commit hash to check.
            urls (str|list[str]): The URL or list of URLs to check.
            token (str): The GitHub personal access token for authentication.
        Returns:
            bool: True if the commit exists, False otherwise.
        '''
        headers: json = {}
        # If a GitHub token is provided, include it in the request headers for authentication
        if token and token != "":
            headers: json = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            }
        # Check the existence of the commit hash in the CAN repository
        # by sending a GET request to the commit URLs
        for repo_url in urls if isinstance(urls, list) else [urls]:
            check_url = repo_url.replace("hash", commit_hash)
            try:
                resp = get(check_url, headers=headers, timeout=10)
                logger.info("protobuf_manager: url: %s, headers: %s",
                            check_url, headers)
                if resp.ok:
                    return True
                # If the request fails, log a warning with the status code and response text
                logger.warning(
                    "protobuf_manager: Request to %s failed with status code %s: %s",
                    check_url, resp.status_code, resp.text)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(
                    "protobuf_manager: " \
                    "Failed to check commit existence for hash '%s' at URL '%s'",
                    commit_hash,
                    check_url
                )
                logger.error("protobuf_manager: %s", e)
        return False

    @staticmethod
    @abstractmethod
    def check_commit_existence(commit_hash: str) -> bool:
        '''
        Checks if a given commit hash exists in the repository.
        Args:
            commit_hash (str): The commit hash to check.
        Returns:
            bool: True if the commit exists, False otherwise.
        '''
        raise NotImplementedError(
            "Subclasses must implement the check_commit_existence method.")

    @staticmethod
    def download(commit_hash: str,
                 network: str,
                 in_url: str | list[str],
                 cache: str,
                 token: str = None) -> bool:
        '''
        Downloads the protobuf descriptor for a given commit hash and network from the repository.
        Args:
            commit_hash (str): The commit hash for which to download the protobuf descriptor
            network (str): The network for which to download the protobuf descriptor
            url (str|list[str]): URL or list of URLs from which to download the protobuf descriptor
            cache (str): Path to the cache directory where the downloaded proto file will be stored
            token (str): The GitHub personal access token for authentication
        Returns:
            bool: True if the download is successful, False otherwise
        '''
        headers: json = {}
        # If a GitHub token is provided, include it in the request headers for authentication
        if token and token != "":
            headers: json = {
                "Authorization": f"Bearer {token}",
            }
        # Directory in the cache where the .proto file for the specified commit hash will be stored
        version_dir: str = os.path.join(cache, commit_hash)
        # List of URLs to check for the protobuf descriptor
        urls: list[str] = []
        # If in_url is a list, use it directly; if it's a string, convert it to a list
        if isinstance(in_url, list):
            urls = in_url
        elif isinstance(in_url, str):
            urls.append(in_url)
        for url_sample in urls:
            try:
                url: str = url_sample.replace("hash", commit_hash).replace(
                    "network", network)
                logger.info("protobuf_manager: URL: %s", url)
                resp = get(url, headers=headers, timeout=10)
                if resp and resp.ok:
                    break
            except Exception:  # pylint: disable=broad-exception-caught
                logger.error(
                    "protobuf_manager: "
                    "Error while downloading proto for network '%s' (version %s)",
                    network, commit_hash)
        if not resp or not resp.ok:
            logger.warning(
                "protobuf_manager: Proto for network '%s' (version %s) not downloaded: %s.",
                network, commit_hash,
                str(resp.status_code) if resp else 'No response')

            return False
        try:
            if not os.path.exists(LibManager.CACHE_DIR):
                os.makedirs(LibManager.CACHE_DIR)
            if not os.path.exists(cache):
                os.makedirs(cache)
            if not os.path.exists(version_dir):
                os.makedirs(version_dir)
            proto_dir = os.path.join(version_dir, "proto")
            if not os.path.exists(proto_dir):
                os.makedirs(proto_dir)
            with open(os.path.join(proto_dir, f"{network}.proto"),
                      "w",
                      encoding="utf-8") as fh:
                fh.write(resp.text)
                return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(
                "protobuf_manager: "
                "Failed to save downloaded proto for network '%s' (version %s)",
                network, commit_hash)
            logger.error("Exception %s: %s", type(e).__name__, e)
            return False
        return False

    @staticmethod
    @abstractmethod
    def download_proto_version(commit_hash: str, network: str) -> bool:
        '''
        Downloads the protobuf descriptor for a given commit hash and network from the repository.
        Args:
            commit_hash (str): The commit hash for which to download the protobuf descriptor.
            network (str): The network for which to download the protobuf descriptor.
        Returns:
            bool: True if the download is successful, False otherwise.
        '''
        raise NotImplementedError(
            "Subclasses must implement the download_proto_version method.")


class LibcanManager(LibManager):
    '''
    A utility class for interacting with the CAN repository to 
    check commit existence and download protobuf descriptors.
    '''

    TOKEN: str = None
    '''GitHub personal access token used for authentication when accessing the CAN repository.'''
    CAN_COMMIT_URL: str = "https://api.github.com/repos/eagletrt/can/commits/hash"
    '''URL to the commit page in the can repository'''
    LIBCAN_COMMIT_URL: str = CAN_COMMIT_URL.replace("can", "libcan-sw")
    '''URL to the commit page in the libcan-sw repository'''
    CAN_COMMIT_URLS: list[str] = [
        CAN_COMMIT_URL,
        LIBCAN_COMMIT_URL,
    ]
    '''URLs to the commit pages in the can and libcan-sw repositories'''

    CAN_PROTO_URL: str = "https://raw.githubusercontent.com" \
    "/eagletrt/can/hash/proto/network/network.proto"
    '''URL to the raw .proto file in the can repository'''
    LIBCAN_PROTO_URL: str = CAN_PROTO_URL.replace("can", "libcan-sw")
    '''URL to the raw .proto file in the libcan-sw repository'''
    CAN_PROTO_URLS: list[str] = [
        CAN_PROTO_URL,
        LIBCAN_PROTO_URL,
    ]
    '''URLs to the raw .proto files in the can and libcan-sw repositories'''

    CACHE_DIR: str = os.path.join(LibManager.CACHE_DIR, "can")
    '''Cache directory used for storing .proto files and descriptor sets for CAN.'''

    @staticmethod
    def check_commit_existence(commit_hash: str) -> bool:
        '''
        Checks if a given commit hash exists in the CAN repository.
        Args:
            commit_hash (str): The commit hash to check.
        Returns:
            bool: True if the commit exists, False otherwise.
        '''
        return LibManager.check(commit_hash,
                                LibcanManager.CAN_COMMIT_URLS,
                                token=LibcanManager.TOKEN)

    @staticmethod
    def download_proto_version(commit_hash: str, network: str) -> bool:
        '''
        Downloads the protobuf descriptor for a given 
        commit hash and network from the CAN repository.
        Args:
            commit_hash (str): The commit hash for which to download the protobuf descriptor.
            network (str): The network for which to download the protobuf descriptor.
        Returns:
            bool: True if the download is successful, False otherwise.
        '''
        return LibManager.download(commit_hash,
                                   network,
                                   LibcanManager.CAN_PROTO_URLS,
                                   cache=LibcanManager.CACHE_DIR,
                                   token=LibcanManager.TOKEN)


class LibgpsManager(LibManager):
    '''
    A utility class for interacting with the GPS repository to check commit existence.
    '''
    GPS_COMMIT_URL: str = "https://api.github.com" \
        "/repos/eagletrt/gpslib/commits/hash"
    '''URL to the commit page in the gps repository'''
    GPS_PROTO_URL: str = "https://raw.githubusercontent.com" \
        "/eagletrt/gpslib/hash/network.proto"
    '''URL to the raw .proto file in the gps repository'''

    CACHE_DIR: str = os.path.join(LibManager.CACHE_DIR, "gps")
    '''Cache directory used for storing .proto files and descriptor sets for GPS.'''

    @staticmethod
    def check_commit_existence(commit_hash: str) -> bool:
        '''
        Checks if a given commit hash exists in the GPS repository.
        Args:
            commit_hash (str): The commit hash to check.
        Returns:
            bool: True if the commit exists, False otherwise.
        '''
        return LibManager.check(commit_hash, LibgpsManager.GPS_COMMIT_URL)

    @staticmethod
    def download_proto_version(commit_hash: str, network: str) -> bool:
        '''
        Downloads the protobuf descriptor for a given 
        commit hash and network from the GPS repository.
        Args:
            commit_hash (str): The commit hash for which to download the protobuf descriptor.
            network (str): The network for which to download the protobuf descriptor.
        Returns:
            bool: True if the download is successful, False otherwise.
        '''
        logger.info(
            "protobuf_manager: Downloading GPS proto for network '%s' (version %s),",
            network, commit_hash)
        return LibManager.download(commit_hash,
                                   network,
                                   LibgpsManager.GPS_PROTO_URL,
                                   cache=LibgpsManager.CACHE_DIR)
