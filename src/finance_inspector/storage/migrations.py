from __future__ import annotations

from sqlite3 import Connection


def run_migrations(conn: Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)"
    )
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}

    def apply(version: str, check_already_done, sql: str) -> None:
        if version in applied:
            return
        if check_already_done(conn):
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
            )
            applied.add(version)
            return
        conn.execute(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
        )
        applied.add(version)

    def has_col(table: str, col: str):
        return lambda c: col in {
            r[1] for r in c.execute(f"PRAGMA table_info({table})")
        }

    apply(
        "001_category_id_on_transactions",
        has_col("transactions", "category_id"),
        "ALTER TABLE transactions ADD COLUMN category_id INTEGER REFERENCES categories(id)",
    )
    apply(
        "002_user_id_on_statements",
        has_col("statements", "user_id"),
        "ALTER TABLE statements ADD COLUMN user_id INTEGER REFERENCES users(id)",
    )
    apply(
        "003_user_id_on_categories",
        has_col("categories", "user_id"),
        "ALTER TABLE categories ADD COLUMN user_id INTEGER REFERENCES users(id)",
    )
    apply(
        "004_country_on_users",
        has_col("users", "country"),
        "ALTER TABLE users ADD COLUMN country TEXT",
    )
    apply(
        "005_theme_on_users",
        has_col("users", "theme"),
        "ALTER TABLE users ADD COLUMN theme TEXT NOT NULL DEFAULT 'light'",
    )

    _migrate_drop_unique_sha256(conn, applied)
    _migrate_drop_unique_category_name(conn, applied)

    conn.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_unique_constraint(conn: Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA index_list({table})").fetchall()
    for row in rows:
        if row["unique"]:
            cols = conn.execute(f"PRAGMA index_info({row['name']})").fetchall()
            if len(cols) == 1 and cols[0]["name"] == column:
                return True
    return False


def _migrate_drop_unique_sha256(conn: Connection, applied: set[str]) -> None:
    version = "006_drop_unique_sha256"
    if version in applied:
        return
    if not _has_unique_constraint(conn, "statements", "sha256"):
        conn.execute(
            "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
        )
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
        "INSERT INTO statements_new"
        " SELECT id, filename, uploaded_at, sha256, pdf_bytes, statement_title, user_id"
        " FROM statements"
    )
    conn.execute("DROP TABLE statements")
    conn.execute("ALTER TABLE statements_new RENAME TO statements")
    conn.commit()
    conn.execute(
        "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
    )


def _migrate_drop_unique_category_name(conn: Connection, applied: set[str]) -> None:
    version = "007_drop_unique_category_name"
    if version in applied:
        return
    if not _has_unique_constraint(conn, "categories", "name"):
        conn.execute(
            "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
        )
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
    conn.execute(
        "INSERT INTO categories_new SELECT id, name, created_at, deleted_at, user_id FROM categories"
    )
    conn.execute("DROP TABLE categories")
    conn.execute("ALTER TABLE categories_new RENAME TO categories")
    conn.commit()
    conn.execute(
        "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
    )
