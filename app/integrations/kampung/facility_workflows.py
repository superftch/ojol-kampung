"""Kampung facility operations using the active game session."""

from __future__ import annotations

import asyncio
import json
import re
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from app.core.exceptions import HttpCoreError
from app.core.models import (
    AUTO_SUBJECT,
    STUDY_LABELS,
    SUBJECTS,
    Need,
    Product,
    Resource,
    ShopPreview,
)
from app.core.storage import write_private
from app.integrations.kampung.game_parsers import (
    coin,
)
from app.integrations.kampung.shop_locations import (
    BPJS_KANTOR_BY_VILLAGE,
    GYM_FACILITIES_BY_VILLAGE,
    STUDY_FACILITIES_BY_VILLAGE,
)
from app.modules.gameplay.recreation import solve_foto_shots
from app.modules.gameplay.sppg import solve_nampan_picks
from app.modules.gameplay.study import (
    extract_quiz_bank,
    is_track_max,
    quiz_answers,
    save_skills,
    subjects,
)
from app.modules.worker.settings import auto_flags

if TYPE_CHECKING:
    from app.integrations.kampung.http_api import OjolHttpApi


class FacilityWorkflows:
    def __init__(self, api: OjolHttpApi) -> None:
        self.api = api

    async def _minigame_wait(self, seconds: float) -> None:
        wait_time = seconds * getattr(self.api, "minigame_wait_multiplier", 1.0)
        if wait_time > 0:
            await asyncio.sleep(wait_time)

    async def complete_minigame(self, facility_id, game, request_id):
        start_payload = {
            "action": "start",
            "projectId": facility_id,
            "requestId": request_id,
            "game": game,
        }
        started = await self.api.request("/api/minigame", start_payload)
        if not isinstance(started, dict):
            raise HttpCoreError("Respons start minigame tidak valid", category="rejected")
        play_id = started.get("playId")
        if not play_id:
            raise HttpCoreError("Play ID minigame tidak ditemukan", category="rejected")

        if game == "gym":
            plan = started.get("plan")
            reps = plan.get("reps") if isinstance(plan, dict) else plan
            if not isinstance(reps, list) or not reps:
                raise HttpCoreError("Plan minigame gym tidak valid", category="rejected")

            holds = []
            for rep in reps:
                fill = rep.get("fill", 1400)
                center = rep.get("center", 0.7)
                hold = round(fill * center)
                holds.append(hold)

            total_hold_seconds = sum(holds) / 1000.0
            pause_seconds = (len(holds) - 1) * 1.1 if len(holds) > 1 else 0.0
            total_wait = total_hold_seconds + pause_seconds
            await self._minigame_wait(total_wait)

            finish_payload = {
                "action": "finish",
                "playId": play_id,
                "holds": holds,
            }
            result = await self.api.request("/api/minigame", finish_payload)
            if not isinstance(result, dict):
                raise HttpCoreError("Respons finish minigame tidak valid", category="rejected")
            detail = result.get("detail") or {}
            if detail.get("invalid"):
                raise HttpCoreError("Minigame tidak sah (terlalu cepat)", category="rejected")
            if detail.get("expired"):
                raise HttpCoreError("Minigame kedaluwarsa", category="rejected")
            return result

        raise HttpCoreError(f"Minigame {game} belum didukung", category="blocked")

    async def gym_facility(self, identifier, effects=None):
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9-]{36}", identifier):
            return None
        try:
            details = await self.api.request(f"/api/facilities/{identifier}")
        except HttpCoreError:
            return None
        service = details.get("service")
        if (
            details.get("id") != identifier
            or details.get("state") != "DONE"
            or not isinstance(service, dict)
            or service.get("open") is not True
        ):
            return None
        item = re.sub(r"-t[0-9]+$", "", details.get("item", ""))
        products = []
        if item in {"gym-desa", "gym-mini-desa"}:
            try:
                minigame = await self.api.request(f"/api/minigame?projectId={identifier}&game=gym")
            except HttpCoreError:
                minigame = None
            if isinstance(minigame, dict) and minigame.get("playsLeft", 0) > 0:
                mg_name = minigame.get("name") or "Angkat beban"
                mg_gain = (minigame.get("kebutuhan") or {}).get("fisik", 15)
                products.append(
                    Product(
                        name=mg_name,
                        price=Decimal(0),
                        effects={"fisik": mg_gain},
                        row_text=json.dumps(
                            {
                                "shop": identifier,
                                "item": "minigame",
                                "game": "gym",
                                "resource": "fisik",
                            }
                        ),
                        enabled=True,
                    )
                )
        if (
            not details.get("nextAt")
            and not details.get("myVisitUntil")
            and type(service.get("priceMilli")) is int
        ):
            effect = (effects or {}).get(item, {})
            gain = effect.get("fisik", 55)
            products.append(
                Product(
                    name=service["label"],
                    price=coin(service["priceMilli"]),
                    effects=effect or {"fisik": gain},
                    row_text=json.dumps({"shop": identifier, "item": "use", "resource": "fisik"}),
                    enabled=True,
                )
            )
        if not products:
            return None
        return ShopPreview(
            id=identifier,
            plot_id=identifier,
            name=details.get("title", "Gym desa"),
            category="fasum",
            distance_squared=0,
            products=products,
        )

    async def gym_plays_left(self) -> int:
        village = (self.api.home or {}).get("desa")
        gym_ids = list(GYM_FACILITIES_BY_VILLAGE.get(village, ()))
        for fid in gym_ids:
            try:
                minigame = await self.api.request(f"/api/minigame?projectId={fid}&game=gym")
                if isinstance(minigame, dict) and "playsLeft" in minigame:
                    return int(minigame.get("playsLeft", 0))
            except HttpCoreError:
                continue
        if not self.api.physical_places:
            try:
                tempat = await self.api.request("/api/kebutuhan?tempat=fisik")
                self.api.physical_places = [
                    p for p in tempat.get("places", []) if p.get("kind") == "fasum"
                ]
            except HttpCoreError:
                self.api.physical_places = []
        for place in self.api.physical_places:
            fid = place.get("id")
            if fid:
                try:
                    minigame = await self.api.request(f"/api/minigame?projectId={fid}&game=gym")
                    if isinstance(minigame, dict) and "playsLeft" in minigame:
                        return int(minigame.get("playsLeft", 0))
                except HttpCoreError:
                    continue
        return 0

    async def physical_facility(self, place, effects=None):
        identifier = place.get("id")
        gain = place.get("gain")
        if (
            place.get("kind") != "fasum"
            or place.get("open") is not True
            or type(place.get("priceMilli")) is not int
            or place["priceMilli"] < 0
            or type(gain) is not int
            or not 0 < gain <= 100
            or not isinstance(identifier, str)
            or not re.fullmatch(r"[a-f0-9-]{36}", identifier)
        ):
            return None
        details = await self.api.request(f"/api/facilities/{identifier}")
        service = details.get("service")
        if (
            details.get("id") != identifier
            or details.get("state") != "DONE"
            or not isinstance(service, dict)
            or service.get("studySessions")
            or service.get("open") is not True
        ):
            return None
        item = re.sub(r"-t[0-9]+$", "", details.get("item", ""))
        products = []
        if item in {"gym-desa", "gym-mini-desa"}:
            try:
                minigame = await self.api.request(f"/api/minigame?projectId={identifier}&game=gym")
            except HttpCoreError:
                minigame = None
            if isinstance(minigame, dict) and minigame.get("playsLeft", 0) > 0:
                mg_name = minigame.get("name") or "Angkat beban"
                mg_gain = (minigame.get("kebutuhan") or {}).get("fisik", 15)
                products.append(
                    Product(
                        name=mg_name,
                        price=Decimal(0),
                        effects={"fisik": mg_gain},
                        row_text=json.dumps(
                            {
                                "shop": identifier,
                                "item": "minigame",
                                "game": "gym",
                                "resource": "fisik",
                            }
                        ),
                        enabled=True,
                    )
                )
        if (
            not details.get("nextAt")
            and not details.get("myVisitUntil")
            and type(service.get("priceMilli")) is int
            and service["priceMilli"] == place["priceMilli"]
        ):
            effect: dict[Need | Resource, int] = (effects or {}).get(item, {})
            if effect.get("fisik") != gain:
                effect = {"fisik": gain}
            products.append(
                Product(
                    name=service["label"],
                    price=coin(service["priceMilli"]),
                    effects=effect,
                    row_text=json.dumps({"shop": identifier, "item": "use", "resource": "fisik"}),
                    enabled=True,
                )
            )
        if not products:
            return None
        return ShopPreview(
            id=identifier,
            plot_id=identifier,
            name=place["name"],
            category="fasum",
            distance_squared=0,
            products=products,
        )

    async def study_status(self, mode):
        if mode not in STUDY_LABELS:
            raise HttpCoreError("Type belajar tidak didukung", category="blocked")
        me = await self.api.request("/api/game/me")
        self.api.config_version = me["configVersion"]
        identifier = STUDY_FACILITIES_BY_VILLAGE.get((me.get("home") or {}).get("desa"), {}).get(
            mode
        )
        if identifier is None:
            raise HttpCoreError(
                "Fasilitas belajar desa akun belum terverifikasi", category="blocked"
            )
        facility, quiz = await asyncio.gather(
            self.api.request(f"/api/facilities/{identifier}"),
            self.api.request(f"/api/facilities/{identifier}/kuis"),
        )
        service = facility.get("service") or {}
        expected_item = "perpustakaan-desa" if mode == "perpus" else "universitas"
        if (
            facility.get("id") != identifier
            or re.sub(r"-t[0-9]+$", "", facility.get("item", "")) != expected_item
            or facility.get("state") != "DONE"
            or type(service.get("priceMilli")) is not int
            or service["priceMilli"] < 0
            or (mode == "perpus" and service["priceMilli"] != 0)
            or (mode == "kuliah" and service["priceMilli"] == 0)
            or type(service.get("studySessions")) is not int
            or service["studySessions"] <= 0
            or type(quiz.get("available")) is not bool
        ):
            raise HttpCoreError("Fasilitas/tarif belajar belum terverifikasi", category="schema")
        if isinstance(me.get("skill"), dict) and isinstance(me["skill"].get("tracks"), list):
            save_skills(self.api.directory, me["skill"]["tracks"])
        return {"facility": facility, "quiz": quiz, "tracks": me["skill"]["tracks"]}

    async def quiz_bank(self):
        cache = self.api.directory / "http-quiz-bank.json"
        version = self.api.config_version
        if cache.is_file():
            saved = json.loads(cache.read_text())
            if saved.get("version") == version and saved.get("tracks"):
                return saved["tracks"]
        html = await self.api.request("/kampung", text=True)
        for path in re.findall(r"<script[^>]+src=[\"\x27]([^\"\x27]+)", html):
            if not path.startswith("/_next/static/"):
                continue
            bank = extract_quiz_bank(await self.api.request(path, text=True))
            if bank:
                write_private(cache, {"version": version, "tracks": bank})
                return bank
        raise HttpCoreError("Bacaan dan bank soal client belum terverifikasi", category="schema")

    async def study_start(
        self, mode, track, expected_price, expected_wallet, min_balance, request_id
    ):
        request_id = str(UUID(request_id))
        if track not in SUBJECTS or subjects(self.api.directory).get(mode) not in (
            track,
            AUTO_SUBJECT,
        ):
            raise HttpCoreError("Pilihan bidang belajar berubah", category="rejected")
        status = await self.study_status(mode)
        facility = status["facility"]
        service = facility["service"]
        skill = next((row for row in status["tracks"] if row["id"] == track), None)
        price = coin(service["priceMilli"])
        if (
            not skill
            or is_track_max(skill, mode)
            or skill.get("pending")
            or facility.get("nextAt")
            or facility.get("myVisitUntil")
            or service.get("open") is not True
            or (service.get("studyTracks") is not None and track not in service["studyTracks"])
            or price != Decimal(expected_price)
        ):
            raise HttpCoreError(
                "Bidang, tarif, jadwal, atau cooldown belajar berubah", category="rejected"
            )
        state = await self.api.snapshot()
        if state.phase == "sleeping":
            raise HttpCoreError("Karakter sedang tidur", category="sleeping")
        if (
            state.phase != "idle"
            or state.wallet != Decimal(expected_wallet)
            or (
                price > Decimal(0) and state.wallet - price < max(Decimal(20), Decimal(min_balance))
            )
        ):
            raise HttpCoreError("Fase atau saldo berubah sebelum belajar", category="rejected")
        if not auto_flags(self.api.directory)[mode]:
            raise HttpCoreError("Auto belajar dinonaktifkan", category="auto_disabled")
        result = await self.api.request(
            f"/api/facilities/{facility['id']}/use", {"requestId": request_id, "track": track}
        )
        if (
            not isinstance(result, dict)
            or result.get("requestId") != request_id
            or result.get("projectId") != facility["id"]
            or type(result.get("priceMilli")) is not int
            or result.get("priceMilli") != service["priceMilli"]
            or not isinstance(result.get("id"), str)
        ):
            raise HttpCoreError(
                "Receipt belajar belum cocok; transaksi tidak diulang", category="uncertain"
            )
        return result

    async def study_quiz(self, mode, visit_id, track):
        visit_id = str(UUID(visit_id))
        status = await self.study_status(mode)
        quiz = status["quiz"]
        if (
            quiz.get("available") is not True
            or quiz.get("visitId") != visit_id
            or quiz.get("track", {}).get("id") != track
        ):
            raise HttpCoreError("Kunjungan/kuis belajar berubah", category="rejected")
        try:
            answers = quiz_answers(quiz, await self.quiz_bank())
        except (KeyError, TypeError, ValueError) as exc:
            raise HttpCoreError(
                "Soal belum cocok dengan bacaan client; jawaban tidak ditebak", category="rejected"
            ) from exc
        state = await self.api.snapshot()
        if state.phase == "sleeping":
            raise HttpCoreError("Karakter sedang tidur", category="sleeping")
        if state.phase != "idle" or not auto_flags(self.api.directory)[mode]:
            raise HttpCoreError(
                "Auto belajar nonaktif atau akun tidak idle", category="auto_disabled"
            )
        result = await self.api.request(
            f"/api/facilities/{status['facility']['id']}/kuis",
            {"visitId": visit_id, "answers": answers},
        )
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("track"), dict)
            or result.get("track", {}).get("id") != track
            or type(result.get("benar")) is not int
            or type(result.get("total")) is not int
            or result.get("total") != len(answers)
            or not 0 <= result["benar"] <= len(answers)
            or type(result.get("bonus")) is not int
            or not 0 <= result["bonus"] <= 1
        ):
            raise HttpCoreError(
                "Hasil kuis belum terverifikasi; submit tidak diulang", category="uncertain"
            )
        return result

    async def bpjs_status(self):
        return await self.api.request("/api/bpjs")

    async def ensure_bpjs(self):
        if not getattr(self.api, "home", None):
            await self.api.snapshot()
        try:
            status = await self.bpjs_status()
        except HttpCoreError:
            return {}
        kartu = status.get("kartu")
        rules = status.get("rules", {})
        wallet_milli = status.get("walletMilli", 0)
        iuran_milli = rules.get("iuranMilli", 5000)
        village = (self.api.home or {}).get("desa")
        kantor_id = BPJS_KANTOR_BY_VILLAGE.get(village)
        if (
            (not kartu or not kartu.get("aktif") or kartu.get("sisaHari", 0) <= 0)
            and kantor_id
            and wallet_milli >= iuran_milli
        ):
            await self.api.request(
                "/api/bpjs/bayar",
                {"projectId": kantor_id, "requestId": str(uuid4())},
            )
            status = await self.bpjs_status()
        return status

    async def complete_facility_kegiatan(self, facility_id):
        try:
            kegiatan = await self.api.request(f"/api/facilities/{facility_id}/kegiatan")
        except HttpCoreError:
            return None
        if not isinstance(kegiatan, dict) or not kegiatan.get("available"):
            return None
        visit_id = kegiatan.get("visitId")
        kind = kegiatan.get("kind")
        plan = kegiatan.get("plan") or {}
        if kind == "tensi":
            periods = plan.get("periods") or []
            stops = [round(p * 0.25) for p in periods]
            return await self.api.request(
                f"/api/facilities/{facility_id}/kegiatan",
                {"visitId": visit_id, "stops": stops},
            )
        if kind == "detak":
            beats = plan.get("beats") or []
            taps = [int(b) for b in beats]
            return await self.api.request(
                f"/api/facilities/{facility_id}/kegiatan",
                {"visitId": visit_id, "taps": taps},
            )
        if kind == "nampan":
            items = plan.get("items") or []
            picks = solve_nampan_picks(items)
            return await self.api.request(
                f"/api/facilities/{facility_id}/kegiatan",
                {"visitId": visit_id, "picks": picks},
            )
        if kind == "foto":
            periods = plan.get("periods") or []
            shots = solve_foto_shots(periods)
            return await self.api.request(
                f"/api/facilities/{facility_id}/kegiatan",
                {"visitId": visit_id, "shots": shots},
            )
        return None

    async def garden_status(self):
        result = await self.api.request("/api/daily/garden")
        if not isinstance(result, dict) or "gardens" not in result:
            raise HttpCoreError("Format status kebun & kolam tidak valid", recoverable=True)
        return result

    async def garden_action(self, garden_id: str, action: str):
        if action not in {"panen", "rawat", "tanam"}:
            raise ValueError(f"Aksi kebun tidak valid: {action}")
        return await self.api.request(f"/api/daily/garden/{garden_id}", payload={"action": action})
