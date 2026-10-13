# Revenue funnel realization control

This module turns a retained evidence ledger into a deterministic portfolio view of:

`qualified -> proposed/claimed -> accepted/merged -> invoiced/awarded -> paid`

It exists because **activity is not cash**. A merge is not payment, an advertised amount is not an award,
an award is not a transfer, and a transfer with no retained provider receipt is not accepted as payment evidence.

## What it does

- derives stage from retained event evidence rather than a caller-supplied status;
- requires qualification before commercial progress, acceptance/merge before award/invoice, and award/invoice before payment;
- requires `PAYMENT_RECEIVED` to carry a positive amount and a retained `PROVIDER_RECEIPT`;
- keeps accepted/merged or invoiced/awarded but unpaid work `economically_unfinished`;
- separates DNR, new inbound, collision, and Muse evidence from economic stage;
- marks cheap unresolved items under the configured threshold as micro-batch candidates instead of pretending they are worth bespoke pursuit;
- canonicalizes the portfolio and emits a content-addressed semantic receipt;
- exact-recompiles during verification, so merely rehashing a forged packet does not make it valid.

## Trust / authority boundary

`truth_boundary` is `RETAINED_EVIDENCE_INPUT_NOT_PROVIDER_AUTHENTICATED`.

The compiler does **not** query Gmail, Slack, GitHub, a bank, Stripe, a customer, or a sponsor. It proves only that
the supplied retained evidence is internally consistent under this schema. All external-send, Muse-selection,
provider-mutation, invoice-creation, payment-movement, receivable-establishment, and revenue-recognition authority
bits are hard false.

A `PROVIDER_RECEIPT` row is therefore a retained claim about a provider receipt, not independent authentication of
the provider. Operators must bind real provider evidence before treating the output as current business truth.

## CLI

```bash
python -m revenue.revenue_funnel_control.engine compile input.json bundle.json
python -m revenue.revenue_funnel_control.engine verify bundle.json
```

Inputs are bounded regular files. Output is create-exclusive mode `0600`; existing output is never overwritten.

## Economic semantics

The portfolio sums only explicit `PAYMENT_RECEIVED` event values under `payment_received_by_currency`.
It never sums advertised/reference amounts into revenue and never converts currencies or project tokens.
If the payment target is unknown, the stage is `PAYMENT_RECORDED_TARGET_UNKNOWN`, not `PAID`.
