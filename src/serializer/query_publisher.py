import json

from src.utils.logger_utils import logger
from src.serializer.query_protocol import (
    QueryChunkInfo,
    QueryError,
    QueryState,
    QueryStatus,
    build_status,
    content_topic,
    legacy_eof_topic,
    legacy_error_topic,
    status_topic,
)

STATUS_QOS: int = 1
'''Statuses are published at QoS 1: losing the message that reports a failure would leave
the requester waiting forever, which is exactly what the protocol exists to prevent.'''

CONTENT_QOS: int = 0
'''Chunks are published at QoS 0, as before: the manifest sent on completion lets the
requester detect a missing chunk without paying for QoS 1 on the whole payload.'''

class QueryPublisher:
    '''
    Single place where the query protocol reaches MQTT: builds the topics of a transaction
    and publishes on them without ever raising.

    Every publish is guarded because the MQTT connection is dropped, and set to None, as
    soon as the broker disconnects: an unguarded publish inside a failure handler would
    raise a second exception and the failure would never be reported.

    Attributes:
        mqtt (MQTTConnection): The connection used to publish, may be disconnected.
        vehicle_id (str): The vehicle the transaction belongs to.
        device_id (str): The device the transaction belongs to.
        transaction_id (str): The transaction being answered.
        legacy_topics (bool): Whether to also publish the pre-protocol eof and error topics.
    '''
    def __init__(
        self,
        mqtt,
        vehicle_id: str,
        device_id: str,
        transaction_id: str,
        legacy_topics: bool = True,
    ) -> None:
        self.mqtt = mqtt
        self.vehicle_id: str = vehicle_id
        self.device_id: str = device_id
        self.transaction_id: str = transaction_id
        self.legacy_topics: bool = legacy_topics

    def _safe_publish(self, topic: str, payload: bytes, qos: int) -> bool:
        '''
        Publishes a payload, reporting failures through the return value instead of exceptions.

        Args:
            topic (str): The topic to publish on.
            payload (bytes): The message body.
            qos (int): The QoS to publish with.
        Returns:
            bool: True if the broker accepted the message, False otherwise.
        '''
        connection = getattr(self.mqtt, "connection", None)
        if connection is None:
            logger.error(f"query_publisher: No MQTT connection available, cannot publish on '{topic}'")
            return False
        try:
            result = connection.publish(topic, payload, qos=qos)
        except Exception as error:
            logger.error(f"query_publisher: Failed to publish on '{topic}': {error}")
            return False
        return_code = getattr(result, "rc", 0)
        if return_code != 0:
            logger.error(f"query_publisher: Broker refused the message on '{topic}', return code: {return_code}")
            return False
        return True

    def publish_status(self, status: QueryStatus) -> bool:
        '''
        Publishes a status message on the status topic of the transaction.

        Args:
            status (QueryStatus): The status to publish.
        Returns:
            bool: True if the broker accepted the message, False otherwise.
        '''
        topic = status_topic(self.vehicle_id, self.device_id, self.transaction_id)
        try:
            payload = status.serializeAsProtobufString()
        except Exception as error:
            logger.error(f"query_publisher: Failed to serialize the status of query {self.transaction_id}: {error}")
            return False
        return self._safe_publish(topic, payload, STATUS_QOS)

    def publish_accepted(self) -> bool:
        '''Tells the requester the query has been received and queued.'''
        return self.publish_status(build_status(self.transaction_id, QueryState.QUERY_STATE_ACCEPTED))

    def publish_running(self) -> bool:
        '''Tells the requester the query is being executed.'''
        return self.publish_status(build_status(self.transaction_id, QueryState.QUERY_STATE_RUNNING))

    def publish_completed(
        self,
        chunks: list[QueryChunkInfo],
        total_rows: int,
        details: dict[str, str] = None,
    ) -> bool:
        '''
        Tells the requester every chunk has been published, and which ones.

        Args:
            chunks (list[QueryChunkInfo]): Manifest of the published chunks.
            total_rows (int): Total number of data rows published.
            details (dict[str, str]): Extra diagnostic fields.
        Returns:
            bool: True if the broker accepted the message, False otherwise.
        '''
        published = self.publish_status(
            build_status(
                self.transaction_id,
                QueryState.QUERY_STATE_COMPLETED,
                total_chunks=len(chunks),
                total_rows=total_rows,
                chunks=chunks,
                details=details,
            )
        )
        if self.legacy_topics:
            self._safe_publish(
                legacy_eof_topic(self.vehicle_id, self.device_id, self.transaction_id), b"", CONTENT_QOS
            )
        return published

    def publish_failure(
        self,
        code: QueryError,
        stage: str,
        description: str,
        details: dict[str, str] = None,
    ) -> bool:
        '''
        Tells the requester the query failed, and that any chunk already received must be discarded.

        Args:
            code (QueryError): The protocol error code.
            stage (str): The stage the failure belongs to.
            description (str): Human readable detail.
            details (dict[str, str]): Extra diagnostic fields.
        Returns:
            bool: True if the broker accepted the message, False otherwise.
        '''
        logger.error(
            f"query_publisher: Query {self.transaction_id} failed at stage '{stage}' with {code.name}: {description}"
        )
        published = self.publish_status(
            build_status(
                self.transaction_id,
                QueryState.QUERY_STATE_FAILED,
                error=code,
                stage=stage,
                description=description,
                details=details,
            )
        )
        if self.legacy_topics:
            self._safe_publish(
                legacy_error_topic(self.vehicle_id, self.device_id, self.transaction_id),
                json.dumps({"error": description, "code": code.name, "stage": stage}).encode("utf-8"),
                CONTENT_QOS,
            )
        return published

    def publish_chunk(self, name: str, payload: bytes) -> bool:
        '''
        Publishes the payload of a chunk on its own content topic.

        Args:
            name (str): The '{network}--{measurement}' name identifying the chunk.
            payload (bytes): The serialized chunk.
        Returns:
            bool: True if the broker accepted the message, False otherwise.
        '''
        return self._safe_publish(
            content_topic(self.vehicle_id, self.device_id, self.transaction_id, name), payload, CONTENT_QOS
        )

    def chunk_topic(self, name: str) -> str:
        '''
        Args:
            name (str): The '{network}--{measurement}' name identifying the chunk.
        Returns:
            str: The topic the chunk is published on, as reported in the manifest.
        '''
        return content_topic(self.vehicle_id, self.device_id, self.transaction_id, name)

__all__ = ["QueryPublisher", "STATUS_QOS", "CONTENT_QOS"]
