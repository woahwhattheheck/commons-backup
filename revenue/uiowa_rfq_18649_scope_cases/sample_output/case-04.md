# CASE-04 — Wording preference that does not miss an acceptance criterion

Disposition: **PRIME_JUDGMENT_NOT_DEFECT**.
Request class: `wording_preference`.
Phase: **draft** / artifact `RIS-SW-F02`.
Payment effect: **NONE_SECTION_2_UNCHANGED**.
Exhibit blob: `48465060fff1402af966871352e894686fffe05e`.

## Request

Prime prefers the draft finding say 'opportunity' instead of 'gap' without changing the cited observation.

Exact example edit:

```
If the prime direction is editorial only, replace the word 'gap' with 'opportunity' in RIS-SW-F02. Keep SRC-018 and the technical observation unchanged.
```

## Before

```
RIS / software / F-02: Automated unit-test gating is a gap on the documented service pipeline. [SRC-018]
```

## After

```
RIS / software / F-02: Automated unit-test gating is an opportunity on the documented service pipeline. [SRC-018]
Editorial wording preference applied. Source ID and observation unchanged. Not scored as artifact nonconformance.
```

## Rationale

No Section 5 criterion is missed: the conclusion still traces to SRC-018, the 12-cell frame is intact, and no product/vendor claim is introduced. Section 5.2.6 treats a wording preference as a bounded prime comment, not a defect. Section 9 keeps University-facing narrative with the prime. Zero incremental fee. Section 2 unchanged.

## Source clauses

- **§5.2.6** `S5_2_6_COMMENTS` — Comments that correct TJLabs artifact nonconformance are incorporated; comments that require prime judgment, new evidence, or scope change are recorded as bounded open items.
- **§9** `S9_PRIME_JUDGMENT` — The prospective prime retains professional judgment, benchmarking conclusions, final recommendations, University-facing narrative, and contracting authority.
- **§10** `S10_PROTOCOL` — TJLabs corrects actual artifact nonconformance, documents a blocker, or identifies the request as a scope/evidence/judgment change. Exhibit remains nonbinding until authorized writing.

## Effort (labeled hypothetical)

- Class: `editorial_preference`
- Hours (hypothetical): 0
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
