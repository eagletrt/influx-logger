"""Tests for repository lookup and protobuf cache paths."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock, patch

from src.parser.libmanager import LibcanManager, LibgpsManager, LibManager, LibSerializersManager


class ConcreteLibManager(LibManager):

    @staticmethod
    def check_commit_existence(commit_hash):
        return bool(commit_hash)

    @staticmethod
    def download_proto_version(commit_hash, network):
        return bool(commit_hash and network)


class TestLibManager(TestCase):

    def test_proto_cache_path_normalizes_extension_and_prefix(self):
        self.assertEqual(LibManager.proto_cache_path("proto/can/Pack"),
                         "can/Pack.proto")
        self.assertEqual(LibManager.proto_cache_path("gps.proto"), "gps.proto")

    def test_check_tries_multiple_urls_and_adds_token_header(self):
        failed = MagicMock(ok=False, status_code=404, text="missing")
        success = MagicMock(ok=True)
        with patch("src.parser.libmanager.get", side_effect=[failed,
                                                             success]) as get:
            self.assertTrue(
                LibManager.check("abc", ["https://x/hash", "https://y/hash"],
                                 "token"))
        self.assertEqual(get.call_args_list[0].args[0], "https://x/abc")
        self.assertEqual(
            get.call_args_list[0].kwargs["headers"]["Authorization"],
            "Bearer token")

    def test_cache_directories_and_download_file(self):
        with TemporaryDirectory() as temp:
            cache = Path(temp) / "cache"
            version = cache / "abc"
            with patch.object(LibManager, "CACHE_DIR", str(cache)):
                result = LibManager.create_cache_directories(
                    str(cache), str(version))
                self.assertTrue(Path(result).is_dir())
                with patch("src.parser.libmanager.get",
                           return_value=MagicMock(ok=True,
                                                  text="syntax = 'proto3';")):
                    self.assertTrue(
                        LibManager.download("abc",
                                            "network", ["https://x/hash"],
                                            cache=str(cache)))
            self.assertTrue((version / "proto" / "network.proto").exists())

    def test_concrete_manager_contracts(self):
        self.assertTrue(ConcreteLibManager.check_commit_existence("abc"))
        self.assertFalse(ConcreteLibManager.check_commit_existence(""))
        with self.assertRaises(NotImplementedError):
            LibManager.check_commit_existence("hash")
        with self.assertRaises(NotImplementedError):
            LibManager.download_proto_version("hash", "can")

    def test_repository_managers_delegate_to_shared_lookup_and_download(self):
        managers = (LibcanManager, LibgpsManager, LibSerializersManager)
        with patch.object(LibManager, "check", return_value=True) as check, \
                patch.object(LibManager, "download", return_value=True) as download:
            for manager in managers:
                self.assertTrue(manager.check_commit_existence("hash"))
                self.assertTrue(manager.download_proto_version("hash", "can"))
        self.assertEqual(check.call_count, 3)
        self.assertEqual(download.call_count, 3)
