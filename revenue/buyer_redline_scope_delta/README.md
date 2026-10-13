# Buyer / Prime Redline → Paid-Scope Delta

Operation: `BUYER-REDLINE-TO-PAID-SCOPE-DELTA-20260916-AEGISZ`

A deterministic internal compiler for comparing one retained **proposed-not-accepted** SOW/offer against a buyer or prime counter-draft. It turns source-bound commercial/contract deltas into an owner-review packet without accepting terms, signing anything, giving legal advice, or silently absorbing expanded scope.

## Decisions

Only five machine decisions exist:

- `ACCEPTABLE_AS_WRITTEN` — no semantic clause or commercial-header delta was detected. This is **not acceptance or signature authority**.
- `OWNER_REVIEW` — operational/commercial semantics changed and a human owner must decide.
- `REQUOTE_REQUIRED` — scope, deliverables, schedule, price/currency, or adverse payment timing changed; prior economics must not be silently reused.
- `LEGAL_REVIEW_REQUIRED` — IP, liability/warranty, or termination language changed. This is routing to qualified human review, **not legal advice**.
- `HOLD_CONTRADICTION` — source generation/category/currency/logical-key contradictions prevent a trustworthy decision.

Precedence is HOLD → LEGAL → REQUOTE → OWNER → unchanged.

## Source contract

Each document carries:

- stable document ID and generation;
- exact source URL/repository-relative locator;
- retained source SHA-256;
- observed timestamp with timezone;
- `truth_state=PROPOSED_NOT_ACCEPTED`;
- document currency, proposed total price in minor units, and payment days;
- categorized clauses with stable logical keys and structured scalar terms.

The counter must name the exact baseline generation it edits. A stale generation is a HOLD. The compiler never fetches or mutates a provider; source hashes are retained evidence bindings for an upstream custody process.

## Categories

`SCOPE`, `DELIVERABLES`, `ACCEPTANCE`, `PRICE_PAYMENT`, `SCHEDULE`, `DATA_SECURITY`, `IP`, `LIABILITY_WARRANTY`, `TERMINATION`, `DEPENDENCIES`, `ASSUMPTIONS`.

Changed IP/liability/warranty/termination language routes to legal review. Changed scope/deliverables/schedule or document/currency/price/payment economics can force a requote. Deleted/modified acceptance criteria are always surfaced.

## Strictness

CLI JSON uses a strict loader:

- duplicate object keys are rejected;
- `NaN`/`Infinity` are rejected;
- booleans cannot masquerade as integer money/timing values;
- unsafe traversal paths and HTTPS userinfo are rejected;
- Unicode is not silently normalized, so byte/semantic differences stay visible;
- duplicate logical keys produce `HOLD_CONTRADICTION`;
- clause-category drift across one logical key produces `HOLD_CONTRADICTION`;
- conflicting clause/header currencies produce `HOLD_CONTRADICTION`.

No `assert` carries production safety logic. Tests run both normal and `python -O`.

## Five-minute synthetic demo

```bash
python revenue/buyer_redline_scope_delta/compile_redline.py compile \
  --input revenue/buyer_redline_scope_delta/fixtures/requote.synthetic.json \
  --out-dir /tmp/redline-demo

python revenue/buyer_redline_scope_delta/compile_redline.py verify \
  --input revenue/buyer_redline_scope_delta/fixtures/requote.synthetic.json \
  --packet /tmp/redline-demo/packet.md \
  --receipt /tmp/redline-demo/receipt.json
```

The fixture expands one workflow to two while holding price flat and widens payment from net-30 to net-45. Expected machine decision: `REQUOTE_REQUIRED`.

## Tests

```bash
python -m unittest discover -s revenue/buyer_redline_scope_delta/tests -p 'test_*.py' -v
python -O -m unittest discover -s revenue/buyer_redline_scope_delta/tests -p 'test_*.py' -v
```

Hostiles include deleted acceptance, scope expansion without price change, currency drift, wider payment terms, unlimited liability, IP changes, stale baseline generation, duplicate/conflicting logical keys, category drift, header/clause currency conflict, boolean money, unsafe paths, URL userinfo, Unicode normalization differences, duplicate JSON keys, non-finite JSON, receipt/packet tampering, fail-on-HOLD behavior, and optimized-Python execution.

## Authority boundary

The output is an internal owner-review artifact. It cannot:

- sign or accept a buyer/prime draft;
- provide a legal opinion;
- send email, Slack, portal submissions, forms, or DMs;
- create an invoice or payment link;
- mutate CRM, provider, accounting, payment, or contract state;
- infer award, accepted work, cash, payment, or revenue.

Any later external message remains a separate owner-controlled workflow and, under the current swarm operating model, requires a fresh Muse single-writer collision election immediately before send.
