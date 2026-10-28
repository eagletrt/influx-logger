"""Tests for Parser synchronization boundaries."""

from threading import Event, Thread
from unittest.mock import patch

from src.parser.parser import LibcanManager, Parser


def test_parser_wakes_for_queued_message_and_stops() -> None:
    """Parser processes a queued message and exits after a stop signal."""
    parser = Parser()
    message_processed = Event()

    def parse_message(_message: tuple[list[str], bytes]) -> None:
        del _message
        message_processed.set()

    with patch.object(parser, "parse_msg", side_effect=parse_message):
        parser.start()
        parser.add_to_queue((["vehicle", "device", "can"], b"payload"))

        assert message_processed.wait(timeout=1)

        parser.stop_parser()
        parser.join(timeout=1)

    assert not parser.is_alive()


def test_device_version_registration_is_safe_for_concurrent_callers() -> None:
    """Concurrent registrations leave a consistent device and descriptor state."""
    parser = Parser()
    versions = [f"version-{index}" for index in range(20)]

    workers = [
        Thread(target=parser.register_device_version,
               args=("vehicle", "device", LibcanManager, version))
        for version in versions
    ]

    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    registered_version = parser.device_versions["vehicle/device"][
        LibcanManager]
    assert registered_version in versions
    assert registered_version in parser.protobuf_manager.version_descriptors
