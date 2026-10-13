# Right-now revenue control tower

This lane turns the existing offer catalog, offer-specific payment receipt,
smart-outreach evidence, provider-confirmed settled-cash evidence,
settled-award evidence, and canonical collision receipts into one deterministic
execution queue. It is deliberately larger than a new SKU: it joins what
Commons can sell, who has evidenced pain, what must not be resent, what has
actually been paid, what can happen next, and which external facts still block
direct offer revenue.

The compiler reads canonical public sources and every canonical outreach
suppression receipt. It validates prices against their owner catalogs, keeps
global cash / offer-specific payment / reply / acceptance facts separate,
reuses Smart Outreach's measured qualification decisions, ranks the work queue,
and emits SHA-256 receipts for every directly composed source.

```sh
python3 host/settled_cash.py validate revenue/right_now/settled_cash.json
python3 host/settled_cash.py summary revenue/right_now/settled_cash.json
python3 host/settled_awards.py validate revenue/right_now/settled_awards.json
python3 host/settled_awards.py summary revenue/right_now/settled_awards.json
python3 host/right_now_revenue.py compile
python3 host/right_now_revenue.py validate
python3 host/gpt_action_packets.py validate
python3 host/gpt_action_packets.py next
python3 -m unittest test_settled_cash.py test_settled_awards.py test_right_now.py test_right_now_execution.py test_right_now_checkout_authority.py test_smart_outreach.py test_gpt_action_packets.py
```

Buyer-facing first rung: [agent-triage.html](../../agent-triage.html).
Canonical $199 terms: [diagnostic_offer.json](./diagnostic_offer.json).
Settled cash: [settled_cash.json](./settled_cash.json).
Settled awards: [settled_awards.json](./settled_awards.json).
GPT packets: [action_packets.json](./action_packets.json).
Demand ledger: [demand_ledger.json](./demand_ledger.json).
Experiments: [experiments.json](./experiments.json).

`control.json` is the committed browser projection. `validate` fails whenever
the projection drifts from its sources, including a price, global cash,
offer-specific payment, settled cash, settled award, candidate, collision, or
hash change. `right-now.js` renders that exact snapshot without creating a
second ledger.

## Checkout-authority boundary

`active_chargeable_checkout` is not minted by the right-now catalog. The
compiler derives that fact from the canonical offer sources plus the
buyer-visible `data-checkout` anchors on the canonical product pages. The
reviewed authority root pins each offer's Stripe account, product, price,
payment-link identity, base payment URL, and retained provider receipt digest.
A retained offer must be `ACTIVE_VERIFIED`, its provider binding must carry the
live-mode evidence, and its verification timestamp may not postdate the catalog
evidence boundary. Every `data-checkout` anchor on the public page must resolve
to the pinned base payment URL; UTM/query decoration may vary.

The catalog boolean and its `LIVE_PUBLIC_CHECKOUT_PAGE` row are redundant
assertions only. They must reconcile exactly to that retained authority and no
second unbound live-checkout row may appear. Both the provider offer and public
page are SHA-256 source-receipted in the compiled control. This is still retained
evidence, not a fresh Stripe re-query: the compiler does not create, update,
charge, refund, or infer a purchase from the checkout.

## Settled-cash boundary

`settled_cash.json` records provider-confirmed USD payouts only after the
provider state is `PAID`. The Frantic row binds the payout to the exact provider
claim ID, provider receipt ID, bounty number, claimant, and merged result URL.
The ledger intentionally does not guess a Frantic posting URL when the posting
ID is not evidenced. The validator rejects duplicate cash, claim, receipt, and
idempotency IDs; non-canonical or non-positive amounts; non-PAID lifecycle
states such as SENT, MERGED, ACCEPTED, DELIVERED, FUNDED, or PENDING; malformed
public references; future evidence timestamps; bank/withdrawability promotion;
and repeat-collection instructions.

This is the authoritative source for global `collected_cash_usd`. The legacy
`revenue/payment_ready/current_receipt.json` remains an offer-specific GGUF
purchase-intent receipt and can truthfully remain at USD 0 while unrelated
provider cash is already settled. `NONE_DO_NOT_RESEND` is authoritative
collection suppression, not an instruction to request payment again.

## Settled-award boundary

`settled_awards.json` records sponsor-confirmed paid awards in their original
currencies. The validator rejects duplicate award IDs, duplicate idempotency
keys, non-canonical or non-positive amounts, malformed public references,
future payment dates, invented USD equivalents, availability promotion, and
repeat-collection instructions. Private receipt locators remain redacted.

A paid award is not automatically USD cash, bank availability, wallet custody,
or withdrawability. Currency totals stay separate. The 25 RTC award is not
converted into the USD cash total. `NONE_DO_NOT_RESEND` is authoritative
collection suppression, not an instruction to contact the sponsor again.

## Truth boundary

The control tower performs zero contact, transport, payment, acceptance,
conversion, withdrawal, or delivery actions. `READY_TO_DRAFT` is not
authorization to send. An intake is not payment, a merged result is not cash,
an offer-specific payment receipt is not the global cash ledger, and a public
quote is not buyer acceptance. Missing external facts stay explicit blockers
rather than being promoted into progress.

## Operator loop

1. Land first-party demand evidence in Smart Outreach.
2. Rerun its planner and preserve every collision / do-not-resend receipt.
3. Add provider-confirmed USD payouts only through the strict settled-cash ledger.
4. Add sponsor-confirmed non-USD paid awards only through the strict settled-awards ledger.
5. Compile this control snapshot.
6. Work the highest-ranked non-held queue item.
7. Record the real external event in its owner ledger.
8. Recompile; never hand-edit `control.json` into a better state.

Longer-horizon NOW, SOON, and LATER routes remain in the catalog and on the
commerce page. This control plane changes execution order, not ambition.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
