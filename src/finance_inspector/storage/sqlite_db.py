from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone, date
from pathlib import Path

from finance_inspector.models.category import Category, CategoryKeyword
from finance_inspector.models.statement import Statement
from finance_inspector.models.transaction import Transaction

DEFAULT_PDF = Path("data/statements/statement.pdf")


def get_conn(db_path: str = "data/app.db") -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS statements
        (
            id
            INTEGER
            PRIMARY
            KEY
            AUTOINCREMENT,
            filename
            TEXT
            NOT
            NULL,
            uploaded_at
            TEXT
            NOT
            NULL,
            sha256
            TEXT
            NOT
            NULL
            UNIQUE,
            pdf_bytes
            BLOB
            NOT
            NULL,
            statement_title
            TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS categories
        (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            deleted_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS category_keywords
        (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            keyword     TEXT    NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories (id),
            UNIQUE (category_id, keyword)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions
        (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            statement_id INTEGER NOT NULL,
            booking_date TEXT    NOT NULL,
            title        TEXT    NOT NULL,
            details      TEXT    NOT NULL,
            money_out    REAL,
            money_in     REAL,
            balance      REAL,
            currency     TEXT    NOT NULL,
            category_id  INTEGER,
            FOREIGN KEY (statement_id) REFERENCES statements (id),
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_statement ON transactions(statement_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(booking_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ck_category ON category_keywords(category_id)")

    # Migration: add category_id column to transactions if missing
    tx_cols = {row[1] for row in conn.execute("PRAGMA table_info(transactions)").fetchall()}
    if "category_id" not in tx_cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN category_id INTEGER REFERENCES categories(id)")

    conn.commit()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def upsert_statement(conn: sqlite3.Connection, filename: str, pdf_bytes: bytes) -> Statement:
    """
    Insert statement if not present (by sha256). Return Statement either way.
    """
    digest = _sha256(pdf_bytes)

    existing = conn.execute(
        "SELECT id, filename, uploaded_at, sha256, statement_title FROM statements WHERE sha256 = ?", (digest,)
    ).fetchone()
    if existing:
        return Statement(
            id=int(existing["id"]),
            filename=existing["filename"],
            uploaded_at=datetime.fromisoformat(existing["uploaded_at"]),
            sha256=existing["sha256"],
            statement_title=existing["statement_title"],
        )

    uploaded_at = datetime.now(timezone.utc)
    cur = conn.execute(
        "INSERT INTO statements (filename, uploaded_at, sha256, pdf_bytes) VALUES (?, ?, ?, ?)",
        (filename, uploaded_at.isoformat(), digest, pdf_bytes),
    )
    conn.commit()
    return Statement(
        id=int(cur.lastrowid),
        filename=filename,
        uploaded_at=uploaded_at,
        sha256=digest,
    )


def list_statements(conn: sqlite3.Connection) -> list[Statement]:
    rows = conn.execute(
        "SELECT id, filename, uploaded_at, sha256, statement_title FROM statements ORDER BY id DESC"
    ).fetchall()
    return [
        Statement(
            id=int(r["id"]),
            filename=r["filename"],
            uploaded_at=datetime.fromisoformat(r["uploaded_at"]),
            sha256=r["sha256"],
            statement_title=r["statement_title"],

        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


def create_category(conn: sqlite3.Connection, name: str) -> Category:
    now = datetime.now(timezone.utc)
    cur = conn.execute(
        "INSERT INTO categories (name, created_at) VALUES (?, ?)",
        (name, now.isoformat()),
    )
    conn.commit()
    return Category(id=int(cur.lastrowid), name=name, created_at=now)


def soft_delete_category(conn: sqlite3.Connection, category_id: int) -> None:
    now = datetime.now(timezone.utc)
    conn.execute(
        "UPDATE categories SET deleted_at = ? WHERE id = ?",
        (now.isoformat(), category_id),
    )
    conn.execute(
        "UPDATE transactions SET category_id = NULL WHERE category_id = ?",
        (category_id,),
    )
    conn.commit()


def restore_category(conn: sqlite3.Connection, category_id: int) -> None:
    conn.execute("UPDATE categories SET deleted_at = NULL WHERE id = ?", (category_id,))
    conn.commit()


def list_categories(conn: sqlite3.Connection, include_deleted: bool = False) -> list[Category]:
    if include_deleted:
        rows = conn.execute("SELECT id, name, created_at, deleted_at FROM categories ORDER BY name").fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, created_at, deleted_at FROM categories WHERE deleted_at IS NULL ORDER BY name"
        ).fetchall()
    return [
        Category(
            id=int(r["id"]),
            name=r["name"],
            created_at=datetime.fromisoformat(r["created_at"]),
            deleted_at=datetime.fromisoformat(r["deleted_at"]) if r["deleted_at"] else None,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Category keywords
# ---------------------------------------------------------------------------


def add_keyword(conn: sqlite3.Connection, category_id: int, keyword: str) -> CategoryKeyword:
    keyword_clean = keyword.strip().lower()
    cur = conn.execute(
        "INSERT OR IGNORE INTO category_keywords (category_id, keyword) VALUES (?, ?)",
        (category_id, keyword_clean),
    )
    conn.commit()
    return CategoryKeyword(id=cur.lastrowid, category_id=category_id, keyword=keyword_clean)


def remove_keyword(conn: sqlite3.Connection, keyword_id: int) -> None:
    conn.execute("DELETE FROM category_keywords WHERE id = ?", (keyword_id,))
    conn.commit()


def list_keywords(conn: sqlite3.Connection, category_id: int) -> list[CategoryKeyword]:
    rows = conn.execute(
        "SELECT id, category_id, keyword FROM category_keywords WHERE category_id = ? ORDER BY keyword",
        (category_id,),
    ).fetchall()
    return [
        CategoryKeyword(id=int(r["id"]), category_id=int(r["category_id"]), keyword=r["keyword"])
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Transaction categorization
# ---------------------------------------------------------------------------


def categorize_transactions(conn: sqlite3.Connection, statement_id: int) -> None:
    """Match transaction titles against category keywords (case-insensitive substring)."""
    rows = conn.execute(
        """
        SELECT ck.category_id, ck.keyword
        FROM category_keywords ck
        JOIN categories c ON c.id = ck.category_id
        WHERE c.deleted_at IS NULL
        ORDER BY c.name, ck.keyword
        """
    ).fetchall()

    if not rows:
        conn.execute(
            "UPDATE transactions SET category_id = NULL WHERE statement_id = ?",
            (statement_id,),
        )
        conn.commit()
        return

    keyword_map: list[tuple[str, int]] = [(r["keyword"], r["category_id"]) for r in rows]

    txs = conn.execute(
        "SELECT id, title FROM transactions WHERE statement_id = ?",
        (statement_id,),
    ).fetchall()

    for tx in txs:
        title_lower = tx["title"].lower()
        matched_category_id = None
        for keyword, category_id in keyword_map:
            if keyword in title_lower:
                matched_category_id = category_id
                break
        conn.execute(
            "UPDATE transactions SET category_id = ? WHERE id = ?",
            (matched_category_id, tx["id"]),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


def _compute_statement_title(txs: list[Transaction]) -> str | None:
    months = sorted({t.booking_date.strftime("%Y-%m") for t in txs if t.booking_date})
    if not months:
        return None
    if len(months) == 1:
        return months[0]
    return f"{months[0]} — {months[-1]}"


def replace_transactions(conn: sqlite3.Connection, statement_id: int, txs: list[Transaction]) -> None:
    conn.execute("DELETE FROM transactions WHERE statement_id = ?", (statement_id,))
    conn.executemany(
        """
        INSERT INTO transactions (statement_id, booking_date, title, details, money_out, money_in, balance, currency)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                statement_id,
                t.booking_date.isoformat(),
                t.title,
                t.details,
                t.money_out,
                t.money_in,
                t.balance,
                t.currency,
            )
            for t in txs
        ],
    )
    statement_title = _compute_statement_title(txs)
    if statement_title:
        conn.execute(
            "UPDATE statements SET statement_title = ? WHERE id = ?",
            (statement_title, statement_id),
        )
    conn.commit()
    categorize_transactions(conn, statement_id)


def load_transactions(conn: sqlite3.Connection, statement_id: int) -> list[Transaction]:
    rows = conn.execute(
        """
        SELECT t.booking_date, t.title, t.details, t.money_out, t.money_in,
               t.balance, t.currency, c.name AS category
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.statement_id = ?
        ORDER BY t.booking_date ASC, t.id ASC
        """,
        (statement_id,),
    ).fetchall()

    return [
        Transaction(
            booking_date=date.fromisoformat(r["booking_date"]),
            title=r["title"],
            details=r["details"],
            money_out=r["money_out"],
            money_in=r["money_in"],
            balance=r["balance"],
            currency=r["currency"],
            category=r["category"],
        )
        for r in rows
    ]
