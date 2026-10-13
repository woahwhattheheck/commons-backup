# Diversey Proof-of-Clean — submission and release checklist

**This checklist does not authorize an external submission.** Candidate repository bytes are not human/legal/provider authority.

## A. Revalidate the opportunity

Immediately before external action:

- [ ] Re-open the official challenge page and confirm it is active.
- [ ] Confirm close remains 2026-09-21 23:59 US Eastern.
- [ ] Confirm award, eligibility, participation types, form fields, attachment rules, and submission-count limit.
- [ ] Read the current Challenge Agreement in full.
- [ ] Retain the exact reviewed Challenge Agreement generation and SHA-256 at the owner authority boundary.

## B. Applicant / eligibility — HUMAN ONLY

- [ ] Select the truthful participation type.
- [ ] Supply legal applicant/entity name and contact details.
- [ ] Confirm eligibility under the current challenge rules.
- [ ] Supply first-hand team roles, relevant experience, and project history.
- [ ] Confirm who has authority to submit and accept resulting obligations.

Do not infer identity, legal status, biographies, or authority from GitHub metadata.

## C. Technical truth

- [ ] Human technical owner confirms or revises working TRL 2.
- [ ] Every cited paper is checked against the attributed statement.
- [ ] Literature performance is never represented as CleanTrace performance.
- [ ] Final proposal says there is no integrated CleanTrace prototype unless new exact evidence exists.
- [ ] Detection limit, sensitivity, specificity, false-result rate, shelf life, and surface recovery remain unmeasured unless exact evidence exists.
- [ ] ≤25 minutes remains a design target, not an achieved result.
- [ ] Strain-level identification is not claimed without binder-specific validation.
- [ ] Whole-room assessment is not claimed for this surface-sampling v1 concept.

## D. Scientific / partner review

- [ ] Qualified biosensor/microbiology reviewer checks binder selection, electrode chemistry, sample handling, and validation plan.
- [ ] Target organisms come from a real professional-cleaning use case.
- [ ] Reference method and acceptance criteria are defined for future experiments.
- [ ] Viable-vs-nonviable detection requirement is explicit.
- [ ] Surface recovery and cleaning-chemical matrix effects are treated as separate validation problems.

## E. IP / legal review — HUMAN ONLY

- [ ] Current Challenge Agreement IP/license terms reviewed; acceptance is performed only by an authorized human.
- [ ] Ownership of the final proposal is understood.
- [ ] Phage/RBP source, access, and licensing path reviewed.
- [ ] Electrode/transducer chemistry IP reviewed.
- [ ] Freedom-to-operate/patentability claims removed unless supported by legal review.
- [ ] No third-party copyrighted text/figures are reused without permission.
- [ ] No confidential buyer/partner information is included without authorization.

## F. Human-authorship gate

The official challenge says submissions produced solely with generative AI are not of interest.

- [ ] Named applicant materially rewrites `PROPOSAL-DRAFT.md` into a separate final artifact.
- [ ] Human applicant supplies first-hand experience/skills and selects participation/partnering posture.
- [ ] Human applicant can independently explain mechanism, limitations, and development plan.
- [ ] Final text contains no `[HUMAN: ...]`, `[UNMEASURED ...]`, or `DO NOT SUBMIT THIS FILE VERBATIM` markers.
- [ ] Final text is checked for unsupported specificity, invented history, and marketing overclaim.
- [ ] Exact final proposal path + SHA-256 are entered in `readiness.json`.

## G. Candidate observations are not authority

`readiness.json.human_observations` may become `true` only when factually observed, but those booleans **cannot** authorize `READY` on their own.

`readiness.json.external_observations` must remain `false`. Never encode registration, submission, award, or payment as candidate booleans. Real provider events require retained evidence records at the trusted host boundary.

## H. Fixed host owner-release record — HUMAN / OWNER BOUNDARY

Before `READY`, retain this exact file outside the repository candidate tree:

`/var/lib/commons-authority/diversey-proof-clean-2026/owner-release.json`

The record must bind:

- [ ] schema `DIVERSEY_PROOF_CLEAN_2026_OWNER_RELEASE_V1`;
- [ ] carrier `DIVERSEY-RAPID-PROOF-CLEAN-2026`;
- [ ] operation `DIVERSEY-RECOVERY-AUTHORITY-ZIFK3N7-20260914`;
- [ ] decision `AUTHORIZE_SUBMISSION`;
- [ ] opaque applicant ID and reviewer ID;
- [ ] current Challenge Agreement generation + SHA-256;
- [ ] exact final-proposal SHA-256;
- [ ] exact source-bundle SHA-256 emitted by `validate_submission.source_bundle_sha256(...)` over retained source generations;
- [ ] every required human/legal/IP/authorship gate `true`;
- [ ] authorization time and validity window no later than the official deadline.

A release file inside the competition directory or a candidate-selected alternate path must not pass.

## I. Machine gate

Run from this directory:

```bash
python validate_submission.py
python -m unittest -v test_validate_submission.py
python validate_submission.py --require-ready
```

Expected pre-human state:

- structural validation: PASS with `state=BLOCKED`;
- hostile unit tests: PASS;
- `--require-ready`: exit code `2` while `state=BLOCKED`.

Do not change state to `READY` merely to make the final command green.

## J. Final release fence — HUMAN ONLY

Before any portal submit action:

- [ ] `state=READY` for factual reasons.
- [ ] All candidate human observations are true and separately backed by the fixed owner-release record.
- [ ] Current Challenge Agreement was actually reviewed/accepted by the authorized Solver, not by candidate JSON.
- [ ] Final proposal bytes match both `readiness.json` and the owner-release record.
- [ ] Owner-release source-bundle digest matches the exact retained source bytes.
- [ ] Applicant identity / participation type / partnership posture are correct.
- [ ] Verifier-owned UTC is still before the challenge deadline.
- [ ] Explicit owner authorization names this exact carrier/operation/proposal generation.

Only then may an authorized human/account owner cross the external portal release fence.

## K. Post-submission provider evidence

If an external event really occurs, retain one evidence record per event under:

`/var/lib/commons-authority/diversey-proof-clean-2026/events/*.json`

- `SUBMITTED` must bind the exact submitted proposal SHA-256 and provider receipt/source digest.
- `AWARD_RECEIVED` requires retained `SUBMITTED` evidence.
- `PAYMENT_RECEIVED` requires retained `AWARD_RECEIVED` evidence.
- Every event record needs provider-source identity, provider-source SHA-256, and observed UTC.
- Do not book expected award/payment as revenue.
- If Diversey proposes collaboration, preserve the exact communication and open a separate commercial-negotiation lane.
