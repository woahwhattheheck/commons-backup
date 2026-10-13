# Client Implementation Onboarding Workspace

A local-first, dependency-free post-sale operations product for service firms. It starts **after** an authorized owner has independently established that a bounded scope was accepted. It does not infer acceptance from CRM stage, email text, a proposal, or a payment intent.

## What it does

- opens one accepted-work workspace bound to the canonical accepted scope SHA-256;
- preserves immutable scope generations and explicit local change-control lineage;
- tracks required customer/internal inputs by exact artifact digest and local review state;
- computes conservative kickoff readiness (`INPUTS_REQUIRED`, `OWNER_REVIEW_REQUIRED`, `READY_FOR_KICKOFF_REVIEW`, `ON_HOLD`);
- executes ordered implementation milestones with dependency gates and exactly-once operation IDs;
- binds deliverable revisions to exact SHA-256 values and invalidates stale reviews after any artifact revision;
- conservatively resets current-generation input/milestone approvals when an owner approves a scope change;
- exports deterministic JSON, Markdown, CSV, and SHA-256 receipt artifacts;
- re-verifies exports against the current SQLite state;
- exposes a **read-only** loopback browser/API view. All mutation remains in the local CLI.

## Authority ceiling

The product has no customer/prospect send, calendar mutation, contract/signature, payment/refund/invoice, CRM/provider, customer-system deployment, legal/accounting/tax, buyer-acceptance inference, cash, receivable, or recognized-revenue authority. `CUSTOMER_REVIEWED_LOCAL` is merely an operator-recorded local disposition; the software never contacts or authenticates a customer.

Commercial hypothesis: **$2,500 fixed setup + $299/month managed workspace / PROPOSED_NOT_ACCEPTED**.

## Quick start

```bash
python onboarding.py --db demo.db init --input example_accepted_work.json --op open-demo
python onboarding.py --db demo.db status --workspace ws-demo-example
python server.py --db demo.db --host 127.0.0.1 --port 8765
```

Mutating workflow is CLI-only:

```bash
python onboarding.py --db demo.db receive-input --workspace ws-demo-example --input-id client-brief --sha <64-hex> --op recv-brief-1
python onboarding.py --db demo.db review-input --workspace ws-demo-example --input-id client-brief --decision ACCEPTED_LOCAL --op review-brief-1
python onboarding.py --db demo.db milestone --workspace ws-demo-example --milestone-id kickoff --transition START --op start-kickoff-1
python onboarding.py --db demo.db deliverable --workspace ws-demo-example --milestone-id kickoff --deliverable-id kickoff-plan --sha <64-hex> --op plan-artifact-1
python onboarding.py --db demo.db review-deliverable --workspace ws-demo-example --milestone-id kickoff --deliverable-id kickoff-plan --revision 1 --decision OWNER_APPROVED_LOCAL --op review-plan-1
```

Export is create-exclusive:

```bash
python onboarding.py --db demo.db export --workspace ws-demo-example --out-dir ./handoff
python onboarding.py --db demo.db verify --workspace ws-demo-example --out-dir ./handoff
```

## Tests

```bash
python -B -m unittest -v test_onboarding.py
python -O -B -m unittest -v test_onboarding.py
python -m py_compile onboarding.py server.py test_onboarding.py
```

The focused suite covers happy-path handoff, missing/rejected inputs, exact replay and changed-op conflicts, milestone dependencies, stale deliverable review, change-control invalidation, strict input validation, deterministic export/tamper checks, create-exclusive/symlink refusal, restart persistence, concurrent replay, read-only HTTP, loopback-only binding, and real CLI execution.
