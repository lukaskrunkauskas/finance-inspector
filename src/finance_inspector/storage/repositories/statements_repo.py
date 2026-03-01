from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from sqlite3 import Connection

from finance_inspector.models.statement import Statement


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def upsert_statement(
    conn: Connection,
    filename: str,
    pdf_bytes: bytes,
    user_id: int,
    source: str | None = None,
    statement_title: str | None = None,
) -> Statement:
    digest = _sha256(pdf_bytes)

    existing = conn.execute(
        "SELECT id, filename, uploaded_at, sha256, statement_title, source"
        " FROM statements WHERE sha256 = ? AND user_id = ?",
        (digest, user_id),
    ).fetchone()
    if existing:
        # Update title/source if they were just computed (may have been None on first insert)
        if statement_title or source:
            conn.execute(
                "UPDATE statements SET statement_title = COALESCE(?, statement_title),"
                " source = COALESCE(?, source) WHERE id = ?",
                (statement_title, source, int(existing["id"])),
            )
            conn.commit()
        return Statement(
            id=int(existing["id"]),
            filename=existing["filename"],
            uploaded_at=datetime.fromisoformat(existing["uploaded_at"]),
            sha256=existing["sha256"],
            statement_title=statement_title or existing["statement_title"],
            source=source or existing["source"],
        )

    uploaded_at = datetime.now(timezone.utc)
    cur = conn.execute(
        "INSERT INTO statements (filename, uploaded_at, sha256, pdf_bytes, user_id, source, statement_title)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (filename, uploaded_at.isoformat(), digest, pdf_bytes, user_id, source, statement_title),
    )
    conn.commit()
    return Statement(
        id=int(cur.lastrowid),
        filename=filename,
        uploaded_at=uploaded_at,
        sha256=digest,
        source=source,
        statement_title=statement_title,
    )


def get_statement_pdf_bytes(conn: Connection, statement_id: int) -> bytes | None:
    row = conn.execute(
        "SELECT pdf_bytes FROM statements WHERE id = ?", (statement_id,)
    ).fetchone()
    return bytes(row["pdf_bytes"]) if row else None


def list_statements(conn: Connection, user_id: int) -> list[Statement]:
    rows = conn.execute(
        "SELECT id, filename, uploaded_at, sha256, statement_title, source"
        " FROM statements WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    return [
        Statement(
            id=int(r["id"]),
            filename=r["filename"],
            uploaded_at=datetime.fromisoformat(r["uploaded_at"]),
            sha256=r["sha256"],
            statement_title=r["statement_title"],
            source=r["source"],
        )
        for r in rows
    ]
