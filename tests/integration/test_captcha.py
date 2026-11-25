"""Solver captcha polyline: cocokkan bentuk, jangan kirim kode salah."""

import tempfile

import pytest
from defusedxml.common import DTDForbidden

from app.modules.captcha import (
    _SEED,
    SvgCaptchaSolverError,
    delete_template_from_bank,
    get_bank_templates,
    get_pending_reviews,
    learn_polyline,
    load_bank,
    resolve_review,
    save_template_to_bank,
    solve_polyline_captcha,
)


def _svg(digits, offset=0):
    rows = []
    for index, digit in enumerate(digits):
        for stroke in _SEED[digit][0]:
            points = [(x * 20 + index * 60 + offset, y * 20 + 5) for x, y in stroke]
            rows.append('<polyline points="' + " ".join(f"{x},{y}" for x, y in points) + '"/>')
    return "<svg>" + "".join(rows) + "</svg>"


def test_svg_parser_rejects_doctype():
    from app.modules.captcha import solve_svg_captcha

    with pytest.raises(DTDForbidden):
        solve_svg_captcha('<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg"/>')


def test_seed_shapes_solve_and_reversed_strokes_still_match():
    assert solve_polyline_captcha(_svg("57")) == "57"
    assert solve_polyline_captcha(_svg("82")) == "82"


def test_unknown_glyph_raises_instead_of_guessing():
    svg = '<svg><polyline points="10,10 25,45 40,10"/></svg>'  # bentuk "V"
    with pytest.raises(SvgCaptchaSolverError):
        solve_polyline_captcha(svg)


def test_narrow_single_stroke_is_digit_one():
    assert solve_polyline_captcha('<svg><polyline points="10,0 10,40"/></svg>') == "1"


def test_confirmed_codes_are_learned_without_duplicates():
    with tempfile.TemporaryDirectory() as tmp:
        svg = _svg("20", offset=7)
        learn_polyline(tmp, svg, "20")
        first = {digit: len(rows) for digit, rows in load_bank(tmp).items()}
        learn_polyline(tmp, svg, "20")
        assert {digit: len(rows) for digit, rows in load_bank(tmp).items()} == first
        assert solve_polyline_captcha(svg, tmp) == "20"


def test_digit_six_seed_matches():
    assert solve_polyline_captcha(_svg("67")) == "67"


def test_unknown_glyph_records_to_cek_reviews():

    with tempfile.TemporaryDirectory() as tmp:
        svg = '<svg><polyline points="0,0 5,10 10,0 15,10 20,0"/></svg>'
        with pytest.raises(SvgCaptchaSolverError):
            solve_polyline_captcha(svg, tmp, trip_id="trip-test-123")
        pending = get_pending_reviews(tmp)
        assert len(pending) == 1
        assert pending[0]["trip_id"] == "trip-test-123"
        assert len(pending[0]["glyph"]) == 1


def test_get_pending_reviews_discovers_error_files():
    import json
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        err_dir = Path(tmp) / "errors"
        err_dir.mkdir(parents=True)
        sample_error = {
            "error_id": "OJL-DF67EFD4AB5D",
            "category": "SvgCaptchaSolverError",
            "message": "Gagal memecahkan gambar cek: Glyph cek belum dikenali: [[[0.0, 0.0], [0.5, 1.0], [1.0, 0.0]]]",
            "time": "2026-11-24T08:00:00Z",
        }
        (err_dir / "OJL-DF67EFD4AB5D.json").write_text(json.dumps(sample_error))

        pending = get_pending_reviews(tmp)
        assert len(pending) == 1
        assert pending[0]["error_id"] == "OJL-DF67EFD4AB5D"
        assert pending[0]["glyph"] == [[[0.0, 0.0], [0.5, 1.0], [1.0, 0.0]]]

        # Test resolving error
        resolve_review(
            tmp, "OJL-DF67EFD4AB5D", digit="4", glyph=[[[0.0, 0.0], [0.5, 1.0], [1.0, 0.0]]]
        )
        # After resolve, it should no longer be pending
        assert len(get_pending_reviews(tmp)) == 0
        # Bank should have digit 4
        bank = get_bank_templates(tmp)
        assert "4" in bank
        assert len(bank["4"]) >= 1


def test_save_and_delete_bank_template():
    with tempfile.TemporaryDirectory() as tmp:
        new_glyph = [[[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]]
        save_template_to_bank(tmp, "4", new_glyph)
        bank = get_bank_templates(tmp)
        assert len(bank.get("4", [])) >= 1

        idx = len(bank["4"]) - 1
        delete_template_from_bank(tmp, "4", idx)
        bank2 = get_bank_templates(tmp)
        assert len(bank2.get("4", [])) == idx


def test_matching_sample_svg_attached_to_review():
    import json
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        # Create a sample SVG in cek-samples
        samples_dir = Path(tmp) / "cek-samples"
        samples_dir.mkdir(parents=True)
        raw_svg = '<svg xmlns="http://www.w3.org/2000/svg"><polyline points="10,0 10,40"/><polyline points="50,0 55,10 60,0"/></svg>'
        (samples_dir / "trip-sample-99.svg").write_text(raw_svg)

        # Create an error with unknown glyph from that trip
        err_dir = Path(tmp) / "errors"
        err_dir.mkdir(parents=True)
        from app.modules.captcha import _glyphs, _normalize

        second_glyph = _normalize(_glyphs(raw_svg)[1])

        sample_error = {
            "error_id": "OJL-AABBCCDDEEFF",
            "category": "SvgCaptchaSolverError",
            "message": f"Gagal memecahkan gambar cek: Glyph cek belum dikenali: {json.dumps(second_glyph)}",
            "time": "2026-11-24T08:00:00Z",
        }
        (err_dir / "OJL-AABBCCDDEEFF.json").write_text(json.dumps(sample_error))

        pending = get_pending_reviews(tmp)
        assert len(pending) == 1
        assert pending[0]["error_id"] == "OJL-AABBCCDDEEFF"
        # Must attach matching raw_svg from cek-samples
        assert pending[0]["svg_text"] == raw_svg


def test_reversed_stroke_digit_matches():
    # Test digit 7 drawn in reverse direction (bottom-to-top)
    pts_forward = _SEED["7"][0][0]
    pts_reversed = pts_forward[::-1]
    reversed_svg = (
        '<svg><polyline points="'
        + " ".join(f"{x * 20},{y * 20}" for x, y in pts_reversed)
        + '"/></svg>'
    )
    # Must successfully solve as 7 despite reversed drawing direction
    assert solve_polyline_captcha(reversed_svg) == "7"


def test_no_duplicate_review_when_both_cek_review_and_error_file_exist():
    import json
    from pathlib import Path

    from app.modules.captcha import _normalize, record_unknown_glyph

    with tempfile.TemporaryDirectory() as tmp:
        sample_glyph = [[(10, 0), (20, 20), (30, 0)]]
        norm = _normalize(sample_glyph)
        # 1. Bot creates cek-reviews
        rev_id = record_unknown_glyph(tmp, sample_glyph, norm, trip_id="trip-12345")
        assert rev_id is not None

        # 2. Worker error logger creates error file
        err_dir = Path(tmp) / "errors"
        err_dir.mkdir(parents=True)
        err_data = {
            "error_id": "OJL-112233445566",
            "category": "SvgCaptchaSolverError",
            "message": f"Gagal memecahkan gambar cek: Glyph cek belum dikenali: {json.dumps(norm)}",
            "time": "2026-11-24T08:05:00Z",
            "trip_id": "trip-12345",
        }
        (err_dir / "OJL-112233445566.json").write_text(json.dumps(err_data))

        # 3. get_pending_reviews must deduplicate so user sees only 1 review card, not 2
        pending = get_pending_reviews(tmp)
        assert len(pending) == 1
        assert pending[0]["id"] == rev_id
        assert pending[0]["error_id"] == "OJL-112233445566"

        # 4. Resolving that single review must clear both IDs
        resolve_review(tmp, rev_id, digit="3", glyph=sample_glyph)
        assert len(get_pending_reviews(tmp)) == 0


def test_solve_records_all_unknown_glyphs_in_two_digit_captcha():
    from app.modules.captcha import get_pending_reviews

    with tempfile.TemporaryDirectory() as tmp:
        # SVG with 2 unknown glyphs (spaced > 14px apart)
        svg = '<svg><polyline points="0,0 5,10 10,0"/><polyline points="50,0 55,10 60,0"/></svg>'
        with pytest.raises(SvgCaptchaSolverError):
            solve_polyline_captcha(svg, directory=tmp, trip_id="trip-multi")

        # Both unknown glyphs must be recorded
        pending = get_pending_reviews(tmp)
        assert len(pending) == 2
        assert all(p["trip_id"] == "trip-multi" for p in pending)


def test_contributor_info_persists_and_not_dropped():
    with tempfile.TemporaryDirectory() as tmp:
        glyph_a = [[[10.0, 0.0], [10.0, 40.0], [30.0, 40.0]]]
        save_template_to_bank(tmp, "4", glyph_a, contributed_by="yakis")
        bank = get_bank_templates(tmp)
        assert "4" in bank
        assert any(isinstance(v, dict) and v.get("by") == "yakis" for v in bank["4"])

        # Identical glyph should update contributor
        save_template_to_bank(tmp, "4", glyph_a, contributed_by="zeta")
        bank2 = get_bank_templates(tmp)
        matching = [v for v in bank2["4"] if isinstance(v, dict) and v.get("by") == "zeta"]
        assert len(matching) == 1


def test_resolve_review_resolves_duplicate_reviews_for_same_trip():
    import json
    from pathlib import Path

    from app.modules.captcha import _normalize, record_unknown_glyph

    with tempfile.TemporaryDirectory() as tmp:
        g1 = [[(0.0, 0.0), (10.0, 20.0), (20.0, 0.0)]]
        norm = _normalize(g1)
        r1 = record_unknown_glyph(tmp, g1, norm, trip_id="trip-dup-99")
        # Polling retry creates another review file for the same trip with slightly different ID if forced
        rev_dir = Path(tmp) / "cek-reviews"
        r2_file = rev_dir / "REV-FORCE2.json"
        r2_file.write_text(
            json.dumps(
                {
                    "id": "REV-FORCE2",
                    "time": "2026-11-24T08:10:00Z",
                    "trip_id": "trip-dup-99",
                    "raw_glyph": g1,
                    "normalized_glyph": norm,
                    "status": "pending",
                }
            )
        )

        # Resolving one review must resolve all reviews for trip-dup-99
        resolve_review(tmp, r1, digit="4", glyph=g1, resolved_by="yakis")
        pending = get_pending_reviews(tmp)
        assert len(pending) == 0


def test_bank_recognition_auto_clears_pending_reviews():
    import json
    from pathlib import Path

    from app.modules.captcha import _normalize

    with tempfile.TemporaryDirectory() as tmp:
        g = [[(15.0, 0.0), (15.0, 40.0), (35.0, 40.0)]]
        norm = _normalize(g)
        rev_dir = Path(tmp) / "cek-reviews"
        rev_dir.mkdir(parents=True)
        (rev_dir / "REV-AUTO1.json").write_text(
            json.dumps(
                {
                    "id": "REV-AUTO1",
                    "time": "2026-11-24T08:15:00Z",
                    "trip_id": "trip-auto-1",
                    "raw_glyph": g,
                    "normalized_glyph": norm,
                    "status": "pending",
                }
            )
        )

        # Before learning, it shows in pending
        assert len(get_pending_reviews(tmp)) == 1

        # Now bank learns this glyph
        save_template_to_bank(tmp, "4", g, contributed_by="yakis")

        # After learning, get_pending_reviews must automatically filter it out
        assert len(get_pending_reviews(tmp)) == 0


def test_digit_four_from_live_human_check_samples():
    """Dua sampel live cek manusia kantor (25 Nov 2026) berangka 44."""
    svg = (
        '<svg><polyline points="34.2,41.2 32.1,5.8 17.4,30.6 38.6,32.3"/>'
        '<polyline points="90.5,42.5 87.7,11.7 73.2,33.2 93.3,32.9"/></svg>'
    )
    assert solve_polyline_captcha(svg) == "44"


@pytest.mark.parametrize(
    ("points", "kode"),
    [
        # sampel 4 resolusi lain (68x68, garis 4px) - tetap harus terbaca
        (
            "44.8,56.0 45.2,49.8 45.7,43.6 46.1,37.4 46.6,31.2 47.0,25.1 47.4,18.9 "
            "47.9,12.7 45.5,12.0 40.7,16.0 35.9,20.0 31.1,24.0 26.3,28.0 21.6,32.0 "
            "16.8,36.0 12.0,40.1 12.2,42.1 18.5,41.7 24.7,41.4 31.0,41.0 37.2,40.7 "
            "43.5,40.3 49.7,39.9 56.0,39.6",
            "4",
        ),
        ("38,12 26,24 34,24 34,52", "1"),
        ("12,10 55,10 25,55", "7"),
        ("50,30 22,30 22,14 50,13 47,32 10,55", "9"),
    ],
)
def test_four_and_one_are_not_confused(points, kode):
    assert solve_polyline_captcha(f'<svg><polyline points="{points}"/></svg>') == kode
