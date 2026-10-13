# Worked example: a disputed case and a supplied correction

This is the recorded, strictly fictional `CASE-7001` / `SUBJECT-7001` journey. The normal and real optimized rehearsals both completed on 19 September 2026. Each retained the original snapshot and a separately supplied revision. The software did not infer, approve or apply corrections in another system.

| Retained packet | Reconciliation result | Current milestone | Issue count |
|---|---|---|---:|
| Baseline from `sample_case.json` | `REVIEW_REQUIRED` | `null`, status `AMBIGUOUS` | 5 |
| Revision from `revised_case.json` | `NO_DECLARED_BLOCKERS` | `REVIEW`, status `KNOWN` | 0 |

`NO_DECLARED_BLOCKERS` refers to these configured checks on supplied records. Both receipts retained all eight authority flags as false: underwriting, affordability, eligibility, fraud determination, customer contact, lender submission, commercial acceptance, and payment or revenue. No lending decision follows from this comparison.

## Read the five baseline findings

The baseline cutoff is `2026-09-18T14:00:00Z`. `BROKER-01` and `LENDER-01` supply their observations at 13:00 UTC. Every issue has severity `BLOCK` and its own explicitly linked action.

| Baseline issue / action | Code and subject | Supplied evidence and resulting finding |
|---|---|---|
| `ISSUE-0001` / `ACTION-0001` | `DOCUMENT_REQUIREMENT_UNMET`, `document:IDENTITY` | One distinct validated hash is required. The only identity hash is disputed, so the uncontested validated count is zero. The linked action asks for the required uncontested observations. |
| `ISSUE-0002` / `ACTION-0002` | `DOCUMENT_REQUIREMENT_UNMET`, `document:INCOME` | One distinct validated hash is required, and no income document observation is supplied. Its source list remains empty; the tool does not invent a responsible source. |
| `ISSUE-0003` / `ACTION-0003` | `DOCUMENT_STATUS_CONFLICT`, the identity hash | The broker declares `DOC-ID-01` validated; the lender declares the same document hash rejected. Both observations remain visible. The linked action asks for clarification of the contradictory declarations. |
| `ISSUE-0004` / `ACTION-0004` | `FIELD_CONFLICT`, `field:requested_amount` | The broker supplies GBP 25,000,000 minor units; the lender supplies GBP 24,500,000 minor units. Both values remain in the receipt. The linked action asks for reconciliation while preserving provenance. |
| `ISSUE-0005` / `ACTION-0005` | `MILESTONE_AMBIGUOUS`, `status_group:2026-09-18T10:00:00Z` | `EV-002` declares `DOCUMENTS` and `EV-003` declares `REVIEW` at the same time. The tool retains ambiguity instead of choosing by event ID. |

The full identity-hash subject is `document_hash:3cc6b61be99057c7c4657b50035f4f48a4bca571d87a555035eecd05cb2fe76e`. The identity requirement and status conflict are separate findings: one explains the unmet requirement, the other preserves the contradictory evidence that prevents counting the hash.

The 12:00 event `EV-004` is a request naming `INTAKE`. It stays in the four-event timeline but does not establish or roll back the current status. Opaque message references are retained; the tool does not retrieve any message.

The supplied money values are fictional record values, not quoted prices or recommendations. The declared document hashes come from fictional placeholder labels; no real identity or income document is included or authenticated.

## Inspect what the revision actually supplies

The revision retains the same case and subject identifiers and supplies a new cutoff of `2026-09-19T14:00:00Z`, with source observations at 13:00 that day.

| Supplied correction | Recorded consequence |
|---|---|
| The lender record now supplies GBP 25,000,000 minor units, matching the broker record | `requested_amount` is `ALIGNED`. The tool has not decided which historical amount was correct. |
| Both records now declare the same identity hash validated | The contradictory status finding is absent, and the identity requirement has one distinct uncontested validated hash. |
| Both records supply the same declared validated income hash | The income requirement has one distinct validated hash; repeated copies count once. |
| `EV-003` now has timestamp `2026-09-18T11:00:00Z`, after the 10:00 `DOCUMENTS` event | The supplied status sequence is unambiguous, with current milestone `REVIEW`. The later informational request remains in the history. |

These are explicit edits in a separately supplied fictional input, not corrections inferred by the software or authenticated changes from a live broker/lender. The original packet remains available with its five issues. Issue IDs belong to their own receipt; the recorded comparison joins issue code and subject and displays each packet's IDs. It does not assume numbered IDs stay stable after an issue set changes.

## Reproduce and inspect the handoff

From this component directory, choose a new output directory:

```sh
python -B rehearse_mortgage.py --output-dir /tmp/new-mortgage-worked-example
```

Read `READOUT.md` and `rehearsal.json`, then each packet's `summary.html`, `receipt.json` and `exceptions.csv`. The original supplied bytes are retained as each packet's `case.json`. Each packet includes its verifier source and can be checked from that packet directory with:

```sh
python -B mortgage_case_reconcile.py verify-bundle .
```

The accepted runs exercised eight CLI commands per mode. Both packet verifications passed; an intentionally edited receipt was rejected with exit 2, and an attempted overwrite was rejected with exit 2 while every existing packet file remained unchanged. All nine baseline files and all nine revised files matched byte-for-byte between the normal and optimized runs. [EXECUTION.md](EXECUTION.md) records commands, source pins, artifact identities and the proof boundary; [OPERATOR_GUIDE.md](OPERATOR_GUIDE.md) covers normal operation.

This completion preserves **Z-Quorum-7F2C / GPT-5.6 Sol** as the author of the original concept and damaged carrier in [issue 15959](https://github.com/woahwhattheheck/commons/issues/15959). It is a reconstruction against the retained contract, not a claim that the damaged source previously executed successfully.
