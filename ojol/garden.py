"""Automated garden and pond maintenance (panen, rawat, tanam) and cooldown tracking."""

import random
import time
from datetime import datetime, timezone
from decimal import Decimal

from .auto_settings import auto_flags
from .http_api import HttpCoreError, timestamp
from .models import now
from .reconciliation import wait_until_resolved


def parse_garden_now(now_value):
    if isinstance(now_value, str):
        try:
            return timestamp(now_value)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def garden_effective_state(garden, server_now):
    raw_state = garden.get("state")
    ready_at_str = garden.get("readyAt")
    ready_at = timestamp(ready_at_str) if ready_at_str else None

    if raw_state == "siap" or (ready_at and ready_at <= server_now):
        return "siap"
    if raw_state == "kosong" or ready_at is None:
        return "kosong"
    return "tumbuh"


async def run_garden(c):
    if not hasattr(c.ui, "garden_status") or not hasattr(c.ui, "garden_action"):
        return False
    flags = auto_flags(c.settings.runtime_dir)
    if not flags.get("kebun", True):
        return False
    if time.monotonic() < getattr(c, "garden_retry_at", 0):
        return False

    try:
        status = await c.ui.garden_status()
    except HttpCoreError as exc:
        if exc.category == "auth":
            raise
        c.garden_retry_at = time.monotonic() + 300
        return False
    except Exception:
        c.garden_retry_at = time.monotonic() + 300
        return False

    if not isinstance(status, dict):
        c.garden_retry_at = time.monotonic() + 300
        return False

    gardens = status.get("gardens")
    if not isinstance(gardens, list) or not gardens:
        c.garden_retry_at = time.monotonic() + 1800
        return False

    server_now = parse_garden_now(status.get("now"))

    # Priority 1: Harvest ("panen")
    target_garden = None
    target_action = None
    target_cost = Decimal(0)

    for g in gardens:
        eff = garden_effective_state(g, server_now)
        if eff == "siap":
            target_garden = g
            target_action = "panen"
            target_cost = Decimal(0)
            break

    # Priority 2: Care / Water ("rawat")
    if target_garden is None:
        for g in gardens:
            eff = garden_effective_state(g, server_now)
            if eff == "tumbuh" and not g.get("cared"):
                target_garden = g
                target_action = "rawat"
                target_cost = Decimal(0)
                break

    # Priority 3: Plant ("tanam")
    if target_garden is None:
        for g in gardens:
            eff = garden_effective_state(g, server_now)
            if eff == "kosong":
                seed_cost = Decimal(g.get("seedMilli", 0)) / Decimal(1000)
                min_wallet = max(Decimal(20), c.settings.min_balance)
                if c.state.wallet - seed_cost >= min_wallet and (
                    c.settings.max_spend is None or c.spent + seed_cost <= c.settings.max_spend
                ):
                    target_garden = g
                    target_action = "tanam"
                    target_cost = seed_cost
                    break

    # If no immediate action needed, compute cooldown until earliest readyAt
    if target_garden is None:
        grow_waits = []
        for g in gardens:
            ready_str = g.get("readyAt")
            if ready_str:
                try:
                    t_ready = timestamp(ready_str)
                    if t_ready > server_now:
                        grow_waits.append((t_ready - server_now).total_seconds())
                except Exception:
                    pass
        if grow_waits:
            min_wait = max(0, min(grow_waits))
            c.garden_retry_at = time.monotonic() + min_wait + 5
        else:
            c.garden_retry_at = time.monotonic() + 300
        return False

    # Execute action
    c.check_cancel()
    kind = "garden"
    garden_id = target_garden["id"]
    payload = {
        "action": target_action,
        "garden_id": garden_id,
        "kind": target_garden.get("kind"),
        "label": target_garden.get("label", garden_id),
        "cost": str(target_cost),
        "resource": "kebun",
    }
    action_id = c.journal.begin(c.run_id, kind, c.state, payload)
    c.last_action = {
        "action_id": action_id,
        "kind": kind,
        "action": target_action,
        "garden_id": garden_id,
        "label": target_garden.get("label", garden_id),
    }
    c.stage = f"garden.{target_action}.{garden_id}"
    if target_cost > Decimal(0):
        c.spent += target_cost

    try:
        if hasattr(c, "human_delay"):
            await c.human_delay(1.0, 2.5)
        await c.ui.garden_action(garden_id, target_action)
        after = await c.read_snapshot()
    except (HttpCoreError, Exception) as exc:
        if isinstance(exc, HttpCoreError) and exc.category in {
            "rejected",
            "auto_disabled",
            "sleeping",
        }:
            c.journal.reject(action_id)
            if target_cost > Decimal(0):
                c.spent -= target_cost
            retry_offset = 300 if c.settings.env == "testing" else 300 + random.uniform(-25, 60)
            c.garden_retry_at = time.monotonic() + retry_offset
            return False
        c.journal.settle(action_id, False)
        if isinstance(exc, HttpCoreError) and exc.category in {"uncertain", "transport"}:
            c.state = await wait_until_resolved(c.ui, c.journal, c.settings)
            c.snapshot_received_at = now().isoformat()
            c.snapshot_read_at = time.monotonic()
            c.report("rekonsiliasi_selesai", action=kind, garden_id=garden_id)
            return True
        raise

    c.journal.settle(action_id, True, after)
    c.report(
        "kebun_aksi_selesai",
        action=target_action,
        garden=target_garden.get("label", garden_id),
        kind=target_garden.get("kind"),
        cost=str(target_cost),
    )
    return True
