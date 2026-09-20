# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Wheel/tire size math: whether a tire's diameter can physically mount on a wheel, and
whether its section width sits in that wheel's recommended range.

Diameter must match exactly — a tire's bead seats on the wheel's bead seat diameter, so an
18" wheel only takes an 18" tire; nothing "close" mounts. Width is a range, not a point: a
tire is engineered around a manufacturer-specified rim width with a narrower minimum and a
wider maximum it can still be mounted on, and a "recommended"/ideal band inside that where
its contact patch and sidewall shape come out as designed. ``_RIM_WIDTH_BY_TIRE_MM`` is a
commonly published reference table for that relationship (widely cited by tire retailers,
e.g. Tire Rack's rim-width guidance); real tires vary by model, so this is a reasonable
default to flag against, not a substitute for the specific tire's own spec sheet.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import astuple, dataclass
from typing import Literal

WidthFit = Literal["ideal", "acceptable", "not_recommended"]

_TIRE_SIZE = re.compile(r"(\d{3})/(\d{2,3})R(\d{2})")


@dataclass(frozen=True)
class RimWidthRange:
    min_in: float
    ideal_low_in: float
    ideal_high_in: float
    max_in: float


# Tire section width (mm) -> (min rim, ideal-low, ideal-high, max rim), all in inches.
_RIM_WIDTH_BY_TIRE_MM: dict[int, RimWidthRange] = {
    185: RimWidthRange(5.0, 5.5, 6.5, 7.0),
    195: RimWidthRange(5.5, 6.0, 6.5, 7.5),
    205: RimWidthRange(5.5, 6.0, 7.5, 7.5),
    215: RimWidthRange(6.0, 6.5, 7.5, 8.0),
    225: RimWidthRange(6.0, 6.5, 8.0, 8.5),
    235: RimWidthRange(6.5, 7.0, 8.5, 9.0),
    245: RimWidthRange(7.0, 7.5, 9.0, 9.5),
    255: RimWidthRange(7.0, 8.0, 9.5, 10.0),
    265: RimWidthRange(7.5, 8.5, 10.0, 10.5),
    275: RimWidthRange(8.0, 9.0, 10.5, 11.0),
    285: RimWidthRange(8.5, 9.5, 11.0, 11.5),
    295: RimWidthRange(9.0, 10.0, 11.5, 12.0),
    305: RimWidthRange(9.5, 10.5, 12.0, 12.5),
    315: RimWidthRange(9.5, 10.5, 12.5, 13.0),
}
_TABULATED_WIDTHS = sorted(_RIM_WIDTH_BY_TIRE_MM)


def parse_tire_size(size: str) -> tuple[int, int, int] | None:
    """``(section_width_mm, aspect_ratio_pct, diameter_in)`` from a metric size like
    ``"225/45R17"``, or None when the string doesn't parse."""
    match = _TIRE_SIZE.search(size)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def parse_wheel_diameter_in(option_values: dict[str, str]) -> float | None:
    return _parse_inches(option_values.get("diameter"))


def parse_wheel_width_in(option_values: dict[str, str]) -> float | None:
    return _parse_inches(option_values.get("width"))


def _parse_inches(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.rstrip('"'))
    except ValueError:
        return None


def rim_width_range_for_tire(width_mm: int) -> RimWidthRange:
    """The tabulated range for ``width_mm``, or a linear interpolation between the two
    nearest tabulated widths when it falls between them (clamped at the table's ends)."""
    if width_mm in _RIM_WIDTH_BY_TIRE_MM:
        return _RIM_WIDTH_BY_TIRE_MM[width_mm]
    if width_mm <= _TABULATED_WIDTHS[0]:
        return _RIM_WIDTH_BY_TIRE_MM[_TABULATED_WIDTHS[0]]
    if width_mm >= _TABULATED_WIDTHS[-1]:
        return _RIM_WIDTH_BY_TIRE_MM[_TABULATED_WIDTHS[-1]]
    lower = max(w for w in _TABULATED_WIDTHS if w < width_mm)
    upper = min(w for w in _TABULATED_WIDTHS if w > width_mm)
    fraction = (width_mm - lower) / (upper - lower)
    low, high = astuple(_RIM_WIDTH_BY_TIRE_MM[lower]), astuple(_RIM_WIDTH_BY_TIRE_MM[upper])
    return RimWidthRange(*(a + (b - a) * fraction for a, b in zip(low, high, strict=True)))


def width_fit(wheel_width_in: float, tire_width_mm: int) -> WidthFit:
    band = rim_width_range_for_tire(tire_width_mm)
    if band.ideal_low_in <= wheel_width_in <= band.ideal_high_in:
        return "ideal"
    if band.min_in <= wheel_width_in <= band.max_in:
        return "acceptable"
    return "not_recommended"


def ideal_tire_widths_for_wheel(wheel_width_in: float) -> tuple[int, int] | None:
    """The ``(min_mm, max_mm)`` span of tabulated tire widths whose ideal band covers a
    wheel this wide, or None when no tabulated width's ideal band reaches it (a wheel
    narrower or wider than anything in the table)."""
    matches = [
        w
        for w, band in _RIM_WIDTH_BY_TIRE_MM.items()
        if band.ideal_low_in <= wheel_width_in <= band.ideal_high_in
    ]
    return (min(matches), max(matches)) if matches else None


@dataclass(frozen=True)
class FitmentVerdict:
    diameter_match: bool
    wheel_diameter_in: float
    tire_diameter_in: float
    wheel_width_in: float
    tire_width_mm: int
    width_fit: WidthFit
    ideal_tire_width_mm: tuple[int, int] | None
    summary: str


def check_fitment(
    wheel_option_values: dict[str, str], tire_option_values: dict[str, str]
) -> FitmentVerdict | None:
    """None when either record isn't a fully specified wheel or tire variant (a family
    with no ``diameter``/``width``/``size`` of its own)."""
    wheel_diameter = parse_wheel_diameter_in(wheel_option_values)
    wheel_width = parse_wheel_width_in(wheel_option_values)
    tire_size = tire_option_values.get("size")
    parsed_tire = parse_tire_size(tire_size) if tire_size else None
    if wheel_diameter is None or wheel_width is None or parsed_tire is None:
        return None
    tire_width_mm, _aspect, tire_diameter = parsed_tire

    diameter_match = wheel_diameter == tire_diameter
    if not diameter_match:
        summary = (
            f'Will not fit: the wheel is {wheel_diameter:g}" and this tire is '
            f'{tire_diameter:g}" — a tire only mounts on a wheel of its own diameter.'
        )
        return FitmentVerdict(
            diameter_match=False,
            wheel_diameter_in=wheel_diameter,
            tire_diameter_in=tire_diameter,
            wheel_width_in=wheel_width,
            tire_width_mm=tire_width_mm,
            width_fit="not_recommended",
            ideal_tire_width_mm=ideal_tire_widths_for_wheel(wheel_width),
            summary=summary,
        )

    fit = width_fit(wheel_width, tire_width_mm)
    ideal_range = ideal_tire_widths_for_wheel(wheel_width)
    if fit == "ideal":
        summary = f'Ideal width match: {tire_width_mm}mm on a {wheel_width:g}" wide wheel.'
    elif fit == "acceptable":
        summary = (
            f'Fits, but {tire_width_mm}mm is not the ideal width for a {wheel_width:g}" wide wheel'
        )
        if ideal_range:
            summary += f" (ideal is {ideal_range[0]}-{ideal_range[1]}mm)."
        else:
            summary += "."
    else:
        summary = f'Not recommended: {tire_width_mm}mm is outside the safe range for a {wheel_width:g}" wide wheel'
        if ideal_range:
            summary += f" (aim for {ideal_range[0]}-{ideal_range[1]}mm)."
        else:
            summary += "."
    return FitmentVerdict(
        diameter_match=True,
        wheel_diameter_in=wheel_diameter,
        tire_diameter_in=tire_diameter,
        wheel_width_in=wheel_width,
        tire_width_mm=tire_width_mm,
        width_fit=fit,
        ideal_tire_width_mm=ideal_range,
        summary=summary,
    )


_FIT_RANK: dict[WidthFit, int] = {"ideal": 0, "acceptable": 1, "not_recommended": 2}


@dataclass(frozen=True)
class TireCandidate:
    product_id: str
    title: str
    option_values: dict[str, str]
    in_stock: bool


@dataclass(frozen=True)
class TireRecommendation:
    """A staff pick: the best-fitting *in-stock* tire for a wheel, in the spirit of a
    fitment guide's "here's what we'd actually put on this" call rather than only a
    computed range. ``better_out_of_stock`` names a tire that would rank higher — a
    closer or truly ideal width match — when the catalog carries one, so the answer is
    "here's what we have, and here's what would be ideal if it weren't backordered"
    rather than silently recommending the best of a poor set."""

    product_id: str
    title: str
    verdict: FitmentVerdict
    better_out_of_stock: TireRecommendation | None = None


def _distance_from_ideal_center(wheel_width_in: float, tire_width_mm: int) -> float:
    band = rim_width_range_for_tire(tire_width_mm)
    center = (band.ideal_low_in + band.ideal_high_in) / 2
    return abs(wheel_width_in - center)


def recommend_tire(
    wheel_option_values: dict[str, str], candidates: Sequence[TireCandidate]
) -> TireRecommendation | None:
    """The best same-diameter tire for this wheel among ``candidates``, preferring an
    in-stock one; None when nothing in ``candidates`` shares the wheel's diameter at all
    (nothing to recommend, rather than a wrong-diameter guess)."""
    wheel_width = parse_wheel_width_in(wheel_option_values)
    if wheel_width is None:
        return None

    def sort_key(pair: tuple[TireCandidate, FitmentVerdict]) -> tuple[int, float]:
        _candidate, verdict = pair
        return (
            _FIT_RANK[verdict.width_fit],
            _distance_from_ideal_center(wheel_width, verdict.tire_width_mm),
        )

    scored: list[tuple[TireCandidate, FitmentVerdict]] = []
    for candidate in candidates:
        verdict = check_fitment(wheel_option_values, candidate.option_values)
        if verdict is not None and verdict.diameter_match:
            scored.append((candidate, verdict))
    if not scored:
        return None
    scored.sort(key=sort_key)

    in_stock = [pair for pair in scored if pair[0].in_stock]
    if not in_stock:
        return None
    best_candidate, best_verdict = in_stock[0]

    better_out_of_stock: TireRecommendation | None = None
    best_key = sort_key(in_stock[0])
    for candidate, verdict in scored:
        if not candidate.in_stock and sort_key((candidate, verdict)) < best_key:
            better_out_of_stock = TireRecommendation(candidate.product_id, candidate.title, verdict)
            break  # scored is sorted best-first, so the first such hit is the best one
    return TireRecommendation(
        best_candidate.product_id, best_candidate.title, best_verdict, better_out_of_stock
    )
