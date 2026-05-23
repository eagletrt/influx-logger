"""Simple MongoDB connection helper.

Provides get_mongo_client and get_mongo_db helpers.
"""
from typing import List, Optional, Tuple
import os

from external.serializers.py.lapcounter.lapcounter import Line
from logger_utils import logger

try:
    from pymongo import MongoClient
except Exception:  # pragma: no cover - runtime dependency
    MongoClient = None


limit: int = 5000
lines: List[object] = []

_connection: Optional[Tuple["MongoClient", object]] = None

def connect(url:str, port:int, username:str, password:str, db_name:str) -> Tuple["MongoClient", object]:
    global _connection
    if _connection is not None:
        return _connection
    """Connect to MongoDB and return (client, db) tuple."""
    if MongoClient is None:
        raise RuntimeError("pymongo is not installed")

    uri = f"mongodb://{username}:{password}@{url}:{port}/{db_name}"
    client = MongoClient(uri)
    db = client[db_name]
    _connection = (client, db)
    return _connection

def get_mongo_client(uri: Optional[str] = None, **kwargs) -> "MongoClient":
    """Return a pymongo.MongoClient instance.

    uri: MongoDB connection string. If not provided, reads MONGO_URI env var.
    Additional kwargs are passed to MongoClient.
    """
    if MongoClient is None:
        raise RuntimeError("pymongo is not installed")

    uri = uri or os.getenv("MONGO_URI")
    if not uri:
        raise ValueError("MongoDB URI not provided (argument or MONGO_URI env)")

    client = MongoClient(uri, **kwargs)
    return client


def get_mongo_db(uri: Optional[str] = None, db_name: Optional[str] = None, **kwargs) -> Tuple["MongoClient", object]:
    """Return (client, db) tuple.

    db_name: name of the database. If not provided, reads MONGO_DB env var.
    """
    client = get_mongo_client(uri, **kwargs)
    db_name = db_name or os.getenv("MONGO_DB")
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
        _connection = _connection or get_mongo_db()
        collection = _connection[1]["telemetry_lines"]
        docs = []
        for line in lines:
            doc = {
                "measurement": line.measurement,
                "tags": line.tags,
                "fields": line.fields,
                "timestamp": line.timestamp,
            }
            docs.append(doc)
        collection.insert_many(docs)
        lines = []
    except Exception as e:
        logger.fatal(f"Error committing lines to MongoDB: {e}")


__all__ = ["get_mongo_client", "get_mongo_db", "push_line", "commit"]
