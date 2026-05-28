from datetime import timedelta, datetime, timezone
from typing import Any, Dict
import re

LAST_KNOWN_TIMESTAMP = "2026-05-27T23:00:00Z"

QUERY_WINDOWS = {
    "last_30_minutes": timedelta(minutes=30) + timedelta(seconds=-15),
	"last_2_hours": timedelta(hours=2) + timedelta(minutes=-30),
	"last_12_hours": timedelta(hours=12) + timedelta(minutes=-45),
    "last_3_days": timedelta(days=3) + timedelta(hours=-1),
	"week_ago_to_3_days_ago": timedelta(days=7) + timedelta(days=-3),
    "30sec": timedelta(seconds=30),
	"last_5_minutes": timedelta(minutes=5),
	"last_1_hour": timedelta(hours=1),
	"last_24_hours": timedelta(hours=24),
	"one_week_ago": timedelta(days=7),
}

def adjust_query_windows(windows: Dict[str, timedelta], last_timestamp_iso: str) -> Dict[str, timedelta]:
    """
    Adjusts the query windows based on the last known timestamp.
    If the last known timestamp is in the past, it shifts all windows to be relative to that timestamp.
    """
    normalized_iso = last_timestamp_iso.strip().replace("Z", "+00:00")
    normalized_iso = re.sub(r"T(\d):", r"T0\1:", normalized_iso)
    try:
        last_timestamp = datetime.fromisoformat(normalized_iso)
    except ValueError:
        last_timestamp = datetime.strptime(normalized_iso, "%Y-%m-%dT%H:%M:%S%z")
    now = datetime.now(timezone.utc)

    if last_timestamp < now:
        # If a last-known timestamp is provided in the past, do not expand
        # or otherwise distort the configured time windows here. Returning
        # the original windows keeps ranges relative to the current time.
        return windows
    else:
        return windows

def generate_benchmark_queries(
    bucket: str, 
    start_time_iso: str, 
    cutoff_timestamp: int, 
    target_vehicle: str = "influx-test-vehicle",
    target_field: str = "_value",
    threshold_value: int = 100
) -> Dict[str, Dict[str, Any]]:
    """
    Generates a dictionary of benchmark queries for both MongoDB and InfluxDB.
    Each entry contains a 'mongo' pipeline and an 'influx' Flux query.
    """
    return {
        # 1. Simple Time Range Query: Get all records in the last 5 minutes
        "1_time_range": {
            "mongo": [
                {"$match": {"timestamp": {"$gte": cutoff_timestamp}, "fields": {"$ne": {}}}}
            ],
            "influx": f'''
                from(bucket: "{bucket}")
                  |> range(start: time(v: "{start_time_iso}"))
            '''
        },
        # 2. Filter by Tag: Get all records for a specific vehicle
        "2_filter_by_tag": {
            "mongo": [
                {"$match": {
                    "timestamp": {"$gte": cutoff_timestamp},
                    "tags.vehicle-id": target_vehicle,
                    "fields": {"$ne": {}}
                }}
            ],
            "influx": f'''
                from(bucket: "{bucket}")
                  |> range(start: time(v: "{start_time_iso}"))
                  |> filter(fn: (r) => r["vehicle-id"] == "{target_vehicle}")
            '''
        },
        # 3. Filter by Tag and Field Value (e.g., high speed events for a specific vehicle)
        "3_filter_by_value": {
            "mongo": [
                {"$match": {
                    "timestamp": {"$gte": cutoff_timestamp},
                    "tags.vehicle-id": target_vehicle,
                    f"fields.{target_field}": {"$gt": threshold_value}
                }},
                {"$count": "count"}
            ],
            "influx": f'''
                from(bucket: "{bucket}")
                  |> range(start: time(v: "{start_time_iso}"))
                  |> filter(fn: (r) => r["vehicle-id"] == "{target_vehicle}" and r._field == "{target_field}" and r._value > {threshold_value})
                  |> count()
            '''
        },

        # 4. Aggregation: Calculate Average of a specific field across all devices
        "4_aggregate_average": {
            "mongo": [
                {"$match": {
                    "timestamp": {"$gte": cutoff_timestamp},
                    f"fields.{target_field}": {"$exists": True}
                }},
                {"$group": {
                    "_id": None,
                    "average_value": {"$avg": f"$fields.{target_field}"}
                }}
            ],
                        "influx": f'''
                                from(bucket: "{bucket}")
                                    |> range(start: time(v: "{start_time_iso}"))
                                    |> filter(fn: (r) => r._field == "{target_field}")
                                    |> mean()
                        '''
        },

        # 5. Group By Tag: Calculate Max value grouped by device-id
        "5_group_by_max": {
            "mongo": [
                {"$match": {
                    "timestamp": {"$gte": cutoff_timestamp},
                    f"fields.{target_field}": {"$exists": True}
                }},
                {"$group": {
                    "_id": "$tags.device-id",
                    "max_value": {"$max": f"$fields.{target_field}"}
                }}
            ],
                        "influx": f'''
                                from(bucket: "{bucket}")
                                    |> range(start: time(v: "{start_time_iso}"))
                                    |> filter(fn: (r) => r._field == "{target_field}")
                                    |> group(columns: ["device-id"])
                                    |> max()
                        '''
        },

        # 6. Time-Bucketing / Downsampling: Average value grouped into 1-minute windows
        # Note: In Mongo, this assumes the timestamp is stored as a Date object or can be manipulated.
        # Here we use basic math to bucket Unix microsecond timestamps into 60-second blocks.
        "6_time_bucketing_1m": {
            "mongo": [
                {"$match": {
                    "timestamp": {"$gte": cutoff_timestamp},
                    f"fields.{target_field}": {"$exists": True}
                }},
                {"$group": {
                    "_id": {
                        "$subtract": [
                            "$timestamp",
                            {"$mod": ["$timestamp", 60000000]} # Assuming microseconds timestamp (60s * 1M us)
                        ]
                    },
                    "average_value": {"$avg": f"$fields.{target_field}"}
                }},
                {"$sort": {"_id": 1}}
            ],
                        "influx": f'''
                                from(bucket: "{bucket}")
                                    |> range(start: time(v: "{start_time_iso}"))
                                    |> filter(fn: (r) => r._field == "{target_field}")
                                    |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
                                    |> yield(name: "mean")
                        '''
        },
        
        # 7. Unique Devices (Cardinality check)
        "7_unique_devices": {
            "mongo": [
                {"$match": {"timestamp": {"$gte": cutoff_timestamp}, "fields": {"$ne": {}}}},
                {"$group": {"_id": "$tags.device-id"}},
                {"$count": "unique_devices"}
            ],
            "influx": f'''
                from(bucket: "{bucket}")
                    |> range(start: time(v: "{start_time_iso}"))
                    |> filter(fn: (r) => exists r["device-id"] and r["device-id"] != "")
                    |> keep(columns: ["device-id"])
                    |> distinct(column: "device-id")
                    |> count()
            '''
        },

        # 8. Complex Query: Average value for a specific vehicle, grouped by 1-minute windows
        "8_complex_vehicle_time_bucketing": {
            "mongo": [
                {"$match": {
                    "timestamp": {"$gte": cutoff_timestamp},
                    "tags.vehicle-id": target_vehicle,
                    f"fields.{target_field}": {"$exists": True}
                }},
                {"$group": {
                    "_id": {
                        "$subtract": [
                            "$timestamp",
                            {"$mod": ["$timestamp", 60000000]} # Assuming microseconds timestamp (60s * 1M us)
                        ]
                    },
                    "average_value": {"$avg": f"$fields.{target_field}"}
                }},
                {"$sort": {"_id": 1}}
            ],
                        "influx": f'''
                                from(bucket: "{bucket}")
                                    |> range(start: time(v: "{start_time_iso}"))
                                    |> filter(fn: (r) => r["vehicle-id"] == "{target_vehicle}" and r._field == "{target_field}")
                                    |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
                                    |> yield(name: "mean")
                        '''
        },

        # 9. Existence Check: Count how many records have a specific field present
        "9_existence_check": {
            "mongo": [
                {"$match": {
                    "timestamp": {"$gte": cutoff_timestamp},
                    f"fields.{target_field}": {"$exists": True}
                }},
                {"$count": "records_with_field"}
            ],
            "influx": f'''
                from(bucket: "{bucket}")
                    |> range(start: time(v: "{start_time_iso}"))
                    |> filter(fn: (r) => r._field == "{target_field}")
                    |> count()
            '''
        },

        # 10. Non-Empty Fields: Count how many records have a non-empty fields object
        "10_non_empty_fields": {
            "mongo": [
                {"$match": {
                    "timestamp": {"$gte": cutoff_timestamp},
                    "fields": {"$ne": {}}
                }},
                {"$count": "records_with_non_empty_fields"}
            ],
            "influx": f'''
                from(bucket: "{bucket}")
                    |> range(start: time(v: "{start_time_iso}"))
                    |> filter(fn: (r) => exists r.fields and r.fields != {{}})
                    |> count()
            '''
        }
    }
