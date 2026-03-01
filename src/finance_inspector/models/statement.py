from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Statement:
    id: int | None
    filename: str
    uploaded_at: datetime
    sha256: str
    statement_title: str | None = None
    source: str | None = None
