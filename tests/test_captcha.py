"""Solver captcha polyline: cocokkan bentuk, jangan kirim kode salah."""

import tempfile

import pytest

from ojol.svg_captcha_solver import (
    _SEED,
    SvgCaptchaSolverError,
    learn_polyline,
    load_bank,
    solve_polyline_captcha,
)


def _svg(digits, offset=0):
    rows = []
    for index, digit in enumerate(digits):
        for stroke in _SEED[digit][0]:
            points = [(x * 20 + index * 60 + offset, y * 20 + 5) for x, y in stroke]
            rows.append('<polyline points="' + " ".join(f"{x},{y}" for x, y in points) + '"/>')
    return "<svg>" + "".join(rows) + "</svg>"


def test_seed_shapes_solve_and_reversed_strokes_still_match():
    assert solve_polyline_captcha(_svg("57")) == "57"
    assert solve_polyline_captcha(_svg("82")) == "82"


def test_unknown_glyph_raises_instead_of_guessing():
    svg = '<svg><polyline points="0,0 3,3 6,0 9,9 12,3 15,15"/></svg>'
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
