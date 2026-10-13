# Evidence-bound commercial experiment lab

`revenue/commercial_experiment_lab` answers a different question from the commercial funnel:

> Given a caller-recorded cohort and arm assignment, which segment × offer × proof-package × route arm is associated with stronger evidenced outcomes — **without pretending the caller proved when that experiment was declared**?

It does not send outreach, discover leads, mutate a CRM, or decide that an account may be contacted. It compiles the real `revenue/commercial_funnel` input first and uses that package's normalized opportunity outcomes as the only source of REPLY / ACCEPTANCE / CASH truth.

## Why this exists

Commons already distinguishes traffic, reply, acceptance, delivery, transfer and cash. That prevents false promotion of weak outcome evidence. The experiment lab adds deterministic cohort/arm analytics while keeping a strict boundary around a harder fact: v1 cannot independently authenticate when the caller created its plan, assignments or thresholds. Therefore v1 is **descriptive-only** and emits no expand/pause/keep-testing strategy recommendation.

Message count is never a success metric here. An arm can only improve its commercial outcome metrics when the upstream funnel has evidence for stronger stages.

## Caller-recorded plan and assignment model

Input schema: `commons-commercial-experiment-input/v1`.

A plan declares:

- stable `id` and `revision`;
- one offering `family`;
- immutable plan source reference and UTC `declared_at`;
- the complete opportunity-ID cohort;
- 2–32 arms;
- per-arm `segment`, exact upstream `offer_id` + `offer_version`, `proof_package`, and `route_class`;
- a minimum eligible sample per arm;
- caller-recorded integer-basis-point thresholds retained as historical metadata only; v1 never treats them as authenticated predeclaration or strategy authority.

Assignments bind each recorded opportunity exactly once to one arm. Every assignment must:

1. occur at or after plan declaration;
2. occur before the opportunity's **first upstream funnel event**;
3. bind an exact immutable evidence reference;
4. match the upstream opportunity family and exact offer identity.

A missing assignment, duplicate/cross-arm opportunity assignment, timestamp that is not internally ordered before the first upstream event, family mismatch, or offer rewrite is a hard refusal. These checks prove consistency of the supplied record, **not** real-world predeclaration chronology.

The lab validates immutable-reference **shape** offline. It does not independently authenticate Git hosting, commit time, remote bytes, plan creation time, assignment creation time, or threshold declaration time. Every packet therefore records `chronology.state: SELF_ASSERTED_UNVERIFIED`, sets all three chronology-authentication flags to `false`, and sets `strategy_recommendations_authorized: false`. Provider/source chronology must be added by a future independently verifiable authority before this product may claim a predeclared experiment.

## Outputs

A successful compile creates, exclusively:

- `report.json` — deterministic analytical body;
- `report.csv` — one row per arm;
- `report.md` — human review summary;
- `packet.json` — report body plus output hashes;
- `receipt.json` — content-addressed receipt binding experiment identity, upstream funnel identity, packet and outputs.

Input identity is order-independent: it binds the normalized recorded plan + normalized assignments + the upstream funnel semantic `input_sha256`, not arbitrary JSON list order.

## Metrics

Only upstream opportunities whose state is `FUNNEL_PACKET_READY_FOR_HUMAN_REVIEW` enter performance rates or cash totals. Held opportunities remain visible. Because experiment chronology is self-asserted, **no arm can receive an expand/pause/keep-testing recommendation in v1**.

Per arm:

- assigned / eligible / held counts;
- cumulative stage counts;
- cumulative stage reach in exact integer basis points;
- adjacent stage transition rates in basis points;
- lower-median integer seconds from TRAFFIC to REPLY / ACCEPTANCE / CASH;
- gross, reversal and net cash by currency with **no implicit FX conversion**;
- `DESCRIPTIVE_ONLY` strategy status with exact reasons, including the chronology limitation and any upstream HOLD / self-asserted sample note.

Pairwise arm deltas are always labelled `OBSERVATIONAL_NOT_CAUSAL`.

## Strategy status and chronology boundary

Every arm has exactly one v1 strategy status: `DESCRIPTIVE_ONLY`. The reasons always include `SELF_ASSERTED_CHRONOLOGY_UNVERIFIED`; they may additionally report `UPSTREAM_HOLD_PRESENT` or `SELF_ASSERTED_MINIMUM_SAMPLE_NOT_MET`.

This is deliberate fail-closed behavior. A caller can take a completed funnel, inspect the outcomes, backdate `declared_at` / `assigned_at`, rewrite the arm metadata or thresholds, and reseal syntactically valid source references. v1 cannot distinguish that history from a genuinely predeclared experiment because it has no independently observed chronology authority. The receipt will bind whatever record was supplied, but it will **not** promote that record into authenticated predeclaration evidence or strategy advice.

A future version may add strategy recommendations only when plan + assignment existence and chronology are independently read back from an authority whose exact bytes and observed timestamps can be verified.

## CLI

Compile with trusted process UTC (there is intentionally no caller-selected production `--as-of`):

```bash
python -m revenue.commercial_experiment_lab.cli compile \
  revenue/commercial_experiment_lab/example_input.json \
  --out-dir /tmp/commercial-experiment-lab
```

Byte-verify the recorded historical compilation:

```bash
python -m revenue.commercial_experiment_lab.cli verify \
  revenue/commercial_experiment_lab/example_input.json \
  --packet /tmp/commercial-experiment-lab/packet.json \
  --receipt /tmp/commercial-experiment-lab/receipt.json \
  --report-json /tmp/commercial-experiment-lab/report.json \
  --report-csv /tmp/commercial-experiment-lab/report.csv \
  --report-md /tmp/commercial-experiment-lab/report.md
```

Exit codes: `0` success, `2` malformed/refused I/O/input, `4` verification mismatch.

Library callers may pass an explicit `as_of` to `compile_experiment` for deterministic historical replay/tests. Production CLI compilation always uses process UTC.

## Authority ceiling

Every packet and receipt explicitly sets all of these to `false`: buyer contact, send/resend, mailbox/CRM/provider mutation, calendar booking, proposal/bid submission, contract/signature, pricing commitment, payment request/collection, bank/wallet action, fulfillment, cash-availability assertion, accounting/tax authority, and revenue recognition.

Existing DNR, suppression, consent, collision, provider and owner controls remain authoritative.

## Development gate

```bash
python -m py_compile revenue/commercial_experiment_lab/*.py
python -m unittest -v revenue.commercial_experiment_lab.test_compiler revenue.commercial_experiment_lab.test_cli
python -O -m unittest -v revenue.commercial_experiment_lab.test_compiler revenue.commercial_experiment_lab.test_cli
```

The repository checkout additionally runs an integration test through the real `revenue.commercial_funnel` compiler.
