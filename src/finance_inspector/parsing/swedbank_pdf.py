from __future__ import annotations

import re
from datetime import date

import pdfplumber

from finance_inspector.models.transaction import Transaction

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_amount(s: str) -> float | None:
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    cleaned = re.sub(r"(?<=\d)\s+(?=\d)", "", s)
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_swedbank_statement_pdf(path: str) -> list[Transaction]:
    txs: list[Transaction] = []

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for row in table:
                    if not row:
                        continue

                    cells = [str(c).strip() if c is not None else "" for c in row]

                    if len(cells) < 5 or not DATE_RE.match(cells[1]):
                        continue

                    booking_date = date.fromisoformat(cells[1])
                    title = cells[2].replace("\n", " ").strip()
                    details = cells[3].replace("\n", " ").strip()
                    amount = _parse_amount(cells[4] if len(cells) > 4 else "")
                    balance = _parse_amount(cells[5] if len(cells) > 5 else "")

                    if amount is None:
                        continue

                    txs.append(
                        Transaction(
                            booking_date=booking_date,
                            title=title,
                            details=details,
                            money_in=amount if amount > 0 else None,
                            money_out=abs(amount) if amount < 0 else None,
                            balance=balance,
                            currency="EUR",
                        )
                    )

    return txs
