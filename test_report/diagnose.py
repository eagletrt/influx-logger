from datetime import datetime, timezone
from pathlib import Path
import sys
import json

from test_report.queries import generate_benchmark_queries, QUERY_WINDOWS
from test_report.mongoconnection import connect
import influxdb_client


def main():
    config_path = Path(__file__).resolve().parents[1] / "config.json"
    with config_path.open() as f:
        config = json.load(f)

def main(window_name: str = "last_5_minutes"):
    config_path = Path(__file__).resolve().parents[1] / "config.json"
    with config_path.open() as f:
        config = json.load(f)

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
        now = datetime.now(timezone.utc)
        if window_name not in QUERY_WINDOWS:
            raise SystemExit(f"Unknown window: {window_name}")
        window = QUERY_WINDOWS[window_name]
        influx_start = now - window
        influx_start_iso = influx_start.isoformat().replace("+00:00", "Z")
        cutoff = int((now - window).timestamp() * 1_000_000)

        queries = generate_benchmark_queries(bucket=config["influx_bucket"], start_time_iso=influx_start_iso, cutoff_timestamp=cutoff, target_field="rpm")
        test_name = "2_filter_by_tag"
        q = queries[test_name]

        print("--- Mongo pipeline ---")
        print(json.dumps(q["mongo"], indent=2, default=str))
        collection = mongo_db["telemetry_lines"]
        mongo_rows = list(collection.aggregate(q["mongo"]))
        print(f"Mongo rows ({len(mongo_rows)}):")
        for r in mongo_rows[:10]:
            print(json.dumps(r, default=str))

        print("--- Influx Flux ---")
        print(q["influx"]) 
        tables = influx_client.query_api().query(org=config["influx_org"], query=q["influx"])
        influx_rows = [dict(rec.values) for table in tables for rec in table.records]
        print(f"Influx rows ({len(influx_rows)}):")
        for r in influx_rows[:10]:
            print(json.dumps(r, default=str))

    finally:
        influx_client.close()
        mongo_client.close()


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "last_5_minutes"
    main(arg)
