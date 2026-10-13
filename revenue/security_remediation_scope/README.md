# Security HOLD → paid remediation scope

This package turns **verified source-packet HOLD/PARTIAL findings** into a deterministic, owner-review implementation SOW. It exists to make an honest `HOLD` commercially useful without converting missing evidence into a positive security/compliance claim.

## Two-input custody model

The compiler takes two files:

1. a normalized `security-remediation-findings-v1` source packet containing the source finding IDs/statuses/requirements/evidence IDs/current-state/gaps;
2. a `security-remediation-scope-v2` file containing only source-packet identity plus proposed remediation work.

The scope file must pin the exact source packet ID, observed-at time, and SHA-256. Compilation re-reads the exact source bytes, verifies that SHA-256, parses them strictly, and **derives the finding fields from those verified bytes**. The scope manifest cannot restate or override a source finding's status/current-state/gap.

The normalized source packet is still evidence input, not an auditor/regulator authority. The resulting report is explicitly `HISTORICAL_OWNER_REVIEW_ONLY`.

## Actionability

Only `PARTIAL`, `HOLD_MISSING_EVIDENCE`, and `HOLD_STALE_EVIDENCE` can receive remediation rows. `SUPPORTED` and `NOT_APPLICABLE` rows cannot be monetized. Unknown source finding IDs are rejected.

If an actionable source finding has no remediation row, it is surfaced under `unscoped_findings` and the whole packet emits `HOLD_UNSCOPED_FINDINGS`. This prevents a convenient subset from making unresolved HOLDs disappear.

## Fixed-scope commercial envelope

Owner-proposed pricing is integer cents only. When all actionable findings are scoped and the total is **$5,000–$30,000**, the report may emit `OWNER_REVIEW_READY`; valid totals outside that envelope emit `HOLD_PRICE_OUTSIDE_FIXED_SCOPE`. Commercial state is always `PROPOSED_NOT_ACCEPTED`.

## Prohibited outcome language

Deliverable, acceptance-test, and change-control text fails closed if it attempts certification/compliance/audit promises such as `certify`, `guaranteed compliance`, `SOC 2 compliant`, `HIPAA compliant`, `ISO 27001 certified`, `PCI compliant`, or `pass an audit`. Concrete technical/evidence work is scopeable; an auditor, regulator, lawyer, customer acceptance decision, or security guarantee is not.

## Demo

```bash
cd revenue/security_remediation_scope
python synthetic_fixture.py source > /tmp/security-remediation-source.json
python synthetic_fixture.py scope > /tmp/security-remediation-input.json
python remediation_scope.py compile \
  --input /tmp/security-remediation-input.json \
  --source-packet /tmp/security-remediation-source.json \
  --report-json /tmp/security-remediation-report.json \
  --report-md /tmp/security-remediation-report.md
python remediation_scope.py verify \
  --input /tmp/security-remediation-input.json \
  --source-packet /tmp/security-remediation-source.json \
  --report-json /tmp/security-remediation-report.json
```

The synthetic source packet has two actionable findings plus one supported/nonbillable finding. The matching scope totals $17,500.

## Determinism and verification

Duplicate JSON keys, floats/non-finite numbers, unknown critical keys, invalid IDs/hashes/timestamps, future source packets, duplicate IDs/dependencies, Boolean prices, unknown finding references, nonactionable monetization, source-byte/hash drift, and malformed price values fail closed.

The receipt binds exact scope bytes, normalized scope semantics, exact source packet bytes, normalized source semantics, and canonical report body. Verification recompiles from both retained inputs.

## Authority ceiling

Every report hard-codes `false` for buyer contact, contract acceptance, compliance certification, security attestation, deployment, invoice authorization, payment, and revenue recognition. The tool is offline; it does not send, deploy, sign, invoice, charge, certify, or recognize anything.
