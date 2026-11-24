"""Shared coin parsing, timestamp parsing, and Indonesian number formatting helpers."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def parse_coins(value: Any) -> Decimal:
    """Parse a coin value safely into a finite Decimal, defaulting to 0."""
    try:
        amount = Decimal(str(value))
        return amount if amount.is_finite() else Decimal(0)
    except InvalidOperation:
        return Decimal(0)


def format_coins(num: Decimal) -> str:
    """Format a Decimal coin amount using Indonesian grouping and comma decimals."""
    whole, _, fraction = f"{num:,f}".partition(".")
    fraction = fraction.rstrip("0")
    return whole.replace(",", ".") + ("," + fraction if fraction else "")


def format_koin(value: Any) -> str:
    """Format a coin value with a comma decimal separator and 'koin' suffix."""
    return f"{str(value).replace('.', ',')} koin"


def display_coin(value: Decimal) -> str:
    """Format a Decimal coin value for web status reports without trailing zeros."""
    return (
        format(value, "f").rstrip("0").rstrip(".").replace(".", ",")
        if value % 1
        else str(int(value))
    )


def parse_api_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 API timestamp with mandatory timezone info."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Missing timezone")
    return parsed
