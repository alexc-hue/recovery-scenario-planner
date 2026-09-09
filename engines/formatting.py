"""Shared display formatting helpers."""

from __future__ import annotations


def money(x: float) -> str:
    """Format a signed dollar amount with the sign in front of the symbol
    (e.g. -$1,234 rather than $-1,234)."""
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.0f}"
