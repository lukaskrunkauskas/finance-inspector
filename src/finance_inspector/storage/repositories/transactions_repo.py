from __future__ import annotations

from datetime import date
from sqlite3 import Connection

from finance_inspector.models.transaction import Transaction


def replace_transactions(conn: Connection, statement_id: int, txs: list[Transaction]) -> None:
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
    conn.commit()
    categorize_transactions(conn, statement_id)


def load_transactions(conn: Connection, statement_id: int) -> list[Transaction]:
    rows = conn.execute(
        """
        SELECT t.id,
               t.booking_date,
               t.title,
               t.details,
               t.money_out,
               t.money_in,
               t.balance,
               t.currency,
               t.irrelevant,
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
            id=r["id"],
            booking_date=date.fromisoformat(r["booking_date"]),
            title=r["title"],
            details=r["details"],
            money_out=r["money_out"],
            money_in=r["money_in"],
            balance=r["balance"],
            currency=r["currency"],
            category=r["category"],
            irrelevant=bool(r["irrelevant"]),
        )
        for r in rows
    ]


def set_transaction_irrelevant(conn: Connection, tx_id: int, value: bool) -> None:
    conn.execute(
        "UPDATE transactions SET irrelevant = ? WHERE id = ?",
        (int(value), tx_id),
    )
    conn.commit()


def categorize_transactions(conn: Connection, statement_id: int) -> None:
    stmt_row = conn.execute(
        "SELECT user_id FROM statements WHERE id = ?", (statement_id,)
    ).fetchone()
    user_id = stmt_row["user_id"] if stmt_row else None

    if user_id is None:
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
