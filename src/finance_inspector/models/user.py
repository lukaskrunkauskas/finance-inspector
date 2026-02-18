from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class User:
    id: int | None
    username: str
    email: str
    first_name: str
    last_name: str
    password_hash: str
    created_at: datetime
    country: str | None = None
    theme: str = "light"
