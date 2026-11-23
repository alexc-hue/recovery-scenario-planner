"""Shared display formatting helpers."""

from __future__ import annotations


def money(x: float) -> str:
    """Format a signed dollar amount with the sign in front of the symbol
    (e.g. -$1,234 rather than $-1,234). A negative amount that rounds to zero
    prints as $0, not -$0."""
    digits = f"{abs(x):,.0f}"
    sign = "-" if x < 0 and digits != "0" else ""
    return f"{sign}${digits}"
