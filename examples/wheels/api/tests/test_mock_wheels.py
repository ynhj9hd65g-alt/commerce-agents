# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import pytest

from shopping_agent import SearchFilters, Unavailable


def test_catalog_loads_and_validates(backend):
    assert backend.store_name == "ACME Wheels"
    assert len(backend.products) == 6
    wheel = backend.products["wheel-kaiten-sf01"]
    assert wheel.category == "wheel"
    assert wheel.variants and all(v.attributes.get("bolt_pattern") for v in wheel.variants)


async def test_search_relevance(backend, session):
    wheels = await backend.search_products(session, "JDM wheels")
    assert wheels and all(p.category == "wheel" for p in wheels[:4])

    tires = await backend.search_products(session, "drift tire")
    assert any(p.product_id == "tire-kumo-trz-drift" for p in tires)

    nothing = await backend.search_products(session, "zzzqqq")
    assert nothing == []


async def test_out_of_stock_items_are_searchable(backend, session):
    results = await backend.search_products(session, "kaiten sf-01 gunmetal 19")
    assert any(p.product_id == "wheel-kaiten-sf01" and p.in_stock for p in results)
    details = await backend.get_product_details(session, "wheel-kaiten-sf01-19x10-35-gunmetal")
    assert details is not None and details.in_stock is False


def test_resolve_vehicle_matches_and_misses(backend):
    wrx = backend.resolve_vehicle("my 2020 Subaru WRX")
    assert wrx is not None and wrx.bolt_pattern == "5x114.3"

    assert backend.resolve_vehicle("a spaceship") is None
    assert backend.resolve_vehicle(None) is None


async def test_search_filters_by_vehicle_bolt_pattern(backend, session):
    """A WRX (5x114.3) should surface the Kaiten and Raion wheels but not the 5x100 Meisho
    or the 4x100 Hachiroku, and every returned wheel should carry a fitment_check note."""
    fitting = await backend.search_products(
        session, "wheels", SearchFilters(attributes={"vehicle": "2020 Subaru WRX"}), limit=10
    )
    ids = {p.product_id for p in fitting}
    assert "wheel-kaiten-sf01" in ids
    assert "wheel-raion-gt3" in ids
    assert "wheel-meisho-rpf" not in ids
    assert "wheel-hachiroku-classic" not in ids
    for product in fitting:
        assert "5x114.3" in product.attributes["fitment_check"]


async def test_search_by_bolt_pattern_attribute(backend, session):
    results = await backend.search_products(
        session, "wheels", SearchFilters(attributes={"bolt_pattern": "5x100"}), limit=10
    )
    assert any(p.product_id == "wheel-meisho-rpf" for p in results)
    assert all(p.product_id != "wheel-hachiroku-classic" for p in results)


async def test_add_to_cart_rejects_out_of_stock_variant(backend, session):
    with pytest.raises(Unavailable):
        await backend.add_to_cart(session, "wheel-kaiten-sf01-19x10-35-gunmetal", 1)


async def test_add_to_cart_accepts_in_stock_variant(backend, session):
    cart = await backend.add_to_cart(session, "wheel-kaiten-sf01-18x95-22-bronze", 4)
    assert cart.item_count == 4
    assert cart.items[0].option_values["finish"] == "Bronze"


async def test_get_disclosure_surfaces_fitment_and_sourcing(backend, session):
    disclosure = await backend.get_disclosure(session, "wheel-kaiten-sf01-18x95-22-bronze")
    assert disclosure is not None
    labels = {row.label for row in disclosure.rows}
    assert {"Bolt pattern", "Center bore", "Ships from"} <= labels


async def test_fulfillment_reflects_longest_dropship_lead_time(backend, session):
    options = await backend.get_fulfillment_options(
        session, ["wheel-kaiten-sf01-18x95-22-bronze", "wheel-raion-gt3-18x95-12-satinblack"]
    )
    standard = next(o for o in options if o.fee == 0.0)
    assert "28" in standard.eta  # the Raion's 21-28 day built-to-order lead time dominates
