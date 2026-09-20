# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import pytest

from wheels.api.fitment import (
    TireCandidate,
    check_fitment,
    ideal_tire_widths_for_wheel,
    parse_tire_size,
    parse_wheel_diameter_in,
    parse_wheel_width_in,
    recommend_tire,
    rim_width_range_for_tire,
    width_fit,
)


def test_parse_tire_size():
    assert parse_tire_size("225/45R17") == (225, 45, 17)
    assert parse_tire_size("not a tire size") is None


def test_parse_wheel_option_values():
    values = {"diameter": '18"', "width": '9.5"', "offset": "+22mm", "finish": "Bronze"}
    assert parse_wheel_diameter_in(values) == 18.0
    assert parse_wheel_width_in(values) == 9.5
    assert parse_wheel_diameter_in({}) is None
    assert parse_wheel_diameter_in({"diameter": "not a number"}) is None


def test_rim_width_range_exact_lookup():
    band = rim_width_range_for_tire(245)
    assert (band.min_in, band.ideal_low_in, band.ideal_high_in, band.max_in) == (7.0, 7.5, 9.0, 9.5)


def test_rim_width_range_interpolates_between_tabulated_widths():
    # 250mm sits halfway between the tabulated 245mm and 255mm rows.
    band = rim_width_range_for_tire(250)
    low, high = rim_width_range_for_tire(245), rim_width_range_for_tire(255)
    assert band.ideal_low_in == pytest.approx((low.ideal_low_in + high.ideal_low_in) / 2)
    assert band.max_in == pytest.approx((low.max_in + high.max_in) / 2)


def test_rim_width_range_clamps_past_the_table_ends():
    assert rim_width_range_for_tire(50) == rim_width_range_for_tire(185)
    assert rim_width_range_for_tire(9999) == rim_width_range_for_tire(315)


@pytest.mark.parametrize(
    ("wheel_width_in", "tire_width_mm", "expected"),
    [
        (8.0, 245, "ideal"),  # squarely inside 245mm's 7.5-9.0 ideal band
        (7.0, 195, "acceptable"),  # within 195mm's 5.5-7.5 min/max but above its 6.5 ideal-high
        (9.5, 235, "not_recommended"),  # past 235mm's 9.0 max entirely
    ],
)
def test_width_fit_classifies_each_band(wheel_width_in, tire_width_mm, expected):
    assert width_fit(wheel_width_in, tire_width_mm) == expected


def test_ideal_tire_widths_for_wheel_returns_a_span():
    assert ideal_tire_widths_for_wheel(9.5) == (255, 285)
    assert ideal_tire_widths_for_wheel(1.0) is None  # narrower than anything tabulated


def test_check_fitment_flags_diameter_mismatch_regardless_of_width():
    """The user's own example: an 18-inch wheel and a 17-inch tire."""
    wheel = {"diameter": '18"', "width": '9.5"'}
    tire = {"size": "225/45R17"}
    verdict = check_fitment(wheel, tire)
    assert verdict is not None
    assert verdict.diameter_match is False
    assert "18" in verdict.summary and "17" in verdict.summary
    assert "not" in verdict.summary.lower() or "will not" in verdict.summary.lower()


def test_check_fitment_ideal_width_match():
    wheel = {"diameter": '19"', "width": '10"'}
    tire = {"size": "265/35R19"}
    verdict = check_fitment(wheel, tire)
    assert verdict is not None
    assert verdict.diameter_match is True
    assert verdict.width_fit == "ideal"


def test_check_fitment_acceptable_but_not_ideal_states_the_ideal_range():
    wheel = {"diameter": '15"', "width": '7"'}
    tire = {"size": "195/50R15"}
    verdict = check_fitment(wheel, tire)
    assert verdict is not None
    assert verdict.diameter_match is True
    assert verdict.width_fit == "acceptable"
    assert verdict.ideal_tire_width_mm is not None
    assert str(verdict.ideal_tire_width_mm[0]) in verdict.summary


def test_check_fitment_returns_none_for_incomplete_records():
    assert check_fitment({}, {"size": "225/45R17"}) is None
    assert check_fitment({"diameter": '18"', "width": '9.5"'}, {}) is None


_WHEEL_18X95 = {"diameter": '18"', "width": '9.5"'}


def test_recommend_tire_picks_the_ideal_in_stock_match():
    candidates = [
        TireCandidate("t-wrong-diameter", "Wrong diameter", {"size": "225/45R17"}, True),
        TireCandidate("t-too-narrow", "Too narrow", {"size": "225/40R18"}, True),
        TireCandidate("t-ideal", "Ideal width", {"size": "265/40R18"}, True),
    ]
    pick = recommend_tire(_WHEEL_18X95, candidates)
    assert pick is not None
    assert pick.product_id == "t-ideal"
    assert pick.verdict.width_fit == "ideal"
    assert pick.better_out_of_stock is None


def test_recommend_tire_prefers_in_stock_over_a_better_out_of_stock_match():
    candidates = [
        TireCandidate("t-acceptable-in-stock", "In stock", {"size": "245/40R18"}, True),
        TireCandidate("t-ideal-out-of-stock", "Backordered", {"size": "265/40R18"}, False),
    ]
    pick = recommend_tire(_WHEEL_18X95, candidates)
    assert pick is not None
    assert pick.product_id == "t-acceptable-in-stock"
    assert pick.better_out_of_stock is not None
    assert pick.better_out_of_stock.product_id == "t-ideal-out-of-stock"


def test_recommend_tire_none_when_nothing_shares_the_wheels_diameter():
    candidates = [TireCandidate("t-17", "Wrong diameter", {"size": "225/45R17"}, True)]
    assert recommend_tire(_WHEEL_18X95, candidates) is None


def test_recommend_tire_none_when_the_only_same_diameter_tire_is_out_of_stock():
    candidates = [TireCandidate("t-18-oos", "Out of stock", {"size": "265/40R18"}, False)]
    assert recommend_tire(_WHEEL_18X95, candidates) is None
