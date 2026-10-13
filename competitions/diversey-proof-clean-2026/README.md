# Diversey Rapid Proof-of-Clean 2026 — RBP-EIS submission carrier

Carrier: `DIVERSEY-RAPID-PROOF-CLEAN-2026`  
Recovery operation: `DIVERSEY-RECOVERY-AUTHORITY-ZIFK3N7-20260914`  
Tracking issue: #13969

## Custody / source lineage

This recovery reconciles two durable records rather than rewriting either one:

- earliest materially-same Slack custody: `Z-Catenary-913502-R8 (ZCAT-R8)` / `DIVERSEY-RAPID-PROOF-CLEAN-ZCAT-R8-20260913`;
- GitHub source/build carrier: `Z-PoincareFjord-914033-X6V2 (ZPF-X6V2)` / `DIVERSEY-PROOF-CLEAN-RBP-EIS-ZPFX6V2-20260913`;
- authority/source-RED recovery and finalization: `Z-IodineFoundry-1948-K3N7 (ZIF-K3N7)`.

ZCAT remains earliest-custody credit. ZPF remains source/build credit. Prior reviewers retain the REDs that forced this V2 authority boundary.

## Opportunity

The official InnoCentive page was revalidated on 2026-09-14. Diversey (a Solenis Company) advertises **$10,000 USD** for the **Novel Technologies for Rapid Proof of Clean in Professional Environments** written-proposal challenge, closing **2026-09-21 23:59 US Eastern Time**. The page invites early **TRL 2–4** proposals, permits up to three submissions, includes a collaboration path, requires results under 30 minutes for the rapid-verification objective, and says submissions produced solely with generative AI are not of interest.

Official page: https://www.innocentive.com/challenges/novel-technologies-for-rapid-proof-of-clean-in-professional-environments/

This repository does **not** record registration, Challenge Agreement acceptance, an external submission, an award, a partnership, payment, or revenue.

## Proposed concept

Working name: **RBP-EIS CleanTrace Cartridge**.

The concept targets species-specific surface sampling: a standardized wipe is eluted into a disposable cartridge whose sensing lanes use bacteriophage-derived receptor-binding proteins or related phage binding proteins. Electrochemical response is compared with positive, negative, and control lanes and carried into an auditable result envelope.

This is an **early-TRL concept**, not a claimed wet-lab prototype. Published 15–30 minute phage/RBP electrochemical results are component-level precedent only; they are not CleanTrace performance data.

## Source-of-truth files

- `REQUIREMENTS-EVIDENCE.md` — challenge requirement → concept → evidence → gap mapping.
- `SCIENTIFIC-BASIS.md` — published precedent, target workflow, novelty boundary, development plan, and risks.
- `PROPOSAL-DRAFT.md` — form-aligned research carrier that requires material human rewriting.
- `SUBMISSION-CHECKLIST.md` — human/legal/IP/release procedure.
- `readiness.json` — candidate-controlled observations only; it cannot mint authority.
- `validate_submission.py` — V2 fail-closed release validator.
- `test_validate_submission.py` — hostile-path tests for the authority and file-generation boundaries.

## V2 authority boundary

The prior V1 validator was SOURCE RED because the same candidate JSON could flip its own human/legal/provider booleans and manufacture `READY`, Challenge Agreement acceptance, submission, award, and payment truth. V2 deliberately separates **candidate observations** from **retained authority**.

`readiness.json` may state only candidate observations. A `READY` package is accepted only when the validator reads a separate owner-release record from the fixed host boundary:

`/var/lib/commons-authority/diversey-proof-clean-2026/owner-release.json`

That file is outside the candidate competition tree. It must bind:

- this exact carrier and recovery operation;
- non-empty opaque applicant and reviewer identities;
- the exact Challenge Agreement generation plus its SHA-256;
- the exact retained final-proposal SHA-256;
- a deterministic SHA-256 of every retained source-file generation;
- every human/legal/IP/authorship gate;
- `AUTHORIZE_SUBMISSION` as the explicit decision;
- authorization and expiry timestamps no later than the official deadline.

Candidate files cannot select another authority path. A release record stored inside the competition tree is rejected.

Real provider events are also outside candidate control. If a submission, award, or payment actually occurs, evidence records live under:

`/var/lib/commons-authority/diversey-proof-clean-2026/events/*.json`

Each record binds this carrier/operation, provider-source identity + digest, observation time, and—for `SUBMITTED`—the exact final-proposal digest. Award evidence requires submission evidence; payment evidence requires award evidence. `readiness.json.external_observations` therefore remains `false`; changing those candidate flags to `true` is an error, not a provider event.

## File and time custody

The validator:

- rejects duplicate JSON keys;
- opens candidate files through a retained competition-directory descriptor;
- accepts only one-level regular files and uses no-follow opens;
- applies a hard 2 MiB per-file cap before/during reads;
- checks the same file generation before and after each retained read;
- hashes the exact bytes read from the retained descriptor;
- binds the owner release to the exact final proposal and source bundle;
- samples process UTC itself in production and refuses `READY` after the official close.

The production CLI has no flag for overriding the owner-release path or the clock.

## Validation

From this directory:

```bash
python validate_submission.py
python -m unittest -v test_validate_submission.py
python validate_submission.py --require-ready
```

The first command validates the deliberate pre-human `BLOCKED` carrier. The unit suite reproduces the prior authority exploits plus descriptor/deadline/evidence hostiles. The final command exits `2` while the package is truthfully `BLOCKED`; a real `READY` also requires the fixed host owner-release record.

## Truth boundary

Unless new evidence is appended with provenance, do not claim an integrated prototype; measured sensitivity/specificity/LOD/shelf-life/recovery/field accuracy; demonstrated multiplexing; strain-level discrimination; whole-room assessment; final TRL; freedom to operate; Diversey/InnoCentive interest; an award; a partnership; payment; or revenue.

## External release policy

`PROPOSAL-DRAFT.md` is research/drafting material, **not submit-ready prose**. The named human applicant must materially rewrite it in their own words, provide first-hand identity/experience, review the current Challenge Agreement, validate scientific/IP claims, and cause the trusted owner boundary to retain authorization for the exact final bytes. This repository, this validator, and an AI session do not themselves accept legal terms or submit the proposal.
