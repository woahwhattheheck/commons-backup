# CASE-03 — Newly supplied evidence during draft review

Disposition: **EVIDENCE_DEPENDENCY_HOLD**.
Request class: `newly_supplied_evidence`.
Phase: **draft** / artifact `IAM-SEC-HOLD`.
Payment effect: **NONE_SECTION_2_UNCHANGED**.
Exhibit blob: `48465060fff1402af966871352e894686fffe05e`.

## Request

Prime forwards a synthetic IAM MFA policy excerpt after the draft packet, asking that the IAM/security HOLD be flipped to supported.

Exact example edit:

```
Add SRC-031 to the register as newly supplied, unauthorized-for-promotion until digest/currentness compile. Keep IAM-SEC cell HOLD. Do not promote unknown evidence.
```

## Before

```
IAM / security: HOLD — no authorized MFA policy in the evidence register.
Register: (no SRC for IAM MFA policy).
```

## After

```
IAM / security: HOLD — SRC-031 newly supplied (synthetic fixture POL-IAM-MFA-v3 excerpt) is registered but not yet digest-bound or currentness-compiled. Unknown/new evidence is not promoted to a supported state.
Register: SRC-031 kind=policy owner=prime currentness=uncompiled digest=UNKNOWN.
```

## Rationale

Section 5.2.3 forbids silently promoting missing or untrusted evidence to a supported state. Section 3 requires blocked items to be identified rather than fabricated. The new bytes are recorded as a dependency. This is not new AIS-group scope and does not rewrite the draft delivery trigger in Section 2. If a material new evidence universe arrived after an accepted final generation, that would be Section 7 change-control instead.

## Source clauses

- **§5.2.3** `S5_2_3_NO_PROMOTE` — Missing, stale, conflicting, or untrusted evidence is visibly bounded and cannot silently promote a cell to a supported state.
- **§3** `S3_NO_FABRICATE` — Blocked items are identified; unavailable inputs are not fabricated.
- **§5.2.6** `S5_2_6_COMMENTS` — Comments that correct TJLabs artifact nonconformance are incorporated; comments that require prime judgment, new evidence, or scope change are recorded as bounded open items.
- **§2** `S2_TRIGGERS` — Kickoff is written-authorization triggered; draft is delivery triggered; only the final base milestone is acceptance-triggered. Artifact cure does not rewrite those triggers.

## Effort (labeled hypothetical)

- Class: `in_base_evidence_processing`
- Hours (hypothetical): 2
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
