from __future__ import annotations

from sqlite3 import Connection

from finance_inspector.storage.migrations import run_migrations


def init_db(conn: Connection) -> None:
    _create_schema(conn)
    run_migrations(conn)
    conn.commit()


def _create_schema(conn: Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users
        (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT NOT NULL UNIQUE,
            email         TEXT NOT NULL,
            first_name    TEXT NOT NULL,
            last_name     TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            country       TEXT,
            theme         TEXT NOT NULL DEFAULT 'light'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS statements
        (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            filename        TEXT NOT NULL,
            uploaded_at     TEXT NOT NULL,
            sha256          TEXT NOT NULL,
            pdf_bytes       BLOB NOT NULL,
            statement_title TEXT,
            user_id         INTEGER REFERENCES users (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS categories
        (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            created_at TEXT NOT NULL,
            deleted_at TEXT,
            user_id    INTEGER REFERENCES users (id)
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stmt_user ON statements(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cat_user ON categories(user_id)")
