"""Private stdio MCP server exposing only the inspected Ojol actions."""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server import MCPServer

from .http_api import HttpCoreError, OjolHttpApi


@asynccontextmanager
async def lifespan(server):
    global api
    directory = Path(os.environ["OJOL_HTTP_RUNTIME_DIR"])
    api = OjolHttpApi(directory, Path(os.environ["OJOL_HTTP_SESSION_FILE"]))
    try:
        yield {}
    finally:
        await api.__aexit__()


server = MCPServer("ojol-http", lifespan=lifespan)


async def invoke(method, **kwargs):
    if os.environ.get("OJOL_ENV") == "testing":
        return {
            "ok": False,
            "error": "HTTP live diblokir dalam testing",
            "category": "blocked",
            "recoverable": False,
        }
    before = api.retries
    try:
        async with asyncio.timeout(30):
            if api.client is None:
                await api.__aenter__()
            result = await getattr(api, method)(**kwargs)
            if method == "snapshot":
                result = result.model_dump(mode="json")
            elif method in {"purchase", "job_action"}:
                result = {"accepted": True}
            return {"ok": True, "data": result, "read_retries": api.retries - before}
    except HttpCoreError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "category": exc.category,
            "recoverable": exc.recoverable,
        }
    except TimeoutError:
        return {
            "ok": False,
            "error": "Deadline core HTTP tercapai; transaksi tidak diulang",
            "category": "transport",
            "recoverable": method in {"snapshot", "preview", "daily_wallet", "study_status"},
        }
    except (KeyError, TypeError, ValueError, AttributeError):
        return {
            "ok": False,
            "error": "Skema API Ojol berubah",
            "category": "schema",
            "recoverable": method
            in {"snapshot", "preview", "daily_wallet", "study_status", "garden_status"},
        }


@server.tool()
async def ojol_snapshot() -> dict:
    """Read wallet, resources, trips and receipts using server time."""
    return await invoke("snapshot")


@server.tool()
async def ojol_daily_wallet(day: str) -> dict:
    """Read bounded wallet history and verified Ojol payouts for one WIB date."""
    return await invoke("daily_wallet", day=day)


@server.tool()
async def ojol_preview_shop(resource: str) -> dict:
    """Read verified shop catalogs for a resource without sending a travel request."""
    return await invoke("preview", resource=resource)


@server.tool()
async def ojol_purchase(
    product: dict, expected_wallet: str, expected_resource: int, min_balance: str, request_id: str
) -> dict:
    """Buy one observed item once, enforcing fresh price/resources and balance >=5."""
    return await invoke(
        "purchase",
        product=product,
        expected_wallet=expected_wallet,
        expected_resource=expected_resource,
        min_balance=min_balance,
        request_id=request_id,
    )


@server.tool()
async def ojol_ensure_bpjs() -> dict:
    """Check BPJS card status and auto-buy if not owned and wallet has enough balance."""
    return await invoke("ensure_bpjs")


@server.tool()
async def ojol_study_status(mode: str) -> dict:
    """Read the configured library/university, subjects, cooldown and visit quiz."""
    return await invoke("study_status", mode=mode)


@server.tool()
async def ojol_study_start(
    mode: str,
    track: str,
    expected_price: str,
    expected_wallet: str,
    min_balance: str,
    request_id: str,
) -> dict:
    """Start one explicitly enabled study visit after fresh price, skill and balance checks."""
    return await invoke(
        "study_start",
        mode=mode,
        track=track,
        expected_price=expected_price,
        expected_wallet=expected_wallet,
        min_balance=min_balance,
        request_id=request_id,
    )


@server.tool()
async def ojol_study_quiz(mode: str, visit_id: str, track: str) -> dict:
    """Answer one observed visit quiz using its client reading material; never replay a submit."""
    return await invoke("study_quiz", mode=mode, visit_id=visit_id, track=track)


@server.tool()
async def ojol_job_action(kind: str) -> dict:
    """Search once or claim once after server arrival. No registration, quit or sleep actions."""
    return await invoke("job_action", kind=kind)


@server.tool()
async def ojol_garden_status() -> dict:
    """Read garden status (kebun sayur & kolam ikan)."""
    return await invoke("garden_status")


@server.tool()
async def ojol_garden_action(garden_id: str, action: str) -> dict:
    """Perform garden action (panen, rawat, tanam)."""
    return await invoke("garden_action", garden_id=garden_id, action=action)


if __name__ == "__main__":
    server.run(transport="stdio")
