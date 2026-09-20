# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The ACME Wheels deployment's shopping agent config. ACME Wheels is a fictional
JDM performance wheel and tire storefront that dropships every item from suppliers in
Japan; there is no merchant agent in this example, since the ask this vertical answers
("what fits my car, what does it cost landed, when does it arrive") is entirely on the
shopping side."""

from __future__ import annotations

from shopping_agent import ShoppingAgentConfig

DOMAIN_SEARCH_NOTES = (
    "Every item is a JDM performance wheel or tire, dropshipped from Japan; there is no "
    'local stock. Name the customer\'s vehicle (e.g. \'attributes={"vehicle": "2020 Subaru '
    "WRX\"}') to filter wheels to ones whose bolt pattern actually fits it; unresolved "
    "vehicles are left unfiltered rather than dropped. Other useful attribute filters: "
    "bolt_pattern (e.g. '5x114.3'), diameter, width, offset, and finish for wheels; size "
    "(e.g. '225/40R18') and dot_approved for tires. get_product_details and search results "
    "carry per-variant fitment facts (bolt_pattern, center_bore_mm, hub_ring_required, "
    "supplier, lead_time_days) in their attributes and specs; state them plainly rather than "
    "assuming a US-warehouse-style overnight fulfillment. get_disclosure surfaces the same "
    "facts as a structured card and should be offered whenever fitment or lead time is in "
    "question."
)


def build_shopping_config() -> ShoppingAgentConfig:
    return ShoppingAgentConfig(
        brand_name="ACME Wheels",
        assistant_name="ACME Wheels Fitment Assistant",
        brand_voice=(
            "warm and technically fluent; upfront about fitment risk, hub rings, dropship "
            "lead time, and street-legality rather than glossing over them to close a sale"
        ),
        domain_search_notes=DOMAIN_SEARCH_NOTES,
        enable_disclosures=True,
        # No merchant-managed campaigns or listing edits exist for this vertical, but
        # orders, cart, policies, and fulfillment (dropship lead time) all apply.
        policy_intent_terms=(
            "return",
            "returns",
            "refund",
            "exchange",
            "warranty",
            "guarantee",
            "fitment",
            "fit",
            "fits",
            "hub ring",
            "hub centric",
            "bolt pattern",
            "center bore",
            "lead time",
            "dropship",
            "customs",
            "duties",
            "duty",
            "dot approved",
            "street legal",
            "street legality",
            "policy",
            "policies",
        ),
        order_intent_terms=(
            "order",
            "orders",
            "delivery",
            "shipment",
            "tracking",
            "tracking number",
            "lead time",
            "when will it arrive",
            "when will it ship",
        ),
        product_id_patterns=(
            r"\bwheel-[a-z0-9]+(?:-[a-z0-9]+)*\b",
            r"\btire-[a-z0-9]+(?:-[a-z0-9]+)*\b",
        ),
    )
