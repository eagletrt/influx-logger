"""Tests for batching and write behavior in InfluxWriter."""

from threading import Lock
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from influxdb_client.client.write_api import Point

from src.influx.influx_writer import InfluxWriter
from src.utils.bucket_type import BucketType


class TestInfluxWriter(TestCase):
    """
    Tests for InfluxWriter batching, commit, and write behavior.
    """

    def setUp(self):
        self.client = MagicMock(org="org")
        self.writer = InfluxWriter(self.client,
                                   adr_bucket="adr",
                                   log_bucket="logs",
                                   batch_size=2)
        self.writer.parser = MagicMock()

    def test_batch_limit_prepare_commit_and_success(self):
        """
        Tests that is_list_limit_reached returns True when the batch size is reached,
        that prepare_for_commit retrieves points from the parser, and that commit
        writes the points to InfluxDB and resets the parser timer.
        """
        self.assertFalse(self.writer.is_list_limit_reached(1))
        self.assertTrue(self.writer.is_list_limit_reached(2))
        points = [MagicMock(), MagicMock()]
        self.writer.parser.pop_points.return_value = points
        self.writer.write_api.write.return_value = None
        with patch(
                "src.influx.influx_writer.InfluxWriter._InfluxWriter__pack_lines",
                return_value="line\n"):
            self.assertTrue(self.writer.commit(BucketType.ADR))
        self.writer.parser.reset_timer.assert_called_once_with()
        self.writer.write_api.write.assert_called_once_with(
            bucket="adr", org="org", record="line\n", write_precision="us")
        self.client.reset_ping.assert_called_once_with()

    def test_commit_rejects_invalid_empty_missing_bucket_and_write_failure(
            self):
        """
        Tests that commit returns False for invalid bucket types, empty points,
        missing buckets, and write failures.
        """
        self.assertFalse(self.writer.commit("unknown"))
        self.writer.parser.pop_points.return_value = []
        self.assertFalse(self.writer.commit(BucketType.LOG))
        self.writer.buckets[BucketType.ADR] = None
        self.writer.parser.pop_points.return_value = [MagicMock()]
        with patch(
                "src.influx.influx_writer.InfluxWriter._InfluxWriter__pack_lines",
                return_value="x"):
            self.assertFalse(self.writer.commit(BucketType.ADR))
        self.writer.buckets[BucketType.ADR] = "adr"
        self.writer.write_api.write.side_effect = RuntimeError("offline")
        with patch(
                "src.influx.influx_writer.InfluxWriter._InfluxWriter__pack_lines",
                return_value="x"):
            self.assertFalse(self.writer.commit(BucketType.ADR))

    def test_prepare_batch_and_pack_lines(self):
        """
        Tests that prepare_for_commit retrieves points from the parser and that
        __pack_lines converts them to line protocol strings.
        """
        self.writer.parser.pop_points.return_value = ["point"]
        self.assertEqual(self.writer.prepare_for_commit(BucketType.LOG),
                         ["point"])
        self.writer.parser.pop_points.assert_called_with(
            bucket_type=BucketType.LOG, max_points_to_pop=2)
        fake_point = MagicMock()
        fake_point.to_line_protocol.return_value = "measurement value=1i"
        with patch.object(Point, "from_dict", return_value=fake_point):
            self.assertEqual(
                InfluxWriter._InfluxWriter__pack_lines([  # pylint: disable=protected-access
                    {
                        "x": 1
                    }, None,
                    object()
                ]),
                "measurement value=1i\n")
        self.assertEqual(InfluxWriter._InfluxWriter__pack_lines([]), "")  # pylint: disable=protected-access

    def test_commit_checks_batches_expiration_and_shutdown_paths(self):
        """
        Tests that check_and_commit checks for batch expiration and handles shutdown paths.
        """
        self.writer.parser.is_timer_expired.return_value = False
        with patch.object(self.writer, "commit") as commit:
            with patch.object(self.writer,
                              "_InfluxWriter__check_to_commit",
                              side_effect=[True, False]):
                self.writer.check_and_commit()
        commit.assert_called_once_with(bucket_type=BucketType.LOG)
        self.writer.parser.is_timer_expired.return_value = True
        with patch.object(self.writer, "commit") as commit:
            self.writer.check_and_commit()
        self.assertEqual(commit.call_count, 2)
        with patch.object(self.writer.parser, "graceful_stop") as stop, \
                patch.object(self.writer.parser, "join"):
            self.writer.graceful_stop()
        stop.assert_called_once_with()
        with patch.object(self.writer.parser, "stop_parser") as stop, \
                patch.object(self.writer.parser, "join"):
            self.writer.stop()
        stop.assert_called_once_with()

    def test_run_starts_parser_processes_signal_and_stops_gracefully(self):
        """
        Tests that the run method starts the parser, processes signals, and stops gracefully.
        """
        self.writer.stopped = MagicMock(side_effect=[False, True])
        parser = SimpleNamespace(
            __new_points_event_lock__=Lock(),
            points_increased=MagicMock(),
            start=MagicMock(),
            graceful_stop=MagicMock(),
        )
        parser.points_increased.wait = MagicMock()
        self.writer.parser = parser
        with patch.object(self.writer, "check_and_commit") as check:
            self.writer.run()
        parser.start.assert_called_once_with()
        parser.points_increased.wait.assert_called_once_with()
        check.assert_called_once_with()
        parser.graceful_stop.assert_called_once_with()
