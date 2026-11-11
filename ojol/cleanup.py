import re
from math import hypot, isfinite
from random import shuffle

from .http_api import HttpCoreError


async def scan(api, blocks, limit, *, include_neighbors=False, dirty_only=True):
    me = await api.request("/api/game/me")
    home = me.get("home") if isinstance(me, dict) else None
    if not isinstance(home, dict):
        raise HttpCoreError("Rumah akun belum tersedia")

    if not all(type(home.get(key)) in (int, float) and isfinite(home[key]) for key in ("x", "y")):
        raise HttpCoreError("Koordinat rumah akun belum tersedia")
    blocks = blocks or [home.get("block")]
    if len(blocks) > 24 or not all(
        isinstance(block, str) and re.fullmatch(r"[A-Z][0-9]{2}", block) for block in blocks
    ):
        raise ValueError("Gunakan maksimal 24 kode blok seperti K39")
    blocks = list(dict.fromkeys(blocks))
    if include_neighbors and len(blocks) == 1:
        home_block = blocks[0]
        row, col = ord(home_block[0]), int(home_block[1:])
        neighbors = [
            f"{chr(r)}{c:02d}"
            for r in range(max(ord("A"), row - 1), min(ord("Z"), row + 1) + 1)
            for c in range(max(0, col - 1), min(99, col + 1) + 1)
        ]
        blocks.extend(block for block in neighbors if block != home_block)

    world = await api.request("/api/world/plots?v=2&blocks=" + ",".join(blocks))
    plots = world.get("plots") if isinstance(world, dict) else None
    if not isinstance(plots, list) or any(not isinstance(plot, dict) for plot in plots):
        raise HttpCoreError("Format respons peta berubah")

    candidates = {}
    for plot in plots:
        if plot.get("k") != "R" or plot.get("s") != "O" or plot.get("e"):
            continue
        if dirty_only and not plot.get("kt"):
            continue
        if not dirty_only and not isinstance(plot.get("w"), dict):
            continue
        plot_id = plot.get("id")
        if not isinstance(plot_id, str) or not re.fullmatch(
            r"[A-Z][0-9]{2}-[A-Z][0-9]{2}", plot_id
        ):
            raise HttpCoreError("ID plot rumah tidak valid")
        if plot_id.split("-", 1)[0] not in blocks or plot_id == home.get("plotId"):
            continue
        if not all(
            type(plot.get(key)) in (int, float) and isfinite(plot[key]) for key in ("x", "y")
        ):
            raise HttpCoreError("Koordinat plot rumah tidak valid")
        if (plot["x"], plot["y"]) == (home["x"], home["y"]):
            continue
        candidates[plot_id] = {"plot_id": plot_id, "x": plot["x"], "y": plot["y"]}
        if not dirty_only:
            nickname = plot["w"].get("n")
            candidates[plot_id]["nickname"] = nickname if isinstance(nickname, str) else "Warga"

    ordered = sorted(
        candidates.values(),
        key=lambda plot: (hypot(plot["x"] - home["x"], plot["y"] - home["y"]), plot["plot_id"]),
    )
    return {"blocks": blocks, "total_candidates": len(ordered), "candidates": ordered[:limit]}


async def find_unvisited(api):
    houses = await scan(api, None, None, include_neighbors=True, dirty_only=False)
    shuffle(houses["candidates"])
    for house in houses["candidates"]:
        status = await api.request(f"/api/daily/house?plotId={house['plot_id']}")
        if not isinstance(status, dict) or type(status.get("visitedToday")) is not bool:
            raise HttpCoreError("Status kunjungan rumah belum bisa dipastikan")
        if not status["visitedToday"]:
            return house
    return None
