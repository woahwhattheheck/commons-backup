# Accepted Work to Cash Reconciler

`accepted_work_to_cash_reconciler` is the operational composition layer above
`revenue_funnel_control`. The upstream compiler proves an evidence-bound economic
stage; this module answers the next narrower question:

> Given retained acceptance, route, contact and cash-related evidence, what is
> the next **owner action** for each item without accidentally authorizing a send,
> invoice, payment mutation, receivable, accounting entry, or revenue claim?

It exists for merged/delivered work, paid-work platforms, subcontract/workshare
promises, accepted proposals, invoices/payment links, sponsor adjudications, and
retained payment evidence. It is deliberately stricter than either "merged = paid"
or "a second retained ref/hash = authenticated provider cash."

## Important boundaries

- `MERGED` alone becomes `MERGED_WORK_ONLY`, not buyer/sponsor acceptance.
- `ACCEPTED` is externally accepted only when its retained source class is
  `BUYER_MESSAGE` or `SPONSOR_MESSAGE`.
- A retained `PAYMENT_RECEIVED` event is **not** provider-authenticated cash.
- `payment_confirmations` are retained caller-supplied confirmation assertions.
  They must bind an upstream payment event and obey chronology/bounds, but this
  generation has no provider adapter or independently authenticated provider-byte
  boundary. Therefore they can enrich review context but can never produce a
  terminal paid/done state.
- Copying the exact upstream payment ref + digest is rejected as duplicate retained
  evidence. A different ref, a different digest, a route-evidence ref/digest, or a
  copied retained digest is still unauthenticated and remains `VERIFY_PROVIDER_CASH`.
- `DONE_PAID` is intentionally unavailable in this generation. Terminal paid truth
  requires a future separately authenticated, source-bound provider object proving
  the exact opportunity/payment/amount/provider transaction.
- New contact is never authorized. If contact is the next step and a source-bound
  route exists, the product emits `MUSE_REQUIRED` with exact recipient + purpose.
  Even a historical `MUSE_CLEAR` event does not become reusable send authority.
- A prior outbound becomes `WAIT_EXTERNAL`; `DNR` becomes `INBOUND_ONLY`;
  collision becomes `HOLD_COLLISION`; a later human inbound becomes
  `INBOUND_REVIEW`.
- Same-second contact evidence is fail-closed instead of ordered by arbitrary
  lexical event ids: DNR wins, collision wins, and simultaneous inbound+outbound
  becomes `HOLD_CONTACT_AMBIGUITY` until separately resolved.
- Queue order is by deterministic realizability band, then opportunity id. Headline
  amount is reported but never used to rank the queue.
- All authority bits are hard false.

## Composition contract

Input schema: `TJL_ACCEPTED_WORK_TO_CASH_V1`

The document contains:

1. `funnel_input`: the ordinary `TJL_REVENUE_FUNNEL_V1` source ledger. This module
   calls the merged upstream compiler itself rather than trusting caller-authored
   stage labels. The upstream engine module is sealed on first normal import before
   a downstream first import can capture its compiler/verifier exports; ordinary
   pre-import export reassignment/deletion therefore fails closed.
2. `routes`: zero or one evidence-bound route per opportunity. Route evidence must
   be a buyer/sponsor message, provider directory, or organizer rules source.
3. `payment_confirmations`: zero or one retained, unauthenticated confirmation
   assertion per upstream `PAYMENT_RECEIVED` event, keyed by opportunity id +
   payment event id. These assertions are integrity-bound into the packet/receipt
   but are explicitly not provider authentication.

The compiler emits a content-addressed
`TJL_ACCEPTED_WORK_TO_CASH_BUNDLE_V1` and the verifier recompiles both the upstream
funnel semantics and the reconciler semantics from embedded input.

The packet truth boundary is
`COMPOSED_RETAINED_EVIDENCE_NOT_PROVIDER_AUTHENTICATED`. Summary fields also expose
`provider_authenticated_payment_evidence_available=false` and
`terminal_paid_requires_provider_authenticated_evidence=true` so downstream code
cannot silently reinterpret retained confirmation assertions as provider truth.

The ordinary-module semantic-root boundary is documented in
`SEMANTIC_ROOT_BOUNDARY.md`. It covers both post-import reconciler-global rebinding
and review `5233132461`'s pre-import upstream-export poisoning predecessor. Direct
module-`__dict__` mutation, custom/meta-path loaders, installed-source replacement,
function default/closure/code mutation, interpreter replacement, and host takeover
remain outside this metadata boundary.

## Terminal actions

Representative terminal actions are:

- `VERIFY_PROVIDER_CASH`
- `RECONCILE_PAYMENT_EVIDENCE`
- `INBOUND_REVIEW`
- `MUSE_REQUIRED`
- `WAIT_EXTERNAL`
- `INBOUND_ONLY`
- `HOLD_COLLISION`
- `HOLD_CONTACT_AMBIGUITY`
- `OWNER_INVOICE_PREPARATION_REVIEW`
- `ACCEPTANCE_EVIDENCE_REQUIRED`
- `ROUTE_EVIDENCE_REQUIRED`
- `DONE_ZERO_VALUE`

`OWNER_INVOICE_PREPARATION_REVIEW` is an internal review state only. The authority
map still forbids invoice creation or delivery. `DONE_ZERO_VALUE` is available only
for upstream zero-settlement-target work; it is not a payment assertion.

## CLI

```bash
python -m revenue.accepted_work_to_cash_reconciler.engine compile \
  revenue/accepted_work_to_cash_reconciler/example.json /tmp/work-to-cash.bundle.json

python -m revenue.accepted_work_to_cash_reconciler.engine verify \
  /tmp/work-to-cash.bundle.json
```

CLI input is a bounded regular UTF-8 JSON file with duplicate keys, floats,
non-finite constants and oversized integers rejected. Output is create-exclusive
mode `0600` and is never silently overwritten.

## Tests

```bash
python -m py_compile \
  revenue/revenue_funnel_control/__init__.py \
  revenue/accepted_work_to_cash_reconciler/*.py \
  test_accepted_work_to_cash_reconciler.py \
  test_accepted_work_to_cash_reconciler_hostile.py \
  test_accepted_work_to_cash_reconciler_semantic_root.py \
  test_accepted_work_to_cash_reconciler_preimport_upstream_seal.py
python -m unittest -v \
  test_accepted_work_to_cash_reconciler.py \
  test_accepted_work_to_cash_reconciler_hostile.py \
  test_accepted_work_to_cash_reconciler_semantic_root.py \
  test_accepted_work_to_cash_reconciler_preimport_upstream_seal.py
python -O -m unittest -v \
  test_accepted_work_to_cash_reconciler.py \
  test_accepted_work_to_cash_reconciler_hostile.py \
  test_accepted_work_to_cash_reconciler_semantic_root.py \
  test_accepted_work_to_cash_reconciler_preimport_upstream_seal.py
```

The hostile suites retain exact predecessors for arbitrary invented confirmation
bindings, route-evidence relabeling, copied payment digests, exact self-copy,
same-second contact ambiguity, post-import semantic-root rebinding, and pre-import
upstream compiler/verifier/factory export poisoning. The root tests are enrolled by
the existing Commons `test_*.py` retained-test path. This product intentionally adds
no new standalone workflow slot; exact-head CI is read from the retained Commons
battery before merge.
