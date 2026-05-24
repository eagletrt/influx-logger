from datetime import datetime, timezone
from pathlib import Path
import json
import sys

from test_report.queries import generate_benchmark_queries, QUERY_WINDOWS
from test_report.mongoconnection import connect
import influxdb_client


def expand_mongo_rows(mongo_rows):
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
            rec.update(tags)
            try:
                if isinstance(timestamp, (int, float)):
                    rec["_time"] = datetime.fromtimestamp(timestamp / 1_000_000, timezone.utc).isoformat()
            except Exception:
                pass
            expanded.append(rec)
    return expanded


def normalize_row_for_cmp(row):
    # pick a stable representation
    keys = sorted(k for k in row.keys() if k not in {"result", "table", "_start", "_stop"})
    normalized = []
    for k in keys:
        v = row.get(k, "")
        if k == "_time":
            # normalize time strings to ISO with 'T'
            try:
                from datetime import datetime
                if isinstance(v, str):
                    ts = v.replace(" ", "T")
                    dt = datetime.fromisoformat(ts)
                else:
                    # assume datetime-like
                    dt = v
                v = dt.isoformat()
            except Exception:
                pass
        if k == "_value":
            # normalize numeric-like values
            try:
                v_float = float(v)
                v = str(v_float)
            except Exception:
                # booleans or other strings
                if isinstance(v, bool):
                    v = str(v)
                else:
                    v = str(v)
        normalized.append((k, v))
    return tuple(normalized)


if __name__ == '__main__':
    window_name = sys.argv[1] if len(sys.argv) > 1 else 'last_24_hours'
    config_path = Path(__file__).resolve().parents[1] / 'config.json'
    with config_path.open() as f:
        config = json.load(f)

    mongo_client, mongo_db = connect(
        url=config['mongo_url'],
        port=config['mongo_port'],
        username=config.get('mongo_username', ''),
        password=config.get('mongo_password', ''),
        db_name=config['mongo_db'],
    )
    influx_client = influxdb_client.InfluxDBClient(
        url=config['influx_url'],
        token=config['influx_token'],
        org=config['influx_org'],
    )

    try:
        now = datetime.now(timezone.utc)
        window = QUERY_WINDOWS[window_name]
        influx_start = now - window
        influx_start_iso = influx_start.isoformat().replace('+00:00', 'Z')
        cutoff = int((now - window).timestamp() * 1_000_000)

        queries = generate_benchmark_queries(bucket=config['influx_bucket'], start_time_iso=influx_start_iso, cutoff_timestamp=cutoff, target_field='rpm')
        test_name = '1_time_range'
        q = queries[test_name]

        collection = mongo_db['telemetry_lines']
        mongo_rows = list(collection.aggregate(q['mongo']))
        expanded = expand_mongo_rows(mongo_rows)

        tables = influx_client.query_api().query(org=config['influx_org'], query=q['influx'])
        influx_rows = [dict(rec.values) for table in tables for rec in table.records]

        set_mongo = set(normalize_row_for_cmp(r) for r in expanded)
        set_influx = set(normalize_row_for_cmp(r) for r in influx_rows)

        only_mongo = list(set_mongo - set_influx)
        only_influx = list(set_influx - set_mongo)

        print(f"expanded mongo: {len(expanded)}, influx: {len(influx_rows)}")
        print(f"only_mongo: {len(only_mongo)}, only_influx: {len(only_influx)}")
        print('\nExamples only in mongo:')
        for ex in only_mongo[:5]:
            print(ex)
        print('\nExamples only in influx:')
        for ex in only_influx[:5]:
            print(ex)

    finally:
        influx_client.close()
        mongo_client.close()
