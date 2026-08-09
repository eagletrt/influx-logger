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
        self.mqtt: MQTTConnection = mqtt_client
        self.log_bucket: str = log_bucket
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

            start_dt = datetime.utcfromtimestamp(int(start_time) / 1000000.0).strftime('%Y-%m-%dT%H:%M:%SZ')
            stop_dt = datetime.utcfromtimestamp(int(stop_time) / 1000000.0).strftime('%Y-%m-%dT%H:%M:%SZ')

            flux_query = f'''
                from(bucket: "{self.log_bucket}")
                |> range(start: {start_dt}, stop: {stop_dt})
                |> filter(fn: (r) => r["vehicle-id"] == "{vehicle_id}")
                |> filter(fn: (r) => r["device-id"] == "{device_id}")
                |> drop(columns: ["_time"])
                |> pivot(rowKey:["_start"], columnKey: ["_field"], valueColumn: "_value")
                |> group(columns: ["network", "_measurement"])
            '''

            tables = self.query_api.query(flux_query, org=self.client.org)

            if not tables:
                logger.warning(f"InfluxReader: Nessun dato trovato per la query {transaction_id}")

            for table in tables:
                if not table.records:
                    continue

                measurement_name = table.records[0].values.get("_measurement", "unknown")

                network_name = table.records[0].values.get("network", "unknown")

                exclude_keys = {"_start", "_stop", "_measurement", "result", "table", "_time", "vehicle-id", "device-id", "network"}
                columns_set = set()
                for record in table.records:
                    for key in record.values.keys():
                        if key not in exclude_keys:
                            columns_set.add(key)
                
                fieldnames = ["_timestamp"] + sorted(list(columns_set))

                csv_buffer = io.StringIO()
                writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
                writer.writeheader()

                for record in table.records:
                    row = {}
                    dt = record.values.get("_time") or record.values.get("_start")
                    if dt is not None:
                        if isinstance(dt, (int, float)):
                            row["_timestamp"] = int(dt * TimestampPrecision.get_factor(self.timestamp_precision))
                        elif hasattr(dt, 'timestamp'):
                            row["_timestamp"] = int(dt.timestamp() * TimestampPrecision.get_factor(self.timestamp_precision))
                        else:
                            row["_timestamp"] = 0
                    
                    for key in columns_set:
                        row[key] = record.values.get(key, "")
                    
                    writer.writerow(row)

                csv_content = csv_buffer.getvalue()
                compressed_content = gzip.compress(csv_content.encode('utf-8'))

                topic_out = f"{vehicle_id}/{device_id}/query/{transaction_id}/data/content/{network_name}--{measurement_name}"
                self.mqtt.connection.publish(topic_out, compressed_content)
                logger.info(f"InfluxReader: Inviato CSV compresso per '{network_name}--{measurement_name}' ({len(table.records)} righe).")

            eof_topic = f"{vehicle_id}/{device_id}/query/{transaction_id}/data/content/eof"
            self.mqtt.connection.publish(eof_topic, b"")
            logger.info(f"InfluxReader: Query {transaction_id} completata (inviato EOF).")

        except Exception as e:
            logger.error(f"InfluxReader: Errore durante la query {transaction_id}: {e}", exc_info=True)
            error_topic = f"{vehicle_id}/{device_id}/query/{transaction_id}/data/content/error"
            if self.mqtt and self.mqtt.connection:
                error_payload = json.dumps({"error": str(e)}).encode('utf-8')
                self.mqtt.connection.publish(error_topic, error_payload)