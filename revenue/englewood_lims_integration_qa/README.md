# Englewood LIMS integration-QA evidence core

This package is an internal, provider-free delivery primitive for the **City of Englewood, Colorado RFP 26-031** teaming seam. Public procurement material describes a full-lifecycle LIMS for the Utilities Department at the Allen Water Treatment Plant, including implementation, configuration, integration, testing, deployment, support, operational integrity, robust audit trails, real-time validation, and secure multi-user workflows.

It does **not** represent TokenJunkieLabs as the LIMS prime, satisfy the complete RFP, submit a proposal, contact the City, deploy a LIMS, or claim buyer acceptance. The registered solicitation package and an established LIMS vendor remain authoritative for the actual requirements, architecture, security controls, acceptance plan, and commercial response.

## What the gate proves

`gate.py` accepts a complete synthetic/review evidence snapshot and returns `READY_FOR_PRIME_REVIEW` only when all of the following remain coherent at **trusted process time**:

- every mandatory declared requirement is mapped to an exactly-one passing test execution;
- five non-negotiable evidence controls are present and passing: audit-chain integrity, real-time validation, multi-user role separation, integration replay idempotency, and requirement traceability;
- configure, execute-test, validate, and release-approval evidence binds to one release, expected roles, and a three-actor configure/test/approve separation;
- integration events tolerate exact duplicate delivery but reject changed-content identity reuse, sequence gaps, invalid no-effect retries, and quarantine evidence;
- the audit ledger is an ordered SHA-256 chain with monotonic timestamps and evidence for every required workflow action;
- snapshots and evidence are fresh against a time source outside the packet; caller-owned historical timestamps cannot preserve READY indefinitely;
- READY/HOLD receipts are deterministic, self-digested, short-lived, and carry **no** proposal, deployment, operational-release, contract, payment, buyer-acceptance, or recognized-revenue authority.

The public CLI intentionally does not accept `--as-of` or another caller-supplied clock. `evaluate` and `verify` use process UTC. The private injected-time helpers exist for deterministic tests/fixtures only.

## Synthetic acceptance

`acceptance.py` builds an 80-packet deterministic corpus at a fixed test clock:

- 40 clean packets → `READY_FOR_PRIME_REVIEW`;
- 40 packets → `HOLD`, five each across eight isolated defects: mandatory coverage loss, test failure, broken audit chain, failed validation, role collision, quarantined integration evidence, changed-content event-ID reuse, and incomplete snapshot.

The corpus is synthetic and contains no City, laboratory, sample, employee, customer, credential, regulated record, or production-system data.

## Run locally

```bash
python -m unittest -q revenue.englewood_lims_integration_qa.test_gate
python -O -m unittest -q revenue.englewood_lims_integration_qa.test_gate
python -m py_compile revenue/englewood_lims_integration_qa/gate.py revenue/englewood_lims_integration_qa/acceptance.py revenue/englewood_lims_integration_qa/test_gate.py
python revenue/englewood_lims_integration_qa/acceptance.py
```

## Authority boundary

This is evidence/reconciliation software only. It performs no City/ATL/vendor contact, procurement submission, bidder registration, requirement certification, production LIMS write, SCADA/instrument connection, laboratory decision, water-treatment decision, user provisioning, deployment, contract/signature, payment, or revenue recognition. A `READY_FOR_PRIME_REVIEW` receipt means only that the supplied synthetic/review packet satisfied this package's narrow evidence contract while the receipt remained fresh.
