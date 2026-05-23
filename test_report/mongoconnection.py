"""Simple MongoDB connection helper.

Provides get_mongo_client and get_mongo_db helpers.
"""
from typing import Any, List, Optional, Tuple

from src.influx import Line
from src.logger_utils import logger

try:
    from pymongo import MongoClient
except Exception:  # pragma: no cover - runtime dependency
    MongoClient = None


limit: int = 5000
lines: List[object] = []

_connection: Tuple[Any, object] = None
_connection_settings: Optional[Tuple[str, int, str, str, str]] = None
_BSON_INT64_MIN = -(2**63)
_BSON_INT64_MAX = 2**63 - 1


def _build_uri(url: str, port: int, username: str, password: str, db_name: str) -> str:
    auth_part = ""
    if username and password:
        auth_part = f"{username}:{password}@"
    return f"mongodb://{auth_part}{url}:{port}/{db_name}"


def _sanitize_bson_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if _BSON_INT64_MIN <= value <= _BSON_INT64_MAX:
            return value
        return str(value)
    if isinstance(value, dict):
        return {key: _sanitize_bson_value(inner_value) for key, inner_value in value.items()}
    if isinstance(value, list):
        return [_sanitize_bson_value(inner_value) for inner_value in value]
    if isinstance(value, tuple):
        return [_sanitize_bson_value(inner_value) for inner_value in value]
    return value

def connect(url:str, port:int, username:str, password:str, db_name:str) -> Tuple[Any, object]:
    global _connection
    global _connection_settings
    if _connection is not None:
        return _connection
    if MongoClient is None:
        raise RuntimeError("pymongo is not installed")

    _connection_settings = (url, port, username, password, db_name)
    uri = _build_uri(url, port, username, password, db_name)
    logger.info(f"URI: {uri}")
    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=5000,
    )
    db = client[db_name]
    _connection = (client, db)
    return _connection

def get_mongo_client(uri: str, **kwargs) -> Any:
    """Return a pymongo.MongoClient instance.

    uri: MongoDB connection string. If not provided, reads MONGO_URI env var.
    Additional kwargs are passed to MongoClient.
    """
    if MongoClient is None:
        raise RuntimeError("pymongo is not installed")

    uri = uri
    if not uri:
        raise ValueError("MongoDB URI not provided (argument or MONGO_URI env)")

    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=5000,
        **kwargs,
    )
    return client


def get_mongo_db(uri: str, db_name:str, **kwargs) -> Tuple[Any, object]:
    """Return (client, db) tuple.

    db_name: name of the database. If not provided, reads MONGO_DB env var.
    """
    client = get_mongo_client(uri, **kwargs)
    db_name = db_name
    if not db_name:
        raise ValueError("MongoDB database name not provided (argument or MONGO_DB env)")

    db = client[db_name]
    return client, db

def push_line(line: "Line") -> None:
    """Push a Line to list of pending lines to be committed to MongoDB."""
    global lines
    lines.append(line)
    if len(lines) >= limit:
        commit()

def commit() -> None:
    """Commit pending lines to MongoDB."""
    global lines, _connection
    if not lines:
        return

    try:
        if _connection is None:
            if _connection_settings is None:
                logger.error("Mongo Connection: No MongoDB connection configured, skipping commit")
                return
            _connection = connect(*_connection_settings)

        collection = _connection[1]["telemetry_lines"]
        docs = []
        for line in lines:
            doc = {
                "measurement": line.measurement,
                "tags": line.tags,
                "fields": line.fields,
                "timestamp": line.timestamp,
            }
            docs.append(_sanitize_bson_value(doc))
        try:
            collection.insert_many(docs)
        except Exception as first_error:
            logger.warning(
                f"Mongo Connection: Initial commit failed, retrying once: {first_error}"
            )
            if _connection_settings is None:
                raise
            _connection = connect(*_connection_settings)
            collection = _connection[1]["telemetry_lines"]
            collection.insert_many(docs)

        logger.info(f"Mongo Connection: Committed {len(lines)} lines to MongoDB")
        lines = []
    except Exception as e:
        logger.error(f"Mongo Connection: Error committing lines to MongoDB: {e}")


__all__ = ["get_mongo_client", "get_mongo_db", "push_line", "commit"]
