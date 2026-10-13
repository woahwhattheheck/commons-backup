# CASE-01 — Broken citation in a draft finding

Disposition: **ARTIFACT_CURE_IN_SCOPE**.
Request class: `broken_citation`.
Phase: **draft** / artifact `ESS-SEC-F03`.
Payment effect: **NONE_SECTION_2_UNCHANGED**.
Exhibit blob: `48465060fff1402af966871352e894686fffe05e`.

## Request

Draft finding ESS-SEC-F03 cites SRC-404, which is not in the delivered evidence register.

Exact example edit:

```
Replace `[SRC-404]` on ESS-SEC-F03 with an explicit HOLD. Do not invent a substitute observation.
```

## Before

```
ESS / security / F-03: Privileged-access reviews are performed annually. [SRC-404]
```

## After

```
ESS / security / F-03: HOLD — citation SRC-404 is not present in the delivered evidence register. No substitute observation is invented. Cell remains HOLD until a register source ID is supplied.
```

## Rationale

Section 5.2.1 requires every populated technical conclusion to trace to a source ID in the delivered register. SRC-404 is absent, so the populated conclusion is genuine TJLabs artifact nonconformance. Section 7 says a small correction of that kind is not new scope. Section 2 is unchanged: draft remains delivery-triggered; this cure is not a payment event.

## Source clauses

- **§5.2.1** `S5_2_1_TRACE` — Every populated technical conclusion traces to one or more source IDs.
- **§5.2.3** `S5_2_3_NO_PROMOTE` — Missing, stale, conflicting, or untrusted evidence is visibly bounded and cannot silently promote a cell to a supported state.
- **§7** `S7_CURE_NOT_SCOPE` — A small correction to a TJLabs-authored artifact that fails an agreed acceptance criterion is not treated as a new scope item.
- **§2** `S2_TRIGGERS` — Kickoff is written-authorization triggered; draft is delivery triggered; only the final base milestone is acceptance-triggered. Artifact cure does not rewrite those triggers.

## Effort (labeled hypothetical)

- Class: `in_scope_defect_correction`
- Hours (hypothetical): 1
- Incremental USD: $0
- Label: **HYPOTHETICAL / NOT ACCEPTED**

## Section 2 triggers (unchanged)

| Milestone | Share | Amount | Trigger | Acceptance-triggered |
|---|---:|---:|---|---|
| kickoff | 40% | $9,600 | written_authorization | False |
| draft_technical_work_package | 40% | $9,600 | delivery | False |
| final_technical_work_package | 20% | $4,800 | acceptance | True |

## Notes

- $24000 is TJLabs subcontract workshare, not the prime all-inclusive bid fee.
- Artifact cure is not a payment trigger rewrite (Section 2).
- Unknown evidence is never promoted to a supported state.
- Technical disagreement is not automatically a defect.
- New work is proposed, not silently added.
- Effort figures are HYPOTHETICAL / NOT ACCEPTED.
- This packet is not an invoice, acceptance, submission, or schedule.
