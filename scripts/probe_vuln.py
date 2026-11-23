#!/usr/bin/env python3
"""Probe klien-tepercaya: uji apakah server memvalidasi nilai yang dihitung client.

Jalankan: python3 scripts/probe_vuln.py [--dir .local] [--session http-session.json]
Hanya endpoint yang sudah diamati (dokumen docs/http-endpoints.md); request mentah
dipakai supaya tidak terhalang allowlist adapter.
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ojol.http_api import OjolHttpApi  # noqa: E402

# ponytail: id fasum dari capture lama; pindai /api/kebutuhan (places) bila berubah
GYM = "296dc278-b765-4caf-9349-469385d6fc03"
PERPUS = "90ae44da-6d71-495d-83f7-5b0b69400504"


async def call(api, path, payload=None):
    method = "GET" if payload is None else "POST"
    r = await api.client.request(method, path, json=payload, headers=api.browser_headers(path, method))
    try:
        body = r.json()
    except Exception:
        body = r.text[:200]
    return r.status_code, body


async def balance(api):
    return (await call(api, "/api/game/me"))[1].get("balanceMilli")


async def play(api, out, label, make_holds, wait=True):
    st, info = await call(api, f"/api/minigame?projectId={GYM}&game=gym")
    if st != 200:
        out.append((label + " GET", st, str(info)[:120])); return
    st, started = await call(api, "/api/minigame", {
        "action": "start", "projectId": GYM, "requestId": str(uuid.uuid4()), "game": "gym"})
    play_id = started.get("playId") if st == 200 else None
    if not play_id:
        out.append((label + " start", st, str(started)[:200])); return
    reps = (started.get("plan") or {}).get("reps") or []
    holds = make_holds(reps)
    if wait:
        await asyncio.sleep((sum(holds) / 1000) + 1.1 * len(holds))
    before = await balance(api)
    st, fin = await call(api, "/api/minigame", {"action": "finish", "playId": play_id, "holds": holds})
    after = await balance(api)
    out.append((label, st, f"holds={len(holds)} score={fin.get('score')} invalid={(fin.get('detail') or {}).get('invalid')} deltaMilli={after - before}"))
    return play_id, holds


async def t_minigame_holds(api, out):
    """Skor gym dihitung dari `holds` kiriman client: coba holds mustahil, tanpa tunggu, dan replay."""
    await play(api, out, "A normal tanpa tunggu", lambda reps: [round(r["fill"] * r["center"]) for r in reps], wait=False)
    await play(api, out, "B 50 holds sempurna", lambda reps: [round(r["fill"] * r["center"]) for r in reps] * 7)
    await play(api, out, "C 1 hold sempurna", lambda reps: [round(reps[0]["fill"] * reps[0]["center"])])
    # replay: finish play terakhir dua kali lagi
    st, info = await call(api, f"/api/minigame?projectId={GYM}&game=gym")
    st, started = await call(api, "/api/minigame", {"action": "start", "projectId": GYM, "requestId": str(uuid.uuid4()), "game": "gym"})
    pid = started.get("playId")
    if pid:
        reps = (started.get("plan") or {}).get("reps") or []
        holds = [round(r["fill"] * r["center"]) for r in reps]
        await asyncio.sleep((sum(holds) / 1000) + 1.1 * len(holds))
        for n in (1, 2, 3):
            before = await balance(api)
            st, fin = await call(api, "/api/minigame", {"action": "finish", "playId": pid, "holds": holds})
            after = await balance(api)
            out.append((f"D finish ke-{n} playId sama", st, f"score={fin.get('score')} deltaMilli={after - before}"))


async def t_kuis_replay(api, out):
    """Bonus kuis dihitung dari `answers`; coba kirim ulang visitId yang sama."""
    st, fas = await call(api, f"/api/facilities/{PERPUS}")
    out.append(("facility GET", st, str(fas)[:200]))
    if st != 200:
        return
    st, use = await call(api, f"/api/facilities/{PERPUS}/use", {"requestId": str(uuid.uuid4()), "track": "kesehatan"})
    out.append(("use", st, str(use)[:200]))
    st, kuis = await call(api, f"/api/facilities/{PERPUS}/kuis")
    out.append(("kuis GET", st, str(kuis)[:250]))
    visit = kuis.get("visitId")
    if not visit:
        return
    n = len(kuis.get("soal", []))
    st, ans = await call(api, f"/api/facilities/{PERPUS}/kuis",
                         {"visitId": visit, "answers": [0] * n})
    out.append(("kuis jawab", st, str(ans)[:200]))
    st, ans2 = await call(api, f"/api/facilities/{PERPUS}/kuis",
                          {"visitId": visit, "answers": [0] * n})
    out.append(("kuis replay", st, str(ans2)[:200]))


async def t_garden(api, out):
    st, g = await call(api, "/api/daily/garden")
    out.append(("garden GET", st, str(g)[:250]))
    if st != 200:
        return
    ready = [x for x in g.get("gardens", []) if x.get("state") == "SIAP"]
    out.append(("garden siap", 0, [x.get("id") for x in ready]))
    for item in ready[:2]:
        st, r = await call(api, f"/api/daily/garden/{item['id']}", {"action": "panen"})
        out.append((f"panen {item['id']}", st, str(r)[:200]))
        st, r2 = await call(api, f"/api/daily/garden/{item['id']}", {"action": "panen"})
        out.append((f"panen ulang {item['id']}", st, str(r2)[:200]))


async def t_topup_edge(api, out):
    for points in (0, -5, 1000000):
        st, r = await call(api, "/api/topups", {"points": points, "requestId": str(uuid.uuid4())})
        out.append((f"topup points={points}", st, str(r)[:250]))


async def t_ojol(api, out):
    st, t = await call(api, "/api/time")
    out.append(("time", st, str(t)[:120]))
    st, o = await call(api, "/api/ojol", {"action": "tawar", "vehicle": "motor", "mode": "kendara"})
    out.append(("tawar", st, str(o)[:300]))
    pilihan = o.get("pilihan") or []
    if not pilihan:
        return
    pick = max(pilihan, key=lambda p: p.get("fareMilli", 0))
    st, ambil = await call(api, "/api/ojol", {"action": "ambil", "vehicle": "motor", "mode": "kendara", "pilih": pick.get("id")})
    out.append(("ambil", st, str(ambil)[:300]))
    # teleport 1 lompatan jauh (aturan bundle: maks 1.8 petak/detik)
    st, lacak = await call(api, "/api/ojol", {"action": "lacak", "x": 9999, "y": 9999})
    out.append(("lacak 9999,9999", st, str(lacak)[:250]))
    # selesai tanpa jemput, tanpa lacak ke tujuan
    st, sel = await call(api, "/api/ojol", {"action": "selesai"})
    out.append(("selesai tanpa jemput", st, str(sel)[:300]))


async def t_ojol_normal_flow(api, out):
    """Kontrol: selesai tanpa lacak, tapi dijalankan setelah normal."""
    st, sel = await call(api, "/api/ojol", {"action": "selesai"})
    out.append(("selesai kontrol", st, str(sel)[:250]))


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=".local")
    ap.add_argument("--session", default="http-session.json")
    ap.add_argument("--only", default="all")
    a = ap.parse_args()
    d = Path(a.dir)
    tests = {
        "minigame": t_minigame_holds,
        "kuis": t_kuis_replay,
        "garden": t_garden,
        "topup": t_topup_edge,
        "ojol": t_ojol,
    }
    out = []
    async with OjolHttpApi(d, d / a.session) as api:
        out.append(("saldo awal", 200, await balance(api)))
        for name, fn in tests.items():
            if a.only not in ("all", name):
                continue
            out.append((f"=== {name}", 0, ""))
            try:
                await fn(api, out)
            except Exception as e:  # satu tes gagal tidak menghentikan tes lain
                out.append((name, -1, f"{type(e).__name__}: {e}"))
        out.append(("saldo akhir", 200, await balance(api)))
    for name, st, note in out:
        print(f"{st:>4} {name}: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
