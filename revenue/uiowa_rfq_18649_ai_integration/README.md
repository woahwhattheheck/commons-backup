# UIOWA-080 — AI integration and portability readiness

A runnable, vendor-neutral **architecture assessment**, not an AI runtime or a production-readiness certification. Three fictional systems compare synchronous assistance, asynchronous jobs and retrieval-assisted drafting. The result connects recommendation IDs to capabilities, interfaces, data movement, latency, availability, ownership, maintenance and migration effort.

Work order: demo-channel UIOWA-080, parent `1789824784.872159`. Operation: `uiowa-080-quartzp80x-20260919`. Builder: ZZ-QUARTZ-P80X / GPT-6 Astra Pro. Internal build record: Commons issue 16121. This isolated kit does not modify the workbench, compiler, deployment configuration or access controls. It contains no University observations, commercial product selections or live service calls.

## Run the complete sample

Python 3.10+ syntax; actually tested with Python 3.13.5. Standard library only. Run from the repository root:

```sh
KIT=revenue/uiowa_rfq_18649_ai_integration
python "$KIT/example_cases.py" --out /tmp/uiowa-080/cases.json
python "$KIT/assess.py" /tmp/uiowa-080/cases.json --out /tmp/uiowa-080/report
python -m unittest discover -s "$KIT" -p 'test_assess.py' -v
python -O -m unittest discover -s "$KIT" -p 'test_assess.py'
```

The fixture generator is the authoritative, editable source for all three examples. It expands the shared reference patterns into an ordinary, self-contained `cases.json`; the evaluator does not depend on the generator or on inheritance. Do not interpret the generator's fictional `demonstrated` records as experiments performed against real infrastructure.

Outputs are `assessment.json` (full inputs, checks, numeric details and questions), `assessment.md` (human-readable comparison and interview backlog), and `checks.csv` (one row per case/alternative/check). Each carries the exact input-byte SHA-256. JSON retains numeric nulls; Markdown prints UNKNOWN. CSV labels that could be evaluated as spreadsheet formulas are prefixed with an apostrophe; it is a presentation export, not a lossless input format. JSON is the lossless handoff.

`PATTERNS.md` supplies the three reference architectures, a reusable decision worksheet, interface examples and fictional observation records. `REHEARSAL.md` records an actual local run and its validation scope.

## Input contract

The generated fixture is a complete editable example. Validation is implemented in `assess.py`; malformed data raises `InputError`, and the CLI returns status 2. A well-formed assessment can contain unknown estimates and can report conflicts without failing execution. That distinction prevents a missing estimate from turning into a zero or a false successful assessment.

| Field | Contract |
|---|---|
| `schema_version` | Exactly `1.0`. |
| `synthetic` | Boolean. A document with synthetic evidence cannot be relabeled false. This label is provenance, not an independent authenticity check. |
| `basis` | Nonblank explanation of observations, estimates and limitations. |
| `evidence` | ID-to-record object. Each record has `kind` (`synthetic`, `retained`, `assumption`), nonblank `locator` and `note`. References resolve locally; this tool does not fetch or verify external evidence bytes. |
| `cases` | Nonempty list, unique IDs. Each case has `id`, `title`, `recommendation_id`, `requirements` and nonempty `alternatives`. |
| `requirements.response_budget_ms` | Maximum response/acknowledgement budget; nonnegative number or null. |
| `requirements.completion_deadline_ms` | Submission-to-result deadline, including queue/review delays; null is UNKNOWN for async and not applicable for sync when no separate deadline is required. |
| `requirements.response_availability_target` | Probability in [0,1], or null; scoped to the declared response path, not AI usefulness or job completion. |
| `requirements.availability_window` | Common observation/planning window ID, or null. Every dependency must match it before a bound is calculated. |
| `requirements.allowed_zones` | Explicit list of acceptable processing/storage zones, or null. An empty list permits no listed flow zone; it is not the same as unknown. |
| `requirements.max_retention_days` | Nonnegative days or null, applied to each retained flow record. This is a supplied design constraint, not a legal conclusion. |
| `requirements.required_capabilities` | List of distinct capability labels. |
| `requirements.monthly_maintenance_hours`, `migration_budget_hours` | Nonnegative capacity/effort budget or null; not currency and not cash savings. |
| `requirements.core_must_continue_without_ai` | Boolean or null, separately assessed from the availability of AI responses. |

Each alternative has a unique `id`, a `pattern` (`synchronous_assist`, `asynchronous_job`, `retrieval_assist`), `suitable_when`, `tradeoffs`, `change_option`, `capabilities` and `evidence_refs`.

| Alternative field | Contract |
|---|---|
| `latency_basis` | `planning_envelope` or `measured_bound`. Percentile summaries cannot be added as if they were joint end-to-end bounds. |
| `response_stages` | Nonempty serial stages with unique `name` and `ms: {low, high}`. Either endpoint can be null; the total is then incomplete. |
| `completion_stages` | Nonempty serial submission-to-completion path for async. Use `[]` for sync/retrieval; completion then equals response. Include acknowledgement, queue wait and human-review wait where applicable. |
| `response_dependencies` | Nonempty unique-name records with `availability` in [0,1] or null, and matching `window`. These must describe the complete declared serial response dependency set. |
| `independence_assumed` | Explicit boolean. False by default in the examples. A true value exposes a separate independence estimate but never substitutes it for the bounds used by the check. |
| `integration_tasks` | Nonempty unique-name items with `hours: {low, high}` and `owner_role` or null. One-time implementation, training and integration work. |
| `maintenance_tasks` | Nonempty unique-name items with `hours_per_month: {low, high}` and `owner_role` or null. Recurring work, not added to one-time effort. |
| `migration_tasks` | Nonempty unique-name items with `hours: {low, high}` and `owner_role` or null. A later portability exercise, reported separately to avoid double-counting. |
| `data_flows` | Nonempty unique-ID records: `source`, `destination`, `payload`, `zone`, `retention_days`, `minimization`. Zone, retention and minimization can be null. |
| `owners` | Role names or null for `integration`, `support`, `data`, `evaluation`, `change`. These are responsibilities, not employee performance ratings. |
| `portability` | Entries for `request_response_contract`, `prompt_export`, `evaluation_replay`, `adapter_swap`, `data_export`. Each has `state`, `note`, `evidence_refs`. |
| `degraded_mode` | `behavior`: `core_continues`, `manual_queue`, `blocks_core`, or `unknown`; `tested`: boolean/null; nonblank `note`; `evidence_refs`. A claimed successful test requires a resolvable reference. |

Intervals require exactly `low` and `high`; they must be nonnegative, finite and ordered. Booleans are not numbers. Duplicate JSON keys, duplicate record IDs, nonfinite constants, aggregate overflow and unresolved references are rejected. Missing known-input facts remain null rather than being manufactured.

## Decision semantics

`conflict` means an explicit assumption/constraint mismatch. `unknown` means required information is missing or incomparable. `conditional` means a range overlaps a budget, a capability is asserted without its retained exercise, or a degraded behavior still needs validation. `supported_by_inputs` means all applicable checks fit the supplied inputs; it is **not** a recommendation to deploy. `not_applicable` remains visible.

Overall precedence is conflict, then unknown, then conditional, then input-supported. All individual checks remain in the exports, so this summary cannot hide an unknown behind a known conflict. The tool does not rank vendors or maturity levels and does not select a design automatically. The architecture owner considers business consequences and alternatives using the worksheet.

For a complete serial envelope, the low total is the sum of low endpoints and the high total is the sum of high endpoints. These are planning envelopes, not percentiles, confidence intervals or forecasts. Parallel work must first be reduced into a justified stage envelope; this evaluator is not a general dependency-graph simulator. An incomplete stage produces a null total and a separately labeled known-low subtotal.

For response components with comparable probabilities `p_i`, the intersection of component-up events has lower bound `max(0, sum(p_i) - (n-1))` and upper bound `min(p_i)`. These bounds do not assume independence. The optional independent estimate is `product(p_i)`. They describe the modeled component-up event only: unmodeled dependencies, an incomplete response path, semantic quality, incompatible populations or nonstationary behavior are not magically covered. Mismatched/unknown windows produce UNKNOWN. An already-known upper bound below the target can establish a conflict even when another component is unknown.

## Interface to the wider delivery kit

Use `case.id`, `case.recommendation_id`, `alternative.id`, `pattern`, `checks` and `input_sha256` as the stable join fields. `checks.csv` carries them per check; `assessment.json` carries the full supporting evidence and numeric units. Other assessment components must not interpret these design-check states as institutional maturity scores. The toolkit generates no external actions.

For an actual engagement, replace the fictional input with agreed response/completion expectations, retained dependency observations with matching windows, actual data movement/retention facts, current owners, staff-capacity estimates and an export/replay/fallback exercise. Keep uncertainty explicit, distinguish stated from observed practice and retain the source version behind each changed conclusion. Scope, University facts and final professional judgment remain with the engagement team.
