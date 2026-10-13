# New Mexico OCS2026.01 — TPRM technical carrier

This directory is a **technical reference carrier** for New Mexico Office of Cybersecurity opportunity **OCS2026.01, Cyber Third-Party Risk Management**.

It is not a quote, proposal submission, legal opinion, compliance certification, eligibility representation, or evidence of an award. The current controlling RFQ bytes have not been bound into this repository, so direct-prime eligibility remains unverified.

## Source checkpoint — October 4, 2026

The official RFQ and dated Q&A text are now located and read. [`SOURCE_CURRENTNESS_20261004.md`](SOURCE_CURRENTNESS_20261004.md) records the buyer-scope correction, source locators and remaining gaps; [`source_observation_20261004.json`](source_observation_20261004.json) records coverage. This document update does not supply raw PDF identities, supplier evidence or a new qualification result.

The original build in [#15842 / #15867](https://github.com/woahwhattheheck/commons/pull/15867), ZZ-KESTREL-M8D3 recovery and ZZ-IBIS-93C-R3 repair/review remain credited. Engine behavior and accepted proof are unchanged.

## Original carrier design

The September 18 mirror-based source generation described a project to design, develop, and deliver a scalable, multi-tenant third-party risk-management framework, program, and toolset for New Mexico SLCGP local entities, including higher education, county, municipal, and tribal organizations.

The original reference design drew on these reported themes; this list is historical context for the implementation:

- third-party discovery and inventory;
- vendor tiering and assessment;
- contracting workflow support and continuous monitoring;
- cybersecurity governance and risk assessment;
- vulnerability / attack-surface management;
- training and workforce-development support;
- baseline cybersecurity requirements aligned to national frameworks;
- legal / contractual gap analysis; and
- a functional multi-tenant TPRM toolset.

[`PUBLIC_SOURCE_LEDGER.json`](PUBLIC_SOURCE_LEDGER.json) remains the unchanged September 18 observation, with its secondary-source classification and `controlling_rfq_bound=false`. The new official text observation is separate. The retained public-only qualification example is still a historical, incomplete input.

## What ships

### `tprm.py`

A dependency-free deterministic reference engine for:

- strict tenant/vendor identity;
- four-factor reference tiering;
- framework/control evidence records;
- continuous-monitoring events;
- deterministic findings;
- replay-verifiable SHA-256 receipts;
- portfolio compilation with **per-tenant Merkle-like roots** (hashes over assessment receipts); and
- explicit authority-negative output.

The reference tier is a workload triage mechanism, **not** a risk rating, legal conclusion, or compliance claim. Control records distinguish `SATISFIED`, `GAP`, and `UNKNOWN`, but a satisfied reference record never becomes a compliance certification.

### `qualification.py`

A fail-closed pursuit gate separating technical readiness from procurement authority. It will not mint buyer/contact, pricing, signature, legal, or submission authority from caller-provided flags.

Supported postures include:

- `TEAMING_RESEARCH_ONLY`
- `TEAMING_DRAFT_READY_FOR_OWNER_REVIEW`
- `PRIME_TECHNICAL_DRAFT_ONLY`
- `PRIME_DRAFT_READY_FOR_OWNER_REVIEW`

A verified controlling RFQ requires an exact digest. Positive **or negative** prime-eligibility conclusions require evidence digests. Legal-scope claims are separately gated.

### `cli.py`

Offline compile/verify commands with:

- duplicate-key rejection;
- non-finite JSON rejection;
- bounded input size;
- non-symlink ordinary-file input requirement; and
- no output overwrite.

No network or provider side effects exist in the reference engine or CLI.

## Specialist workshare

[`WORKSHARE.md`](WORKSHARE.md) maps the source checkpoint to the current internal specialist posture and labels the engineering workstreams as reference capabilities. An RFQ response must identify its actual deliverables and qualified personnel; the existence of this engine does not establish a buyer purchase, a completed deliverable or procurement/legal authority.

## Run locally

From repository root:

```bash
python revenue/nm_ocs_tprm/verify_manifest.py
```

Example compilation:

```bash
python -m revenue.nm_ocs_tprm.cli assessment \
  revenue/nm_ocs_tprm/examples/assessment.json \
  /tmp/nm-ocs-assessment.json

python -m revenue.nm_ocs_tprm.cli verify-assessment /tmp/nm-ocs-assessment.json
```

## Authority boundary

Nothing in this directory authorizes:

- contacting New Mexico OCS or any prospective prime;
- registering/logging into a procurement portal;
- accepting portal terms;
- quoting or pricing;
- asserting New Mexico price-agreement, GSA, NASPO, certification, insurance, or resident-business status;
- giving legal advice or producing legal conclusions;
- signing or submitting a response;
- spending money;
- representing an award, payment, or revenue.

Those require separate current evidence and owner/provider authority.

## Historical source trail

- ContractRadar: https://contractradar.io/posts/4eaf9a06-6996-410b-8f81-8a0c24b507c8
- HigherGov: https://www.highergov.com/sl/contract-opportunity/nm-cyber-third-party-risk-management-74052876/
- CLEATUS RFQ index: https://www.cleat.ai/government/contracts/cyber-third-party-risk-management-z5p9
- Craxy cached-document index: https://craxy.ai/find-rfps/cmu55x93t01pbyd0x67celjpb

The dated checkpoint records the official response date and remaining scope questions. Exact PDF binding and any subsequently published Q&A remain source work. Supplier evidence and an actual new qualification input/output are absent; the historical example is unchanged.
