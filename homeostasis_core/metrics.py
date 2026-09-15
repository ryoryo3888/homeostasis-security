"""Pure metric functions; policy responses never directly alter sovereignty."""

from __future__ import annotations

import math
from typing import Mapping

from .models import CountryState

SUSTAINING_INDICATORS = (
    "food", "energy", "economy", "environment", "international_trust",
)
CONFLICT_INDICATOR = "conflict_load"


def clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("value must be numeric")
    if minimum > maximum:
        raise ValueError("minimum cannot exceed maximum")
    return max(minimum, min(maximum, value))


def global_homeostasis(indicators: Mapping[str, float]) -> int:
    """Average the five contracted global indicators and subtract 40% of conflict."""
    missing = set(SUSTAINING_INDICATORS + (CONFLICT_INDICATOR,)) - set(indicators)
    if missing:
        raise ValueError(f"required global indicators missing: {sorted(missing)}")
    values = [indicators[name] for name in SUSTAINING_INDICATORS]
    conflict = indicators[CONFLICT_INDICATOR]
    for value in (*values, conflict):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
            raise ValueError("all indicators must be numeric values from 0 through 100")
    score = sum(values) / len(values) - 0.4 * conflict
    return int(round(clamp(score)))


def sovereignty_summary(countries: Mapping[str, CountryState | float]) -> dict[str, object]:
    """Aggregate independently assessed sovereignty scores without response shortcuts."""
    if not countries:
        raise ValueError("at least one country is required")
    per_country = {
        code: value.sovereignty if isinstance(value, CountryState) else value
        for code, value in countries.items()
    }
    for score in per_country.values():
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 100:
            raise ValueError("sovereignty scores must be numeric values from 0 through 100")
    return {
        "by_country": dict(per_country),
        "average": sum(per_country.values()) / len(per_country),
        "minimum": min(per_country.values()),
    }
