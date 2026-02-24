from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection, Row, connect


def get_conn(db_path: str = "data/app.db") -> Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path, check_same_thread=False, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = Row
    return conn
