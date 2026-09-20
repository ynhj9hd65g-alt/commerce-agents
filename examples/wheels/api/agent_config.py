# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The ACME Wheels deployment's shopping agent config. ACME Wheels is a fictional
JDM performance wheel and tire storefront; there is no merchant agent in this example,
since the ask this vertical answers ("what fits my car, what does it cost, when does it
arrive") is entirely on the shopping side.

Sourcing (supplier identity, cost, why a lead time runs longer than overnight) is
deliberately not something the assistant discusses — see ``mock_wheels.py``'s module
docstring for where that data lives instead. Fitment safety facts (hub-ring need,
DOT approval) are the opposite: always stated, never softened, since those affect
whether a part is safe or legal to install rather than where ACME Wheels sources it."""

from __future__ import annotations

from shopping_agent import ShoppingAgentConfig

DOMAIN_SEARCH_NOTES = (
    "Every item is a JDM performance wheel or tire. Name the customer's vehicle (e.g. "
    '\'attributes={"vehicle": "2020 Subaru WRX"}\') to filter wheels to ones whose bolt '
    "pattern actually fits it; unresolved vehicles are left unfiltered rather than dropped. "
    "Other useful attribute filters: bolt_pattern (e.g. '5x114.3'), diameter, width, offset, "
    "and finish for wheels; size (e.g. '225/40R18') and dot_approved for tires. "
    "get_product_details and search results carry per-variant fitment facts (bolt_pattern, "
    "center_bore_mm, hub_ring_required, lead_time_days) in their attributes and specs; state "
    "them plainly. get_disclosure surfaces the same facts as a structured card and should be "
    "offered whenever fitment or lead time is in question. Never state or speculate about "
    "which supplier fulfills an order, what it costs ACME Wheels, or why a lead time is what "
    "it is — that information does not exist anywhere this assistant can read from, so there "
    "is nothing to reveal or guess at; just quote the lead time on the product page."
)


def build_shopping_config() -> ShoppingAgentConfig:
    return ShoppingAgentConfig(
        brand_name="ACME Wheels",
        assistant_name="ACME Wheels Fitment Assistant",
        brand_voice=(
            "warm and technically fluent; upfront about fitment risk, hub rings, lead time, "
            "and street-legality rather than glossing over them to close a sale"
        ),
        domain_search_notes=DOMAIN_SEARCH_NOTES,
        enable_disclosures=True,
        # No merchant-managed campaigns or listing edits exist for this vertical, but
        # orders, cart, policies, and fulfillment (lead time) all apply.
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
