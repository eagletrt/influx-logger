from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from test_report.queries import generate_benchmark_queries
import influxdb_client

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
	sys.path.insert(0, str(CURRENT_DIR))

from performances import Performances, QueryPerformance
from test_report.mongoconnection import connect

log = False

DEFAULT_CONFIG_PATH = CURRENT_DIR.parent / "config.json"
QUERY_WINDOWS = {
	"last_5_minutes": timedelta(minutes=5),
	"last_1_hour": timedelta(hours=1),
	"last_24_hours": timedelta(hours=24),
	"one_week_ago": timedelta(days=7),
	"week_ago_to_3_days_ago": timedelta(days=7) + timedelta(days=-3),
	# Some others random windows int the past
	"last_30_minutes": timedelta(minutes=30) + timedelta(seconds=-15),
	"last_2_hours": timedelta(hours=2) + timedelta(minutes=-30),
	"last_12_hours": timedelta(hours=12) + timedelta(minutes=-45),
}
_TIMESTAMP_FACTORS = {
	"ns": 1_000_000_000,
	"us": 1_000_000,
	"ms": 1_000,
	"s": 1,
}


def _load_config(config_path: Path) -> dict[str, Any]:
	with config_path.open("r", encoding="utf-8") as config_file:
		return json.load(config_file)


def _timestamp_cutoff(now: datetime, window: timedelta, precision: str) -> int:
	factor = _TIMESTAMP_FACTORS.get(precision, 1_000_000)
	cutoff = now - window
	return int(cutoff.timestamp() * factor)


def _find_numeric_value(values: Iterable[Any], key: str) -> int | None:
	for value in values:
		if isinstance(value, dict):
			if key in value:
				try:
					return int(value[key])
				except (TypeError, ValueError):
					continue
			nested = _find_numeric_value(value.values(), key)
			if nested is not None:
				return nested
		elif isinstance(value, list):
			nested = _find_numeric_value(value, key)
			if nested is not None:
				return nested
	return None


def _mongo_query_time_ms(collection: Any, pipeline: list) -> int:
	explain = collection.database.command(
		"explain",
		{"aggregate": collection.name, "pipeline": pipeline, "cursor": {}},
		verbosity="executionStats",
	)
	records = [explain]
	print_results(records)
	duration = _find_numeric_value([explain], "executionTimeMillis")
	if duration is None:
		duration = _find_numeric_value([explain], "executionTimeMillisEstimate")
	if duration is None:
		raise RuntimeError("MongoDB did not return an execution time for the benchmark query")
	return duration

def print_results(records: Iterable[Any]) -> None:
	if log:
		for record in records:
			print(record)

def _influx_query_time_ms(client: influxdb_client.InfluxDBClient, org: str, base_query: str) -> int:
	flux_query = f'''
import "profiler"
option profiler.enabledProfilers = ["query"]

{base_query}
'''
	tables = client.query_api().query(org=org, query=flux_query)
	records = [record.values for table in tables for record in table.records]
	print_results(records)
	duration_ns = _find_numeric_value(records, "TotalDuration")
	if duration_ns is None:
		duration_ns = _find_numeric_value(records, "ExecuteDuration")
	if duration_ns is None:
		raise RuntimeError("InfluxDB did not return a profiler duration for the benchmark query")
	return duration_ns // 1_000_000

def build_performances(config: dict[str, Any], repeat_count: int) -> Performances:
	performances = Performances()
	mongo_client, mongo_db = connect(
		url=config["mongo_url"],
		port=config["mongo_port"],
		username=config.get("mongo_username", ""),
		password=config.get("mongo_password", ""),
		db_name=config["mongo_db"],
	)
	influx_client = influxdb_client.InfluxDBClient(
		url=config["influx_url"],
		token=config["influx_token"],
		org=config["influx_org"],
	)

	try:
		collection = mongo_db["telemetry_lines"]
		now = datetime.now(timezone.utc)
		precision = config.get("timestamp_precision", "us")

		for query_name, window in QUERY_WINDOWS.items():
			cutoff_timestamp = _timestamp_cutoff(now, window, precision)
			influx_start = now - window
			influx_start_iso = influx_start.isoformat().replace("+00:00", "Z")

			queries = generate_benchmark_queries(
				bucket=config["influx_bucket"],
				start_time_iso=influx_start_iso,
			    cutoff_timestamp=cutoff_timestamp,
				target_field="rpm",
			)
			for test_name, q in queries.items():
				for _ in range(repeat_count):
					mongo_time_ms = _mongo_query_time_ms(collection, q["mongo"])
					influx_time_ms = _influx_query_time_ms(
						influx_client,
						config["influx_org"],
						q["influx"],
					)
					performances.add(f"{query_name}_{test_name}", QueryPerformance(influx_time_ms, mongo_time_ms))
	finally:
		influx_client.close()
		mongo_client.close()

	return performances


def main(argv: list[str] | None = None) -> Performances:
	argv = argv or sys.argv
	config_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_CONFIG_PATH
	repeat_count = 50
	config = _load_config(config_path)
	performances = build_performances(config, repeat_count)
	for name, performance in performances.performances.items():
		print(f"\n{name}:\n{performance}")
	print(performances)
	performances.save_all()
	return performances


if __name__ == "__main__":
	main()
