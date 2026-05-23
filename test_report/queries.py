from datetime import datetime
from typing import Any, Dict

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
        # 1. Basic Count (Baseline)
        "1_basic_count": {
            "mongo": [
                {"$match": {"timestamp": {"$gte": cutoff_timestamp}}},
                {"$count": "count"}
            ],
                        "influx": f'''
                                from(bucket: "{bucket}")
                                    |> range(start: time(v: "{start_time_iso}"))
                                    |> count()
                        '''
        },

        # 2. Filter by Tag (Find all data for a specific vehicle)
        "2_filter_by_tag": {
            "mongo": [
                {"$match": {
                    "timestamp": {"$gte": cutoff_timestamp},
                    "vehicle-id": target_vehicle
                }},
                {"$count": "count"}
            ],
                        "influx": f'''
                                from(bucket: "{bucket}")
                                    |> range(start: time(v: "{start_time_iso}"))
                                    |> filter(fn: (r) => r["vehicle-id"] == "{target_vehicle}")
                                    |> count()
                        '''
        },

        # 3. Filter by Tag and Field Value (e.g., high speed events for a specific vehicle)
        "3_filter_by_value": {
            "mongo": [
                {"$match": {
                    "timestamp": {"$gte": cutoff_timestamp},
                    "vehicle-id": target_vehicle,
                    target_field: {"$gt": threshold_value}
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
                    target_field: {"$exists": True}
                }},
                {"$group": {
                    "_id": None,
                    "average_value": {"$avg": f"${target_field}"}
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
                    target_field: {"$exists": True}
                }},
                {"$group": {
                    "_id": "$device-id",
                    "max_value": {"$max": f"${target_field}"}
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
                    target_field: {"$exists": True}
                }},
                {"$group": {
                    "_id": {
                        "$subtract": [
                            "$timestamp",
                            {"$mod": ["$timestamp", 60000000]} # Assuming microseconds timestamp (60s * 1M us)
                        ]
                    },
                    "average_value": {"$avg": f"${target_field}"}
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
                {"$match": {"timestamp": {"$gte": cutoff_timestamp}}},
                {"$group": {"_id": "$device-id"}},
                {"$count": "unique_devices"}
            ],
                        "influx": f'''
                                from(bucket: "{bucket}")
                                    |> range(start: time(v: "{start_time_iso}"))
                                    |> keep(columns: ["device-id"])
                                    |> distinct(column: "device-id")
                                    |> count()
                        '''
        }
    }
