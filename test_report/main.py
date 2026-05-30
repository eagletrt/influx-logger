from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from test_report.queries import adjust_query_windows, generate_benchmark_queries, QUERY_WINDOWS, LAST_KNOWN_TIMESTAMP
import influxdb_client
from test_report.logger_utils import logger
from test_report.performances import Performances, QueryPerformance
from test_report.mongoconnection import connect

try:
	from pymongo.errors import AutoReconnect, NetworkTimeout, ServerSelectionTimeoutError
except Exception:  # pragma: no cover - pymongo may be unavailable in some environments
	AutoReconnect = NetworkTimeout = ServerSelectionTimeoutError = None

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
	sys.path.insert(0, str(CURRENT_DIR))

REPEAT_COUNT:int = 25
log = False

DEFAULT_CONFIG_PATH = CURRENT_DIR.parent / "config.json"

TIMEOUT_MINUTES = 45
TIMEOUT_MS = TIMEOUT_MINUTES * 60 * 1000

_TIMESTAMP_FACTORS = {
	"ns": 1_000_000_000,
	"us": 1_000_000,
	"ms": 1_000,
	"s": 1,
}
_INFLUX_METADATA_KEYS = {"result", "table", "_start", "_stop", "_time", "_measurement", "_field"}
_COUNT_QUERY_NAMES = {}

_MONGO_TIMEOUT_EXCEPTIONS = tuple(
	error for error in (AutoReconnect, NetworkTimeout, ServerSelectionTimeoutError) if error is not None
)


def _safe_int(value: Any) -> int:
	"""Convert various numeric types (int, float, numeric strings) to int safely."""
	if isinstance(value, int):
		return value
	if isinstance(value, float):
		return int(value)
	if isinstance(value, str):
		try:
			return int(value)
		except ValueError:
			return int(float(value))
	# fallback: try numeric conversion
	return int(float(value))


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
					return _safe_int(value[key])
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


def _canonicalize_value(value: Any) -> Any:
	if isinstance(value, datetime):
		return value.astimezone(timezone.utc).isoformat()
	if isinstance(value, dict):
		return {key: _canonicalize_value(inner_value) for key, inner_value in value.items()}
	if isinstance(value, list):
		return [_canonicalize_value(inner_value) for inner_value in value]
	return value


def _epoch_microseconds(value: Any) -> int:
	if isinstance(value, datetime):
		return int(value.astimezone(timezone.utc).timestamp() * 1_000_000)
	if isinstance(value, (int, float)):
		return int(value)
	raise ValueError(f"Unsupported timestamp value: {value!r}")


def _mongo_query_results(collection: Any, pipeline: list) -> list[dict[str, Any]]:
	return [dict(document) for document in collection.aggregate(pipeline)]


def _influx_query_results(client: influxdb_client.InfluxDBClient, org: str, base_query: str) -> list[dict[str, Any]]:
	tables = client.query_api().query(org=org, query=base_query)
	return [dict(record.values) for table in tables for record in table.records]


def _normalize_query_results(query_name: str, mongo_rows: list[dict[str, Any]], influx_rows: list[dict[str, Any]]) -> tuple[Any, Any]:
	if query_name in _COUNT_QUERY_NAMES:
		mongo_count = 0
		for row in mongo_rows:
			for v in row.values():
				try:
					mongo_count += _safe_int(v)
					break
				except Exception:
					continue

		influx_count = 0
		for row in influx_rows:
			if "_value" in row:
				influx_count += _safe_int(row["_value"])
			else:
				for v in row.values():
					try:
						influx_count += _safe_int(v)
						break
					except Exception:
						continue
		return mongo_count, influx_count
	if query_name == "4_aggregate_average":
		mongo_values = [float(row["average_value"]) for row in mongo_rows if "average_value" in row]
		influx_values = [float(row["_value"]) for row in influx_rows if "_value" in row]
		return mongo_values, influx_values

	if query_name == "5_group_by_max":
		mongo_normalized = sorted(
			(
				{
					"group": _canonicalize_value(row.get("_id")),
					"value": _canonicalize_value(row.get("max_value")),
				}
				for row in mongo_rows
				if "_id" in row and "max_value" in row
			),
			key=lambda item: json.dumps(item, sort_keys=True),
		)
		influx_normalized = sorted(
			(
				{
					"group": _canonicalize_value(row.get("device-id")),
					"value": _canonicalize_value(row.get("_value")),
				}
				for row in influx_rows
				if "device-id" in row and "_value" in row
			),
			key=lambda item: json.dumps(item, sort_keys=True),
		)
		return mongo_normalized, influx_normalized

	if query_name == "6_time_bucketing_1m":
		mongo_normalized = sorted(
			(
				{
					"group": _epoch_microseconds(row.get("_id")),
					"value": _canonicalize_value(row.get("average_value")),
				}
				for row in mongo_rows
				if "_id" in row and "average_value" in row
			),
			key=lambda item: (item["group"], json.dumps(item["value"], sort_keys=True, default=str)),
		)
		influx_normalized = sorted(
			(
				{
					"group": _epoch_microseconds(row.get("_time")),
					"value": _canonicalize_value(row.get("_value")),
				}
				for row in influx_rows
				if "_time" in row and "_value" in row
			),
			key=lambda item: (item["group"], json.dumps(item["value"], sort_keys=True, default=str)),
		)
		return mongo_normalized, influx_normalized

	# If Influx returns per-field rows (contains `_field`), expand Mongo documents
	# into comparable per-field records so the two sides can be compared meaningfully.
	if any(isinstance(row, dict) and "_field" in row for row in influx_rows):
		expanded = []
		for row in mongo_rows:
			measurement = row.get("measurement")
			tags = row.get("tags", {}) or {}
			fields = row.get("fields", {}) or {}
			timestamp = row.get("timestamp")
			for fname, fval in (fields.items() if isinstance(fields, dict) else []):
				rec = {
					"_measurement": measurement,
					"_field": fname,
					"_value": fval,
				}
				# include tags
				rec.update(tags)
				# convert numeric microsecond epoch to ISO time if possible
				try:
					from datetime import datetime, timezone as _tz
					if isinstance(timestamp, (int, float)):
						rec["_time"] = datetime.fromtimestamp(timestamp / 1_000_000, _tz.utc).isoformat()
				except Exception:
					pass
				expanded.append(rec)
		return [_canonicalize_value(row) for row in expanded], [_canonicalize_value({key: value for key, value in row.items() if key not in _INFLUX_METADATA_KEYS}) for row in influx_rows]

	return [_canonicalize_value(row) for row in mongo_rows], [_canonicalize_value({key: value for key, value in row.items() if key not in _INFLUX_METADATA_KEYS}) for row in influx_rows]


def _query_results_match(query_name: str, mongo_rows: list[dict[str, Any]], influx_rows: list[dict[str, Any]]) -> bool:
	try:
		mongo_normalized, influx_normalized = _normalize_query_results(query_name, mongo_rows, influx_rows)
		if type(mongo_normalized) == int and type(influx_normalized) == int:
			return mongo_normalized == influx_normalized
		return mongo_normalized == influx_normalized
	except Exception as e:
		logger.error(f"Error normalizing query results for {query_name}: {e}")
		return False


def _is_mongo_timeout_error(error: BaseException) -> bool:
	current_error: BaseException | None = error
	while current_error is not None:
		if _MONGO_TIMEOUT_EXCEPTIONS and isinstance(current_error, _MONGO_TIMEOUT_EXCEPTIONS):
			return True
		if "timed out" in str(current_error).lower():
			return True
		current_error = current_error.__cause__ or current_error.__context__
	return False


def _is_timeout_error(error: BaseException) -> bool:
	return _is_mongo_timeout_error(error) or "timed out" in str(error).lower()


def _mongo_query_time_ms(collection: Any, pipeline: list) -> int:
	try:
		explain = collection.database.command(
			"explain",
			{"aggregate": collection.name, "pipeline": pipeline, "cursor": {}},
			verbosity="executionStats",
		)
	except Exception as e:
		logger.error(f"MongoDB explain failed: {e}")
		raise RuntimeError(f"MongoDB explain failed: {e}") from e
	records = [explain]
	print_results(records)
	duration = _find_numeric_value([explain], "executionTimeMillis")
	if duration is None:
		duration = _find_numeric_value([explain], "executionTimeMillisEstimate")
	if duration is None:
		raise RuntimeError("MongoDB did not return an execution time for the benchmark query")
	return duration

def print_results(records: Iterable[Any]) -> None:
	if log == True:
		for record in records:
			logger.info(f"Record: {json.dumps(record, indent=2, default=str)}")

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

def get_full_query_count(config: dict[str, Any]) -> int:
	'''
	Get the total number of queries which will be tested.

	Returns: int
		- The total count of queries performed during the benchmarking process.
	'''
	query_windows = adjust_query_windows(QUERY_WINDOWS, LAST_KNOWN_TIMESTAMP)
	now = datetime.now(timezone.utc)
	precision = config.get("timestamp_precision", "us")
	bucket = config["influx_bucket"]

	# Sum lengths of generated query dicts for each window instead of iterating
	total = 0
	for _, window in query_windows.items():
		cutoff_timestamp = _timestamp_cutoff(now, window, precision)
		influx_start_iso = (now - window).isoformat().replace("+00:00", "Z")
		# Avoid building the full list in memory; count items as they are generated
		total += sum(1 for _ in generate_benchmark_queries(
			bucket=bucket,
			start_time_iso=influx_start_iso,
			cutoff_timestamp=cutoff_timestamp,
			target_field="rpm",
		))
	return total

def build_performances(config: dict[str, Any], repeat_count: int) -> Performances:
	performances = Performances()
	mongo_client, mongo_db = connect(
		url=config["mongo_url"],
		timeout=TIMEOUT_MS,
		port=config["mongo_port"],
		username=config.get("mongo_username", ""),
		password=config.get("mongo_password", ""),
		db_name=config["mongo_db"],
	)
	influx_client = influxdb_client.InfluxDBClient(
		url=config["influx_url"],
		token=config["influx_token"],
		org=config["influx_org"],
		timeout=TIMEOUT_MS,
	)
	error_count = 0
	success_count = 0
	try:
		collection = mongo_db["telemetry_lines"]
		now = datetime.now(timezone.utc)
		precision = config.get("timestamp_precision", "us")
		query_windows = adjust_query_windows(QUERY_WINDOWS, LAST_KNOWN_TIMESTAMP)
		total_queries = get_full_query_count(config)
		for query_name, window in query_windows.items():
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
				try:
					for _ in range(repeat_count):
						query_timed_out = False
						try:
							mongo_time_ms = _mongo_query_time_ms(collection, q["mongo"])
						except Exception as mongo_error:
							if not _is_timeout_error(mongo_error):
								raise
							mongo_time_ms = TIMEOUT_MS
							query_timed_out = True
							logger.warning(
								f"MongoDB timed out for {test_name}_{query_name}; using {mongo_time_ms} ms"
							)
						try:
							influx_time_ms = _influx_query_time_ms(
									influx_client,
									config["influx_org"],
									q["influx"],
								)
						except Exception as influx_error:
							logger.error(f"InfluxDB query failed for {test_name}_{query_name}: {influx_error}")
							if _is_timeout_error(influx_error):
								influx_time_ms = TIMEOUT_MS
								query_timed_out = True
								logger.warning(
									f"InfluxDB timed out for {test_name}_{query_name}; using {influx_time_ms} ms"
								)
							else:
								influx_time_ms = None
						mongo_rows: list[dict[str, Any]] = []
						influx_rows: list[dict[str, Any]] = []
						try:
							mongo_rows = _mongo_query_results(collection, q["mongo"])
						except Exception as mongo_error:
							if not _is_timeout_error(mongo_error):
								raise
							mongo_time_ms = TIMEOUT_MS
							query_timed_out = True
							logger.warning(
								f"MongoDB timed out for {test_name}_{query_name}; using {mongo_time_ms} ms"
							)
						try:
							influx_rows = _influx_query_results(
								influx_client,
								config["influx_org"],
								q["influx"],
							)
						except Exception as influx_error:
							logger.error(f"InfluxDB query failed for {test_name}_{query_name}: {influx_error}")
							if _is_timeout_error(influx_error):
								influx_time_ms = TIMEOUT_MS
								query_timed_out = True
								logger.warning(
									f"InfluxDB timed out for {test_name}_{query_name}; using {influx_time_ms} ms"
								)
							else:
								raise
						if not query_timed_out and not _query_results_match(test_name, mongo_rows, influx_rows):
							mongo_normalized, influx_normalized = _normalize_query_results(test_name, mongo_rows, influx_rows)
							if type(mongo_normalized) != int:
								mongo_normalized:int = len(mongo_normalized)
							if type(influx_normalized) != int:
								influx_normalized:int = len(influx_normalized)
							raise ValueError(
								f"MongoDB and InfluxDB returned different results: "
								f"mongo_count={mongo_normalized}, influx_count={influx_normalized}"
							)
						performances.add(f"{test_name}_{query_name}", QueryPerformance(influx_time_ms, mongo_time_ms))
				except Exception as e:
					error_count += 1
					logger.error(f"{error_count:02d}/{error_count+success_count:02d}: query {test_name}_{query_name} failed: {e}")
				else:
					success_count += 1
					try:
						performances.save_all("partial_results.json")
						#logger.info("Partial results saved to partial_results.json")
					except Exception as e:
						logger.error(f"Failed to save partial results: {e}")
					logger.info(f"{success_count:02d}/{total_queries:02d}: query {test_name}_{query_name} completed successfully")
		logger.info(f"All queries completed: {success_count} successful, {error_count} errors")
	finally:
		logger.info(f"Completed with {success_count} successful queries and {error_count} errors")
		influx_client.close()
		logger.info(f"InfluxDB connection closed")
		mongo_client.close()
		logger.info(f"MongoDB connection closed")
	return performances


def main(argv: list[str] | None = None) -> Performances:
	argv = argv or sys.argv
	config_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_CONFIG_PATH
	repeat_count = REPEAT_COUNT
	config = _load_config(config_path)
	logger.info(f"Influx config: {config.get('influx', {k: v for k, v in config.items() if str(k).startswith('influx_')})}")
	performances = build_performances(config, repeat_count)
	logger.info("Benchmarking completed")
	logger.info(f"Performances: {performances}")
	logger.info("Saving performance results...")
	performances.save_all()
	logger.info("Performance results saved!")
	return performances


if __name__ == "__main__":
	main()
