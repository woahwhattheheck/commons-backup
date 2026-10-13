# Incident-learning data dictionary and integration contract

Schema identifier: `uiowa-incident-learning/v1`. JSON is the canonical record. `contract.validate(data)` raises `ValueError` for invalid structure; `contract.load(path)` additionally rejects duplicate JSON object keys. `analyze.analyze(data)` returns a new derived report without mutating the packet. All identities are strings, unique within their respective collections. Unknowns are explicit nulls or empty evidence lists, never zero-valued maturity ratings.

## Packet

| Field | Type / meaning |
|---|---|
| schema | Exact schema identifier above. |
| classification | `synthetic` or `engagement`; rendered prominently. The shipped fixture is synthetic only. |
| as_of | ISO-8601 timestamp with explicit timezone/UTC offset. Deterministic assessment cutoff, not the wall clock. |
| sources | Source records keyed by `id`. |
| incidents | Sampled incident records keyed by `id`. |
| conditions | Contributing-condition records keyed by `id`. |
| actions | Unique corrective-action records keyed by `id`; many incidents may refer to one action. |

## Sources and conditions

A source has `id`, `kind`, `observed_at`, `locator`, and `excerpt`. Kinds are `interview`, `incident_record`, `implementation`, `verification`, `measurement`, and `decision`. `observed_at` means the retained evidence's evidentiary time, not today's import time. Later ingestion can preserve the original time; an artifact whose relevant event time is unknown should not be relabeled to satisfy chronology. Sources later than `as_of` are rejected. Locators are retained references, not automatically fetched or authenticated. The fixture resolves every locator to a heading in the generated `synthetic-evidence.md`.

A condition has `id`, `description`, `evidence_ids` and optional `shared_dependency` context. Empty evidence means the condition requires corroboration. A description is not itself proof. Condition occurrence counts describe the supplied incident set and must not be treated as independent group votes or exposure-normalized rates.

## Incidents

Required fields: `id`, `group` (`ESS`, `RIS`, `IAM`), `service`, `impact`, `coverage` (`complete`, `partial`, `unknown`), `evidence_ids`, `condition_ids`, `events`, and `review`.

Each event has `kind`, `at`, `note`, and `evidence_ids`. One canonical milestone is allowed for each of `impact_start`, `detected`, `coordinated`, `mitigated`, `restored`, `verified`, `reviewed`. Missing stages are allowed and reported. For repeated mitigation attempts, preserve source locators and explain which canonical milestone was selected. Intervals use retained incident/verification evidence for both endpoints; interviews alone do not qualify as measured timelines.

Known impact/detection cannot follow restoration; restoration cannot follow verification; verification cannot follow review. Coordination and mitigation are not forced into a universal sequence, and detection may precede visible impact. All recorded event timestamps must be at or before `as_of`. No local-time or timezone guess is made.

`review` contains `analysis` text, `analysis_evidence_ids`, `sharing_evidence_ids`, and `unresolved_questions` (strings). Boolean support flags in the output mean references exist; they do not establish completeness, agreement, source authenticity or the quality of causal reasoning.

## Actions

| Field | Type / meaning |
|---|---|
| id / description | Unique action and intended practice or behavior change. |
| incident_ids / condition_ids | Nonempty reference lists. Conditions must occur in at least one linked incident. |
| status | Reported state: `open`, `in_progress`, `closed`, or `replaced`. Preserved separately from derived evidence state. |
| owner_role | Organizational continuation role, or null. Do not use individual performance scores. |
| created_at | Aware timestamp at/before as-of. |
| due_at | Aware timestamp or null; not earlier than creation. Future due dates are allowed. |
| completed_at | Aware timestamp or null; within creation/as-of bounds. |
| implementation_evidence_ids | Sources of kind implementation; may be empty. |
| verification_evidence_ids | Sources of kind verification; may be empty. |
| replacement | Null, or object with `action_id`, nonempty `reason`, and `evidence_ids` of kind decision. |
| effectiveness | Null, or descriptive measurement pair defined below. |

A replacement must resolve to another action and preserve every original contributing condition. Replacement cycles are rejected. Missing decision evidence is represented as `replacement_unsubstantiated`, not silently omitted. Contradictions between reported status and supplied completion/replacement records are surfaced. `implementation_verified` requires a reported closed state, completion time, implementation evidence no later than completion, and verification evidence no earlier than completion. These are declared-evidence checks; an analyst must still assess relevance and sufficiency.

`overdue_unresolved` is true when `as_of > due_at` and neither an evidenced implementation nor documented replacement resolves the original record. Equality at the due instant is not overdue. `days_past_due = (as_of - due_at) / 86,400 seconds`, rounded to three decimals. The display precision does not establish clock accuracy. Verified late completions expose `late_completion_days` separately. Unknown due time does not mean on time; it produces a named issue and no invented due date.

## Descriptive effectiveness

The object has `metric` (one defined event rule across both windows), `direction` (`lower` or `higher`), and `before`/`after` windows. Each window contains `start`, `end`, `events`, `exposure`, `unit`, `cohort`, `complete` (boolean), and `evidence_ids` (measurement sources). Counts are nonnegative integers or null; booleans are not counts. Multiple events per exposure unit are allowed, so this is not implicitly a success probability. Positive exposure is required for comparison.

Both windows must have start < end <= as-of, and before.end <= after.start. The baseline cannot extend beyond implementation, and follow-up cannot start before completion. Evidence that predates its claimed complete window prevents comparison. Same unit/cohort, retained measurement evidence and complete coverage are required. Missing data produces `not_comparable` with reasons; no measure produces `not_measured`. A comparable pair produces `observed_improvement`, `unchanged`, or `observed_deterioration` based on exact fractions. Rates are `events / exposure * 1,000`. These are descriptive, not statistical or causal conclusions. The operator must check event-definition consistency and changes hidden by a reused cohort name.

## Exports

JSON preserves the incident, action, condition and source arrays, the classification, cutoff, named limitations, and unique-action counts. Markdown includes timelines, action evidence states, limitations, condition traces and full source appendix. The CSV is an action view, not a complete packet: **each data cell contains a JSON-encoded value**. Decode each cell with `json.loads` to recover strings, null, arrays, booleans and objects. Ordinary CSV quoting preserves Unicode, multiline fields and embedded commas. JSON strings begin with a literal quote, preventing formula-looking strings from becoming bare spreadsheet formulas. No spreadsheet formulas are generated.

Each CSV row retains the complete analyzed action, including its `description` and `replacement` decision. These two columns follow the original 17 columns, preserving their order for existing readers. A replacement cell is either JSON `null` or the supplied object containing its successor `action_id`, `reason` and `evidence_ids`; the successor remains its own action row with its own evidence state. Exporting a documented replacement does not mark that successor complete. The CSV still omits packet-level context and the incident, condition and source arrays; retain the JSON report or original packet alongside it when those records are needed.

For integration, retain IDs and locators when mapping to the existing workshare evidence register. Any maturity characterization must be determined by the wider assessment method, not by renaming action states as levels. Merge duplicate IDs deliberately; never concatenate two packets without reconciling their identifier namespaces and source versions.
