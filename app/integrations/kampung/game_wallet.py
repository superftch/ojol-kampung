"""Read and reconcile paginated game wallet history for a WIB reporting day."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any, TypedDict

from app.core.exceptions import HttpCoreError
from app.core.formatting import parse_api_timestamp as timestamp
from app.integrations.kampung.game_parsers import WALLET_PRODUCT_CATEGORIES, integer
from app.modules.ledger.finance import WIB, day_bounds, report_date


class WalletReport(TypedDict):
    income_milli: int
    payout_count: int
    expenses_milli: dict[str, int]
    expense_issue: str | None
    complete: bool
    today_income_milli: int | None
    issue: str | None


def valid_cursor(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 2048


async def read_daily_wallet(
    request: Callable[..., Awaitable[dict[str, Any]]],
    day: date | str,
    read_at: datetime,
) -> WalletReport:
    day = report_date(day)
    start, end = map(datetime.fromisoformat, day_bounds(day))
    result: WalletReport = {
        "income_milli": 0,
        "payout_count": 0,
        "expenses_milli": {},
        "expense_issue": None,
        "complete": False,
        "today_income_milli": None,
        "issue": "Riwayat belum mencapai awal hari",
    }
    if start > read_at:
        result["issue"] = "Tanggal tersebut belum tiba"
        return result

    cursor = None
    seen_cursors = set()
    seen_entries = {}
    previous = None
    try:
        async with asyncio.timeout(12):
            if day == read_at.astimezone(WIB).date():
                try:
                    ojol = await request("/api/ojol")
                    result["today_income_milli"] = integer(ojol["earnedTodayMilli"])
                except (HttpCoreError, KeyError, TypeError):
                    pass

            for _ in range(10):
                page = await request("/api/me/koin", after=cursor)
                items, next_cursor = page["items"], page["next"]
                if not isinstance(items, list) or (
                    next_cursor is not None and not valid_cursor(next_cursor)
                ):
                    raise ValueError("Invalid wallet page")

                for row in items:
                    identifier, kind = row["id"], row["type"]
                    at, amount = timestamp(row["at"]), row["amountMilli"]
                    if (
                        not isinstance(identifier, str)
                        or not identifier
                        or not isinstance(kind, str)
                        or not kind
                        or type(amount) is not int
                        or (kind == "OJOL_ONGKOS" and amount < 0)
                    ):
                        raise ValueError("Invalid wallet entry")

                    in_day = start <= at < end and at <= read_at
                    purchase = in_day and kind == "SHOP_PURCHASE" and amount < 0
                    detail = row.get("detail") if purchase else None
                    product = (
                        " ".join(detail.casefold().split()) if isinstance(detail, str) else None
                    )
                    entry = (at, kind, amount, product)
                    if identifier in seen_entries:
                        if seen_entries[identifier] != entry:
                            raise ValueError("Conflicting wallet entry")
                        continue
                    if previous is not None and at > previous:
                        raise ValueError("Wallet entries out of order")
                    previous = at
                    seen_entries[identifier] = entry
                    if in_day and kind == "OJOL_ONGKOS":
                        result["income_milli"] += amount
                        result["payout_count"] += 1
                    if purchase:
                        if not product:
                            result["expense_issue"] = (
                                "Ada belanja tanpa nama produk yang dapat dibaca"
                            )
                        elif product in WALLET_PRODUCT_CATEGORIES:
                            resource = WALLET_PRODUCT_CATEGORIES[product]
                            expenses = result["expenses_milli"]
                            expenses[resource] = expenses.get(resource, 0) - amount

                if next_cursor is not None and next_cursor in seen_cursors:
                    result["issue"] = "Cursor riwayat berulang"
                    break
                if previous is not None and previous < start:
                    result.update(complete=True, issue=None)
                    break
                if next_cursor is None:
                    break
                seen_cursors.add(next_cursor)
                cursor = next_cursor
            else:
                result["issue"] = "Batas 10 halaman tercapai"
    except TimeoutError:
        result["issue"] = "Batas waktu pembacaan riwayat tercapai"
    except HttpCoreError as exc:
        result["issue"] = (
            "Sesi game ditolak atau kedaluwarsa"
            if exc.category == "auth"
            else "Riwayat koin tidak dapat dibaca"
        )
    except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
        result["issue"] = "Format atau urutan riwayat koin belum dapat diverifikasi"
    return result
