# CASE-02 — Prime disputes a technically supported conclusion

Disposition: **PRIME_JUDGMENT_NOT_DEFECT**.
Request class: `disputed_supported_conclusion`.
Phase: **draft** / artifact `IAM-SEC-F11`.
Payment effect: **NONE_SECTION_2_UNCHANGED**.
Exhibit blob: `48465060fff1402af966871352e894686fffe05e`.

## Request

Prime believes IAM MFA coverage should be scored Established rather than Partial.

Exact example edit:

```
Do not rewrite IAM-SEC-F11. Record a prime-owned judgment overlay. Leave the source-traced Partial conclusion in place unless new authorized evidence is supplied.
```

## Before

```
IAM / security / F-11: MFA coverage for interactive admin paths is Partial. [SRC-022 digest d1e2]
```

## After

```
IAM / security / F-11: MFA coverage for interactive admin paths is Partial. [SRC-022 digest d1e2]
PRIME-JUDGMENT-OPEN: prospective prime disputes Partial vs Established. Overlay recorded; technical conclusion unchanged. Not an artifact defect.
```

## Rationale

Section 5.3: a disagreement with a technically supported conclusion is not by itself an artifact defect. SRC-022 traces the Partial finding. Section 9 keeps professional judgment with the prime. Section 5.2.6 records the comment as a bounded open item rather than converting it into a silent score change or a payment dispute. No Section 2 rewrite.

## Source clauses

- **§5.3** `S5_3_DISAGREEMENT` — A disagreement with a technically supported conclusion is not by itself an artifact defect. Rejections should identify the affected artifact and criterion.
- **§5.2.6** `S5_2_6_COMMENTS` — Comments that correct TJLabs artifact nonconformance are incorporated; comments that require prime judgment, new evidence, or scope change are recorded as bounded open items.
- **§9** `S9_PRIME_JUDGMENT` — The prospective prime retains professional judgment, benchmarking conclusions, final recommendations, University-facing narrative, and contracting authority.
- **§10** `S10_PROTOCOL` — TJLabs corrects actual artifact nonconformance, documents a blocker, or identifies the request as a scope/evidence/judgment change. Exhibit remains nonbinding until authorized writing.

## Effort (labeled hypothetical)

- Class: `prime_judgment_overlay`
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
