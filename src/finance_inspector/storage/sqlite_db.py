from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone, date
from pathlib import Path

from finance_inspector.models.category import Category, CategoryKeyword
from finance_inspector.models.statement import Statement
from finance_inspector.models.transaction import Transaction
from finance_inspector.models.user import User

DEFAULT_PDF = Path("data/statements/statement.pdf")


def get_conn(db_path: str = "data/app.db") -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users
        (
            id
            INTEGER
            PRIMARY
            KEY
            AUTOINCREMENT,
            username
            TEXT
            NOT
            NULL
            UNIQUE,
            email
            TEXT
            NOT
            NULL,
            first_name
            TEXT
            NOT
            NULL,
            last_name
            TEXT
            NOT
            NULL,
            password_hash
            TEXT
            NOT
            NULL,
            created_at
            TEXT
            NOT
            NULL
        )
        """
    )
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
            NULL,
            pdf_bytes
            BLOB
            NOT
            NULL,
            statement_title
            TEXT,
            user_id
            INTEGER
            REFERENCES
            users
        (
            id
        )
            )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS categories
        (
            id
            INTEGER
            PRIMARY
            KEY
            AUTOINCREMENT,
            name
            TEXT
            NOT
            NULL,
            created_at
            TEXT
            NOT
            NULL,
            deleted_at
            TEXT,
            user_id
            INTEGER
            REFERENCES
            users
        (
            id
        )
            )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS category_keywords
        (
            id
            INTEGER
            PRIMARY
            KEY
            AUTOINCREMENT,
            category_id
            INTEGER
            NOT
            NULL,
            keyword
            TEXT
            NOT
            NULL,
            FOREIGN
            KEY
        (
            category_id
        ) REFERENCES categories
        (
            id
        ),
            UNIQUE
        (
            category_id,
            keyword
        )
            )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions
        (
            id
            INTEGER
            PRIMARY
            KEY
            AUTOINCREMENT,
            statement_id
            INTEGER
            NOT
            NULL,
            booking_date
            TEXT
            NOT
            NULL,
            title
            TEXT
            NOT
            NULL,
            details
            TEXT
            NOT
            NULL,
            money_out
            REAL,
            money_in
            REAL,
            balance
            REAL,
            currency
            TEXT
            NOT
            NULL,
            category_id
            INTEGER,
            FOREIGN
            KEY
        (
            statement_id
        ) REFERENCES statements
        (
            id
        ),
            FOREIGN KEY
        (
            category_id
        ) REFERENCES categories
        (
            id
        )
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

    # Migration: add user_id column to statements if missing
    stmt_cols = {row[1] for row in conn.execute("PRAGMA table_info(statements)").fetchall()}
    if "user_id" not in stmt_cols:
        conn.execute("ALTER TABLE statements ADD COLUMN user_id INTEGER REFERENCES users(id)")

    # Migration: add user_id column to categories if missing
    cat_cols = {row[1] for row in conn.execute("PRAGMA table_info(categories)").fetchall()}
    if "user_id" not in cat_cols:
        conn.execute("ALTER TABLE categories ADD COLUMN user_id INTEGER REFERENCES users(id)")

    # Commit pending DDL before table rebuilds
    conn.commit()

    # Migration: remove UNIQUE constraint on statements.sha256 (now deduped per user in code).
    # SQLite can't ALTER constraints, so we rebuild the table.
    _migrate_drop_unique_sha256(conn)

    # Migration: remove UNIQUE constraint on categories.name (now unique per user in code).
    _migrate_drop_unique_category_name(conn)

    # Indexes on user_id columns (must come after migration adds the columns)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stmt_user ON statements(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cat_user ON categories(user_id)")

    conn.commit()


def _has_unique_constraint(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if a table has a UNIQUE constraint on a single column."""
    rows = conn.execute(f"PRAGMA index_list({table})").fetchall()
    for row in rows:
        if row["unique"]:
            cols = conn.execute(f"PRAGMA index_info({row['name']})").fetchall()
            if len(cols) == 1 and cols[0]["name"] == column:
                return True
    return False


def _migrate_drop_unique_sha256(conn: sqlite3.Connection) -> None:
    if not _has_unique_constraint(conn, "statements", "sha256"):
        return
    conn.execute("""
                 CREATE TABLE statements_new
                 (
                     id              INTEGER PRIMARY KEY AUTOINCREMENT,
                     filename        TEXT NOT NULL,
                     uploaded_at     TEXT NOT NULL,
                     sha256          TEXT NOT NULL,
                     pdf_bytes       BLOB NOT NULL,
                     statement_title TEXT,
                     user_id         INTEGER REFERENCES users (id)
                 )
                 """)
    conn.execute(
        "INSERT INTO statements_new SELECT id, filename, uploaded_at, sha256, pdf_bytes, statement_title, user_id FROM statements")
    conn.execute("DROP TABLE statements")
    conn.execute("ALTER TABLE statements_new RENAME TO statements")
    conn.commit()


def _migrate_drop_unique_category_name(conn: sqlite3.Connection) -> None:
    if not _has_unique_constraint(conn, "categories", "name"):
        return
    conn.execute("""
                 CREATE TABLE categories_new
                 (
                     id         INTEGER PRIMARY KEY AUTOINCREMENT,
                     name       TEXT NOT NULL,
                     created_at TEXT NOT NULL,
                     deleted_at TEXT,
                     user_id    INTEGER REFERENCES users (id)
                 )
                 """)
    conn.execute("INSERT INTO categories_new SELECT id, name, created_at, deleted_at, user_id FROM categories")
    conn.execute("DROP TABLE categories")
    conn.execute("ALTER TABLE categories_new RENAME TO categories")
    conn.commit()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def register_user(
        conn: sqlite3.Connection,
        username: str,
        email: str,
        first_name: str,
        last_name: str,
        password_hash: str,
) -> User:
    now = datetime.now(timezone.utc)
    cur = conn.execute(
        "INSERT INTO users (username, email, first_name, last_name, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (username, email, first_name, last_name, password_hash, now.isoformat()),
    )
    conn.commit()
    return User(
        id=int(cur.lastrowid),
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        password_hash=password_hash,
        created_at=now,
    )


def get_user_by_username(conn: sqlite3.Connection, username: str) -> User | None:
    row = conn.execute(
        "SELECT id, username, email, first_name, last_name, password_hash, created_at FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not row:
        return None
    return User(
        id=int(row["id"]),
        username=row["username"],
        email=row["email"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        password_hash=row["password_hash"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def get_all_users_credentials(conn: sqlite3.Connection) -> dict:
    """Build the credentials dict that streamlit-authenticator expects."""
    rows = conn.execute(
        "SELECT username, email, first_name, last_name, password_hash FROM users"
    ).fetchall()
    usernames = {}
    for r in rows:
        usernames[r["username"]] = {
            "email": r["email"],
            "first_name": r["first_name"],
            "last_name": r["last_name"],
            "password": r["password_hash"],
        }
    return {"usernames": usernames}


def save_new_user_from_credentials(conn: sqlite3.Connection, credentials: dict, username: str) -> User:
    """Save a newly registered user from the authenticator's updated credentials dict."""
    user_data = credentials["usernames"][username]
    return register_user(
        conn,
        username=username,
        email=user_data["email"],
        first_name=user_data["first_name"],
        last_name=user_data["last_name"],
        password_hash=user_data["password"],
    )


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------


def upsert_statement(conn: sqlite3.Connection, filename: str, pdf_bytes: bytes, user_id: int) -> Statement:
    """
    Insert statement if not present (by sha256 + user_id). Return Statement either way.
    """
    digest = _sha256(pdf_bytes)

    existing = conn.execute(
        "SELECT id, filename, uploaded_at, sha256, statement_title FROM statements WHERE sha256 = ? AND user_id = ?",
        (digest, user_id),
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
        "INSERT INTO statements (filename, uploaded_at, sha256, pdf_bytes, user_id) VALUES (?, ?, ?, ?, ?)",
        (filename, uploaded_at.isoformat(), digest, pdf_bytes, user_id),
    )
    conn.commit()
    return Statement(
        id=int(cur.lastrowid),
        filename=filename,
        uploaded_at=uploaded_at,
        sha256=digest,
    )


def list_statements(conn: sqlite3.Connection, user_id: int) -> list[Statement]:
    rows = conn.execute(
        "SELECT id, filename, uploaded_at, sha256, statement_title FROM statements WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
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


def create_category(conn: sqlite3.Connection, name: str, user_id: int) -> Category:
    # Check uniqueness per user
    existing = conn.execute(
        "SELECT id FROM categories WHERE name = ? AND user_id = ? AND deleted_at IS NULL",
        (name, user_id),
    ).fetchone()
    if existing:
        raise sqlite3.IntegrityError(f"Category '{name}' already exists.")

    now = datetime.now(timezone.utc)
    cur = conn.execute(
        "INSERT INTO categories (name, created_at, user_id) VALUES (?, ?, ?)",
        (name, now.isoformat(), user_id),
    )
    conn.commit()
    return Category(id=int(cur.lastrowid), name=name, created_at=now)


def soft_delete_category(conn: sqlite3.Connection, category_id: int, user_id: int) -> None:
    now = datetime.now(timezone.utc)
    conn.execute(
        "UPDATE categories SET deleted_at = ? WHERE id = ? AND user_id = ?",
        (now.isoformat(), category_id, user_id),
    )
    conn.execute(
        "UPDATE transactions SET category_id = NULL WHERE category_id = ?",
        (category_id,),
    )
    conn.commit()


def restore_category(conn: sqlite3.Connection, category_id: int, user_id: int) -> None:
    conn.execute(
        "UPDATE categories SET deleted_at = NULL WHERE id = ? AND user_id = ?",
        (category_id, user_id),
    )
    conn.commit()


def list_categories(conn: sqlite3.Connection, user_id: int, include_deleted: bool = False) -> list[Category]:
    if include_deleted:
        rows = conn.execute(
            "SELECT id, name, created_at, deleted_at FROM categories WHERE user_id = ? ORDER BY name",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, created_at, deleted_at FROM categories WHERE user_id = ? AND deleted_at IS NULL ORDER BY name",
            (user_id,),
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
    """Match transaction titles against category keywords (case-insensitive substring).
    Only uses categories belonging to the same user who owns the statement."""
    # Look up user_id from the statement
    stmt_row = conn.execute("SELECT user_id FROM statements WHERE id = ?", (statement_id,)).fetchone()
    user_id = stmt_row["user_id"] if stmt_row else None

    if user_id is None:
        # No user associated — clear categories and return
        conn.execute(
            "UPDATE transactions SET category_id = NULL WHERE statement_id = ?",
            (statement_id,),
        )
        conn.commit()
        return

    rows = conn.execute(
        """
        SELECT ck.category_id, ck.keyword
        FROM category_keywords ck
                 JOIN categories c ON c.id = ck.category_id
        WHERE c.deleted_at IS NULL
          AND c.user_id = ?
        ORDER BY c.name, ck.keyword
        """,
        (user_id,),
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
        SELECT t.booking_date,
               t.title,
               t.details,
               t.money_out,
               t.money_in,
               t.balance,
               t.currency,
               c.name AS category
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
