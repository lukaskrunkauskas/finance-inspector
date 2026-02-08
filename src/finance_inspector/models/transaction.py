from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class Transaction:
    booking_date: date
    title: str
    details: str
    money_out: float | None
    money_in: float | None
    balance: float | None
    currency: str = "EUR"
    category: str | None = None
