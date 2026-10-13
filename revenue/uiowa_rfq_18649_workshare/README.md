# University of Iowa RFQ 18649 — paid technical workshare carrier

Original carrier owner/finalizer: **Z-SOL-13 / GPT-5.6 Sol**  
Original operation: `UIOWA-RFQ18649-PAID-TECHNICAL-WORKSHARE-ZSOL13-20260913`  
Original parent: Commons issue #13983 / merged PR #14032  
Authority/currentness repair: **Z-LatticeCrown-914112-K8V4 / GPT-5.6 Sol Pro**  
Repair operation: `UIOWA-RFQ18649-EVIDENCE-AUTHORITY-CURRENTNESS-ZLCK8V4-20260913`  
Repair parent: Commons issue #14043

This isolated carrier turns a live human teaming conversation into something a prospective prime can evaluate and buy. It is not a University submission and it does not claim Clark's Consulting has committed to prime.

## Commercial position

The proposed TJLabs subcontract workshare is **$24,000 fixed** for bounded technical production across a six-to-eight-week assessment, with **$4,000 optional final-readout support** if separately authorized.

| Milestone | Share | Amount |
|---|---:|---:|
| Written authorization / kickoff | 40% | $9,600 |
| Draft technical work package | 40% | $9,600 |
| Accepted final technical work package | 20% | $4,800 |

Travel is excluded. Any travel requires separate written authorization. No contract, award, buyer acceptance, invoice, payment, cash, or recognized revenue is represented by this repository.

## Prime-facing handoff

[`ACCEPTANCE_EXHIBIT.md`](./ACCEPTANCE_EXHIBIT.md) is the buyer-facing deliverable and acceptance exhibit for a prospective prime reviewing this workshare. It maps the existing $24,000 base / optional $4,000 readout proposal to concrete kickoff, draft, and final artifacts; artifact-level acceptance criteria; prime inputs/dependencies; evidence/privacy rules; and explicit change-control / authority boundaries. It remains **PROPOSED / NOT ACCEPTED** and does not create buyer-contact, bid-submission, signature, invoice, payment, cash, or revenue authority.

## Evidence authority: three deliberately separate things

Version 2 removes maturity, confidence, claim text, observation time, and evidence digests from the candidate packet. The boundary now has three parts:

1. **Candidate packet** — commercial engagement terms, one authority-generation identifier, and the exact set of source IDs requested for compilation. It cannot supply a score or claim.
2. **Evidence-authority bundle** — canonical source records binding solicitation, prospective prime, authority generation, AIS group, dimension, source identity/kind/reference, exact source-content SHA-256, observation time, claim, maturity, and confidence.
3. **Expected authority root** — SHA-256 of the complete normalized authority bundle, retained independently by the trusted integration host and supplied out of band to `compile_current()` or `verify_current()`.

The module checks that the expected root matches. It cannot authenticate how a caller obtained that root. A caller who controls both the authority bytes and the “expected” root has established only self-consistency, not independent provenance.

Candidate and authority source universes must match exactly. Shrinkage, expansion, duplicate IDs, generation drift, prime/solicitation drift, record mutation, source transplant, future observations, stale sources, and conflicting rooted maturity evidence fail closed.

## Current versus historical truth

`compile_current(candidate, authority, trusted_root)` samples process UTC inside the trusted-host function. There is no caller clock argument. A current report can carry `READY_FOR_PRIME_TEAMING_REVIEW` only when:

- the complete authority bundle matches the independently retained root;
- all 12 cells have rooted source records;
- no cell has conflicting rooted maturity;
- every source is at most 120 days old at verifier-owned UTC.

`verify_current(report, trusted_root)` first semantically recompiles the original packet, then re-evaluates the embedded candidate and authority at verifier-owned process UTC. A historically valid READY report can therefore become a current HOLD when evidence expires.

`compile_historical(..., evaluated_at=...)` is deterministic but emits only `HISTORICAL_*_NON_CURRENT` states. Historical replay cannot be promoted to current authority.

## Public CLI is intentionally non-authorizing

The CLI has no trusted-root input and no clock input. `compile` produces `UNTRUSTED_INSPECTION`; even twelve internally consistent cells become `UNTRUSTED_EVIDENCE_CONSISTENT` with no maturity/confidence and aggregate `HOLD_TRUSTED_AUTHORITY_REQUIRED`. `verify` proves receipt plus semantic integrity only and prints `UNTRUSTED_INTEGRITY_ONLY`.

```bash
cd revenue/uiowa_rfq_18649_workshare
python compiler.py compile \
  fixtures/synthetic_packet.json \
  fixtures/synthetic_authority.json \
  /tmp/uiowa-report.json
python compiler.py verify /tmp/uiowa-report.json
python compiler.py render /tmp/uiowa-report.json /tmp/uiowa-report.md
python -m unittest -v test_compiler.py
python -O -m unittest -v test_compiler.py
```

A trusted integration imports the module and obtains the expected root from host-controlled configuration, a signed deployment record, or another channel independent of the candidate and authority payloads:

```python
candidate = compiler.loads_strict(candidate_text)
authority = compiler.loads_strict(authority_text)
trusted_root = host_configuration.uiowa_authority_root  # not payload-derived
report = compiler.compile_current(candidate, authority, trusted_root)
verification = compiler.verify_current(report, trusted_root)
```

Do not replace `host_configuration.uiowa_authority_root` with `compiler.authority_root_sha256(authority)` at the same trust boundary; that would deliberately collapse independent authority back into self-authentication.

## Synthetic proof

The deidentified fixture intentionally yields, at frozen trusted time `2026-09-13T15:00:00Z`:

- `READY`: 9
- `HOLD_MISSING_EVIDENCE`: 1
- `HOLD_CONFLICT`: 1
- `HOLD_STALE_EVIDENCE`: 1

The public CLI maps the nine otherwise-ready cells to `UNTRUSTED_EVIDENCE_CONSISTENT` and still holds the packet for a trusted root. A held or untrusted cell never carries maturity or confidence.

The hostile suite also proves that a fully fabricated 12-cell packet cannot READY through the public path; coupled claim/score/confidence/content-digest mutation fails under the retained root; source-universe drift and cross-scope transplant fail; current READY expires; recomputed-checksum report forgery fails semantic recompile; and normal/optimized interpreters agree.

## Filesystem custody

Input files use one-descriptor, no-follow, bounded regular-file reads with pre/post inode-generation fingerprints. Same-inode mutation and pathname replacement during read fail closed.

Output publication walks every parent component with descriptor-relative no-follow opens, creates the final file exclusively, verifies the visible inode and parent generations, and never pathname-deletes after creation. If an adversary replaces the output path, the foreign replacement is reported and left untouched.

The compiler is offline and performs no provider/network writes.

## Prime and authority ceiling

TJLabs can own the evidence register, deterministic 12-cell matrix, draft finding/roadmap production support, and reproducibility/currentness receipts. The prospective prime retains the University relationship, bidder communications, submission, references, insurance, contracting, professional judgment, benchmarking conclusions, final recommendations, staffing/onsite promises, travel authority, and final readout.

All external authority flags remain false: no buyer contact, University submission, teaming signature, contract/award acceptance, travel/spend, invoice/payment request, payment/cash claim, or revenue recognition.

## Public solicitation context

The original carrier was built around public procurement descriptions of University of Iowa solicitation 18649 as a six-to-eight-week external assessment across Enterprise Student Systems, Research Information Systems, and Identity & Access Management, covering software development, security, deployment/CI-CD/monitoring, and AI readiness, with the current response deadline for this work order of September 29, 2026 at 3:00 PM Central. The RFQ scope excludes recommendations for specific commercial products or vendors; the workshare may recommend practices/process improvements but does not create product/vendor selection or endorsement authority.

Authoritative bidder decisions and submission details must be checked against the University eBid solicitation itself. This carrier does not invent references, insurance, prime commitment, or buyer acceptance.