# Right-now checkout currentness

`revenue/agent_failure_autopsy/offer.json` and `stripe_checkout_current.json` are retained audit evidence for the USD 29 Agent Failure Autopsy. They are **not** a reusable trust root for the word `current`.

## Production authority boundary

Canonical `host/right_now_revenue.py` requires a fresh readback from the fixed absolute collector:

`/usr/local/libexec/commons-stripe-current-readback`

That executable is deployment/credential-host state, not repository state. The compiler provides no CLI argument, environment variable, catalog field, or caller parameter that can select another collector. It launches the collector with an empty inherited environment, accepts one bounded JSON object on stdout, rejects stderr/nonzero/timeout/malformed output, then validates the exact Stripe account, Payment Link, live/active state, product, price, currency, amount, quantity, offer metadata, exact line-item count, `has_more=false`, authenticated operation names, canonical observation time, and a 24-hour process-UTC freshness ceiling.

Deployment must provision the fixed collector outside the repository trust domain with the Stripe read credential/keychain it needs. The collector should be host-admin owned and not writable by the repository checkout/runtime user. If it is absent or fails, current checkout authority fails closed. No repository edit can refresh currentness by changing `stripe_checkout_current.json`, a digest constant, catalog `as_of`, or a caller-supplied authority object.

## Retained receipt

`stripe_checkout_current.json` records the independently observed provider facts from the original read-only Stripe session and remains useful for audit, review, hostile fixtures, and cardinality regression tests. It does not participate in production current-authority construction.

## Truth semantics

`active_chargeable_checkout=true` means only that:

1. historical public-offer integrity still matches the canonical checkout contract; and
2. the credential-host collector just returned matching provider state whose observation is no more than 24 hours old under process-owned UTC.

It does **not** mean a buyer purchased, a contract was accepted, cash settled, or revenue was recognized.

## Failure modes

The compiler fails closed on missing/failing/noisy collector output; malformed or extra/missing fields; future/stale observations; inactive/non-live Payment Link or price; account/link/product/price/URL/metadata/currency/amount/quantity drift; bool/int aliases; second line items; pagination; caller/catalog time overrides; and coherent edits of repo-local readback plus repo-local digest metadata.

The historical compiler is preserved byte-for-byte as `host/right_now_revenue_core.py`; the wrapper owns only the current-provider boundary.
