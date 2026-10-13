# Conversion attribution ledger

Read-only compiler over owner-retained snapshots. Answers **what converted, what is actually paid, what is fulfillment-ready, and what is blocked** without double-counting provider events or inventing revenue.

Closes [commons#14413](https://github.com/woahwhattheheck/commons/issues/14413). Original spec credit: `ZOT-V5K9`.

## States

| State | Meaning |
|---|---|
| `PAID_ATTRIBUTED_READY` | One settled provider event bound to exactly one offer and one lead; offer is not source-red/not-ready; latest fulfillment generation is `READY`. |
| `PAID_FULFILLMENT_BLOCKED` | Settled and uniquely bound, but offer is `SOURCE_RED`/`NOT_READY` or fulfillment is missing/`BLOCKED`/`STALE`/`UNKNOWN`. |
| `ATTRIBUTION_REVIEW` | Settled payment with missing or unknown offer/lead binding. Never enters totals. |
| `UNPAID_PIPELINE` | Qualified lead with no settled attributed payment. Not cash. |

`settled_payment_minor` is a summary of supplied settled-payment facts inside one currency. `cash_collected` and `revenue_recognized` are never asserted.

## CLI

```bash
python revenue/conversion_attribution_ledger/conversion_attribution_ledger.py compile \
  --input examples/happy.json \
  --json-out ledger.json \
  --markdown-out ledger.md

python revenue/conversion_attribution_ledger/conversion_attribution_ledger.py verify \
  --input examples/happy.json \
  --ledger ledger.json
```

Outputs are create-exclusive. Symlink destinations are refused.

## Fail-closed

- duplicate payment ids / duplicate economic `provider_event_id`
- currency mismatch between payment and bound offer
- bool/float/non-finite/unsafe integer money
- unknown fields, malformed UTC timestamps, duplicate JSON keys
- JSON `Infinity`/`NaN`

No provider write, outbound send, Stripe mutation, fulfillment action, or spend authority.
