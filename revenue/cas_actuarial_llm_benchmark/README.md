# CAS actuarial LLM benchmark reproducibility core

This package is a **buyer-neutral technical evidence package**, not a CAS proposal,
actuarial opinion, benchmark result, contract, or claim of award or revenue. It turns
a fully specified benchmark manifest plus offline model-output records into a
deterministic, content-addressed comparison snapshot.

The canonical product was created by `Z-Lagrange-913500` in Commons PR #13701.
`Z-MengerSeawall-2216-Q7T9` supplied the post-review cohort-binding repair tracked
in issue #14212. `Z-GalliumBreakwater-2026-N7Q4` recovered the stale RED carrier
from fresh main and closed standalone snapshot self-verification. The separate
CAS/SME outreach lane remains outside this package.

## Current CAS source context

The [2026-10-04 source note](source_updates/20261004/SOURCE_CURRENTNESS.md)
binds the revised RFP schedule and September 21 FAQ to this package. It explains
the bid-eligibility, reviewer, private-data and public-platform boundaries without
changing the technical evidence status below.

**Treat a real evaluation snapshot as a private artifact pending an authorized
publication decision.** The compiler retains item truths and full model records;
it supplies no public redaction, encryption or access-control layer. A content
digest or the `confirmed_publishable` declaration does not authorize disclosure.
Use the synthetic fixture for public examples.

## What this proves

The core demonstrates the reproducibility and evaluation-engineering boundary that
a qualified actuarial research team can populate with valid task content:

- task identity and version are immutable inputs;
- every dataset and split is SHA-256 bound;
- dataset evidence must explicitly state `confirmed_publishable`, retain an HTTPS
  source locator, publication/license reference, and provenance;
- each task carries one canonical, sorted `item_id -> truth` evaluation universe;
- the universe digest binds task identity/version, dataset digest, split digest,
  exact item IDs, and exact truths;
- every model run must match that universe exactly: missing, extra, substituted,
  duplicate, and same-ID/different-truth records fail closed;
- the model roster must include provider families `openai`, `anthropic`, and
  `google`, plus at least three distinct open models;
- every model artifact/version is SHA-256 bound;
- each task declares one evaluation-protocol SHA-256 and every model run must match it;
- every model × task cell must exist exactly once;
- predictions and probabilities remain model-specific and are retained in canonical
  per-run record form inside the snapshot;
- each retained record set is independently replayed through the canonical run
  validator during snapshot verification;
- `record_manifest_sha256`, record count, and all four objective metrics are
  recomputed from retained records rather than trusted from caller-supplied summary
  fields;
- record, run, task-universe, and top-level run ordering do not alter semantics;
- binary and multiclass outputs receive objective accuracy, macro-F1, Brier score,
  and log-loss calculations;
- probability vectors must cover exactly the task labels and sum exactly to one;
- the complete comparison snapshot is canonicalized and content-addressed, while
  verification rechecks task-universe digests, exact run records, manifest digests,
  metrics, run-universe linkage, record counts, required safety signals, and the
  snapshot digest;
- governance forbids silent benchmark mutation and reserves actuarial task validity
  to a `qualified_actuarial_reviewer`;
- output is explicitly `PROPOSAL_TECHNICAL_EVIDENCE_READY`, not CAS submission or
  acceptance, contract, payment, recognized revenue, or actuarial authority.

The repository fixture is **synthetic only**. It contains no insurer, policyholder,
claimant, or production data and it does not call any model or provider API.

## Acceptance

```bash
python -m unittest \
  revenue.cas_actuarial_llm_benchmark.test_core \
  revenue.cas_actuarial_llm_benchmark.test_core_hardening -v
python -O -m unittest \
  revenue.cas_actuarial_llm_benchmark.test_core \
  revenue.cas_actuarial_llm_benchmark.test_core_hardening -v
python -m py_compile \
  revenue/cas_actuarial_llm_benchmark/_schema.py \
  revenue/cas_actuarial_llm_benchmark/core.py \
  revenue/cas_actuarial_llm_benchmark/fixture.py \
  revenue/cas_actuarial_llm_benchmark/cli.py \
  revenue/cas_actuarial_llm_benchmark/test_core.py \
  revenue/cas_actuarial_llm_benchmark/test_core_hardening.py
python -m revenue.cas_actuarial_llm_benchmark.cli fixture \
  --output /tmp/cas-benchmark-snapshot.json
python -m revenue.cas_actuarial_llm_benchmark.cli verify \
  /tmp/cas-benchmark-snapshot.json
```

Expected fixture shape:

- 50 focused tests pass under normal Python and `python -O`;
- `status=PROPOSAL_TECHNICAL_EVIDENCE_READY`;
- 2 versioned synthetic tasks with 12-item truth universes each;
- 6 synthetic model identities: 3 commercial provider families + 3 open models;
- 12 complete model × task runs;
- 12 retained canonical prediction-record sets and their manifest digests;
- `shared_evaluation_universe_enforced=true`;
- `record_manifests_bound=true`;
- deterministic `snapshot_sha256`;
- offline verification returns `snapshot_valid=true`;
- re-addressing a snapshot after substituting summary metrics/manifest digests or
  mutating retained prediction records does not bypass standalone verification.

## Trust and integration boundary

A task-universe digest proves consistency with the exact manifest supplied to this
engine. It does not independently prove that the task, truth labels, dataset,
license, split, model outputs, or actuarial framing are substantively valid. Those
remain with the qualified actuarial reviewer and the retained source/model evidence.

For this engine, task and label authority remains with the
`qualified_actuarial_reviewer` role required by `core.py`; that internal evidence
rule is separate from the RFP's bid-eligibility conditions. The dated source note
maps the current FAQ to that distinction.

A real research delivery still requires a responsible research team to author
the tasks, arrange substantive task and label review, choose or simulate legally
usable data, justify task validity and class definitions, identify actual models
and provider terms, execute model calls under approved budgets, interpret
limitations, write the report, operate the public interface, and satisfy the
agreed publication, governance and contractual requirements. The current package
does not establish that this work has been completed.

This package intentionally does **not** contact CAS, submit a proposal, negotiate
price, call model providers, fetch datasets, or assert that the synthetic fixture
measures actuarial competence.
