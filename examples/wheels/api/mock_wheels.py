# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The ACME Wheels example's ``StorefrontBackend`` over the fixtures in ``data/``: keyword
search with vehicle-fitment filtering, per-session carts, fixture orders and policies, and
lead-time-aware fulfillment and disclosures. An adopter wiring this vertical to a real
Shopify store replaces this class with one that calls the Shopify Storefront API (catalog,
search) and Admin API or MCP server (cart, checkout) server-side, per ``docs/backends.md``'s
"MCP connectors" guidance; ``checkout_handoff`` would then return the cart's Shopify hosted
checkout URL instead of the default empty list. The domain logic here — bolt-pattern
fitment filtering, hub-ring notes, lead-time quoting — carries over unchanged, since it
lives in this class rather than in the fixtures.

Cost and supplier identity live only in ``data/unit_economics.json`` and only reach
``unit_margin()`` below, a plain method rather than anything ``StorefrontBackend`` declares,
so nothing in the shopping agent's tool surface (search, details, disclosures, fulfillment)
can ever return them to a customer. This mirrors ``examples/retail/api/mock_retail.py``'s
``price_intelligence``/``review_aspects``: internal-only helpers a portal or an ops script
can call directly, never wired to a tool."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from demo_common.storefront_fixtures import (
    SessionCarts,
    example_data_dir,
    find_order,
    find_product,
    keyword_score,
    load_catalog,
    load_json,
    load_orders,
    load_policies,
    load_users,
    newest_orders,
    option_text,
    orders_for,
    preferences_of,
    rank_products,
    search_help,
    stem,
    summary_of,
    tokens,
    unavailable_detail,
    within_price_and_rating,
)
from shopping_agent import (
    Cart,
    Disclosure,
    DisclosureRow,
    FulfillmentOption,
    Order,
    Policy,
    Product,
    ProductDetails,
    SearchFilters,
    ShoppingSessionContext,
    StorefrontBackend,
    Unavailable,
    UserPreferences,
)

from .fitment import (
    TireCandidate,
    check_fitment,
    ideal_tire_widths_for_wheel,
    parse_wheel_width_in,
    recommend_tire,
)

DATA_DIR = example_data_dir(__file__)

_SEARCH_WEIGHTS = {
    "title": 3.0,
    "brand": 2.0,
    "category": 2.0,
    "attributes": 1.5,
    "description": 1.0,
}
_LEAD_TIME_RANGE = re.compile(r"(\d+)\s*-\s*(\d+)")


@dataclass(frozen=True)
class VehicleFitment:
    make: str
    model: str
    label: str
    bolt_pattern: str
    center_bore_mm: float
    aliases: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""


def load_fitment(data_dir: Path) -> list[VehicleFitment]:
    raw = load_json(data_dir, "fitment.json")["vehicles"]
    return [
        VehicleFitment(
            make=entry["make"],
            model=entry["model"],
            label=f"{entry['make']} {entry['model']}",
            bolt_pattern=entry["bolt_pattern"],
            center_bore_mm=float(entry["center_bore_mm"]),
            aliases=tuple(entry.get("aliases", ())),
            notes=entry.get("notes", ""),
        )
        for entry in raw
    ]


@dataclass(frozen=True)
class UnitEconomics:
    cost: float
    supplier: str


def load_unit_economics(data_dir: Path) -> tuple[dict[str, UnitEconomics], float]:
    """``(cost and supplier by variant id, the default markup fraction)``. Internal-only:
    nothing in ``StorefrontBackend`` reads this; see the module docstring."""
    raw = load_json(data_dir, "unit_economics.json")
    by_variant = {
        variant_id: UnitEconomics(cost=float(entry["cost"]), supplier=entry["supplier"])
        for variant_id, entry in raw["variants"].items()
    }
    return by_variant, float(raw["default_markup_pct"]) / 100


class MockWheels(StorefrontBackend):
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        catalog, self.products, self.variants = load_catalog(data_dir)
        self.store_name: str = catalog.get("store_name", "the store")
        self._fitment = load_fitment(data_dir)
        self._unit_economics, self._default_markup = load_unit_economics(data_dir)
        self._users = load_users(data_dir)
        self._orders = load_orders(data_dir)
        self._policies = load_policies(data_dir)
        self._carts = SessionCarts()

    # ------------------------------------------------------------------
    # Vehicle fitment
    # ------------------------------------------------------------------

    def resolve_vehicle(self, text: str | None) -> VehicleFitment | None:
        """The best fitment-table match for free text naming a car (``"2020 Subaru
        WRX"``), or None when nothing overlaps enough to guess at. An unresolved vehicle
        is left unfiltered by ``search_products`` rather than emptying the results, since
        a car this fixture table does not carry is not evidence nothing fits it."""
        if not text:
            return None
        query_terms = {stem(t) for t in tokens(text)}
        best: VehicleFitment | None = None
        best_score = 0
        for vehicle in self._fitment:
            name_terms = {
                stem(t)
                for t in tokens(f"{vehicle.make} {vehicle.model} {' '.join(vehicle.aliases)}")
            }
            score = len(query_terms & name_terms)
            if score > best_score:
                best, best_score = vehicle, score
        return best

    @staticmethod
    def _bolt_patterns(product: ProductDetails) -> set[str]:
        """Every bolt pattern this family's variants carry; empty for a plain record with
        no fitment data (tires, which fit by size rather than bolt pattern)."""
        return {
            pattern
            for variant in (product.variants or [product])
            if (pattern := variant.attributes.get("bolt_pattern"))
        }

    def _fits_vehicle(self, product: ProductDetails, vehicle: VehicleFitment | None) -> bool:
        if vehicle is None or product.category != "wheel":
            return True
        patterns = self._bolt_patterns(product)
        return not patterns or vehicle.bolt_pattern in patterns

    def _stamp_fitment(self, product: Product, vehicle: VehicleFitment) -> Product:
        if product.category != "wheel":
            return product
        note = f"Bolt pattern confirmed for a {vehicle.label} ({vehicle.bolt_pattern})."
        if vehicle.notes:
            note += f" {vehicle.notes}"
        return product.model_copy(
            update={"attributes": {**product.attributes, "fitment_check": note}}
        )

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def listing_of(self, product_id: str) -> ProductDetails | None:
        """The listing an id belongs to: itself, or its family when it is a variant."""
        record = self.product(product_id)
        if record is not None and record.variant_of:
            return self.products.get(record.variant_of)
        return record

    def _searchable_text(self, product: ProductDetails) -> dict[str, str]:
        variant_terms = " ".join(
            f"{k} {v}"
            for variant in (product.variants or [product])
            for k, v in {**variant.attributes, **variant.option_values}.items()
        )
        return {
            "title": product.title,
            "brand": product.brand or "",
            "category": product.category or "",
            "attributes": " ".join(f"{k} {v}" for k, v in product.attributes.items())
            + " "
            + variant_terms
            + " "
            + option_text(product),
            "description": f"{product.short_description or ''} {product.long_description or ''}",
        }

    def _score(self, product: ProductDetails, query_tokens: list[str]) -> float:
        return keyword_score(self._searchable_text(product), _SEARCH_WEIGHTS, query_tokens, {})

    def _soft_filter(self, product: ProductDetails, filters: SearchFilters) -> bool:
        if filters.category and filters.category.lower() not in (product.category or "").lower():
            return False
        if not filters.attributes:
            return True
        haystack_parts = [
            " ".join(f"{k}={v}".lower() for k, v in product.attributes.items()),
            product.title.lower(),
            option_text(product).lower(),
        ]
        for variant in product.variants or [product]:
            haystack_parts.append(
                " ".join(f"{k}={v}".lower() for k, v in variant.attributes.items())
            )
            haystack_parts.append(
                " ".join(f"{k}={v}".lower() for k, v in variant.option_values.items())
            )
        haystack = " ".join(haystack_parts)
        return all(
            str(value).lower() in haystack
            for key, value in filters.attributes.items()
            if key != "vehicle"
        )

    async def search_products(
        self,
        session: ShoppingSessionContext,
        query: str,
        filters: SearchFilters | None = None,
        limit: int = 8,
    ) -> list[Product]:
        del session
        vehicle = self.resolve_vehicle(filters.attributes.get("vehicle")) if filters else None
        ranked = rank_products(
            self.products.values(),
            query,
            filters,
            limit,
            score=self._score,
            hard_filter=lambda product, f: (
                within_price_and_rating(product, f) and self._fits_vehicle(product, vehicle)
            ),
            soft_filter=self._soft_filter,
        )
        results = [summary_of(product) for product in ranked]
        return [self._stamp_fitment(p, vehicle) for p in results] if vehicle else results

    def product(self, product_id: str) -> ProductDetails | None:
        return find_product(self.products, self.variants, product_id)

    async def get_product_details(
        self, session: ShoppingSessionContext, product_id: str
    ) -> ProductDetails | None:
        del session
        return self.product(product_id)

    # ------------------------------------------------------------------
    # Disclosures: the fitment facts box
    # ------------------------------------------------------------------

    def _tire_candidates(self) -> list[TireCandidate]:
        return [
            TireCandidate(v.product_id, v.title, v.option_values, v.in_stock)
            for v in self.variants.values()
            if v.category == "tire"
        ]

    def _cart_fitment_rows(
        self, session: ShoppingSessionContext, product: ProductDetails
    ) -> list[DisclosureRow]:
        """Fitment facts that depend on what else is in the cart, plus two standing
        recommendations for a wheel on its own: the tire widths this catalog considers
        ideal for it, and a specific staff pick from the current catalog (not just the
        computed range), so a customer hears the right size before they've picked a tire
        at all, not only once they've picked a mismatched one."""
        rows: list[DisclosureRow] = []
        if product.category == "wheel":
            wheel_width = parse_wheel_width_in(product.option_values)
            if wheel_width is not None:
                ideal = ideal_tire_widths_for_wheel(wheel_width)
                value = (
                    f"{ideal[0]}-{ideal[1]}mm"
                    if ideal
                    else "narrower or wider than this catalog's tires"
                )
                rows.append(DisclosureRow(label="Ideal tire width for this wheel", value=value))

            recommendation = recommend_tire(product.option_values, self._tire_candidates())
            if recommendation is not None:
                note = recommendation.verdict.summary
                if recommendation.better_out_of_stock is not None:
                    note += (
                        f" {recommendation.better_out_of_stock.title} would be a better width "
                        "match but is currently out of stock."
                    )
                rows.append(
                    DisclosureRow(
                        label="Staff-recommended tire",
                        value=f"{recommendation.title} ({recommendation.verdict.tire_width_mm}mm)",
                        note=note,
                    )
                )
            opposite_category = "tire"
        elif product.category == "tire":
            opposite_category = "wheel"
        else:
            return rows

        for line in self._carts.lines(session.session_id).values():
            other = self.product(line.product_id)
            if (
                other is None
                or other.category != opposite_category
                or other.product_id == product.product_id
            ):
                continue
            wheel_of, tire_of = (
                (product, other) if product.category == "wheel" else (other, product)
            )
            verdict = check_fitment(wheel_of.option_values, tire_of.option_values)
            if verdict is None:
                continue
            if not verdict.diameter_match:
                value = "No — will not mount"
            elif verdict.width_fit == "ideal":
                value = "Yes — ideal"
            elif verdict.width_fit == "acceptable":
                value = "Marginal — mounts, not ideal"
            else:
                value = "Not recommended"
            rows.append(
                DisclosureRow(
                    label=f"Fits {other.title} in your cart?", value=value, note=verdict.summary
                )
            )
        return rows

    async def get_disclosure(
        self, session: ShoppingSessionContext, product_id: str
    ) -> Disclosure | None:
        product = self.product(product_id)
        if product is None:
            return None
        listing = self.listing_of(product_id) or product
        rows: list[DisclosureRow] = []
        if bolt_pattern := product.attributes.get("bolt_pattern"):
            rows.append(DisclosureRow(label="Bolt pattern", value=bolt_pattern))
        if bore := product.attributes.get("center_bore_mm"):
            rows.append(
                DisclosureRow(
                    label="Center bore",
                    value=f"{bore}mm",
                    note=product.attributes.get("hub_ring_required"),
                )
            )
        if offset := product.option_values.get("offset"):
            rows.append(DisclosureRow(label="Offset", value=offset))
        if size := product.option_values.get("size"):
            rows.append(DisclosureRow(label="Tire size", value=size))
        if load_index := product.attributes.get("load_index"):
            speed = product.attributes.get("speed_rating", "")
            rows.append(
                DisclosureRow(label="Load index / speed rating", value=f"{load_index}{speed}")
            )
        if dot := product.attributes.get("dot_approved"):
            rows.append(DisclosureRow(label="DOT approved", value=dot))
        if weight := product.specs.get("weight_lbs"):
            rows.append(DisclosureRow(label="Weight", value=f"{weight} lb"))
        if lead_time := product.attributes.get("lead_time_days"):
            rows.append(
                DisclosureRow(label="Estimated delivery", value=f"{lead_time} business days")
            )
        rows.extend(self._cart_fitment_rows(session, product))
        if not rows:
            return None
        return Disclosure(
            title=f"{listing.title} — fitment",
            product_id=product.product_id,
            rows=rows,
            sources=["ACME Wheels catalog"],
        )

    # ------------------------------------------------------------------
    # Internal only: never called by a StorefrontBackend method, so never
    # reachable from a shopping-agent tool or a customer-facing response.
    # ------------------------------------------------------------------

    def unit_margin(self, product_id: str) -> dict[str, float | str] | None:
        """Cost, price, and margin for one variant, for an ops script or a future
        merchant view — not the shopping agent, which has no way to call this. A
        variant absent from ``unit_economics.json`` falls back to the catalog-wide
        default markup on an assumed cost, so every sellable variant prices out
        positive even before its real landed cost is entered."""
        product = self.product(product_id)
        if product is None or product.has_options:
            return None
        economics = self._unit_economics.get(product_id)
        cost = economics.cost if economics else round(product.price / (1 + self._default_markup), 2)
        supplier = economics.supplier if economics else None
        margin_usd = round(product.price - cost, 2)
        margin_pct = round(margin_usd / product.price * 100, 1) if product.price else 0.0
        result: dict[str, float | str] = {
            "cost": cost,
            "price": product.price,
            "margin_usd": margin_usd,
            "margin_pct": margin_pct,
        }
        if supplier:
            result["supplier"] = supplier
        return result

    # ------------------------------------------------------------------
    # Cart
    # ------------------------------------------------------------------

    async def get_cart(self, session: ShoppingSessionContext) -> Cart:
        return self._carts.cart(session.session_id)

    async def add_to_cart(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        product = self.product(product_id)
        if product is None or product.has_options:
            raise KeyError(product_id)
        if not product.in_stock:
            raise Unavailable(unavailable_detail(product, self.listing_of(product_id)))
        existing = self._carts.lines(session.session_id).get(product_id)
        quantity += existing.quantity if existing else 0
        return self._carts.put(session.session_id, product, quantity)

    async def update_cart_item(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        return self._carts.set_quantity(session.session_id, product_id, quantity)

    async def remove_from_cart(self, session: ShoppingSessionContext, product_id: str) -> Cart:
        return self._carts.remove(session.session_id, product_id)

    def reset_session(self, session_id: str) -> None:
        self._carts.reset(session_id)

    # ------------------------------------------------------------------
    # Customer, orders, help content
    # ------------------------------------------------------------------

    async def get_preferences(self, session: ShoppingSessionContext) -> UserPreferences:
        return preferences_of(self._users, session.user_id)

    async def get_orders(self, session: ShoppingSessionContext, limit: int = 5) -> list[Order]:
        return orders_for(self._orders, session.user_id, limit)

    async def get_order(self, session: ShoppingSessionContext, order_id: str) -> Order | None:
        return find_order(self._orders, session.user_id, order_id)

    def recent_orders(self, limit: int = 6) -> list[Order]:
        return newest_orders(self._orders, limit)

    async def search_policies(self, session: ShoppingSessionContext, query: str) -> list[Policy]:
        del session
        return search_help(self._policies, query)

    # ------------------------------------------------------------------
    # Fulfillment: each variant's own lead time, not same-day delivery
    # ------------------------------------------------------------------

    def _max_lead_days(self, product: ProductDetails) -> int | None:
        text = product.attributes.get("lead_time_days")
        match = _LEAD_TIME_RANGE.search(text) if text else None
        return int(match.group(2)) if match else None

    async def get_fulfillment_options(
        self, session: ShoppingSessionContext, product_ids: list[str]
    ) -> list[FulfillmentOption]:
        del session
        quoted = [product for pid in product_ids if (product := self.product(pid))]
        lead_days = [days for p in quoted if (days := self._max_lead_days(p)) is not None]
        standard = max(lead_days) if lead_days else 14
        return [
            FulfillmentOption(
                method="shipping",
                eta=f"{standard} business days (standard shipping)",
                fee=0.0,
            ),
            FulfillmentOption(
                method="shipping",
                eta=f"{max(standard // 2, 3)} business days (expedited)",
                fee=79.0,
            ),
        ]
