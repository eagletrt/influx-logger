"""Tests for logging and debug line output helpers."""

import logging
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from src.utils.line import Line
from src.utils.logger_utils import _trace
from tools import log_lines as log_lines_module


class TestLoggingHelpers(TestCase):

    def test_trace_level_emits_only_when_enabled(self):
        logger = logging.getLogger("test-trace")
        logger.setLevel(5)
        with self.assertLogs(logger, level=5) as captured:
            _trace(logger, "detail %s", "value")
        self.assertIn("TRACE:test-trace:detail value", captured.output[0])

    def test_log_and_extract_line_files(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "debug"
            log_file = directory / "lines.log"
            with patch.object(log_lines_module, "DEBUG_LOGS_DIR", str(directory)), \
                    patch.object(log_lines_module, "DEBUG_LOGS_FILE", str(log_file)):
                log_lines_module.log_lines(
                    [Line("lap", {}, {"time": 1}, 1_000_000)])
                log_lines_module.extract_lines("lap", "time")
            self.assertTrue(log_file.exists())
            self.assertIn("lap", log_file.read_text(encoding="utf-8"))
            self.assertTrue((directory / "lap_time.log").exists())

    def test_extract_nonmatching_line_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "lines.log"
            source.write_text("other metric=1\n", encoding="utf-8")
            with patch.object(log_lines_module, "DEBUG_LOGS_DIR", str(directory)), \
                    patch.object(log_lines_module, "DEBUG_LOGS_FILE", str(source)):
                log_lines_module.extract_lines("missing", "field")
            self.assertFalse((directory / "missing_field.log").exists())
