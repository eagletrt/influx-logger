"""Focused unit tests for parser data, queue, and status helpers."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from src.parser.libmanager import LibcanManager, LibSerializersManager
from src.parser.parser import Parser
from src.utils.bucket_type import BucketType


class TestParserUnits(TestCase):

    def setUp(self):
        self.parser = Parser()
        self.parser.parserfsms[("v", "d")] = MagicMock()
        self.parser.parserfsms[("v", "d")].is_logging.return_value = True
        self.parser.timer_touch = MagicMock()

    def test_queue_and_fsm_helpers(self):
        self.parser.add_to_queue((["v", "d", "can"], b"x"))
        self.assertEqual(self.parser.row_messages.get_nowait(),
                         (["v", "d", "can"], b"x"))
        self.assertFalse(self.parser.new_fsm(("new", "device")) is False)
        self.parser.parserfsms[("v", "d")].msg_incoming.reset_mock()
        self.parser.notify_fsm_running("v", "d")
        self.parser.parserfsms[("v",
                                "d")].msg_incoming.assert_called_once_with()
        self.parser.set_log_callback(lambda *_: None)
        self.assertTrue(callable(self.parser.log_callback))

    def test_columnar_expansion_and_unwrap(self):
        record = {
            "timestamp": {
                "values": [10, 20]
            },
            "valuesMap": {
                "speed": {
                    "values": [1.5, 2.5]
                },
                "short": [7]
            }
        }
        self.assertEqual(Parser._expand_columnar_record(record), [{
            "timestamp": 10,
            "speed": 1.5,
            "short": 7
        }, {
            "timestamp": 20,
            "speed": 2.5
        }])
        self.assertEqual(Parser._unwrap_values({"values": [1]}), [1])
        self.assertEqual(Parser._unwrap_values(3), 3)
        with self.assertRaisesRegex(ValueError, "timestamp"):
            Parser._expand_columnar_record({"valuesMap": {}})

    def test_push_rows_columnar_records_and_ignores_invalid_records(self):
        with patch.object(self.parser, "timer_touch"):
            self.parser.push("m", {
                "time": 10,
                "value": 2
            }, {
                "vehicle-id": "v",
                "device-id": "d"
            })
            self.parser.push("m", {
                "timestamp": [11, 12],
                "valuesMap": {
                    "value": [3, 4]
                }
            }, {
                "vehicle-id": "v",
                "device-id": "d"
            })
            self.parser.push("m", "unsupported", {})
            self.parser.push("m", 42, {})
        self.assertEqual(self.parser.get_points_count(BucketType.ADR), 3)
        self.assertEqual(self.parser.get_points_count(BucketType.LOG), 3)
        points = self.parser.pop_points(BucketType.ADR, 2)
        self.assertEqual(len(points), 2)
        self.assertEqual(len(self.parser.pop_points(BucketType.ADR)), 1)

    def test_commit_records_handles_lists_and_invalid_empty_records(self):
        with patch.object(self.parser, "push") as push:
            self.parser.commit_to_destination_list(
                {
                    "antenna_name": "a",
                    "samples": [{
                        "x": 1
                    }, "bad"],
                    "single": {
                        "y": 2
                    }
                }, {"vehicle-id": "v"})
        self.assertEqual(push.call_count, 4)
        self.assertEqual(push.call_args_list[1].args[1], {
            "x": 1,
            "antenna_name": "a"
        })

    def test_parse_message_decodes_and_registers_measurements(self):
        self.parser.register_device_version("v", "d", LibcanManager, "version")
        decoder = MagicMock()
        decoder.decode.return_value = {
            "valuesPack": {
                "sample": [{
                    "timestamp": 5,
                    "x": 1
                }]
            }
        }
        self.parser.protobuf_manager.version_descriptors["version"][
            "can"] = decoder
        with patch.object(self.parser, "commit_to_destination_list") as commit:
            self.parser.parse_msg((["v", "d", "can"], b"data"))
        decoder.decode.assert_called_once_with(b"data")
        commit.assert_called_once_with({"sample": [{
            "timestamp": 5,
            "x": 1
        }]}, {
            "vehicle-id": "v",
            "device-id": "d",
            "network": "can"
        })

    def test_version_registration_and_telemetry_status_decoder(self):
        status_path = LibSerializersManager.TELEMETRY_STATUS_PROTO_PATH
        self.parser.new_fsm(("v", "d"))
        decoder = MagicMock()
        decoder.decode_message.return_value = MagicMock(state=1)
        with patch.object(self.parser.protobuf_manager,
                          "download_proto_descriptor",
                          return_value=False):
            self.parser.register_device_version("v", "d",
                                                LibSerializersManager,
                                                "serial")
        self.parser.protobuf_manager.version_descriptors["serial"][
            status_path] = decoder
        with patch.object(self.parser.parserfsms[("v", "d")],
                          "new_telemetry_status") as update:
            self.parser.handle_tlm_status_message(["v", "d"], b"status")
        update.assert_called_once_with(decoder.decode_message.return_value)

    def test_timer_and_stop_helpers(self):
        self.parser.timer_expired = True
        self.parser.reset_timer()
        self.assertFalse(self.parser.is_timer_expired())
        self.parser.destination_lists[BucketType.LOG].put(object())
        self.assertEqual(self.parser.get_points_count(BucketType.LOG), 1)
        self.parser.stop_parser()
        self.assertTrue(self.parser.stop)
        with self.assertRaises(NotImplementedError):
            self.parser.log_session_start(1)
        with self.assertRaises(NotImplementedError):
            self.parser.log_session_end(2)

    def test_inactivity_timer_and_queued_message_processing(self):
        del self.parser.timer_touch
        with patch("src.parser.parser.Timer") as timer_cls:
            self.parser.timer_touch()
        timer_cls.assert_called_once()
        timer_cls.return_value.start.assert_called_once_with()
        self.parser.row_messages.put((["v", "d", "can"], b"payload"))
        with patch.object(self.parser, "parse_msg") as parse:
            self.parser._Parser__parse_next_message()
        parse.assert_called_once_with((["v", "d", "can"], b"payload"))
        self.assertEqual(self.parser.row_messages.unfinished_tasks, 0)
        with patch.object(self.parser.points_increased, "notify_all"):
            self.parser._handle_inactivity()
        self.assertTrue(self.parser.is_timer_expired())

    def test_inactivity_with_queued_work_restarts_timer_and_graceful_stop(
            self):
        self.parser.row_messages.put((["v", "d", "can"], b"pending"))
        self.parser.timer_touch = MagicMock()
        self.parser._handle_inactivity()
        self.assertFalse(self.parser.is_timer_expired())
        self.parser.timer_touch.assert_called_once_with()
        self.parser.row_messages.get_nowait()
        self.parser.row_messages.task_done()
        self.parser.graceful_stop()
        self.assertTrue(self.parser.stop)
