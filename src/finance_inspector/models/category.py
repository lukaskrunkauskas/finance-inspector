from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Category:
    id: int | None
    name: str
    created_at: datetime
    deleted_at: datetime | None = None


@dataclass
class CategoryKeyword:
    id: int | None
    category_id: int
    keyword: str
