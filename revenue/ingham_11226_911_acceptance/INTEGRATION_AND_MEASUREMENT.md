# Vendor-neutral integration, governance, and measurement map

## Rule

Publicly named products below are **context**, not assumed 112-26 bidders, and no private interface/API is claimed. An authorized vendor/buyer must supply the actual integration contract before testing.

## Publicly observed environment / adjacent systems

| Publicly observed system/vendor | Public context | Evidence an evaluator would request if in tested workflow | What this package does NOT assume |
|---|---|---|---|
| CentralSquare Technologies / TriTech CAD | County support-renewal history | event identifiers, timestamps, test-environment export/ingest contract, immutable source reference, recovery behavior | no private API, no current 112-26 role, no write access |
| NiCE Public Safety / evidence & QA | public Ingham customer material around evidence/QA and supervisor workload | authorized recording/transcript reference contract, QA-case identity, audit/export behavior, retention boundaries | no current procurement role, no content access |
| Priority Dispatch / ProQA + simulator | County licensing/simulation history | authorized rubric/version identifiers, simulation-case identity, result/export contract | no scoring algorithm access, no right to alter dispatch protocol |
| PowerDMS | County policy/training platform activity | policy/training version references and approved test export if relevant | no current contract/role claim |
| INdigital | 2026 County authorization to negotiate telephony contract | only an authorized test interface/status contract if relevant | no claim negotiations closed or system is deployed |
| getResQ911 | County staffing-support contract discussion | workforce/process context only unless buyer explicitly includes it | no system integration, no 112-26 bidder claim |
| GovWorx / CommsCoach AI | 2025 County discussion of QA/training automation | only if buyer/vendor confirms current relevant scope; request versioned score/rubric/evidence outputs | no claim the 2025 authorization equals current production/112-26 status |

## Integration evidence contract

Before a connector or adapter is tested, obtain:

1. named system owner;
2. environment (`sandbox`, `test`, `staging`, or explicitly approved production change window);
3. interface version/schema;
4. authentication/role model;
5. allowed operations (read/write/action) and prohibited operations;
6. authoritative source-of-truth field mapping;
7. idempotency/retry semantics;
8. timeout/error semantics;
9. logging/audit requirements and restricted fields;
10. retention/deletion requirements;
11. rollback/reset process for test artifacts;
12. incident/escalation owner.

Unknown fields are blockers, not invitations to infer undocumented behavior.

## Human authority classes

Each action/output is classified before testing:

- `ADVISORY_ONLY` — software may generate evidence/recommendation; human owns decision.
- `HUMAN_APPROVAL_REQUIRED` — software may prepare an action but cannot execute without attributable approval.
- `AUTOMATED_TEST_ALLOWED` — may execute only inside the approved non-production test envelope.
- `HUMAN_ONLY` — no automated execution.
- `PROHIBITED` — stop.

Nothing in this generic workshare authorizes autonomous emergency dispatch, emergency-resource selection, caller triage, alteration of live records, or interruption of live communications.

## Data boundary

Default test data is synthetic or properly de-identified. Before any restricted data is admitted, the authorized buyer/vendor must define at least:

- data classification (including CJI/PII/PHI or other protected classes when relevant);
- minimum necessary fields and permitted purpose;
- approved environment/storage/egress path;
- role/identity controls;
- encryption requirements;
- retention/deletion policy;
- telemetry/redaction rules;
- model/provider data-use constraints;
- incident response and breach/escalation path;
- whether test evidence itself becomes a public record or must be protected.

No restricted payload belongs in this public repository.

## Workforce / quality instrumentation

Every metric needs a named source system, measurement window, denominator, exclusions and owner. No baseline is invented.

| Metric | Reproducible definition |
|---|---|
| QA coverage | evaluated eligible interactions / eligible interactions in agreed population |
| QA denominator loss | eligible interactions omitted without explicit failure disposition / eligible interactions; target zero |
| Review labor | attributable reviewer minutes / evaluated interaction |
| QA agreement | product-human agreement / independently adjudicated gold-set cases, with class-level breakdown where valid |
| Escalation rate | cases routed for human resolution / evaluated cases |
| Rework rate | accepted cases later materially corrected/reopened / accepted cases |
| Coaching throughput | attributable coaching actions completed / agreed period |
| Time-to-coaching | coaching completion timestamp - qualifying QA event timestamp |
| Training throughput | completed approved simulation/training cases / learner / window |
| Training retry burden | repeat attempts / completed approved training cases |
| Supervisor manual load | measured manual minutes on agreed QA/training tasks / window |
| Analyst manual load | measured manual minutes on agreed evidence/QA tasks / window |
| Duplicate-effect rate | duplicate external effects / logical test actions; target zero |
| Failure-to-stop rate | invalid/unsafe fixtures causing prohibited effect / invalid/unsafe fixtures; target zero |
| Human-gate fidelity | human-gated effects with attributable prior approval / all human-gated effects; target 100% |
| Evidence completeness | accepted actions/results with complete lineage receipt / accepted actions/results |
| Recovery burden | failed test instances requiring manual recovery + minutes-to-recover |
| Queue/processing latency | completed processing timestamp - accepted-for-processing timestamp, distribution not just average |
| Hiring/onboarding throughput | only if the actual product scope contains hiring: completed agreed assessment/onboarding stages / window |

## Benefit-claim rule

A statement such as “coverage improved,” “review time fell,” or “staff hours were freed” is allowed only after the underlying before/after evidence is produced with comparable populations and exclusions. Forecasts are clearly labeled. Vendor marketing metrics are not treated as achieved County outcomes.

## Acceptance owner model

A real engagement should name separate people/roles for:

- operational workflow owner;
- security/privacy/data owner;
- vendor technical owner;
- independent test/evidence owner;
- human QA/adjudication owner;
- procurement/contract owner;
- final acceptance authority.

TJLabs can own the bounded test/evidence work if contracted. It does not self-appoint as County acceptance authority.