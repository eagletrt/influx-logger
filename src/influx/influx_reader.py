import json
import csv
import io
from queue import Queue, Empty

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
        logger.info(f"InfluxReader: Processing query {transaction_id} for {vehicle_id}/{device_id}")
        
        try:
            req_data = json.loads(payload.decode('utf-8'))
            start_time = req_data.get("start")
            stop_time = req_data.get("stop")

            if not start_time or not stop_time:
                raise ValueError("Payload must contain 'start' and 'stop' timestamps.")

            # Build the Flux query to fetch data from InfluxDB
            # Pivot(): transform the data so that each field becomes a column
            # group(): separates the results into distinct tables for each message (e.g., INVERTER, BMS, etc.)
            flux_query = f'''
                from(bucket: "{self.log_bucket}")
                |> range(start: {start_time}, stop: {stop_time})
                |> filter(fn: (r) => r["vehicle-id"] == "{vehicle_id}")
                |> filter(fn: (r) => r["device-id"] == "{device_id}")
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                |> group(columns: ["_measurement"])
            '''

            tables = self.query_api.query(flux_query, org=self.client.org)

            if not tables:
                logger.warning(f"InfluxReader: Nessun dato trovato per la query {transaction_id}")

            # Elaborate each table (each measurement) and generate CSV content
            for table in tables:
                if not table.records:
                    continue

                measurement_name = table.records[0].values.get("_measurement", "unknown")

                # Identify the columns to include in the CSV, excluding certain keys
                exclude_keys = {"_start", "_stop", "_measurement", "result", "table", "_time", "vehicle-id", "device-id", "network"}
                columns_set = set()
                for record in table.records:
                    for key in record.values.keys():
                        if key not in exclude_keys:
                            columns_set.add(key)
                
                # C++ expected to have a consistent order of columns, so we sort them
                fieldnames = ["_timestamp"] + sorted(list(columns_set))

                # generate CSV content
                csv_buffer = io.StringIO()
                writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
                writer.writeheader()

                for record in table.records:
                    row = {}
                    # get the timestamp in microseconds
                    dt = record.values.get("_time")
                    if dt:
                        row["_timestamp"] = int(dt.timestamp() * 1_000_000)
                    
                    # populate the row with the values for each column
                    for key in columns_set:
                        row[key] = record.values.get(key, "")
                    
                    writer.writerow(row)

                csv_content = csv_buffer.getvalue()

                # Compress the CSV content using gzip
                compressed_content = gzip.compress(csv_content.encode('utf-8'))

                #publish the compressed CSV content to the MQTT topic
                topic_out = f"{vehicle_id}/{device_id}/query/{transaction_id}/content/{measurement_name}"
                self.mqtt.connection.publish(topic_out, compressed_content)
                logger.info(f"InfluxReader: Inviato CSV per '{measurement_name}' ({len(table.records)} righe).")

            # report the end of the query processing by sending an EOF message
            eof_topic = f"{vehicle_id}/{device_id}/query/{transaction_id}/content/eof"
            self.mqtt.connection.publish(eof_topic, b"")
            logger.info(f"InfluxReader: Query {transaction_id} completata (inviato EOF).")

        except Exception as e:
            logger.error(f"InfluxReader: Errore durante la query {transaction_id}: {e}", exc_info=True)
            error_topic = f"{vehicle_id}/{device_id}/query/{transaction_id}/content/error"
            if self.mqtt and self.mqtt.connection:
                error_payload = json.dumps({"error": str(e)}).encode('utf-8')
                self.mqtt.connection.publish(error_topic, error_payload)