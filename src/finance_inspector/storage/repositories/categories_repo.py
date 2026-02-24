from __future__ import annotations

from datetime import datetime, timezone
from sqlite3 import Connection, IntegrityError

from finance_inspector.models.category import Category, CategoryKeyword

_PALETTE = [
    "#134E8E", "#FFB33F", "#FF4400", "#C00707", "#237227",
    "#8A7650", "#EB4C4C", "#F1FF5E", "#B500B2", "#F2E3BB",
    "#3333FF", "#33FF33",
]


def _pick_color(conn: Connection, user_id: int) -> str:
    count = conn.execute(
        "SELECT COUNT(*) FROM categories WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    return _PALETTE[count % len(_PALETTE)]


def create_category(conn: Connection, name: str, user_id: int, color: str | None = None) -> Category:
    existing = conn.execute(
        "SELECT id FROM categories WHERE name = ? AND user_id = ? AND deleted_at IS NULL",
        (name, user_id),
    ).fetchone()
    if existing:
        raise IntegrityError(f"Category '{name}' already exists.")

    color = color or _pick_color(conn, user_id)
    now = datetime.now(timezone.utc)
    cur = conn.execute(
        "INSERT INTO categories (name, created_at, user_id, color) VALUES (?, ?, ?, ?)",
        (name, now.isoformat(), user_id, color),
    )
    conn.commit()
    return Category(id=int(cur.lastrowid), name=name, color=color, created_at=now)


def update_category_color(conn: Connection, category_id: int, color: str) -> None:
    conn.execute("UPDATE categories SET color = ? WHERE id = ?", (color, category_id))
    conn.commit()


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
            "SELECT id, name, color, created_at, deleted_at FROM categories WHERE user_id = ? ORDER BY name",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, color, created_at, deleted_at"
            " FROM categories WHERE user_id = ? AND deleted_at IS NULL ORDER BY name",
            (user_id,),
        ).fetchall()
    return [
        Category(
            id=int(r["id"]),
            name=r["name"],
            color=r["color"] or "#aaaaaa",
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
