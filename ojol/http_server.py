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
            "recoverable": method in {"snapshot", "preview"},
        }
    except (KeyError, TypeError, ValueError, AttributeError):
        return {
            "ok": False,
            "error": "Skema API Ojol berubah",
            "category": "schema",
            "recoverable": method in {"snapshot", "preview"},
        }


@server.tool()
async def ojol_snapshot() -> dict:
    """Read wallet, resources, trips and receipts using server time."""
    return await invoke("snapshot")


@server.tool()
async def ojol_preview_shop(resource: str) -> dict:
    """Read verified shop catalogs for a resource without sending a travel request."""
    return await invoke("preview", resource=resource)


@server.tool()
async def ojol_purchase(
    product: dict, expected_wallet: str, expected_resource: int, min_balance: str, request_id: str
) -> dict:
    """Buy one observed item once, enforcing fresh price/resources and balance >=20."""
    return await invoke(
        "purchase",
        product=product,
        expected_wallet=expected_wallet,
        expected_resource=expected_resource,
        min_balance=min_balance,
        request_id=request_id,
    )


@server.tool()
async def ojol_job_action(kind: str) -> dict:
    """Search once or claim once after server arrival. No registration, quit or sleep actions."""
    return await invoke("job_action", kind=kind)


if __name__ == "__main__":
    server.run(transport="stdio")
