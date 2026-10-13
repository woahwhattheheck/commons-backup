# Outreach Yield Observatory

A deterministic, provider-agnostic **read-only** evaluator for de-identified outbound evidence.

The tool exists to answer a narrow business question safely: after an outreach cohort has had time to mature, which segment/offer/route combinations have enough observed evidence to deserve more human review?

It does **not** send messages, access Gmail/Slack/CRM providers, select recipients, reserve leads, recognize revenue, or claim causality.

## Input

Pass one JSON object:

```json
{
  "schema_version": 1,
  "as_of": "2026-09-14T16:00:00Z",
  "maturation_hours": 72,
  "policy": {
    "min_matured_exposures": 20,
    "min_positive_reply_ppm": 100000,
    "max_dnr_ppm": 50000,
    "min_paid_scope_acceptances": 1,
    "min_payment_evidenced": 0
  },
  "events": [
    {
      "prospect_key": "lead-7f28",
      "experiment_id": "hotel-ops-v1",
      "segment": "independent-hotel",
      "offer": "paid-discovery",
      "route": "email",
      "event": "SENT",
      "at": "2026-09-10T12:00:00Z"
    },
    {
      "prospect_key": "lead-7f28",
      "experiment_id": "hotel-ops-v1",
      "segment": "independent-hotel",
      "offer": "paid-discovery",
      "route": "email",
      "event": "HUMAN_REPLY",
      "at": "2026-09-10T14:00:00Z",
      "evidence_ref": "provider-message:opaque-ref"
    }
  ]
}
```

`prospect_key` and `experiment_id` must be stable de-identified identifiers. Dimensions reject `@` and control characters so raw email addresses do not accidentally become analytics keys. `evidence_ref` must also be an opaque non-PII reference; values containing `@` are rejected rather than retained in analytics evidence.

Supported lifecycle events:

- `SENT`
- `BOUNCE`
- `DNR`
- `HUMAN_REPLY`
- `POSITIVE_REPLY`
- `PAID_SCOPE_ACCEPTED`
- `PAYMENT_EVIDENCED`

Every outcome event requires `evidence_ref`. Positive reply requires explicit human-reply evidence; paid-scope acceptance requires positive-reply evidence; payment-evidenced requires paid-scope-acceptance evidence. A bounce or DNR cannot coexist with the reply path.

`PAYMENT_EVIDENCED` means only that the supplied evidence labels payment as evidenced. It is **not** cash receipt, booked revenue, accounting recognition, or settlement truth.

## Maturation discipline

Rates use only exposures whose `SENT` timestamp is at least `maturation_hours` old at `as_of`. Immature exposures remain visible but do not enter the denominator. Even an early reply does not shorten the cohort's maturation window.

This prevents a common failure mode: comparing a fresh cohort whose non-responders have not had time to respond with an older cohort whose denominator is actually mature.

Rates are integer parts-per-million (PPM), rounded half-up with integer arithmetic for deterministic output.

## Signals

Signals are conservative review gates:

- `LEARN_MORE`: support or policy evidence gates are not met.
- `STOP_DNR_REVIEW`: matured DNR rate breaches the configured maximum.
- `SCALE_REVIEW`: configured evidence gates pass.

`SCALE_REVIEW` is **not** permission to send. The report explicitly requires a human to re-check current lead claims and provider state before any external action.

Defaults are operational defaults, not universal truths; callers can pass an explicit `policy`.
The policy value must be an object or `null` for defaults; arrays and scalar
values are input errors. The schema version must be the integer `1`.

## CLI

```bash
python host/outreach_yield_observatory.py evidence.json --format json
python host/outreach_yield_observatory.py evidence.json --format markdown -o report.md
```

The CLI is file-in/file-out only. It has no provider client or network code.

## Determinism and fail-closed rules

Exact normalized lifecycle replay is idempotent. Overlapping export pages can
repeat the same `SENT` or outcome row without aborting the report or inflating
exposure counts, rates, or evidence signals. A repeated event kind with a changed
timestamp, evidence reference, or other retained field remains an error.

The evaluator rejects:

- naive or future timestamps;
- missing `SENT`;
- conflicting duplicate lifecycle events for one prospect/experiment;
- inconsistent segment/offer/route within one exposure;
- reply-path events before `SENT`;
- positive/accept/payment events missing their explicit evidence chain;
- contradictory DNR/bounce plus reply-path outcomes;
- obvious raw email-like identifiers, dimensions, and evidence references;
- unknown schema keys.

Cohorts are ranked deterministically using evidence state only. Ranking never performs an action.
