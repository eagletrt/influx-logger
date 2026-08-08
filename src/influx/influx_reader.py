import json
import csv
import io
import gzip

from queue import Queue, Empty
from datetime import datetime

from src.utils.logger_utils import logger
from src.utils.timestamp import TimestampPrecision
from src.influx.influx_manager import InfluxManager
from src.connections.influx_connection import InfluxConnection
from src.connections.mqtt_connection import MQTTConnection

class InfluxReader(InfluxManager):
    """
    A reader for interacting with InfluxDB. Handles incoming query requests,
    fetches data, formats it as CSV, and publishes it back over MQTT.
    """
    def __init__(self, client: InfluxConnection, mqtt_client: MQTTConnection, log_bucket: str, timestamp_precision: str = TimestampPrecision.us.name) -> None:
        super().__init__(client, timestamp_precision, name="InfluxReader")
        self.query_api = self.client.connection.query_api()
        self.mqtt = mqtt_client
        self.log_bucket = log_bucket
        self.query_queue: Queue = Queue()

    def add_query_to_queue(self, vehicle_id: str, device_id: str, transaction_id: str, payload: bytes) -> None:
        """Enqueue the query request for asynchronous processing."""
        self.query_queue.put((vehicle_id, device_id, transaction_id, payload))

    def run(self) -> None:
        logger.info("InfluxReader: Thread started for query processing.")
        while not self.stopped():
            try:
                # Timeout di 1 secondo per non bloccare il controllo di self.stopped()
                vehicle_id, device_id, transaction_id, payload = self.query_queue.get(timeout=1.0)
                self._process_query(vehicle_id, device_id, transaction_id, payload)
            except Empty:
                continue
            except Exception as e:
                logger.error(f"InfluxReader: Error in main loop: {e}")

    def _process_query(self, vehicle_id: str, device_id: str, transaction_id: str, payload: bytes) -> None:
        logger.info(f"InfluxReader: Inizio elaborazione query {transaction_id} per {vehicle_id}/{device_id}")
        
        try:
            req_data = json.loads(payload.decode('utf-8'))
            start_time = req_data.get("start")
            stop_time = req_data.get("stop")

            if not start_time or not stop_time:
                raise ValueError("Payload JSON non valido: 'start' e 'stop' sono obbligatori.")

            start_ns = int(start_time) * 1000
            stop_ns = int(stop_time) * 1000

            flux_query = f'''
                from(bucket: "{self.log_bucket}")
                |> range(start: time(v: {start_ns}), stop: time(v: {stop_ns}))
                |> filter(fn: (r) => r["vehicle-id"] == "{vehicle_id}")
                |> filter(fn: (r) => r["device-id"] == "{device_id}")
                |> rename(columns: {{_time: "timestamp"}})
                |> pivot(rowKey:["timestamp"], columnKey: ["_field"], valueColumn: "_value")
                |> group(columns: ["network", "_measurement"])
            '''

            tables = self.query_api.query(flux_query, org=self.client.org)

            for table in tables:
                records = table.records
                if not records:
                    continue

                network_name = records[0].values.get("network", "unknown")
                measurement_name = records[0].values.get("_measurement", "unknown")

                antenna = records[0].values.get("antenna_name")
                if antenna:

                    network_name = antenna

                    measurement_name = f"{antenna}_{measurement_name}"

                columns_set = set()
                for record in records:
                    for key in record.values.keys():
                        clean_key = key.strip().lower()
                        
                        if not clean_key.startswith("_") and clean_key not in [
                            "result", "table", "network", "antenna_name", 
                            "vehicle-id", "device-id", "vehicle_id", "device_id"
                        ]:
                            columns_set.add(clean_key)
                
                if "timestamp" in columns_set:
                    columns_set.remove("timestamp")

                columns_list = ["_timestamp"] + sorted(list(columns_set))

                csv_buffer = io.StringIO()
                writer = csv.DictWriter(csv_buffer, fieldnames=columns_list, lineterminator='\n')
                writer.writeheader()

                for record in table.records:
                    row = {}
                    
                    dt = record.values.get("timestamp")
                    if dt is not None:
                        if isinstance(dt, (int, float)):
                            row["_timestamp"] = int(dt / 1000)
                        elif hasattr(dt, 'timestamp'):
                            row["_timestamp"] = int(dt.timestamp()) * 1000000 + dt.microsecond
                        else:
                            row["_timestamp"] = 0
                    
                    for key, value in record.values.items():
                        clean_key = key.strip().lower()
                        if clean_key in columns_set and value is not None and value != "":
                            row[clean_key] = value
                    
                    writer.writerow(row)

                csv_content = csv_buffer.getvalue()
                compressed_content = gzip.compress(csv_content.encode('utf-8'))

                topic_out = f"{vehicle_id}/{device_id}/query/{transaction_id}/data/content/{network_name}--{measurement_name.lower()}"
                
                self.mqtt.connection.publish(topic_out, compressed_content, qos=0)  
                logger.info(f"InfluxReader: Inviato CSV compresso per '{network_name}--{measurement_name.lower()}' ({len(records)} righe).")

            eof_topic = f"{vehicle_id}/{device_id}/query/{transaction_id}/data/content/eof"
            self.mqtt.connection.publish(eof_topic, b"", qos=0)  # <-- Aggiunto .connection
            logger.info(f"InfluxReader: Query {transaction_id} completata (inviato EOF).")

        except Exception as e:
            logger.error(f"InfluxReader: Errore durante la query {transaction_id}: {e}")
            error_topic = f"{vehicle_id}/{device_id}/query/{transaction_id}/data/content/error"
            self.mqtt.connection.publish(error_topic, json.dumps({"error": str(e)}).encode('utf-8'), qos=0)  