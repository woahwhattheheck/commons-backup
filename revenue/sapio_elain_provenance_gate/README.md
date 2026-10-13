# Sapio ELaiN record-provenance validation gate

Buyer-neutral, offline delivery core for an ELaiN / third-party-AI record-provenance pilot. It binds each AI-derived record to exact source snapshot, connector, model, tool, prompt-policy, query/result hashes, pseudonymous user + role, intended-use risk, change-control reference, and an explicit human approval of the exact output artifact.

## Outcome boundary

The strongest result is `QA_REVIEW_READY_EVIDENCE_ONLY`. The receipt always keeps batch release, QA disposition, GxP validation/certification, regulatory compliance, production deployment, buyer acceptance, payment, and recognized-revenue authority false. Content hashes prove integrity of the supplied evidence set; they do not prove provider/source authenticity by themselves.

## Fail-closed behavior

The gate rejects malformed schemas, undeclared or digest-mismatched components/sources, secret-shaped fields, noncanonical identities/hashes/timestamps, and changed-payload event-id reuse. It HOLDs stale/future source snapshots, source/generation chronology breaks, nonhuman or nongranting approval, approval of the wrong artifact, and future approval. Exact duplicate event replay is collapsed deterministically.

The public `assess_bundle()` obtains UTC time internally; callers cannot backdate freshness. `verify_receipt()` is intentionally integrity-only and cannot authorize current release.

## CLI

`python -m revenue.sapio_elain_provenance_gate.cli assess bundle.json`

`python -m revenue.sapio_elain_provenance_gate.cli verify bundle.json receipt.json`

No network/provider/customer/payment/deployment action exists in this package. Synthetic fixture data only is used in tests.
