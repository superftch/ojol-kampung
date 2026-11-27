"""Job vacancy normalization, salary multiplier calculation, and skill matching."""

from __future__ import annotations

import math
from typing import Any


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_skill_for_profession(
    skill_state: dict[str, Any], profession: str
) -> dict[str, Any]:
    """Match a profession to the account's skill track and effective bonusBps."""
    global_level = _as_int(skill_state.get("level"), 0)
    global_bonus_bps = _as_int(skill_state.get("bonusBps"), 0)
    tracks = skill_state.get("tracks")
    if isinstance(tracks, list):
        for track in tracks:
            if not isinstance(track, dict):
                continue
            profs = track.get("professions")
            if isinstance(profs, list) and profession in profs:
                track_bonus_bps = _as_int(track.get("bonusBps"), 0)
                return {
                    "track_id": track.get("id") or "",
                    "track_name": track.get("name") or "",
                    "track_icon": track.get("icon") or "",
                    "level": _as_int(track.get("level"), 0),
                    "bonus_bps": max(global_bonus_bps, track_bonus_bps),
                }
    return {
        "track_id": "",
        "track_name": "",
        "track_icon": "",
        "level": global_level,
        "bonus_bps": global_bonus_bps,
    }


def _compute_transport_deduction(
    transport: dict[str, Any] | None,
    home_desa: str | None,
    job_desa: str | None,
    gross_milli: int,
) -> tuple[int, str | None]:
    """Compute cross-village transport deduction matching client tc()."""
    if not isinstance(transport, dict) or not home_desa or not job_desa or home_desa == job_desa:
        return 0, None
    nilai = _as_float(transport.get("nilai"), 0.0)
    if nilai <= 0:
        return 0, None
    jenis = str(transport.get("jenis") or "")
    nilai_label = str(nilai).rstrip("0").rstrip(".").replace(".", ",")
    if jenis == "koin_per_hari":
        deduct = round(1000 * nilai)
        return min(gross_milli, deduct), f"Potongan transport lintas desa ({nilai_label} koin/hari)"
    deduct = math.ceil(gross_milli * nilai / 100)
    return min(gross_milli, deduct), f"Potongan transport lintas desa ({nilai_label}%)"


def _facility_blocked_reason(
    me: dict[str, Any],
    v: dict[str, Any],
    skill_info: dict[str, Any],
    is_current: bool,
    is_full: bool,
) -> str | None:
    if is_current:
        return "Kamu sedang bekerja di sini."
    if not me.get("home"):
        return "Lowongan bisa dilamar setelah kamu punya rumah."
    if me.get("jobBlock"):
        return str(me["jobBlock"])
    if is_full:
        return "Kuota sedang penuh."
    profile = me.get("profile") if isinstance(me.get("profile"), dict) else {}
    gender = v.get("gender")
    if gender and profile.get("gender") != gender:
        return f"Khusus warga {'wanita' if gender == 'perempuan' else 'pria'}."
    min_age = _as_int(v.get("minAge"), 0)
    age = profile.get("age")
    if min_age > 0 and (age is None or _as_int(age, 0) < min_age):
        return f"Khusus warga berumur {min_age} tahun ke atas."
    min_skill = _as_int(v.get("minSkillLevel"), 0)
    if skill_info["level"] < min_skill:
        track_label = (
            f"{skill_info['track_icon']} {skill_info['track_name']} ".strip()
            if skill_info["track_name"]
            else "keahlian"
        )
        return f"Butuh {track_label} ⭐{min_skill} (kamu ⭐{skill_info['level']})."
    fee_milli = _as_int(v.get("feeMilli"), 0)
    balance_milli = _as_int(me.get("balanceMilli"), 0)
    if fee_milli > 0 and balance_milli < fee_milli:
        return f"Sewa lapak {fee_milli / 1000:g} koin, koinmu tidak cukup."
    return None


def _business_blocked_reason(
    me: dict[str, Any],
    v: dict[str, Any],
    is_current: bool,
    is_full: bool,
) -> str | None:
    if v.get("mine"):
        return "Ini lowongan usahamu sendiri."
    if is_current:
        return "Kamu sedang bekerja di sini."
    if not me.get("home"):
        return "Lowongan bisa dilamar setelah kamu punya rumah."
    if me.get("jobBlock"):
        return str(me["jobBlock"])
    if is_full:
        return "Semua tempat sudah terisi."
    return None


def build_job_vacancies_payload(
    me: dict[str, Any], biz_items: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Normalize facility and business job vacancies with salary multipliers and eligibility."""
    catalog = me.get("catalog") if isinstance(me.get("catalog"), dict) else {}
    skill_state = me.get("skill") if isinstance(me.get("skill"), dict) else {}
    ekonomi = me.get("ekonomi") if isinstance(me.get("ekonomi"), dict) else {}
    home = me.get("home") if isinstance(me.get("home"), dict) else {}
    current_job = me.get("job") if isinstance(me.get("job"), dict) else None

    home_desa = home.get("desa")
    transport = catalog.get("transport") if isinstance(catalog.get("transport"), dict) else None
    ekonomi_bonus_bps = _as_int(ekonomi.get("bonusBps"), 0)
    ekonomi_rem_bps = _as_int(ekonomi.get("remBps"), 0)
    contract_days_default = _as_int(catalog.get("contractDays"), 7)

    raw_vacancies = catalog.get("vacancies")
    fac_vacancies = raw_vacancies if isinstance(raw_vacancies, list) else []
    raw_biz = biz_items if biz_items is not None else catalog.get("bizVacancies")
    biz_vacancies = raw_biz if isinstance(raw_biz, list) else []

    normalized: list[dict[str, Any]] = []

    for v in fac_vacancies:
        if not isinstance(v, dict):
            continue
        profession = str(v.get("profession") or "")
        facility_id = str(v.get("facilityId") or "")
        if not profession or not facility_id:
            continue

        slots = _as_int(v.get("slots"), 0)
        filled = _as_int(v.get("filled"), 0)
        is_full = filled >= slots
        fee_milli = _as_int(v.get("feeMilli"), 0)
        base_milli = _as_int(v.get("wageMilliDay"), 0)
        min_skill = _as_int(v.get("minSkillLevel"), 0)

        skill_info = _resolve_skill_for_profession(skill_state, profession)
        skill_bonus_bps = skill_info["bonus_bps"]
        after_skill = (base_milli * (10000 + skill_bonus_bps)) // 10000
        skill_bonus_milli = after_skill - base_milli

        transport_deduct, transport_note = _compute_transport_deduction(
            transport, home_desa, v.get("desa"), after_skill
        )
        after_transport = max(0, after_skill - transport_deduct)

        if fee_milli > 0:
            applied_ekonomi_bps = 0
            ekonomi_bonus_milli = 0
            net_milli = after_transport
        else:
            applied_ekonomi_bps = ekonomi_bonus_bps
            ekonomi_bonus_milli = (after_transport * applied_ekonomi_bps) // 10000
            net_milli = after_transport + ekonomi_bonus_milli

        is_current = bool(
            current_job
            and current_job.get("employerId") == facility_id
            and current_job.get("profession") == profession
        )
        blocked_reason = _facility_blocked_reason(me, v, skill_info, is_current, is_full)
        is_bumdes = bool(v.get("bumdes"))

        normalized.append(
            {
                "id": f"fac:{facility_id}:{profession}",
                "kind": "facility",
                "facility_id": facility_id,
                "vacancy_id": None,
                "profession": profession,
                "place_name": str(v.get("facility") or v.get("item") or "Fasilitas"),
                "source": "bumdes" if is_bumdes else "pemerintah",
                "source_label": "BUMDes" if is_bumdes else "Pemerintah",
                "desa": v.get("desa"),
                "desa_name": v.get("desaName") or v.get("desa") or "",
                "cross_desa": bool(home_desa and v.get("desa") and home_desa != v.get("desa")),
                "block": None,
                "owner_nick": None,
                "slots": slots,
                "filled": filled,
                "available_slots": max(0, slots - filled),
                "is_full": is_full,
                "kosong_at": v.get("kosongAt"),
                "skill_track_id": skill_info["track_id"],
                "skill_track_name": skill_info["track_name"],
                "skill_track_icon": skill_info["track_icon"],
                "min_skill_level": min_skill,
                "account_skill_level": skill_info["level"],
                "skill_met": skill_info["level"] >= min_skill,
                "skill_gap": max(0, min_skill - skill_info["level"]),
                "gender_req": v.get("gender"),
                "min_age": _as_int(v.get("minAge"), 0) or None,
                "fee_milli": fee_milli,
                "contract_days": contract_days_default,
                "salary": {
                    "base_milli": base_milli,
                    "skill_bonus_bps": skill_bonus_bps,
                    "skill_bonus_milli": skill_bonus_milli,
                    "transport_deduct_milli": transport_deduct,
                    "transport_note": transport_note,
                    "ekonomi_bonus_bps": applied_ekonomi_bps,
                    "ekonomi_bonus_milli": ekonomi_bonus_milli,
                    "subsidi_bps": 0,
                    "subsidi_milli": 0,
                    "net_milli": net_milli,
                },
                "is_current_job": is_current,
                "can_apply": blocked_reason is None,
                "blocked_reason": blocked_reason,
            }
        )

    for v in biz_vacancies:
        if not isinstance(v, dict):
            continue
        vacancy_id = str(v.get("id") or "")
        profession = str(v.get("profession") or "")
        if not vacancy_id or not profession:
            continue

        slots = _as_int(v.get("slots"), 0)
        filled = _as_int(v.get("hired"), 0)
        is_full = filled >= slots
        base_milli = _as_int(v.get("rate"), 0)
        skill_info = _resolve_skill_for_profession(skill_state, profession)

        transport_deduct, transport_note = _compute_transport_deduction(
            transport, home_desa, v.get("desa"), base_milli
        )
        after_transport = max(0, base_milli - transport_deduct)
        ekonomi_bonus_milli = (after_transport * ekonomi_bonus_bps) // 10000
        subsidi_milli = (after_transport * ekonomi_rem_bps) // 10000
        net_milli = after_transport + ekonomi_bonus_milli + subsidi_milli

        is_current = bool(
            current_job and current_job.get("employerId") == v.get("businessId")
        )
        blocked_reason = _business_blocked_reason(me, v, is_current, is_full)

        normalized.append(
            {
                "id": f"biz:{vacancy_id}",
                "kind": "business",
                "facility_id": None,
                "vacancy_id": vacancy_id,
                "profession": profession,
                "place_name": str(v.get("name") or v.get("catalogId") or "Usaha Warga"),
                "source": "usaha",
                "source_label": "Usaha Warga",
                "desa": v.get("desa"),
                "desa_name": v.get("desaName") or v.get("desa") or "",
                "cross_desa": bool(home_desa and v.get("desa") and home_desa != v.get("desa")),
                "block": v.get("block"),
                "owner_nick": v.get("ownerNick"),
                "slots": slots,
                "filled": filled,
                "available_slots": max(0, slots - filled),
                "is_full": is_full,
                "kosong_at": None,
                "skill_track_id": skill_info["track_id"],
                "skill_track_name": skill_info["track_name"],
                "skill_track_icon": skill_info["track_icon"],
                "min_skill_level": 0,
                "account_skill_level": skill_info["level"],
                "skill_met": True,
                "skill_gap": 0,
                "gender_req": None,
                "min_age": None,
                "fee_milli": 0,
                "contract_days": _as_int(v.get("days"), contract_days_default),
                "salary": {
                    "base_milli": base_milli,
                    "skill_bonus_bps": 0,
                    "skill_bonus_milli": 0,
                    "transport_deduct_milli": transport_deduct,
                    "transport_note": transport_note,
                    "ekonomi_bonus_bps": ekonomi_bonus_bps,
                    "ekonomi_bonus_milli": ekonomi_bonus_milli,
                    "subsidi_bps": ekonomi_rem_bps,
                    "subsidi_milli": subsidi_milli,
                    "net_milli": net_milli,
                },
                "is_current_job": is_current,
                "can_apply": blocked_reason is None,
                "blocked_reason": blocked_reason,
            }
        )

    normalized.sort(
        key=lambda item: (
            -item["salary"]["net_milli"],
            item["is_full"],
            item["skill_gap"],
            item["profession"].lower(),
        )
    )

    tracks_out = []
    if isinstance(skill_state.get("tracks"), list):
        for t in skill_state["tracks"]:
            if isinstance(t, dict) and t.get("id"):
                tracks_out.append(
                    {
                        "id": t["id"],
                        "name": t.get("name") or t["id"],
                        "icon": t.get("icon") or "",
                        "level": _as_int(t.get("level"), 0),
                        "bonus_bps": _as_int(t.get("bonusBps"), 0),
                    }
                )

    return {
        "current_job": {
            "profession": current_job.get("profession"),
            "place_name": current_job.get("facility") or current_job.get("business") or "",
            "employer_type": current_job.get("employerType"),
            "rate_milli_day": _as_int(current_job.get("rateMilliDay"), 0),
            "ekonomi_bps": _as_int(current_job.get("ekonomiBps"), 0),
            "end_at": current_job.get("endAt"),
        }
        if current_job
        else None,
        "has_home": bool(home),
        "home_desa": home_desa,
        "home_desa_name": home.get("desaName") or "",
        "balance_milli": _as_int(me.get("balanceMilli"), 0),
        "ekonomi": {
            "bonus_bps": ekonomi_bonus_bps,
            "rem_bps": ekonomi_rem_bps,
        },
        "account_skills": tracks_out,
        "summary": {
            "total_count": len(normalized),
            "available_count": sum(1 for x in normalized if not x["is_full"]),
            "skill_match_count": sum(1 for x in normalized if x["skill_met"]),
            "skill_match_available_count": sum(
                1 for x in normalized if x["skill_met"] and not x["is_full"]
            ),
            "eligible_count": sum(1 for x in normalized if x["can_apply"]),
            "biz_count": sum(1 for x in normalized if x["kind"] == "business"),
        },
        "vacancies": normalized,
    }
