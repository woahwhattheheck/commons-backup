# VeriCodeGen Lean Refactor Arena — competition report evidence template

This is a preparation aid, **not** a submitted competition report. The current official competition page requires a single-blind 4–9 page report with at least Approach, Models, Budget, and Reproduction sections. Re-read the official template/rules before submission because organizer requirements can change.

## Approach

- Exact harness/source commit:
- Benchmark/task provenance and hashes:
- Candidate generation strategy:
- Proof-statement/context immutability mechanism:
- Candidate selection rule:
- Differences between local triage and the organizer’s official evaluator:

## Models

For every model used, record the exact provider/model identifier, version/date if exposed, decoding configuration, tool access, and the role it played. Include failed/abandoned generation attempts if their cost counts toward the per-problem budget.

## Budget

- Track:
- Per-problem allowed budget from current official rules:
- Exact request ledger source:
- Total API cost per problem:
- Any non-API compute used during development:
- Confirmation that reported budget includes failed/retried calls:

The harness represents money in integer **micro-USD** and refuses a candidate ledger above 3,000,000 micro-USD/problem for the current closed-source track contract. That is a guardrail, not proof of provider billing correctness: reconcile against provider receipts before a real submission.

## Reproduction

- OS / architecture:
- Lean toolchain(s):
- Exact compiler command wrappers:
- Target version:
- Transfer versions:
- Harness package digest:
- Out-of-band result commitment(s):
- Model backend configuration:
- Steps to reproduce candidate generation:
- Steps to reproduce compiler verification:

## Results

Report organizer metrics only from the organizer evaluator. Local harness `token_count` is a deterministic lexical approximation and `elapsed_ns` is repeated local wall time; neither should be relabeled as an official score.

## Integrity / limitations

- Candidate proof bodies cannot change the frozen preamble/import context or theorem declaration because source is assembled by the harness.
- Compiler subprocess resource limits are **not a security sandbox**. Run generated Lean in an appropriately isolated environment.
- A self-hash detects accidental/local tampering; bind important result packages to an out-of-band digest for stronger custody.
- This repository carrier performs no model/API call, registration, organizer contact, competition submission, or spend.
