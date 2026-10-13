# OHSU Digital Pathology IMS — qualification and synthetic integration evidence

Evidence-only internal tooling for **OHSU RFP-2027-2012, Digital Pathology Image Management System**.

## Why this exists

OHSU's public procurement page lists the opportunity as issued **2026-09-11** and due **2026-10-11**. The public description requires an enterprise digital-pathology IMS with bi-directional Epic Beaker integration, end-to-end clinical pathology workflows, centralized image management/view/share/analyze capability, and scalable native/third-party AI and image-analysis integration across clinical, educational, and research missions.

Critically, OHSU's listing also tells respondents to read and confirm **minimum requirements contained in the RFP document**. The public summary therefore is not enough to establish bidder eligibility.

This pack turns that boundary into code:

- `qualification.py` is the deterministic candidate/replay compiler. It binds opportunity identity and public source, requires a captured full-RFP digest, explicit minimum-qualification rows, and evidence for every mandatory row.
- The candidate bundle carries a content-addressed `requirements_manifest` and completeness-attestation record. Those hashes prove internal consistency, but because they travel with the candidate they are **not** sufficient positive authority for the current requirement universe.
- `current_authority.py` is the current-positive-authority boundary. Its supported CURRENT APIs accept only a payload or exact JSON bytes. They spawn a fresh Python `-I -S` verifier process; caller-selected clocks, trust roots, root paths, and launcher arguments are not API inputs.
- The isolated verifier owns wall-clock sampling and reads the approved completeness-attestation SHA-256 only from `/etc/commons/ohsu_digital_pathology_ims/trusted_completeness.sha256`.
- The retained root is fail-closed: POSIX no-follow descriptor traversal, root ownership for production ancestors/root, no group/other writable ancestors, exact regular-file / one-link / private-mode checks, bounded exact bytes, stable descriptor generation, and final visible pathname-generation equality.
- A deterministic caller-injected root/time seam remains available only as `evaluate_historical_with_root`; its schema is explicitly historical and it **always** emits `decision=HOLD` and `current_authority=false`, even when the supplied root matches.
- The production root is deliberately not checked into this repository. Until a concrete independent completeness review approves and separately provisions it, current evaluation remains `HOLD`.
- A public-listing-only capture deterministically remains `HOLD`; it can never silently become bidder qualification.
- Receipts explicitly deny outreach, intent-to-bid, proposal submission, clinical use, payment, and buyer-acceptance authority.
- `integration_contract.py` provides a PHI-free synthetic bidirectional Beaker↔IMS trace model without claiming Epic certification or clinical interoperability.

## Completeness authority boundary

The in-bundle manifest records:

- the exact full-RFP SHA-256;
- exact total and mandatory requirement counts;
- a canonical digest over `{id, mandatory, text}` for every captured minimum;
- one non-empty source locator for every requirement ID;
- an independent completeness-review record containing reviewer identity, artifact reference, manifest-core digest, and its deterministic SHA-256.

Those bindings catch stale and internally inconsistent rewrites, but the candidate can re-mint them after replacing the requirement universe. Current `READY_FOR_INTERNAL_BID_REVIEW` therefore additionally requires the candidate completeness-attestation digest to equal the independently retained verifier root.

Do **not** populate the production trust root by reading the digest back from the candidate currently being evaluated. The root has authority only when it comes from a separately approved completeness review and is retained outside the candidate bundle under the custody contract above.

## Current versus historical authority

`qualification.evaluate(payload, evaluated_at=...)` remains deterministic history/replay machinery. It does not establish right-now authority on its own.

`current_authority.evaluate_current(payload)` and `evaluate_current_bytes(raw)` are the supported current paths. Their function signatures expose no root, clock, verifier path, or launcher selector. The imported module's helper globals are not the authority process: the actual CURRENT receipt is created by a fresh isolated child, so ordinary parent-process monkeypatching cannot substitute a root or clock.

`evaluate_historical_with_root(...)` is intentionally injectable for reconstruction and tests, but structurally cannot emit CURRENT authority. Its receipt is separately truth-labeled `HISTORICAL_INTEGRITY_ONLY_V2`, forced to `HOLD`, and `current_authority=false`.

`READY_FOR_INTERNAL_BID_REVIEW` is internal evidence state only. It does **not** mean OHSU has accepted the bidder, Epic has certified an integration, an IMS is clinically validated, or anyone may contact OHSU, register, submit an intent, submit a proposal, sign, spend, invoice, collect payment, or recognize revenue.

## Validation

```bash
cd revenue/ohsu_digital_pathology_ims
python -m py_compile qualification.py current_authority.py integration_contract.py cli.py test_qualification.py test_current_authority.py test_integration_contract.py test_cli.py
python -m unittest -v
python -O -m unittest -v
python cli.py fixtures/public_listing_only.json
```

The focused suite covers the original qualification/integration contract plus predecessor killers for:

- direct caller-root/caller-clock minting;
- imported child-entrypoint misuse;
- parent-process helper/root/clock/launcher rebinding;
- strict duplicate-key JSON ingress;
- retained-root symlink, hard-link, mode, malformed/oversize, and pathname-generation swap attacks;
- no-follow/nonblocking CLI ingress for symlink/FIFO final components;
- removal of the production `--evaluated-at` surface.

The CLI uses exit `0` only for verifier-root-backed `READY_FOR_INTERNAL_BID_REVIEW`, `3` for a truthful `HOLD`, and `2` for malformed/unreadable evidence or current-verifier failure. There is deliberately no caller clock option.

## Next evidence step

Acquire the official RFP package through the procurement process, hash the exact source package, transcribe the actual minimum qualifications, record source coordinates, obtain a separate independent completeness review, and preserve that approved attestation digest under the production retained-root custody contract. Only then can the current gate truthfully test whether the exact reviewed universe is still the candidate being evaluated.

Until that independent root exists, `HOLD` is the correct current result.

No external outreach or submission is performed by this module.
