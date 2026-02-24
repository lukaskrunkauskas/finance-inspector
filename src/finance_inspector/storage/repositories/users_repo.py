from __future__ import annotations

from datetime import datetime, timezone
from sqlite3 import Connection, IntegrityError

from finance_inspector.category_configs import get_config_for_country
from finance_inspector.models.enums.category_enum import CategoryEnum
from finance_inspector.models.user import User


def register_user(
        conn: Connection,
        username: str,
        email: str,
        first_name: str,
        last_name: str,
        password_hash: str,
        country: str | None = None,
) -> User:
    now = datetime.now(timezone.utc)
    cur = conn.execute(
        "INSERT INTO users (username, email, first_name, last_name, password_hash, created_at, country, theme)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'light')",
        (username, email, first_name, last_name, password_hash, now.isoformat(), country),
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
        country=country,
        theme="light",
    )


def get_user_by_username(conn: Connection, username: str) -> User | None:
    row = conn.execute(
        "SELECT id, username, email, first_name, last_name, password_hash, created_at, country, theme"
        " FROM users WHERE username = ?",
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
        country=row["country"],
        theme=row["theme"] or "light",
    )


def get_all_users_credentials(conn: Connection) -> dict:
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


def save_new_user_from_credentials(conn: Connection, credentials: dict, username: str) -> User:
    user_data = credentials["usernames"][username]
    return register_user(
        conn,
        username=username,
        email=user_data["email"],
        first_name=user_data["first_name"],
        last_name=user_data["last_name"],
        password_hash=user_data["password"],
    )


def seed_default_categories(conn: Connection, user_id: int, country: str | None) -> None:
    from finance_inspector.storage.repositories.categories_repo import create_category

    config = get_config_for_country(country or "EN")
    for member in CategoryEnum:
        keywords = config.get(member, [])
        try:
            cat = create_category(conn, member.value, user_id)
        except IntegrityError:
            row = conn.execute(
                "SELECT id FROM categories WHERE name = ? AND user_id = ? AND deleted_at IS NULL",
                (member.value, user_id),
            ).fetchone()
            if row is None:
                continue
            cat_id = int(row["id"])
        else:
            cat_id = cat.id

        for kw in keywords:
            conn.execute(
                "INSERT OR IGNORE INTO category_keywords (category_id, keyword) VALUES (?, ?)",
                (cat_id, kw.strip().lower()),
            )
    conn.commit()


def update_user_theme(conn: Connection, user_id: int, theme: str) -> None:
    conn.execute("UPDATE users SET theme = ? WHERE id = ?", (theme, user_id))
    conn.commit()
