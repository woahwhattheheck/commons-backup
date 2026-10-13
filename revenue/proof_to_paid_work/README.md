# Proof-to-Paid Work Conversion Kit

This package turns a bounded paid-work record into reusable **internal** conversion material while failing external payment/revenue claims closed.

It does **not** replace `revenue/verified_paid_proof/**`. That package is the authority boundary for real payment/publication claims. `proof_to_paid_work` consumes the same conservative premise: caller-supplied task, merge, acceptance, provider, email, Slack, or receipt references are **assertions**, not independently authenticated proof.

## What this adds

The missing commercial layer is reusable structure around an already-evidenced paid-work lifecycle:

- strict provenance/admission record for task source, advertised native-currency amount, delivered/merged work, acceptance refs, and settlement assertion;
- native-currency guard: v1 refuses cross-currency settlement conversion entirely;
- internal buyer-neutral case-study draft;
- generic public-safe case-study template;
- fixed-fee QA/integration/repair service menu with explicit acceptance criteria;
- direct advertised-bounty payment-request draft that links merged/accepted work and asks for the advertised amount/currency, with no eligibility fishing;
- hard-false outbound/provider/publication/revenue authority;
- deterministic SHA-256 receipt over the normalized private envelope plus public generic template.

## Public/private boundary

**Never commit real settlement input or `--private-json` output.**

Private material may contain sponsor labels, exact task/work URLs, private evidence references, settlement assertions, and a direct payment-request draft. The public renderer intentionally emits only generic templates and `PROPOSED_NOT_ACCEPTED` reference services. It contains no named sponsor, engagement ID, evidence reference, settlement amount, work URL, buyer identity, or real payment/revenue claim.

A real public payment claim requires a separately authoritative, publication-safe result from `revenue/verified_paid_proof` or a future successor. The current raw `verified_paid_proof` generation is intentionally fail-closed.

## Native-currency rule

If an advertised task is denominated in a non-USD asset (for example a sponsor token), keep the award in that asset. Do not convert it to USD merely because a settlement is asserted. v1 refuses settlement currency/decimal mismatches and emits no USD conversion field.

## Payment-request rule

A payment-request draft is emitted only when:

- work state is `MERGED` or `ACCEPTED`;
- settlement is not asserted `SETTLED`;
- the advertised amount/currency and public work URL are present.

The template is intentionally direct:

> The work is merged/accepted here: `<work URL>`
>
> Please send the advertised `<amount> <currency>` award for this work.

It does not ask whether the contributor is eligible.

## Service menu

The checked-in public template exposes three buyer-neutral hypotheses, all `PROPOSED_NOT_ACCEPTED`:

- $5,000 / 5-business-day Evidence Reconciliation Diagnostic;
- $15,000 / 10-business-day Integration & Acceptance Sprint;
- $10,000 / 10-business-day Deterministic Repair Sprint.

Each has explicit acceptance criteria and exclusions. None is staffing, platform replacement, a buyer commitment, or recognized revenue.

## Run

```bash
python -m revenue.proof_to_paid_work revenue/proof_to_paid_work/example.synthetic.json
python -m revenue.proof_to_paid_work revenue/proof_to_paid_work/example.synthetic.json --public-json
# PRIVATE INPUT-ASSERTION AUDIT OUTPUT. Never publish or commit this stream.
python -m revenue.proof_to_paid_work revenue/proof_to_paid_work/example.synthetic.json --private-json
```

## Test

```bash
python -m unittest revenue.proof_to_paid_work.test_core -v
python -O -m unittest revenue.proof_to_paid_work.test_core -v
python -m compileall -q revenue/proof_to_paid_work
```

The fixture is synthetic and uses `example.invalid`. Real provider/mailbox/Slack receipt identifiers are intentionally absent from this public repository.

## Authority ceiling

No network, prospect contact, email/DM send, Muse request, provider mutation, payment initiation, payout collection, customer acceptance, receivable, booked/recognized revenue, token valuation, or publication authority. A generated payment-request draft is text only and still requires the governing single-writer/outbound process before transmission.
