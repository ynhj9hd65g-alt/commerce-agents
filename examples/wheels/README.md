# ACME Wheels (JDM performance wheels & tires)

A shopping-agent-only vertical: a fictional storefront selling performance wheels and
tires. It exists to show two things the other four verticals don't need — matching a part
to a specific car before the customer can buy it, and keeping cost/supplier data (and a
margin on top of it) out of everything the shopping agent can read from — and how both
flow through `StorefrontBackend` into the model's answers. There is no merchant agent or
web app here; see "What this example is not" below.

## Run

```bash
uvicorn wheels.api.main:app --app-dir examples --reload --port 8004
```

Chat needs `ANTHROPIC_API_KEY` in `examples/wheels/.env`, the repo-root `.env`, or the
environment; the catalog and cart routes below do not. This vertical isn't wired into
`scripts/run_demo.py` or `scripts/smoke_chat.py` since both assume a Next.js storefront
app that doesn't exist here (see "What this example is not").

```bash
curl -s localhost:8004/api/health
curl -s localhost:8004/api/products | python3 -m json.tool
curl -s -X POST localhost:8004/api/session -d '{"user_id": "demo-user"}' -H 'content-type: application/json'
```

Chat over SSE needs a session id from `/api/session` in the `X-Session-Id` header (see
`demo_common.sessions.SESSION_HEADER`) on `POST /api/chat`; drive it with `curl --no-buffer`
or a short `httpx` script against those two routes. For a REPL-style console instead of the
FastAPI app, follow `shopping-agent/runtime-agent-sdk/main.py`'s pattern (`make_options` +
`run_turn` from `shopping_agent_sdk`) over `MockWheels` and `build_shopping_config()`.

## Try

1. What wheels do you have for a 2020 Subaru WRX?
2. Which of those is the lightest, and what do I give up to get it?
3. Add the Kaiten in bronze to my cart, front and rear, and tell me when it'll actually arrive.
4. I want a drift tire for my S14 — is it street legal?
5. Who's your supplier for the Kaiten, and why does it take two weeks?
6. I've got a Hakosuka — what fits it?
7. I want the Kaiten 18x9.5 up front — what tire width should I run, and does the Raiden 235/40R18 work?
8. What tire should I run on the Kaiten 19x10 rear?

A good run: turn 1 returns the three 5x114.3 wheels (Kaiten, Raion, Kessho — not the 5x100
Meisho, 4x100 Hachiroku, or 4x114.3 Genroku) each carrying a `fitment_check` note; turn 2
names the Kessho monoblock as lightest and states the real trade-off (not rebuildable like
the Raion's bolted three-piece, unlike a vague "some assembly differences"); turn 3 adds the
staggered pair and quotes the lead time from `get_fulfillment_options` plainly, not a
same-day promise; turn 4 finds the Kumo TR-Z and states plainly that it isn't DOT-approved
rather than glossing over it; turn 5 has nothing to reveal — `domain_search_notes` tells the
model that supplier and cost data doesn't exist anywhere it can read from, so the honest
answer is that ACME Wheels doesn't share sourcing details, not a fabricated one; turn 6
returns only the Genroku R8, sized for the Hakosuka/Kenmeri's own 66.1mm hub rather than the
73.1mm-bore wheels the rest of the catalog is built around; turn 7 states the ideal band
(255-285mm) for the Kaiten's 9.5" width and says the 235mm Raiden is outside it — narrower
than recommended, not merely a preference — rather than confirming it fits because the
diameters happen to match; turn 8 names the Raiden PS-01 245/35R19 as the pick (the only
in-stock 19" tire) while volunteering that the Kumo TR-Z 265/35R19 would be the truly ideal
width and is only unavailable, not a worse choice.

## What is specific to this example

- `api/mock_wheels.py`: `MockWheels`, the `StorefrontBackend` over `data/catalog.json`,
  plus the vehicle-fitment resolver (`resolve_vehicle`, backed by `data/fitment.json`) that
  filters search to wheels whose bolt pattern matches the named car, and a `get_disclosure`
  implementation that renders bolt pattern, center bore, hub-ring need, load index, DOT
  status, and lead time as a structured card.
- **`api/fitment.py`: wheel/tire size validation, independent of any catalog data.**
  Diameter must match exactly — a 17" tire cannot mount on an 18" wheel no matter how close
  it looks — so `check_fitment` treats that as a hard fail regardless of width. Width is a
  range: `_RIM_WIDTH_BY_TIRE_MM` is a published tire-width-to-rim-width reference table
  (section width in mm → minimum, ideal band, and maximum rim width in inches), and
  `width_fit` classifies a wheel's width against a given tire's width as `ideal`,
  `acceptable` (mounts, but the tire will balloon on too narrow a wheel or flatten and
  expose its sidewall on too wide one), or `not_recommended`. `MockWheels.get_disclosure`
  calls this two ways: on a wheel by itself it always states the ideal tire-width band for
  it (`ideal_tire_widths_for_wheel`), so a customer hears the right size before picking a
  tire at all; on either a wheel or a tire that has the other already in the cart, it adds a
  `Fits <the other item> in your cart?` row with the verdict and, for a mismatch or a
  marginal fit, the ideal range to aim for instead. `test_fitment.py` covers the size math
  directly; `test_mock_wheels.py` covers the cart-aware disclosure rows, including the
  user's own example (an 18" wheel with a 17" tire).
- **A staff pick, not just a computed range.** A published range is useful, but a fitment
  guide worth the name (Apex Wheels' chassis-specific guides are the model here) names a
  specific size, not just a band, and says so honestly when the ideal one isn't in stock.
  `recommend_tire` ranks every same-diameter tire in the catalog — ideal beats acceptable
  beats not-recommended, ties broken by distance from the ideal band's center — and prefers
  an in-stock one; when a better match exists but is backordered, the recommendation still
  names it (`better_out_of_stock`) rather than silently picking whatever's on the shelf. A
  wheel with no same-diameter tire in the catalog at all (the Genroku's 14" size) gets no
  staff pick and falls back to the abstract ideal-width band alone — there's nothing honest
  to point at.
- `api/agent_config.py`: `domain_search_notes` documents the `vehicle` search attribute and
  the fitment fields the model should read off each result rather than assume, and states
  plainly that sourcing (supplier, cost, why a lead time is what it is) is nothing the
  assistant has access to — it isn't told to withhold known facts, the facts simply aren't
  anywhere in what `StorefrontBackend` returns.
- Fitment is a search-time filter, not a product option: a customer doesn't "choose" a
  bolt pattern the way they choose a size, so it lives in `SearchFilters.attributes` and
  each variant's `attributes`, per [`docs/backends.md`](../../docs/backends.md)'s "what is
  not a variant" guidance, rather than as another entry in `options`.
- **Cost and margin are tracked, deliberately out of the agent's reach.**
  `data/unit_economics.json` holds each variant's landed cost, its supplier, and a default
  markup; `MockWheels.unit_margin(product_id)` computes cost, price, and margin from it.
  That method isn't declared on `StorefrontBackend`, so it can't be wired to a tool the
  model calls — the same pattern `examples/retail/api/mock_retail.py` uses for
  `price_intelligence`/`review_aspects`, portal-only helpers a customer-facing surface
  never touches. `test_mock_wheels.py::test_unit_margin_is_positive_and_hidden_from_the_agent_surface`
  asserts `unit_margin` isn't on `StorefrontBackend`, and a second test walks every
  customer-visible field for the word "dropship" or a supplier name.

## What this example is not

- **No merchant agent.** The premise ("what fits my car, what does it cost, when does it
  arrive") is entirely a shopping-side problem; there's no operator surface to
  demonstrate. `scripts/check.py`'s `VERTICALS` tuple and the cross-vertical contract suite
  in `examples/demo_common/tests/fixtures.py` both assume both roles, so this vertical
  keeps its own `api/tests/conftest.py` instead of joining them. A merchant agent would be
  the natural home for a real margin *report* (`unit_margin` rolled up across the catalog);
  today it's callable but not surfaced anywhere.
- **No storefront web app.** `examples/retail/storefront-web` is ~30 files of UI that
  would mostly duplicate the existing product-card and cart components without
  demonstrating anything new; drive this vertical with curl, a REPL, or a small script
  against `/api/chat` instead. Wiring it into `examples/web-shared/` is a reasonable next
  step if the fitment card (`present_disclosure`) earns a dedicated component.

## Why sourcing is hidden but fitment and legality aren't

Not naming a supplier or explaining a fulfillment model is ordinary retail discretion —
most stores don't publish their supply chain, and nothing requires them to. That's
different from a false claim (a fake local warehouse, a delivery promise the business
can't hit), which risks real consumer-protection exposure and which this vertical avoids:
lead times in `get_fulfillment_options` and `get_disclosure` are the same real numbers as
before, just described without the supplier/country narrative. Two categories of
disclosure stay on regardless, because they're safety and legal facts about the part
itself, not sourcing: `dot_approved` (a tire that isn't street-legal says so) and
`hub_ring_required`/`center_bore_mm` (installing a wheel without a needed hub ring is a
safety issue). `docs/safety.md` and the `street-legality`/`hub-rings-and-lugs` policies in
`data/policies.json` are the places to extend this line if the catalog grows.

## Data

`data/catalog.json` has six wheel families and three tire families, spanning the tiers a
real curated JDM catalog would carry rather than one flat price point: flow-formed
(Kaiten), bolted three-piece forged (Raion), forged monoblock (Kessho — the lightest wheel
in the catalog, at the cost of not being rebuildable like the Raion), direct-fit lightweight
cast (Meisho, no hub ring needed on its platform), a budget retro mesh (Hachiroku), and a
period-correct heritage eight-spoke for 1960s-70s classics (Genroku, sized for the Hakosuka/
Kenmeri rather than a modern platform). Tires run from everyday UHP (Raiden) through a
DOT-legal trackday step-up (Hayate) to a non-DOT drift compound (Kumo). Four bolt patterns
(5x114.3, 5x100, 4x100, 4x114.3) are deliberately represented so fitment filtering has
something to filter. `data/fitment.json` maps a handful of well-known JDM platforms (WRX,
Silvia S13/S14/S15, Skyline R32 GT-R, Skyline Hakosuka/Kenmeri, AE86, Miata NA/NB, BRZ/86) to
bolt pattern, center bore, and stock offset range; `resolve_vehicle` does a token-overlap
match against it rather than anything more precise, so it's a demo-grade lookup, not a
fitment database. `data/unit_economics.json` holds cost, supplier, and the default markup,
keyed by variant id — see "What is specific to this example" above for why it's a separate
file rather than more fields on the catalog. `users.json`, `orders.json`, `policies.json`,
and `memory-seed.json` follow the same shape as the other verticals' (`docs/backends.md`).

This lineup is a fictional stand-in for a real curation exercise: pulling together
best-in-tier options across heritage, forged, monoblock, and budget segments so a customer
picks a car and application rather than hunting brand by brand. The names are invented per
this repo's `CLAUDE.md` ("no real company, brand, product, or person appears"); a real build
on this pattern would source that lineup from actual manufacturers and their authorized US
distributors instead of a single supplier per item.

## Wiring in a real Shopify store

This vertical ships fixture-backed, per the "MCP connectors" section of the root
[`README.md`](../../README.md#mcp-connectors): a commerce platform's own MCP server (or
REST API) for catalog, cart, or checkout is called from a `StorefrontBackend` method
server-side, never from the model directly. To point this vertical at a real Shopify store
instead of `data/catalog.json`:

- **`search_products` / `get_product_details`**: call the Shopify Storefront API (or its
  MCP server) for products and variants; map a Shopify product to a family and each of its
  variants per `docs/backends.md`'s "product shell that always has variants" row, and keep
  bolt pattern, center bore, and lead time as variant metafields surfaced through
  `attributes`, exactly as the fixture does — leaving cost and supplier metafields off that
  mapping, the same way the fixture keeps them in a file `StorefrontBackend` never reads.
- **`get_cart` / `add_to_cart` / `update_cart_item` / `remove_from_cart`**: call the
  Shopify Storefront API's cart mutations, keyed by a cart id held server-side with the
  session (never a tool argument).
- **`checkout_handoff`**: override it to return the cart's Shopify-hosted checkout URL
  (`docs/backends.md`'s "platform hosted checkout" row) — the one method this fixture
  backend leaves at its default (no handoff; the host's own checkout route applies).
- **`get_orders` / `get_order`**: the Shopify Admin API's orders, scoped to the
  authenticated customer.
- **Margin**: a real deployment computes it the same way `unit_margin` does — from a cost
  Shopify's Admin API or your own PO/landed-cost system holds, never from a field on the
  Storefront-facing product — and reports it to a merchant view or a BI tool, not to
  `StorefrontBackend`.
- Keep `resolve_vehicle` and the bolt-pattern filtering in `search_products` as they are;
  that logic is independent of where the catalog data comes from.

Shopify credentials go with the session/service credential per `docs/backends.md`'s
"Step 1", never as a tool argument or in the model's context.
