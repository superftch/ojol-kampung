"""Crowdsourced captcha template bank, glyph review queue, and polyline solver."""

import contextlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.models import ROOT
from app.modules.captcha.matcher import (
    _SEED,
    _SWITCH,
    SvgCaptchaSolverError,
    _extract_glyph,
    _glyphs,
    _normalize,
    _shape_distance,
)


def _bank_path(directory: str | Path) -> Path:
    return Path(directory) / "cek-templates.json"


def _normalize_dirs(directory) -> list:
    return [directory] if isinstance(directory, (str, Path)) else list(directory or [])


def load_bank(directory=None) -> dict:
    """Load and merge seed, repository, and per-directory captcha glyph template banks."""
    seeds = {
        digit: [[[list(p) for p in stroke] for stroke in variant] for variant in variants]
        for digit, variants in _SEED.items()
    }
    repo_bank = ROOT / "assets" / "cek-templates.json"
    stored: dict = {}

    def merge_templates(target: dict, source) -> None:
        if not isinstance(source, dict):
            return
        for digit, variants in source.items():
            if not isinstance(variants, list):
                continue
            target.setdefault(digit, [])
            for v in variants:
                g = _extract_glyph(v)
                if not g:
                    continue
                try:
                    norm_v = _normalize(g)
                except (ValueError, TypeError, ZeroDivisionError):
                    continue
                found_idx = None
                for idx, existing in enumerate(target[digit]):
                    try:
                        if _shape_distance(norm_v, _normalize(_extract_glyph(existing))) < 0.02:
                            found_idx = idx
                            break
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass
                if found_idx is None:
                    target[digit].append(v)
                elif (
                    isinstance(v, dict)
                    and v.get("by")
                    and (
                        not isinstance(target[digit][found_idx], dict)
                        or not target[digit][found_idx].get("by")
                    )
                ):
                    target[digit][found_idx] = v

    if repo_bank.is_file():
        with contextlib.suppress(OSError, ValueError):
            merge_templates(stored, json.loads(repo_bank.read_text()))

    for d in _normalize_dirs(directory):
        if d:
            bp = _bank_path(d)
            if bp.is_file():
                with contextlib.suppress(OSError, ValueError):
                    merge_templates(stored, json.loads(bp.read_text()))

    for digit, variants in seeds.items():
        if not stored.get(digit):
            stored[digit] = [
                [[list(p) for p in stroke] for stroke in variant] for variant in variants
            ]
    return stored


def save_bank(directory, bank: dict) -> None:
    """Persist template bank to target directories and repository assets outside testing."""
    for d in _normalize_dirs(directory):
        try:
            if d:
                path = Path(d) / "cek-templates.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(bank))
        except OSError:
            pass
    if os.environ.get("OJOL_ENV") != "testing":
        try:
            repo_bank = ROOT / "assets" / "cek-templates.json"
            repo_bank.parent.mkdir(parents=True, exist_ok=True)
            repo_bank.write_text(json.dumps(bank))
        except OSError:
            pass


def get_bank_templates(directory=None) -> dict:
    return load_bank(directory)


def save_template_to_bank(directory, digit: str, glyph: list, contributed_by: str | None = None):
    """Save a new glyph variant into the digit bank across one or more directories."""
    digit = str(digit).strip()
    if len(digit) != 1 or not digit.isdigit():
        raise ValueError("Digit harus berupa karakter angka 0-9")
    if not isinstance(glyph, list) or not glyph:
        raise ValueError("Data glyph tidak valid")

    dirs = _normalize_dirs(directory)
    primary_dir = dirs[0] if dirs else None
    bank = load_bank(primary_dir)
    cleaned_glyph = [[list(p) for p in stroke] for stroke in glyph if isinstance(stroke, list)]
    if not cleaned_glyph:
        raise ValueError("Data stroke glyph kosong")

    norm_new = _normalize(cleaned_glyph)
    shapes = bank.get(digit, [])
    exact_idx = None
    for idx, shape in enumerate(shapes):
        dist = _shape_distance(
            norm_new, _normalize([[tuple(p) for p in s] for s in _extract_glyph(shape)])
        )
        if dist < 0.02:
            exact_idx = idx
            break

    entry = (
        {
            "glyph": cleaned_glyph,
            "by": str(contributed_by).strip() if contributed_by else None,
            "at": datetime.now(UTC).isoformat(),
        }
        if contributed_by
        else cleaned_glyph
    )

    if exact_idx is not None:
        shapes[exact_idx] = entry
    else:
        shapes.append(entry)

    bank[digit] = shapes
    save_bank(dirs, bank)
    return bank


def delete_template_from_bank(directory, digit: str, index: int):
    """Delete a variant from the specified digit template bank."""
    digit = str(digit).strip()
    dirs = _normalize_dirs(directory)
    primary_dir = dirs[0] if dirs else None
    bank = load_bank(primary_dir)
    if digit in bank and 0 <= index < len(bank[digit]):
        bank[digit].pop(index)
        save_bank(dirs, bank)
    return bank


def record_unknown_glyph(directory, glyph, normalized, trip_id=None, svg_text=None, force=False):
    """Store an unrecognized glyph into the review queue without creating duplicates.

    force=True tetap mengantre walau bank sudah "mengenali" bentuk itu: salah baca
    tidak pernah melempar error, jadi tanpa force glyph-nya tak pernah tampil di Bank Angka.
    """
    if not directory:
        return None
    try:
        rev_dir = Path(directory) / "cek-reviews"
        rev_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        cur_min_x = None
        if glyph:
            with contextlib.suppress(TypeError, ValueError):
                cur_min_x = min(x for stroke in glyph for x, _ in stroke)

        if rev_dir.is_dir():
            for existing_file in rev_dir.glob("*.json"):
                try:
                    ex_data = json.loads(existing_file.read_text())
                    if ex_data.get("status") != "pending":
                        continue
                    if trip_id and ex_data.get("trip_id") == trip_id:
                        ex_raw = ex_data.get("raw_glyph")
                        ex_min_x = None
                        if ex_raw:
                            with contextlib.suppress(TypeError, ValueError):
                                ex_min_x = min(x for stroke in ex_raw for x, _ in stroke)
                        ex_g = ex_data.get("normalized_glyph") or ex_raw
                        if cur_min_x is not None and ex_min_x is not None:
                            # posisi x saja tidak cukup: glyph path selalu mulai di 0
                            same_shape = (
                                not ex_g or _shape_distance(normalized, _normalize(ex_g)) < 0.05
                            )
                            if abs(cur_min_x - ex_min_x) < 5 and same_shape:
                                touched = force and not ex_data.get("force")
                                if touched:
                                    ex_data["force"] = True
                                if svg_text and not ex_data.get("svg_text"):
                                    ex_data["svg_text"] = svg_text
                                    touched = True
                                if touched:
                                    existing_file.write_text(json.dumps(ex_data, indent=2))
                                return ex_data.get("id") or existing_file.stem
                        else:
                            ex_g = ex_data.get("normalized_glyph") or ex_raw
                            if ex_g and _shape_distance(normalized, _normalize(ex_g)) < 0.05:
                                return ex_data.get("id") or existing_file.stem
                    elif not trip_id:
                        ex_g = ex_data.get("normalized_glyph") or ex_data.get("raw_glyph")
                        if ex_g and _shape_distance(normalized, _normalize(ex_g)) < 0.05:
                            return ex_data.get("id") or existing_file.stem
                except (OSError, ValueError, TypeError):
                    pass

        rev_id = f"REV-{uuid4().hex[:10].upper()}"
        data = {
            "id": rev_id,
            "time": datetime.now(UTC).isoformat(),
            "trip_id": trip_id,
            "raw_glyph": [[list(p) for p in stroke] for stroke in glyph],
            "normalized_glyph": normalized,
            "status": "pending",
        }
        if svg_text:
            data["svg_text"] = svg_text
        if force:
            data["force"] = True
        (rev_dir / f"{rev_id}.json").write_text(json.dumps(data, indent=2))
        return rev_id
    except OSError:
        return None


def _path_glyphs(svg_text):
    """Glyph kasar dari cek berbasis <path> (model svg-captcha) lewat tabel pola digit."""
    import base64

    from app.modules.captcha.matcher import SvgCaptchaSolver

    model = json.loads(base64.b64decode(SvgCaptchaSolver.model))
    glyphs = []
    for shape in re.findall(r'<path[^>]*\bd="([^"]+)"', svg_text):
        digit = model.get(re.sub(r"[\d.\s]*", "", shape))
        if digit and digit in _SEED:
            glyphs.append([[list(point) for point in stroke] for stroke in _SEED[digit][0]])
    return glyphs


def record_captcha_review(directory, svg_text, trip_id=None):
    """Antrekan semua glyph dari satu gambar cek yang gagal dipecahkan ke Bank Angka."""
    if not directory or not isinstance(svg_text, str) or "<svg" not in svg_text:
        return []
    try:
        glyphs = _glyphs(svg_text) if "<polyline" in svg_text else _path_glyphs(svg_text)
    except (SvgCaptchaSolverError, ValueError, TypeError):
        return []
    ids = []
    for glyph in glyphs:
        try:
            normalized = _normalize(glyph)
        except (ValueError, TypeError, ZeroDivisionError):
            continue
        rid = record_unknown_glyph(
            directory, glyph, normalized, trip_id=trip_id, svg_text=svg_text, force=True
        )
        if rid:
            ids.append(rid)
    return ids


def _is_closed_glyph(norm_g) -> bool:
    if not norm_g:
        return True
    return (
        ((norm_g[0][0][0] - norm_g[0][-1][0]) ** 2 + (norm_g[0][0][1] - norm_g[0][-1][1]) ** 2)
        ** 0.5
    ) < 0.15


def get_pending_reviews(directory, account_name: str | None = None) -> list[dict]:
    """Collect all pending unrecognized captcha glyphs for a single account directory."""
    if not directory:
        return []
    path = Path(directory)
    resolved_file = path / "cek-reviews-resolved.json"
    resolved_ids: set[str] = set()
    if resolved_file.is_file():
        try:
            resolved_ids = set(json.loads(resolved_file.read_text()))
        except (ValueError, OSError):
            resolved_ids = set()

    bank = load_bank(directory)
    reviews: list[dict] = []
    seen_ids: set[str] = set()

    samples_dir = path / "cek-samples"
    samples_cache: list[tuple[str, str]] = []
    if samples_dir.is_dir():
        for s_file in sorted(
            samples_dir.glob("*.svg"), key=lambda f: f.stat().st_mtime, reverse=True
        ):
            try:
                content = s_file.read_text().strip()
                if content.startswith("<svg"):
                    samples_cache.append((s_file.stem, content))
            except OSError:
                pass

    def find_matching_svg(target_glyph, trip_id=None):
        if trip_id:
            for stem, content in samples_cache:
                if stem == trip_id:
                    return content
        try:
            norm_target = _normalize(target_glyph)
            for _, sample_svg in samples_cache:
                for s_glyph in _glyphs(sample_svg):
                    if _shape_distance(norm_target, _normalize(s_glyph)) < 0.08:
                        return sample_svg
        except (SvgCaptchaSolverError, ValueError, TypeError):
            pass
        return None

    def is_already_recognized_by_bank(glyph) -> bool:
        try:
            norm_g = _normalize(glyph)
            closed = _is_closed_glyph(norm_g)
            for digit, variants in bank.items():
                if digit == "0" and not closed:
                    continue
                for shape in variants:
                    raw_shape = _extract_glyph(shape)
                    cost = _shape_distance(
                        norm_g, _normalize([[tuple(p) for p in s] for s in raw_shape])
                    )
                    if cost < _SWITCH:
                        return True
        except (ValueError, TypeError, ZeroDivisionError):
            pass
        return False

    rev_dir = path / "cek-reviews"
    if rev_dir.is_dir():
        for file in sorted(rev_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            if file.stem in resolved_ids:
                continue
            try:
                data = json.loads(file.read_text())
                rid = data.get("id") or file.stem
                if (
                    rid in resolved_ids
                    or file.stem in resolved_ids
                    or (data.get("trip_id") and data.get("trip_id") in resolved_ids)
                    or data.get("status") != "pending"
                ):
                    continue
                glyph = data.get("normalized_glyph") or data.get("raw_glyph")
                if glyph and rid not in seen_ids:
                    if not data.get("force") and is_already_recognized_by_bank(glyph):
                        resolved_ids.add(file.stem)
                        resolved_ids.add(rid)
                        continue
                    svg_text = data.get("svg_text") or find_matching_svg(glyph, data.get("trip_id"))
                    reviews.append(
                        {
                            "id": rid,
                            "error_id": data.get("error_id"),
                            "trip_id": data.get("trip_id"),
                            "time": data.get("time"),
                            "glyph": glyph,
                            "svg_text": svg_text,
                            "account_name": account_name or data.get("account_name"),
                        }
                    )
                    seen_ids.add(rid)
            except (ValueError, OSError):
                continue

    err_dir = path / "errors"
    if err_dir.is_dir():
        for file in sorted(
            err_dir.glob("OJL-*.json"), key=lambda f: f.stat().st_mtime, reverse=True
        ):
            err_id = file.stem
            rev_err_id = f"rev-err-{err_id}"
            if (
                err_id in resolved_ids
                or rev_err_id in resolved_ids
                or err_id in seen_ids
                or rev_err_id in seen_ids
            ):
                continue
            try:
                data = json.loads(file.read_text())
                if data.get("trip_id") and data.get("trip_id") in resolved_ids:
                    continue
                msg = str(data.get("message") or "")
                if (
                    "Glyph cek belum dikenali" in msg
                    or data.get("category") == "SvgCaptchaSolverError"
                ):
                    match = re.search(r"Glyph cek belum dikenali:\s*(\[\[\[.*?\]\]\])", msg)
                    if match:
                        glyph = json.loads(match.group(1))
                        if is_already_recognized_by_bank(glyph):
                            resolved_ids.add(err_id)
                            resolved_ids.add(rev_err_id)
                            continue
                        norm_g = _normalize(glyph)
                        existing_rev = None
                        for rev in reviews:
                            if data.get("trip_id") and rev.get("trip_id") == data.get("trip_id"):
                                existing_rev = rev
                                break
                            if _shape_distance(norm_g, _normalize(rev.get("glyph", []))) < 0.05:
                                existing_rev = rev
                                break
                        if existing_rev:
                            if not existing_rev.get("error_id"):
                                existing_rev["error_id"] = err_id
                            seen_ids.add(err_id)
                            seen_ids.add(rev_err_id)
                            continue

                        svg_text = find_matching_svg(glyph, data.get("trip_id"))
                        reviews.append(
                            {
                                "id": rev_err_id,
                                "error_id": err_id,
                                "trip_id": data.get("trip_id"),
                                "time": data.get("time"),
                                "glyph": glyph,
                                "svg_text": svg_text,
                                "account_name": account_name or data.get("account_name"),
                            }
                        )
                        seen_ids.add(err_id)
                        seen_ids.add(rev_err_id)
            except (OSError, ValueError, TypeError):
                continue

    return reviews


def get_all_pending_reviews(directories, account_names=None) -> list[dict]:
    """Collect and deduplicate pending captcha reviews across all fleet account directories."""
    account_names = account_names or {}
    all_reviews: list[dict] = []
    seen_ids: set[str] = set()

    for d in _normalize_dirs(directories):
        if not d:
            continue
        p = Path(d)
        acc_name = (
            account_names.get(str(p)) or account_names.get(p.name) or account_names.get(p.stem)
        )
        for review in get_pending_reviews(p, account_name=acc_name):
            rid = review.get("id") or review.get("error_id")
            if not rid or rid in seen_ids:
                continue
            norm_r = _normalize(review.get("glyph", []))
            existing_cross = None
            for ex in all_reviews:
                if (
                    ex.get("trip_id")
                    and review.get("trip_id")
                    and ex.get("trip_id") == review.get("trip_id")
                ):
                    existing_cross = ex
                    break
                if _shape_distance(norm_r, _normalize(ex.get("glyph", []))) < 0.04:
                    existing_cross = ex
                    break
            if existing_cross:
                if review.get("account_name") and review["account_name"] not in (
                    existing_cross.get("account_name") or ""
                ):
                    existing_cross["account_name"] = (
                        f"{existing_cross.get('account_name', '')}, {review['account_name']}"
                    ).strip(", ")
                seen_ids.add(rid)
                continue

            seen_ids.add(rid)
            all_reviews.append(review)

    all_reviews.sort(key=lambda x: str(x.get("time") or ""), reverse=True)
    return all_reviews


def resolve_review(
    directory,
    review_id: str,
    digit: str | None = None,
    glyph: list | None = None,
    resolved_by: str | None = None,
) -> None:
    """Mark a captcha review resolved and optionally save its glyph to the template bank."""
    if not directory:
        return
    dirs = _normalize_dirs(directory)
    if digit and glyph:
        save_template_to_bank(dirs, digit, glyph, contributed_by=resolved_by)

    for d in dirs:
        if not d:
            continue
        path = Path(d)
        resolved_file = path / "cek-reviews-resolved.json"
        resolved_ids: set[str] = set()
        if resolved_file.is_file():
            try:
                resolved_ids = set(json.loads(resolved_file.read_text()))
            except (ValueError, OSError):
                resolved_ids = set()

        if review_id:
            resolved_ids.add(review_id)
            if "OJL-" in review_id:
                match = re.search(r"OJL-[0-9A-F]{12}", review_id)
                if match:
                    resolved_ids.add(match.group(0))
                    resolved_ids.add(f"rev-err-{match.group(0)}")

        rev_dir = path / "cek-reviews"
        target_trip_id = None
        if rev_dir.is_dir():
            for rf in rev_dir.glob("*.json"):
                try:
                    data = json.loads(rf.read_text())
                    rid = data.get("id") or rf.stem
                    is_match = False
                    if rf.stem == review_id or rid == review_id:
                        is_match = True
                        if data.get("trip_id"):
                            target_trip_id = data.get("trip_id")
                    elif glyph:
                        g = data.get("normalized_glyph") or data.get("raw_glyph")
                        if g and _shape_distance(_normalize(glyph), _normalize(g)) < 0.10:
                            is_match = True
                            if data.get("trip_id"):
                                target_trip_id = data.get("trip_id")
                    if is_match:
                        resolved_ids.add(rf.stem)
                        resolved_ids.add(rid)
                        data["status"] = "resolved"
                        data["resolved_digit"] = digit
                        if resolved_by:
                            data["resolved_by"] = resolved_by
                        rf.write_text(json.dumps(data, indent=2))
                except (OSError, ValueError, TypeError):
                    pass

            if target_trip_id:
                resolved_ids.add(target_trip_id)
                for rf in rev_dir.glob("*.json"):
                    try:
                        data = json.loads(rf.read_text())
                        if data.get("trip_id") == target_trip_id:
                            resolved_ids.add(rf.stem)
                            if data.get("id"):
                                resolved_ids.add(data.get("id"))
                            data["status"] = "resolved"
                            data["resolved_digit"] = digit
                            if resolved_by:
                                data["resolved_by"] = resolved_by
                            rf.write_text(json.dumps(data, indent=2))
                    except (OSError, ValueError, TypeError):
                        pass

        err_dir = path / "errors"
        if err_dir.is_dir():
            for ef in err_dir.glob("OJL-*.json"):
                try:
                    edata = json.loads(ef.read_text())
                    eid = ef.stem
                    is_err_match = False
                    if (
                        eid == review_id
                        or f"rev-err-{eid}" == review_id
                        or (target_trip_id and edata.get("trip_id") == target_trip_id)
                    ):
                        is_err_match = True
                    elif glyph:
                        emsg = str(edata.get("message") or "")
                        ematch = re.search(r"Glyph cek belum dikenali:\s*(\[\[\[.*?\]\]\])", emsg)
                        if ematch:
                            eglyph = json.loads(ematch.group(1))
                            if _shape_distance(_normalize(glyph), _normalize(eglyph)) < 0.10:
                                is_err_match = True
                    if is_err_match:
                        resolved_ids.add(eid)
                        resolved_ids.add(f"rev-err-{eid}")
                except (OSError, ValueError, TypeError):
                    pass

        with contextlib.suppress(OSError):
            resolved_file.write_text(json.dumps(list(resolved_ids), indent=2))


def dismiss_review(directory, review_id: str, glyph: list | None = None) -> None:
    """Dismiss a captcha review without adding its glyph to the template bank."""
    resolve_review(directory, review_id, digit=None, glyph=glyph)


def learn_polyline(directory, svg_text: str, code: str, contributed_by: str | None = None) -> None:
    """Persist server-confirmed glyph shapes for each digit in the solved captcha."""
    glyphs = _glyphs(svg_text)
    if len(glyphs) != len(code):
        return
    dirs = _normalize_dirs(directory)
    primary_dir = dirs[0] if dirs else None
    bank = load_bank(primary_dir)
    changed = False
    for digit, glyph in zip(code, glyphs, strict=False):
        shapes = bank.get(digit, [])
        normalized = _normalize(glyph)
        if all(
            _shape_distance(
                normalized, _normalize([[tuple(p) for p in s] for s in _extract_glyph(shape)])
            )
            > _SWITCH * 0.9
            for shape in shapes
        ):
            cleaned = [[list(p) for p in stroke] for stroke in glyph]
            entry = (
                {
                    "glyph": cleaned,
                    "by": contributed_by,
                    "at": datetime.now(UTC).isoformat(),
                }
                if contributed_by
                else cleaned
            )
            bank.setdefault(digit, []).append(entry)
            changed = True
    if changed:
        save_bank(dirs, bank)


def solve_polyline_captcha(svg_text: str, directory=None, trip_id=None) -> str:
    """Recognize digits in a polyline SVG captcha using the template bank."""
    bank = load_bank(directory)
    result: list[str] = []
    unknowns = []
    for glyph in _glyphs(svg_text):
        normalized = _normalize(glyph)
        xs = [x for stroke in glyph for x, _ in stroke]
        ys = [y for stroke in glyph for _, y in stroke]
        best_digit, best_cost = None, _SWITCH
        closed = _is_closed_glyph(normalized)
        for digit, variants in bank.items():
            if digit == "0" and not closed:
                continue
            for shape in variants:
                raw_shape = _extract_glyph(shape)
                cost = _shape_distance(
                    normalized, _normalize([[tuple(p) for p in s] for s in raw_shape])
                )
                if cost < best_cost:
                    best_digit, best_cost = digit, cost
        if (
            best_digit is None
            and len(glyph) == 1
            and (max(xs) - min(xs)) / ((max(ys) - min(ys)) or 1.0) < 0.5
        ):
            best_digit = "1"
        if best_digit is None:
            unknowns.append((glyph, normalized))
        else:
            result.append(best_digit)

    if unknowns:
        if directory:
            for g, norm in unknowns:
                record_unknown_glyph(directory, g, norm, trip_id=trip_id, svg_text=svg_text)
        first_norm = unknowns[0][1]
        raise SvgCaptchaSolverError(
            "Glyph cek belum dikenali: " + json.dumps(first_norm, default=list)
        )
    return "".join(result)
