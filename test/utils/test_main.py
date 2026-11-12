"""Tests for executable entry point helpers."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

import src.main as main_module


class TestMain(TestCase):

    def test_safe_stop_stops_and_joins_handler(self):
        handler = MagicMock()
        main_module.safe_stop(handler)
        handler.stop_machine.assert_called_once_with()
        handler.join.assert_called_once_with()

    def test_main_uses_default_or_supplied_config_and_runs_handler(self):
        configuration = MagicMock()
        handler = MagicMock()
        with patch.object(
            main_module.Configuration,
            "load_from_file",
            return_value=configuration
            ) as load, \
                patch.object(main_module, "HandlerFSM", return_value=handler):
            main_module.main(["program", "settings.json"])
        load.assert_called_once_with("settings.json")
        handler.start.assert_called_once_with()
        handler.join.assert_called_once_with()

        with patch.object(
            main_module.Configuration,
            "load_from_file",
            return_value=configuration
        ) as load, \
                patch.object(main_module, "HandlerFSM", return_value=handler):
            main_module.main(["program"])
        load.assert_called_once_with("config.json")

    def test_main_exits_when_config_fails_and_print_fsm_delegates(self):
        with patch.object(main_module.Configuration,
                          "load_from_file",
                          side_effect=OSError("missing")):
            with self.assertRaises(SystemExit) as error:
                main_module.main(["program", "missing.json"])
        self.assertEqual(error.exception.code, 1)
        with patch.object(main_module.Path, "mkdir") as mkdir, \
                patch.object(main_module.HandlerFSM, "draw") as handler_draw, \
                patch.object(main_module.ParserFSM, "draw") as parser_draw, \
                patch.object(main_module.TelemetryFSM, "draw") as telemetry_draw:
            main_module.print_fsm()
        mkdir.assert_called_once_with(parents=True, exist_ok=True)
        self.assertEqual(handler_draw.call_count, 1)
        self.assertEqual(parser_draw.call_count, 1)
        self.assertEqual(telemetry_draw.call_count, 1)
