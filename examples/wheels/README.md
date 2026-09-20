# ACME Wheels (JDM performance wheels & tires)

A shopping-agent-only vertical: a fictional storefront that dropships performance wheels
and tires from suppliers in Japan. It exists to show the one thing the other four
verticals don't need — matching a part to a specific car before the customer can buy it —
and how a dropship backend's price, availability, and fitment facts flow through
`StorefrontBackend` into the model's answers. There is no merchant agent or web app here;
see "What this example is not" below.

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
2. What's the difference between the two that fit, and do either of them need a hub ring on my car?
3. Add the Kaiten in bronze to my cart, front and rear, and tell me when it'll actually arrive.
4. I want a drift tire for my S14 — is it street legal?

A good run: turn 1 returns only the two 5x114.3 wheels (not the 5x100 or 4x100 ones) and
each result carries a `fitment_check` note; turn 2 states the WRX's 56.1mm hub needs a ring
for both (73.1mm bore); turn 3 adds the staggered pair and quotes the dropship lead time
from `get_fulfillment_options`, not a same-day promise; turn 4 finds the Kumo TR-Z and
states plainly that it isn't DOT-approved rather than glossing over it.

## What is specific to this example

- `api/mock_wheels.py`: `MockWheels`, the `StorefrontBackend` over `data/catalog.json`,
  plus the vehicle-fitment resolver (`resolve_vehicle`, backed by `data/fitment.json`) that
  filters search to wheels whose bolt pattern matches the named car, and a `get_disclosure`
  implementation that renders bolt pattern, center bore, hub-ring need, load index, DOT
  status, and supplier/lead time as a structured card.
- `api/agent_config.py`: `domain_search_notes` documents the `vehicle` search attribute and
  the fitment/dropship fields the model should read off each result rather than assume.
- Fitment is a search-time filter, not a product option: a customer doesn't "choose" a
  bolt pattern the way they choose a size, so it lives in `SearchFilters.attributes` and
  each variant's `attributes`, per [`docs/backends.md`](../../docs/backends.md)'s "what is
  not a variant" guidance, rather than as another entry in `options`.
- Multi-supplier pricing is kept simple, per the same guide's "one product sold by several
  sellers" note: each variant's price is the offer this store would actually sell, and a
  second supplier's price/lead time (when one exists) is recorded as
  `attributes.alt_supplier_note` — informational, not a second purchasable record.

## What this example is not

- **No merchant agent.** The premise ("what fits my car, what does it cost landed, when
  does it arrive") is entirely a shopping-side problem; there's no operator surface to
  demonstrate. `scripts/check.py`'s `VERTICALS` tuple and the cross-vertical contract suite
  in `examples/demo_common/tests/fixtures.py` both assume both roles, so this vertical
  keeps its own `api/tests/conftest.py` instead of joining them.
- **No storefront web app.** `examples/retail/storefront-web` is ~30 files of UI that
  would mostly duplicate the existing product-card and cart components without
  demonstrating anything new; drive this vertical with curl, a REPL, or a small script
  against `/api/chat` instead. Wiring it into `examples/web-shared/` is a reasonable next
  step if the fitment card (`present_disclosure`) earns a dedicated component.

## Data

`data/catalog.json` has four wheel families and two tire families; three bolt patterns
(5x114.3, 5x100, 4x100) are deliberately represented so fitment filtering has something to
filter. `data/fitment.json` maps a handful of well-known JDM platforms (WRX, Silvia
S13/S14/S15, Skyline R32 GT-R, AE86, Miata NA/NB, BRZ/86) to bolt pattern, center bore, and
stock offset range; `resolve_vehicle` does a token-overlap match against it rather than
anything more precise, so it's a demo-grade lookup, not a fitment database. `users.json`,
`orders.json`, `policies.json`, and `memory-seed.json` follow the same shape as the other
verticals' (`docs/backends.md`).

## Wiring in a real Shopify store

This vertical ships fixture-backed, per the "MCP connectors" section of the root
[`README.md`](../../README.md#mcp-connectors): a commerce platform's own MCP server (or
REST API) for catalog, cart, or checkout is called from a `StorefrontBackend` method
server-side, never from the model directly. To point this vertical at a real Shopify store
instead of `data/catalog.json`:

- **`search_products` / `get_product_details`**: call the Shopify Storefront API (or its
  MCP server) for products and variants; map a Shopify product to a family and each of its
  variants per `docs/backends.md`'s "product shell that always has variants" row, and keep
  bolt pattern, center bore, and supplier lead time as variant metafields surfaced through
  `attributes`, exactly as the fixture does.
- **`get_cart` / `add_to_cart` / `update_cart_item` / `remove_from_cart`**: call the
  Shopify Storefront API's cart mutations, keyed by a cart id held server-side with the
  session (never a tool argument).
- **`checkout_handoff`**: override it to return the cart's Shopify-hosted checkout URL
  (`docs/backends.md`'s "platform hosted checkout" row) — the one method this fixture
  backend leaves at its default (no handoff; the host's own checkout route applies).
- **`get_orders` / `get_order`**: the Shopify Admin API's orders, scoped to the
  authenticated customer.
- Keep `resolve_vehicle` and the bolt-pattern filtering in `search_products` as they are;
  that logic is independent of where the catalog data comes from.

Shopify credentials go with the session/service credential per `docs/backends.md`'s
"Step 1", never as a tool argument or in the model's context.
