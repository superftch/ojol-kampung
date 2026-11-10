import re
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from .models import Snapshot
from .planner import decimal_id

WIB = ZoneInfo("Asia/Jakarta")


def report_date(value=None):
    if value is None:
        return datetime.now(WIB).date()
    if isinstance(value, date):
        return value
    for pattern in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise ValueError("Tanggal harus YYYY-MM-DD atau DD-MM-YYYY")


def day_bounds(value):
    day = report_date(value)
    start = datetime.combine(day, time.min, WIB)
    return start.astimezone(UTC).isoformat(), (start + timedelta(days=1)).astimezone(
        UTC
    ).isoformat()


def received_income(before: Snapshot, after: Snapshot):
    """Use received payouts, never gross fares or unrelated wallet changes."""
    added = Counter(after.history) - Counter(before.history)
    fresh = list(added.elements())
    payouts = []
    for entry in fresh:
        match = re.search(r"·\s*\+([\d.,]+)\s*$", entry)
        if match:
            payouts.append((entry, decimal_id(match[1])))
    if not payouts:
        return None
    return sum((amount for _, amount in payouts), Decimal(0)), [entry for entry, _ in payouts]


def completion_evidence(before: Snapshot, after: Snapshot):
    """Recover an old ambiguous claim only from one exact route/time/payout receipt."""
    if before.phase != "complete" or after.phase not in {"idle", "searching", "delivering"}:
        return None
    if before.observed_at.astimezone(WIB).date() != after.observed_at.astimezone(WIB).date():
        return None
    route = re.search(r"📍\s*(.*?)\s*🏁\s*(.+)", before.trip or "")
    received = received_income(before, after)
    if not route or not received or len(received[1]) != 1:
        return None
    amount, entries = received
    if (
        before.today_income is None
        or after.today_income is None
        or after.today_income - before.today_income != amount
    ):
        return None
    expected = re.sub(r"\s+", " ", f"{route[1].strip()} → {route[2].strip()}")
    entry = re.sub(r"\s+", " ", entries[0])
    match = re.fullmatch(
        r"(\d{1,2})[.:](\d{2})\s+.+?" + re.escape(expected) + r"\s*·\s*\+[\d.,]+", entry
    )
    if not match:
        return None
    observed = before.observed_at.astimezone(WIB)
    try:
        receipt_time = observed.replace(
            hour=int(match[1]), minute=int(match[2]), second=0, microsecond=0
        )
    except ValueError:
        return None
    minute = observed.replace(second=0, microsecond=0)
    if (
        not minute
        <= receipt_time
        <= min(minute + timedelta(minutes=1), after.observed_at.astimezone(WIB))
    ):
        return None
    return {
        "method": "exact_route_time_received_payout",
        "receipt": entries[0],
        "amount": str(amount),
        "receipt_time_wib": receipt_time.isoformat(),
    }
