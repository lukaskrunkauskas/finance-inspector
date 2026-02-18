from __future__ import annotations

from finance_inspector.models.enums.category_enum import CategoryEnum
from finance_inspector.category_configs.base import BASE_CONFIG
from finance_inspector.category_configs.lt import LT_CONFIG

# Map ISO 3166-1 alpha-2 country codes → keyword configs
_COUNTRY_CONFIGS: dict[str, dict[CategoryEnum, list[str]]] = {
    "LT": LT_CONFIG,
}

# Countries shown in the registration dropdown: code → display name
SUPPORTED_COUNTRIES: dict[str, str] = {
    "EN": "English (Default)",
    "LT": "Lithuania",
}


def get_config_for_country(country_code: str) -> dict[CategoryEnum, list[str]]:
    """Return the keyword config for *country_code*, falling back to BASE_CONFIG."""
    return _COUNTRY_CONFIGS.get(country_code.upper(), BASE_CONFIG)
