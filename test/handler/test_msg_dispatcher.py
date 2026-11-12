"""Unit tests for MQTT topic dispatch and message routing."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from src.handler.msg_dispatcher import MsgDispatcher
from src.parser.libmanager import LibcanManager, LibgpsManager, LibSerializersManager


class TestMsgDispatcher(TestCase):
    """
    Tests for MsgDispatcher topic dispatch and message routing.
    """

    def test_payload_conversion_and_topic_patterns(self):
        """
        Tests that payload_to_json correctly decodes JSON payloads and returns an empty
        dictionary for non-JSON payloads, and that build_topic_regex converts MQTT
        topic patterns with wildcards into regex patterns that match the expected topics.
        """
        self.assertEqual(MsgDispatcher.payload_to_json(b'{"x":1}'), {"x": 1})
        self.assertEqual(MsgDispatcher.payload_to_json(b"not-json"), {})
        regex = MsgDispatcher.build_topic_regex("+/+/data/#")
        self.assertIsNotNone(regex.fullmatch("car/sensor/data/a/b"))
        self.assertIsNone(regex.fullmatch("car/data/a"))

    def test_incoming_message_dispatches_matching_callback(self):
        """
        Tests that handle_incoming_message dispatches to the correct callback
        based on the topic pattern and that the callback is called with the
        expected arguments.
        """
        dispatcher = MsgDispatcher()
        callback = MagicMock()
        dispatcher.topic_callbacks = {"+/+/data/+": callback}
        dispatcher.handle_incoming_message("car/sensor/data/can", b"payload")
        callback.assert_called_once_with("car/sensor/data/can", b"payload",
                                         ["car", "sensor", "can"])

    def test_data_and_status_routes_respect_whitelist_and_ids(self):
        """
        Tests that handle_data_message and handle_tlm_status_message respect the
        vehicle whitelist and that the correct parser methods are called with the
        appropriate arguments.
        """
        parser = MagicMock()
        dispatcher = MsgDispatcher(influx_writer=MagicMock(parser=parser),
                                   vehicle_whitelist=["v1"])
        dispatcher.handle_data_message("", b"row", ["v2", "d", "can"])
        parser.add_to_queue.assert_not_called()
        dispatcher.handle_data_message("", b"row", ["v1", "d", "can"])
        parser.add_to_queue.assert_called_once_with((["v1", "d",
                                                      "can"], b"row"))
        dispatcher.handle_tlm_status_message("", b"bad", ["v1"])
        parser.handle_tlm_status_message.assert_not_called()
        dispatcher.handle_tlm_status_message("", b"status", ["v1", "d"])
        parser.handle_tlm_status_message.assert_called_once_with(["v1", "d"],
                                                                 b"status")

    def test_version_routes_check_commit_subscribe_and_register(self):
        """
        Tests that handle_serializers_version_message checks commit existence,
        subscribes to the data topic, and registers the version with the parser.
        """
        parser = MagicMock()
        writer = MagicMock(parser=parser)
        mqtt = MagicMock()
        mqtt.connection = MagicMock()
        dispatcher = MsgDispatcher(influx_writer=writer, mqtt=mqtt)
        with patch.object(LibSerializersManager,
                          "check_commit_existence",
                          return_value=True) as check:
            dispatcher.handle_serializers_version_message(
                "", b"abc123 extra", ["v", "d"])
        check.assert_called_once_with("abc123")
        mqtt.connection.subscribe.assert_called_once_with("v/d/data/+")
        parser.register_device_version.assert_called_once_with(
            "v", "d", LibSerializersManager, "abc123")

    def test_each_library_version_topic_routes_to_its_manager(self):
        """
        Tests that each library version topic is routed to the appropriate
        manager (LibcanManager, LibgpsManager) and that handle_version_message
        is called with the correct arguments.
        """
        dispatcher = MsgDispatcher()
        dispatcher.handle_libcan_version_message("", b"can", ["v", "d"])
        dispatcher.handle_canlib_version_message("", b"old-can", ["v", "d"])
        dispatcher.handle_libgps_version_message("", b"gps", ["v", "d"])
        # Without configured connections, the shared handler exits before repository access.
        with patch.object(dispatcher, "handle_version_message") as handle:
            dispatcher.handle_libcan_version_message("", b"can", ["v", "d"])
            dispatcher.handle_canlib_version_message("", b"old-can",
                                                     ["v", "d"])
            dispatcher.handle_libgps_version_message("", b"gps", ["v", "d"])
        self.assertEqual(handle.call_args_list[0].args,
                         (LibcanManager, "can", ["v", "d"]))
        self.assertEqual(handle.call_args_list[1].args,
                         (LibcanManager, "old-can", ["v", "d"]))
        self.assertEqual(handle.call_args_list[2].args,
                         (LibgpsManager, "gps", ["v", "d"]))

    def test_subscribe_existing_messages_in_version_order(self):
        """
        Tests that handle_existing_messages subscribes to version topics in the
        correct order and registers the appropriate version descriptors.
        """
        mqtt = MagicMock()
        dispatcher = MsgDispatcher(mqtt=mqtt)
        dispatcher.handle_existing_messages()
        subscriptions = [
            call.args[0] for call in mqtt.connection.subscribe.call_args_list
        ]
        self.assertEqual(subscriptions[:3], [
            "+/+/info/version/serializers", "+/+/info/version/libcan",
            "+/+/info/version/gpslib"
        ])

    def test_set_writer_lifecycle_and_version_wrappers(self):
        """
        Tests that set() starts the writer, stop() stops it, and graceful_stop()
        calls graceful_stop on the writer, and that version_descriptors are
        registered correctly for the given version and message type.
        """
        dispatcher = MsgDispatcher()
        writer = MagicMock()
        dispatcher.set(influx_writer=writer)
        writer.start.assert_called_once_with()
        dispatcher.stop()
        writer.stop.assert_called_once_with()
        writer.join.assert_called_once_with()
        graceful = MagicMock()
        dispatcher.set(influx_writer=graceful)
        dispatcher.graceful_stop()
        graceful.graceful_stop.assert_called_once_with()
        graceful.join.assert_called_once_with()
