# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import pytest

from shopping_agent import SearchFilters, Unavailable


def test_catalog_loads_and_validates(backend):
    assert backend.store_name == "ACME Wheels"
    assert len(backend.products) == 9
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
    """A WRX (5x114.3) should surface the Kaiten, Raion, and Kessho wheels but not the
    5x100 Meisho, the 4x100 Hachiroku, or the 4x114.3 Genroku, and every returned wheel
    should carry a fitment_check note."""
    fitting = await backend.search_products(
        session, "wheels", SearchFilters(attributes={"vehicle": "2020 Subaru WRX"}), limit=10
    )
    ids = {p.product_id for p in fitting}
    assert "wheel-kaiten-sf01" in ids
    assert "wheel-raion-gt3" in ids
    assert "wheel-kessho-monoblock" in ids
    assert "wheel-meisho-rpf" not in ids
    assert "wheel-hachiroku-classic" not in ids
    assert "wheel-genroku-r8" not in ids
    for product in fitting:
        assert "5x114.3" in product.attributes["fitment_check"]


async def test_heritage_wheel_fits_hakosuka_without_hub_ring(backend, session):
    """The Genroku R8 is bored to the Hakosuka/Kenmeri's own 66.1mm hub directly, unlike
    the modern-platform wheels in this catalog, which all need a ring on that hub."""
    hakosuka = backend.resolve_vehicle("Nissan Hakosuka")
    assert hakosuka is not None and hakosuka.bolt_pattern == "4x114.3"

    fitting = await backend.search_products(
        session, "wheels", SearchFilters(attributes={"vehicle": "Nissan Hakosuka"}), limit=10
    )
    ids = {p.product_id for p in fitting}
    assert ids == {"wheel-genroku-r8"}

    details = await backend.get_product_details(session, "wheel-genroku-r8-14x7-0-silver")
    assert details is not None
    assert "No" in details.attributes["hub_ring_required"]


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


async def test_get_disclosure_surfaces_fitment_without_sourcing(backend, session):
    disclosure = await backend.get_disclosure(session, "wheel-kaiten-sf01-18x95-22-bronze")
    assert disclosure is not None
    labels = {row.label for row in disclosure.rows}
    assert {"Bolt pattern", "Center bore", "Estimated delivery"} <= labels
    # No row, value, or note may name a supplier or say where the item ships from: that
    # data lives only in unit_economics.json, which get_disclosure never reads.
    blob = " ".join(f"{r.label} {r.value} {r.note or ''}" for r in disclosure.rows).lower()
    for tell in ("supplier", "japan", "dropship", "osaka", "kansai"):
        assert tell not in blob


async def test_fulfillment_reflects_longest_lead_time_without_sourcing_language(backend, session):
    options = await backend.get_fulfillment_options(
        session, ["wheel-kaiten-sf01-18x95-22-bronze", "wheel-raion-gt3-18x95-12-satinblack"]
    )
    standard = next(o for o in options if o.fee == 0.0)
    assert "28" in standard.eta  # the Raion's 21-28 day built-to-order lead time dominates
    for tell in ("dropship", "japan", "air freight"):
        assert tell not in standard.eta.lower()


def test_unit_margin_is_positive_and_hidden_from_the_agent_surface(backend):
    margin = backend.unit_margin("wheel-kaiten-sf01-18x95-22-bronze")
    assert margin is not None
    assert margin["cost"] < margin["price"]
    assert margin["margin_usd"] == round(margin["price"] - margin["cost"], 2)
    assert margin["margin_pct"] > 0
    assert margin["supplier"] == "Osaka Wheel Supply"

    # unit_margin is not part of StorefrontBackend, so it is unreachable from any tool.
    from shopping_agent import StorefrontBackend

    assert "unit_margin" not in vars(StorefrontBackend)


def test_every_sellable_variant_has_positive_margin(backend):
    for variant in backend.variants.values():
        if not variant.in_stock:
            continue
        margin = backend.unit_margin(variant.product_id)
        assert margin is not None and margin["cost"] < margin["price"], variant.product_id


async def test_catalog_and_disclosure_never_name_a_supplier(backend, session):
    """Regression guard for hiding sourcing: nothing reachable from search, details, or
    disclosures should mention a supplier name or "dropship"."""
    suppliers = {e.supplier.lower() for e in backend._unit_economics.values()}
    for product in backend.products.values():
        haystack = " ".join(
            [product.title, product.short_description or "", product.long_description or ""]
            + [f"{k} {v}" for k, v in product.attributes.items()]
            + [f"{k} {v}" for variant in product.variants for k, v in variant.attributes.items()]
        ).lower()
        assert "dropship" not in haystack
        for supplier in suppliers:
            assert supplier not in haystack
        for variant in product.variants or [product]:
            disclosure = await backend.get_disclosure(session, variant.product_id)
            if disclosure is None:
                continue
            for row in disclosure.rows:
                text = f"{row.label} {row.value} {row.note or ''}".lower()
                assert "dropship" not in text
                for supplier in suppliers:
                    assert supplier not in text
