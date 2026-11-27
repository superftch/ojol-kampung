#!/usr/bin/env python3
"""Inject koin langsung: buat order topup lalu simulasi bayar (mode uji).

Pemakaian:
    python3 inject.py <points> [--dir .local] [--session http-session.json]

points = jumlah koin (bukan milli), sesuai paket di UI topup.
canSimulate hanya true di mode uji; jika false, order dibayar manual lewat QR.
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ojol.http_api import OjolHttpApi


async def call(api, path, payload=None):
    # ponytail: bypass allowlist repo untuk /api/topups; tetap header browser repo
    headers = api.browser_headers(path, "GET" if payload is None else "POST")
    r = await api.client.request(
        "GET" if payload is None else "POST", path, json=payload, headers=headers
    )
    return r.json()


async def inject(directory: Path, session_file: Path, points: int) -> dict:
    async with OjolHttpApi(directory, session_file) as api:
        before = (await call(api, "/api/game/me")).get("balanceMilli")
        order = await call(api, "/api/topups", {"points": points, "requestId": str(uuid.uuid4())})
        order_id = order.get("orderId")
        if not order_id:
            return {"ok": False, "order": order}

        result = {"before": before, "order": order, "ok": False}
        if order.get("canSimulate"):
            await call(api, f"/api/topups/{order_id}/simulate", {})
            for _ in range(6):
                status = await call(api, f"/api/topups/{order_id}", {})
                if status.get("status") == "PAID":
                    result["status"] = "PAID"
                    after = (await call(api, "/api/game/me")).get("balanceMilli")
                    result["after"] = after
                    result["delta_milli"] = (after or 0) - (before or 0)
                    result["ok"] = True
                    break
                await asyncio.sleep(1)
            else:
                result["status"] = "PENDING"
        else:
            result["status"] = "MANUAL_BAYAR_QR"
        return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("points", type=int)
    ap.add_argument("--dir", default=".local")
    ap.add_argument("--session", default="http-session.json")
    args = ap.parse_args()

    directory = Path(args.dir)
    result = asyncio.run(inject(directory, directory / args.session, args.points))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
