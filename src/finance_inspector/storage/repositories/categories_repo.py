from __future__ import annotations

from datetime import datetime, timezone
from sqlite3 import Connection, IntegrityError

from finance_inspector.models.category import Category, CategoryKeyword


def create_category(conn: Connection, name: str, user_id: int) -> Category:
    existing = conn.execute(
        "SELECT id FROM categories WHERE name = ? AND user_id = ? AND deleted_at IS NULL",
        (name, user_id),
    ).fetchone()
    if existing:
        raise IntegrityError(f"Category '{name}' already exists.")

    now = datetime.now(timezone.utc)
    cur = conn.execute(
        "INSERT INTO categories (name, created_at, user_id) VALUES (?, ?, ?)",
        (name, now.isoformat(), user_id),
    )
    conn.commit()
    return Category(id=int(cur.lastrowid), name=name, created_at=now)


def soft_delete_category(conn: Connection, category_id: int, user_id: int) -> None:
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


def restore_category(conn: Connection, category_id: int, user_id: int) -> None:
    conn.execute(
        "UPDATE categories SET deleted_at = NULL WHERE id = ? AND user_id = ?",
        (category_id, user_id),
    )
    conn.commit()


def list_categories(
        conn: Connection, user_id: int, include_deleted: bool = False
) -> list[Category]:
    if include_deleted:
        rows = conn.execute(
            "SELECT id, name, created_at, deleted_at FROM categories WHERE user_id = ? ORDER BY name",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, created_at, deleted_at"
            " FROM categories WHERE user_id = ? AND deleted_at IS NULL ORDER BY name",
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


def add_keyword(conn: Connection, category_id: int, keyword: str) -> CategoryKeyword:
    keyword_clean = keyword.strip().lower()
    cur = conn.execute(
        "INSERT OR IGNORE INTO category_keywords (category_id, keyword) VALUES (?, ?)",
        (category_id, keyword_clean),
    )
    conn.commit()
    return CategoryKeyword(id=cur.lastrowid, category_id=category_id, keyword=keyword_clean)


def remove_keyword(conn: Connection, keyword_id: int) -> None:
    conn.execute("DELETE FROM category_keywords WHERE id = ?", (keyword_id,))
    conn.commit()


def list_keywords(conn: Connection, category_id: int) -> list[CategoryKeyword]:
    rows = conn.execute(
        "SELECT id, category_id, keyword FROM category_keywords WHERE category_id = ? ORDER BY keyword",
        (category_id,),
    ).fetchall()
    return [
        CategoryKeyword(id=int(r["id"]), category_id=int(r["category_id"]), keyword=r["keyword"])
        for r in rows
    ]
