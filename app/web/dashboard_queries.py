"""Read-only dashboard aggregation, financial growth, and log formatting."""

import json
import sqlite3
from contextlib import suppress
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.core.database import read_sqlite
from app.core.formatting import format_coins, parse_coins
from app.core.models import NEEDS, SUBJECTS
from app.core.storage import status_record, status_timestamp
from app.modules.captcha import get_all_pending_reviews
from app.modules.gameplay.kerja import kerja_target_poin
from app.modules.gameplay.study import cached_skills, kursus_cost_info, kursus_subject, subjects
from app.modules.ledger.finance import WIB, day_bounds, report_date
from app.modules.notifications.repository import list_notifications
from app.modules.worker.settings import auto_flags
from app.web.deps import WebContext, get_all_fleet_directories, resolve_account_service

_STAGE_DESCRIPTIONS: dict[str, str] = {
    "worker.reconcile": "Rekonsiliasi Transaksi Game",
    "order.search": "Mencari Order",
    "order.take": "Menerima Order",
    "order.complete": "Menyelesaikan Order",
    "purchase.fuel": "Isi Bensin (SPBU)",
    "sleeping": "Istirahat / Tidur di game",
    "wait.countdown": "Menunggu Countdown Antar Order",
}


def dashboard_snapshot(directory: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Return the fresher snapshot between status.json and game-sync.json."""
    snapshot = data.get("snapshot") or {}
    sync, _ = status_record(directory / "game-sync.json")
    checked = status_timestamp(sync.get("checked_at"))
    observed = status_timestamp(data.get("snapshot_received_at") or snapshot.get("observed_at"))
    if (
        checked
        and (observed is None or checked > observed)
        and isinstance(sync.get("snapshot"), dict)
    ):
        return sync["snapshot"]
    return snapshot


def calculate_growth(today_val: Decimal, yesterday_val: Decimal) -> dict[str, Any]:
    """Calculate relative percentage growth between today and yesterday."""
    if yesterday_val != Decimal(0):
        diff = today_val - yesterday_val
        percent = (diff / abs(yesterday_val)) * Decimal(100)
        direction = "up" if percent > 0 else ("down" if percent < 0 else "neutral")
        sign = "+" if percent > 0 else ""
        return {
            "percent": float(round(percent, 1)),
            "text": f"{sign}{percent:.1f}%",
            "direction": direction,
        }
    if today_val > Decimal(0):
        return {"percent": 100.0, "text": "+100%", "direction": "up"}
    if today_val < Decimal(0):
        return {"percent": -100.0, "text": "-100%", "direction": "down"}
    return {"percent": 0.0, "text": "0.0%", "direction": "neutral"}


def _read_day_cashflows_ro(directory: Path, day: date) -> tuple[Decimal, Decimal]:
    """Read income and expense totals for a WIB day using a read-only SQLite connection."""
    db_file = directory / "history.sqlite3"
    if not db_file.is_file():
        return Decimal(0), Decimal(0)
    start_iso, end_iso = day_bounds(day)
    try:
        with read_sqlite(db_file, timeout=0.5) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT kind, amount FROM cashflows WHERE created>=? AND created<?",
                (start_iso, end_iso),
            ).fetchall()
    except sqlite3.Error:
        return Decimal(0), Decimal(0)

    income = Decimal(0)
    expenses = Decimal(0)
    for row in rows:
        amount = parse_coins(row["amount"])
        if row["kind"] == "income":
            income += amount
        elif row["kind"] == "expense":
            expenses += amount
    return income, expenses


def _format_wib_timestamp(
    raw: Any, *, fmt: str = "%d/%m %H:%M WIB", fallback: str = "Terkini"
) -> str:
    if not raw:
        return fallback
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(WIB)
        return dt.strftime(fmt)
    except ValueError:
        return str(raw)


def _format_study_cost(cost: Decimal) -> str:
    return "Gratis (0 koin)" if cost == Decimal(0) else f"-{format_coins(cost)} koin"


def _format_study_gain(receipt: dict[str, Any]) -> str:
    benar = receipt.get("benar")
    total = receipt.get("total")
    bonus = receipt.get("bonus", 1)
    if benar is not None and total is not None:
        return f"Kuis {benar}/{total} Benar (+{bonus} Keahlian)"
    return f"+{bonus} Keahlian"


def get_account_expense_history(directory: Path | None, limit: int = 50) -> list[dict[str, Any]]:
    """Load recent expense cashflows for a single account directory."""
    if not directory:
        return []
    db_file = directory / "history.sqlite3"
    if not db_file.is_file():
        return []
    try:
        with read_sqlite(db_file, timeout=0.5) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, created, category, amount, detail "
                "FROM cashflows WHERE kind='expense' ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    except sqlite3.Error:
        return []

    results = []
    for row in rows:
        detail: dict[str, Any] = {}
        if row["detail"]:
            try:
                parsed = json.loads(row["detail"])
                if isinstance(parsed, dict):
                    detail = parsed
            except ValueError:
                pass
        product = detail.get("product") or detail.get("action") or row["category"]
        shop = detail.get("shop")
        item_name = f"{product} • {shop}" if shop else str(product)
        amount_num = parse_coins(row["amount"])
        results.append(
            {
                "id": row["id"],
                "created": row["created"],
                "time_display": _format_wib_timestamp(row["created"]),
                "category": row["category"] or "pengeluaran",
                "item_name": item_name,
                "shop": shop,
                "product": product,
                "amount": format_coins(amount_num),
                "amount_num": float(amount_num),
            }
        )
    return results


def get_account_study_history(directory: Path | None, limit: int = 50) -> list[dict[str, Any]]:
    """Load recent study and quiz history for a single account directory."""
    if not directory:
        return []
    db_file = directory / "history.sqlite3"
    if not db_file.is_file():
        return []

    current_skills = {
        skill["id"]: skill
        for skill in cached_skills(directory)
        if isinstance(skill, dict) and "id" in skill
    }

    try:
        with read_sqlite(db_file, timeout=0.5) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, run_id, created, kind, status, payload FROM actions "
                "WHERE kind IN ('study', 'study_quiz') "
                "ORDER BY id DESC LIMIT ?",
                (limit * 2,),
            ).fetchall()

            study_actions: list[dict[str, Any]] = []
            quiz_actions: list[dict[str, Any]] = []
            for row in rows:
                payload: dict[str, Any] = {}
                if row["payload"]:
                    try:
                        parsed = json.loads(row["payload"])
                        if isinstance(parsed, dict):
                            payload = parsed
                    except ValueError:
                        pass
                item = {
                    "id": row["id"],
                    "run_id": row["run_id"],
                    "created": row["created"],
                    "kind": row["kind"],
                    "status": row["status"],
                    "payload": payload,
                }
                if row["kind"] == "study":
                    study_actions.append(item)
                else:
                    quiz_actions.append(item)

            matched_quiz_ids: set[int] = set()
            sessions: list[dict[str, Any]] = []

            for st in study_actions:
                st_payload = st["payload"]
                receipt = st_payload.get("receipt") or {}
                visit_id = receipt.get("id") or st_payload.get("before_visit_id")
                matching_quiz = None
                if visit_id:
                    for qz in quiz_actions:
                        if (
                            qz["id"] not in matched_quiz_ids
                            and qz["payload"].get("visit_id") == visit_id
                        ):
                            matching_quiz = qz
                            matched_quiz_ids.add(qz["id"])
                            break

                mode = st_payload.get("mode") or "perpus"
                track = st_payload.get("track") or (
                    matching_quiz["payload"].get("track") if matching_quiz else "dagang"
                )
                shop = st_payload.get("shop") or (
                    "Perpustakaan Desa" if mode == "perpus" else "Universitas Terbuka"
                )
                product = st_payload.get("product") or {}
                raw_price = product.get("price")
                cost_num = (
                    parse_coins(raw_price)
                    if raw_price is not None
                    else (Decimal(0) if mode == "perpus" else Decimal(4000))
                )
                created_raw = matching_quiz["created"] if matching_quiz else st["created"]
                if matching_quiz:
                    qz_payload = matching_quiz["payload"]
                    qz_receipt = qz_payload.get("receipt") or {}
                    recorded_level = qz_payload.get("skill_level")
                    if recorded_level is None:
                        recorded_level = st_payload.get("skill_level")
                    bonus = _safe_int(qz_receipt.get("bonus"), 0)
                    skill_gain = _format_study_gain(qz_receipt)
                    status_text = "Selesai"
                else:
                    recorded_level = st_payload.get("skill_level")
                    bonus = 0
                    skill_gain = "Kunjungan terdaftar (menunggu kuis)"
                    status_text = "Menunggu kuis"

                sessions.append(
                    _study_session_entry(
                        entry_id=f"study_{st['id']}",
                        created_raw=created_raw,
                        mode=mode,
                        shop=shop,
                        track=track,
                        cost_num=cost_num,
                        recorded_level=recorded_level,
                        bonus=bonus,
                        skill_gain=skill_gain,
                        status_text=status_text,
                    )
                )

            for qz in quiz_actions:
                if qz["id"] in matched_quiz_ids:
                    continue
                qz_payload = qz["payload"]
                qz_receipt = qz_payload.get("receipt") or {}
                mode = qz_payload.get("mode") or "perpus"
                track = qz_payload.get("track") or "dagang"
                shop = qz_payload.get("shop") or (
                    "Perpustakaan Desa" if mode == "perpus" else "Universitas Terbuka"
                )
                cost_num = Decimal(0) if mode == "perpus" else Decimal(4000)
                sessions.append(
                    _study_session_entry(
                        entry_id=f"quiz_{qz['id']}",
                        created_raw=qz["created"],
                        mode=mode,
                        shop=shop,
                        track=track,
                        cost_num=cost_num,
                        recorded_level=qz_payload.get("skill_level"),
                        bonus=_safe_int(qz_receipt.get("bonus"), 0),
                        skill_gain=_format_study_gain(qz_receipt),
                        status_text="Selesai",
                    )
                )

            if not sessions:
                event_rows = conn.execute(
                    "SELECT id, created, event, data FROM events "
                    "WHERE event IN ('belajar_dimulai', 'kuis_belajar_selesai') "
                    "ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                for erow in event_rows:
                    edata: dict[str, Any] = {}
                    if erow["data"]:
                        try:
                            parsed = json.loads(erow["data"])
                            if isinstance(parsed, dict):
                                edata = parsed
                        except ValueError:
                            pass
                    mode = edata.get("mode") or "perpus"
                    track = edata.get("track") or "dagang"
                    cost_val = parse_coins(edata.get("cost", 0))
                    shop = "Perpustakaan Desa" if mode == "perpus" else "Universitas Terbuka"
                    if erow["event"] == "kuis_belajar_selesai":
                        gain = _format_study_gain(edata)
                        st_text = "Selesai"
                        bonus = _safe_int(edata.get("bonus"), 0)
                    else:
                        gain = "Kunjungan dimulai"
                        st_text = "Menunggu kuis"
                        bonus = 0
                    sessions.append(
                        _study_session_entry(
                            entry_id=f"event_{erow['id']}",
                            created_raw=erow["created"],
                            mode=mode,
                            shop=shop,
                            track=track,
                            cost_num=cost_val,
                            recorded_level=edata.get("skill_level"),
                            bonus=bonus,
                            skill_gain=gain,
                            status_text=st_text,
                        )
                    )
    except sqlite3.Error:
        return []

    sessions.sort(key=lambda item: item.get("created") or "", reverse=True)
    _resolve_study_levels(sessions, current_skills)
    return sessions[:limit]


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_study_levels(
    sessions: list[dict[str, Any]],
    current_skills: dict[str, dict[str, Any]],
) -> None:
    """Resolve historical skill levels per track from recorded payloads or reverse-walk."""
    inferred_by_track: dict[str, int] = {
        track_id: skill["level"]
        for track_id, skill in current_skills.items()
        if isinstance(skill.get("level"), int) and not isinstance(skill.get("level"), bool)
    }
    for item in sessions:
        track = item.get("track_id") or ""
        recorded = item.pop("_recorded_level", None)
        bonus = item.pop("_bonus", 0)
        if isinstance(recorded, int) and not isinstance(recorded, bool):
            level: int | None = recorded
            inferred_by_track[track] = max(0, recorded - bonus) if bonus > 0 else recorded
        else:
            level = inferred_by_track.get(track)
            if level is not None and bonus > 0:
                inferred_by_track[track] = max(0, level - bonus)
        item["skill_level"] = level
        item["level_display"] = f"Lv. {level}" if level is not None else ""


def _study_session_entry(
    *,
    entry_id: str,
    created_raw: Any,
    mode: str,
    shop: str,
    track: str,
    cost_num: Decimal,
    recorded_level: Any,
    bonus: int,
    skill_gain: str,
    status_text: str,
) -> dict[str, Any]:
    track_name = SUBJECTS.get(track, track.capitalize() if isinstance(track, str) else "Keahlian")
    return {
        "id": entry_id,
        "time_display": _format_wib_timestamp(created_raw),
        "created": created_raw,
        "mode": mode,
        "mode_label": "Perpustakaan" if mode == "perpus" else "Universitas",
        "facility_name": shop,
        "track_id": track,
        "track_name": track_name,
        "cost": _format_study_cost(cost_num),
        "cost_num": float(cost_num),
        "skill_level": None,
        "level_display": "",
        "skill_gain": skill_gain,
        "status": status_text,
        "_recorded_level": recorded_level,
        "_bonus": bonus,
    }


def _build_account_logs(
    directory: Path, data: dict[str, Any], summary: dict[str, Any]
) -> list[str]:
    logs: list[str] = []
    if data.get("event"):
        ev = data.get("event")
        raw_stage = data.get("stage") or ""
        stage_desc = _STAGE_DESCRIPTIONS.get(raw_stage, raw_stage)
        time_str = _format_wib_timestamp(data.get("time"), fmt="%H:%M:%S WIB")

        if ev == "gagal":
            reason = data.get("reason") or "Bot menemui kendala pada aksi."
            logs.append(f"[{time_str}] ❌ Worker GAGAL saat {stage_desc}")
            logs.append(f"   Alasan: {reason}")
            if data.get("category"):
                logs.append(f"   Kategori: {data.get('category')}")
            if data.get("reconciliation_pending"):
                logs.append(
                    f"   Aksi tertahan: {data.get('reconciliation_pending')} transaksi game belum terkonfirmasi"
                )
            if data.get("last_action"):
                la = data["last_action"]
                logs.append(f"   Aksi terakhir: #{la.get('action_id', '?')} {la.get('kind', '?')}")
        elif ev in {"rekonsiliasi", "rekonsiliasi_otomatis"}:
            attempt = data.get("reconciliation_attempt", 1)
            limit = data.get("reconciliation_limit", 6)
            pending_cnt = data.get("reconciliation_pending", "?")
            logs.append(f"[{time_str}] 🔄 Rekonsiliasi Otomatis ({attempt}/{limit})")
            logs.append(
                f"   Sedang mencocokkan {pending_cnt} aksi transaksi tertahan dengan game..."
            )
        elif ev == "mulai":
            logs.append(f"[{time_str}] ▶️ Worker Mulai ({stage_desc})")
        elif ev == "berhenti":
            reason = data.get("reason") or "Dihentikan oleh pengguna."
            logs.append(f"[{time_str}] ⏹️ Worker Berhenti: {reason}")
        elif ev == "tidur":
            logs.append(f"[{time_str}] 💤 Istirahat / Tidur di game")
        else:
            logs.append(f"[{time_str}] Status: {ev} ({stage_desc})")

    sync_file = directory / "game-sync.json"
    if sync_file.is_file():
        try:
            sync_data = json.loads(sync_file.read_text())
            for action in sync_data.get("reconciliation", []):
                if action.get("status_after") in {"pending", "uncertain"}:
                    desc = action.get("description") or action.get("kind", "Aksi")
                    reason = action.get("reason", "")
                    logs.append(f"⏳ Aksi tertahan: #{action.get('action_id')} {desc} ({reason})")
        except (OSError, ValueError):
            pass

    last_err_file = directory / "last-error.json"
    if last_err_file.is_file():
        try:
            err_data = json.loads(last_err_file.read_text())
            err_ctx = err_data.get("context", err_data)
            err_id = err_ctx.get("error_id")
            err_msg = err_ctx.get("message") or err_data.get("message")
            err_tindakan = err_ctx.get("tindakan") or err_data.get("tindakan")
            if err_id and err_msg:
                logs.append(f"🚨 Error Terakhir [{err_id}]: {err_msg[:120]}")
                if err_tindakan:
                    logs.append(f"   💡 Solusi: {err_tindakan}")
        except (OSError, ValueError):
            pass

    hist_file = directory / "history.jsonl"
    if hist_file.is_file():
        with suppress(OSError):
            logs.extend(hist_file.read_text().strip().splitlines()[-15:])
    if not logs and summary.get("status_text"):
        logs.append(f"Status saat ini: {summary.get('status_text')}")
    return logs


def build_dashboard_payload(ctx: WebContext, user: dict[str, Any]) -> dict[str, Any]:
    """Assemble the complete dashboard payload for an authenticated user."""
    registry = ctx.registry
    owner = registry.owner_for_user(user)
    accounts_list = registry.list(owner)
    selected = registry.selected(owner)
    if not selected and accounts_list:
        selected = accounts_list[0]
        registry.select(owner, selected["id"])

    today_report = report_date()
    yesterday_report = today_report - timedelta(days=1)

    accounts_payload: list[dict[str, Any]] = []
    total_wallet = Decimal(0)
    total_income = Decimal(0)
    total_expenses = Decimal(0)
    total_net_profit = Decimal(0)
    total_yesterday_net = Decimal(0)
    total_yesterday_income = Decimal(0)
    total_trips = 0
    active_workers = 0
    online_accounts = 0
    selected_finance_info: dict[str, Any] | None = None

    for acc in accounts_list:
        acc_service = (
            resolve_account_service(ctx, user, account_id=acc["id"]) if ctx.manager else ctx.service
        )
        sum_info = acc_service.summary() if acc_service else {}
        r_dir = acc_service.settings.runtime_dir if acc_service else None
        acc_snap: dict[str, Any] = {}
        if r_dir:
            st_data, _ = status_record(r_dir / "status.json")
            acc_snap = dashboard_snapshot(r_dir, st_data)

        wallet = acc_snap.get("wallet", sum_info.get("wallet"))
        acc_wallet_num = parse_coins(wallet)
        acc_income_num = parse_coins(acc_snap.get("today_income"))
        raw_trips = acc_snap.get("today_count", sum_info.get("trips", 0))
        try:
            acc_trips = int(raw_trips)
        except (ValueError, TypeError):
            acc_trips = 0

        if r_dir:
            acc_journal_income, acc_expenses = _read_day_cashflows_ro(r_dir, today_report)
            acc_yest_income, acc_yest_exp = _read_day_cashflows_ro(r_dir, yesterday_report)
            acc_yest_net = acc_yest_income - acc_yest_exp
        else:
            acc_journal_income = acc_expenses = acc_yest_income = acc_yest_net = Decimal(0)

        effective_income = max(acc_income_num, acc_journal_income)
        effective_net = effective_income - acc_expenses
        acc_growth_net = calculate_growth(effective_net, acc_yest_net)
        acc_growth_inc = calculate_growth(effective_income, acc_yest_income)

        is_active = bool(sum_info.get("active", False))
        is_online = bool(sum_info.get("online", False))
        total_wallet += acc_wallet_num
        total_income += effective_income
        total_expenses += acc_expenses
        total_net_profit += effective_net
        total_yesterday_net += acc_yest_net
        total_yesterday_income += acc_yest_income
        total_trips += acc_trips
        active_workers += int(is_active)
        online_accounts += int(is_online)

        acc_flags = auto_flags(r_dir) if r_dir else {}
        accounts_payload.append(
            {
                "id": acc["id"],
                "name": acc["name"],
                "archived": bool(acc["archived"]),
                "legacy": bool(acc["legacy"]),
                "is_selected": bool(selected and acc["id"] == selected["id"]),
                "has_cookie": sum_info.get("has_cookie", False),
                "is_running": is_active,
                "is_online": is_online,
                "auto_ojol": bool(acc_flags.get("ojol")),
                "auto_flags": acc_flags,
                "icon": sum_info.get("icon", "⚪"),
                "phase": sum_info.get("phase", "idle"),
                "status_text": sum_info.get("status_text", "Standby"),
                "wallet": format_coins(acc_wallet_num) if wallet is not None else None,
                "wallet_num": float(acc_wallet_num),
                "today_income": format_coins(effective_income),
                "today_income_num": float(effective_income),
                "today_expenses": format_coins(acc_expenses),
                "today_expenses_num": float(acc_expenses),
                "today_net_profit": format_coins(effective_net),
                "today_net_profit_num": float(effective_net),
                "profit_growth": acc_growth_net,
                "income_growth": acc_growth_inc,
                "trips": acc_trips,
                "fuel": acc_snap.get("fuel", sum_info.get("fuel")),
                "condition": acc_snap.get("condition", sum_info.get("condition")),
                "data": acc_snap.get("data", sum_info.get("data")),
            }
        )

        if selected and acc["id"] == selected["id"]:
            selected_finance_info = {
                "today_income": format_coins(effective_income),
                "today_income_num": float(effective_income),
                "today_expenses": format_coins(acc_expenses),
                "today_expenses_num": float(acc_expenses),
                "today_net_profit": format_coins(effective_net),
                "today_net_profit_num": float(effective_net),
                "profit_growth": acc_growth_net,
                "income_growth": acc_growth_inc,
            }

    all_accounts_summary = {
        "total_accounts": len(accounts_payload),
        "active_workers": active_workers,
        "online_accounts": online_accounts,
        "total_wallet": format_coins(total_wallet),
        "total_wallet_num": float(total_wallet),
        "total_income": format_coins(total_income),
        "total_income_num": float(total_income),
        "total_expenses": format_coins(total_expenses),
        "total_expenses_num": float(total_expenses),
        "total_net_profit": format_coins(total_net_profit),
        "total_net_profit_num": float(total_net_profit),
        "profit_growth": calculate_growth(total_net_profit, total_yesterday_net),
        "income_growth": calculate_growth(total_income, total_yesterday_income),
        "total_trips": total_trips,
    }

    fleet_dirs, _ = get_all_fleet_directories(ctx)
    empty_finance = {
        "today_income": "0",
        "today_income_num": 0.0,
        "today_expenses": "0",
        "today_expenses_num": 0.0,
        "today_net_profit": "0",
        "today_net_profit_num": 0.0,
        "profit_growth": {"percent": 0.0, "text": "0.0%", "direction": "neutral"},
        "income_growth": {"percent": 0.0, "text": "0.0%", "direction": "neutral"},
        "expense_history": [],
    }

    if not selected:
        return {
            "account": None,
            "accounts": accounts_payload,
            "all_accounts_summary": all_accounts_summary,
            "finance": empty_finance,
            "study_history": [],
            "skills": [],
            "summary": {},
            "snapshot": {},
            "auto_flags": {},
            "study_subject": "dagang",
            "ojol_mode": "otomatis",
            "limit_reached": False,
            "hours_left": None,
            "logs": [],
            "notifications": [],
            "pending_bank_reviews_count": len(get_all_pending_reviews(fleet_dirs)),
        }

    cur_service = resolve_account_service(ctx, user, account_id=selected["id"])
    summary = cur_service.summary() if cur_service else {}
    directory = cur_service.settings.runtime_dir
    data, _ = status_record(directory / "status.json")
    state = dashboard_snapshot(directory, data)
    kerja_status, _ = status_record(directory / "kerja-status.json")
    kursus_status, _ = status_record(directory / "kursus-status.json")
    skills_list = cached_skills(directory)
    selected_kursus = kursus_subject(directory)

    flags = auto_flags(directory)
    subj_dict = subjects(directory)
    cur_subj = subj_dict.get("perpus") or subj_dict.get("kuliah") or "dagang"
    enabled_needs_count = sum(1 for key in NEEDS if flags.get(key))

    flags_payload = dict(flags)
    flags_payload["study"] = bool(flags.get("perpus") or flags.get("kuliah"))
    flags_payload["garden"] = bool(flags.get("kebun"))
    flags_payload["auto_subject"] = cur_subj == "auto"
    flags_payload["needs_active"] = enabled_needs_count > 0
    flags_payload["needs_count"] = enabled_needs_count
    flags_payload["total_needs"] = len(NEEDS)

    logs = _build_account_logs(directory, data, summary)
    notices = list_notifications(cur_service.settings, limit=10)
    pending_bank_count = len(get_all_pending_reviews(fleet_dirs))

    hours_left = state.get("ojol_hours_left")
    limit_reached = bool(
        summary.get("shift_done")
        or state.get("ojol_shift_done")
        or (isinstance(hours_left, (int, float)) and hours_left <= 0)
        or "Batas narik" in str(summary.get("status_text") or "")
    )

    finance_payload = {
        **(selected_finance_info or empty_finance),
        "expense_history": get_account_expense_history(directory, limit=50),
    }

    return {
        "account": {
            "id": selected["id"],
            "name": selected["name"],
            "has_cookie": summary.get("has_cookie", False),
        },
        "accounts": accounts_payload,
        "all_accounts_summary": all_accounts_summary,
        "finance": finance_payload,
        "study_history": get_account_study_history(directory, limit=50),
        "skills": skills_list,
        "summary": summary,
        "snapshot": state,
        "kerja_status": kerja_status or None,
        "kerja_target_poin": kerja_target_poin(directory),
        "kursus_subject": selected_kursus,
        "kursus_cost": kursus_cost_info(skills_list, selected_kursus),
        "kursus_status": kursus_status or None,
        "auto_flags": flags_payload,
        "study_subject": cur_subj,
        "ojol_mode": getattr(cur_service.settings, "ojol_mode", "otomatis"),
        "limit_reached": limit_reached,
        "hours_left": summary.get("hours_left") or state.get("ojol_hours_left"),
        "logs": logs,
        "notifications": notices,
        "pending_bank_reviews_count": pending_bank_count,
    }
