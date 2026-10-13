# Case Study / Reference Consent Vault

Operation: `CASE-STUDY-REFERENCE-CONSENT-VAULT-20260916`

This package keeps procurement credibility evidence separate from the permission needed to use a counterparty publicly or as a reference.

## Non-negotiable invariant

**A merge, delivery receipt, payment receipt, or owner-approved project fact never becomes publication/reference permission by itself.**

Evidence answers “what can we prove internally?” Permission answers “what are we allowed to say/use, for exactly which purpose, claim, category, subject, and retained evidence generation?”

## States

Each requested use compiles to exactly one state:

- `PUBLIC_CASE_STUDY_OK` — a current explicit permission covers `PUBLIC_CASE_STUDY`, the exact claim text, category, subject, requested naming mode, and every bound evidence generation/hash.
- `REFERENCE_OK` — same binding rules for `REFERENCE`; this does **not** contact the reference.
- `INTERNAL_ONLY` — evidence exists but no explicit permission is bound. This is the safe default.
- `HOLD_PERMISSION` — an explicit supplied permission is expired, revoked, future-dated, wrong-subject, wrong-use/category/claim, lacks naming permission, or binds stale evidence.

## Evidence kinds

`MERGED_WORK`, `DELIVERY`, `PAYMENT`, `OWNER_APPROVED_FACT`.

The compiler does not treat any evidence kind as stronger permission than another. Payment is not testimonial consent. Upstream merge is not sponsor endorsement. Delivery is not permission to name a customer.

## Permission contract

A permission receipt binds:

- counterparty/subject;
- retained permission source + SHA-256 + observation time;
- grant time, optional expiry, optional revocation;
- allowed modes (`PUBLIC_CASE_STUDY`, `REFERENCE`);
- allowed categories;
- exact claim text;
- named-use permission and permitted public name;
- exact evidence ID + generation + SHA-256 bindings.

Changed evidence bytes or generation HOLD rather than silently carrying old consent forward.

## Redaction boundary

The public projection contains only:

- approved public label/name;
- approved claim text;
- category;
- intended use;
- machine state.

It intentionally excludes internal counterparty names, evidence IDs, private repository paths, permission source paths, hashes, private notes, and payment/delivery receipts.

The internal packet retains request state/reasons for owner review.

## Five-minute demo

```bash
python revenue/case_study_reference_consent_vault/compile_vault.py compile \
  --input revenue/case_study_reference_consent_vault/fixtures/vault.synthetic.json \
  --out-dir /tmp/consent-vault

python revenue/case_study_reference_consent_vault/compile_vault.py verify \
  --input revenue/case_study_reference_consent_vault/fixtures/vault.synthetic.json \
  --artifact /tmp/consent-vault/artifact.json \
  --internal /tmp/consent-vault/internal_packet.md \
  --public /tmp/consent-vault/public_projection.md \
  --receipt /tmp/consent-vault/receipt.json
```

The fixture deliberately contains:
- one anonymized case-study permission;
- one named reference permission;
- one payment receipt with **no permission**, which remains `INTERNAL_ONLY`.

## Tests

```bash
python -m unittest discover -s revenue/case_study_reference_consent_vault/tests -p 'test_*.py' -v
python -O -m unittest discover -s revenue/case_study_reference_consent_vault/tests -p 'test_*.py' -v
```

Hostiles cover merge/delivery/payment permission amplification, expiry/revocation/future grants, subject/category/claim/naming mismatch, evidence generation/hash drift, private-source leakage, deterministic ordering, duplicate JSON keys, non-finite JSON, unsafe paths/URL userinfo, strict booleans, tamper detection, HOLD exit behavior, and optimized-Python execution.

## Authority boundary

This package does not send a permission request, contact a customer/reference, publish a case study, post to a website, submit procurement material, sign anything, alter a CRM/provider/payment system, or assert that permission implies acceptance, award, payment, cash, or revenue.

Any later external action remains an independent owner-controlled workflow; under the current swarm rules, outbound also requires a fresh Muse single-writer collision election immediately before send.
