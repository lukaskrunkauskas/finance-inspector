from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from dateutil import parser as dateparser
import pdfplumber

DATE_RE = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\b")
MONEY_RE = re.compile(r"€\s?\d+(?:,\d{3})*(?:\.\d{2})")

# Lines we want to ignore (headers/footers/legal text)
JUNK_PATTERNS = [
    re.compile(r"^EUR Statement\b", re.I),
    re.compile(r"^Generated on\b", re.I),
    re.compile(r"^Revolut Bank\b", re.I),
    re.compile(r"^Balance summary\b", re.I),
    re.compile(r"^Account transactions from\b", re.I),
    re.compile(r"^Date\s+Description\s+Money out\s+Money in\s+Balance\b", re.I),
    re.compile(r"^Report lost or stolen card\b", re.I),
    re.compile(r"^Get help directly in app\b", re.I),
    re.compile(r"^Scan the QR code\b", re.I),
    re.compile(r"^©\s*\d{4}\s+Revolut\b", re.I),
    re.compile(r"^Page\s+\d+\s+of\s+\d+\b", re.I),
]

@dataclass
class Transaction:
    booking_date: date
    title: str
    details: str
    money_out: float | None
    money_in: float | None
    balance: float | None
    currency: str = "EUR"


def _eur_to_float(s: str) -> float:
    return float(s.replace("€", "").replace(",", "").replace(" ", "").strip())


def _is_junk_line(line: str) -> bool:
    return any(p.search(line) for p in JUNK_PATTERNS)


def parse_revolut_statement_pdf(path: str) -> list[Transaction]:
    # 1) Extract text lines
    lines: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for ln in text.splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                if _is_junk_line(ln):
                    continue
                lines.append(ln)

    # 2) Split into transaction blocks: each starts with a DATE_RE line
    blocks: list[list[str]] = []
    current: list[str] = []

    for ln in lines:
        if DATE_RE.match(ln):
            if current:
                blocks.append(current)
            current = [ln]
        else:
            if current:
                current.append(ln)

    if current:
        blocks.append(current)

    # 3) Parse blocks into transactions
    txs: list[Transaction] = []

    for block in blocks:
        first_line = block[0]
        m = DATE_RE.match(first_line)
        if not m:
            continue

        dt_str = m.group(0)  # e.g. "Jan 28, 2026"
        booking_dt = dateparser.parse(dt_str).date()

        # Whatever comes after the date on the first line is often the merchant/title
        rest_after_date = first_line[len(dt_str):].strip()  # e.g. "Benu €14.69"

        # Extract money values (usually amount + balance)
        money_vals = MONEY_RE.findall(" ".join(block))
        amount = _eur_to_float(money_vals[0]) if len(money_vals) >= 1 else None
        balance = _eur_to_float(money_vals[1]) if len(money_vals) >= 2 else None

        joined_lower = " ".join(block).lower()

        # Decide direction (simple but works well for Revolut statements)
        income_keywords = ["top-up", "top up", "salary", "refund", "cashback", "transfer in", "interest"]
        is_income = any(k in joined_lower for k in income_keywords)

        money_in = amount if is_income else None
        money_out = None if is_income else amount

        # Description lines (exclude euro-only lines)
        desc_lines = [l for l in block[1:] if not MONEY_RE.fullmatch(l)]

        # Title: prefer first desc line; otherwise use rest of first line (strip amounts)
        title = desc_lines[0] if desc_lines else rest_after_date
        # Remove trailing amounts from title like "Benu €14.69"
        title = MONEY_RE.sub("", title).strip()

        details = "\n".join(desc_lines[1:]).strip() if len(desc_lines) > 1 else ""

        txs.append(
            Transaction(
                booking_date=booking_dt,
                title=title,
                details=details,
                money_out=money_out,
                money_in=money_in,
                balance=balance,
                currency="EUR",
            )
        )

    return txs
