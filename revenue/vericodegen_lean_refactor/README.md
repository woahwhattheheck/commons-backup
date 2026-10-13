# VeriCodeGen Lean Refactor evidence harness

This directory is an **offline competition-development carrier** for the VeriCodeGen / NeurIPS 2026 Lean Refactor Arena. It is intentionally not a submission client and it makes no leaderboard, award, or payment claim.

The live competition page (re-read before a real run) describes two proof-refactoring tracks. The closed-source-LLM track currently limits API spend to US$3 per problem; the open-source track has a 4×80GB-A100 / 48-hour full-benchmark envelope. Valid proofs are evaluated on proof-source size, Lean elaboration efficiency, and zero-shot version transfer. The public warm-up runs through September 30, the full benchmark is scheduled for November 1, and competition submissions close November 8, 2026. Winner cash prizes are advertised, but this carrier does not encode a numeric prize amount because the public page inspected during this build did not expose a reliable finalized number.

## What this build does

`core.py` turns a strict JSON run into a reproducible evidence package:

1. freezes a task’s preamble/import context and exact theorem declaration;
2. accepts only replacement **proof bodies**, then assembles complete Lean source itself;
3. validates an exact integer-micro-USD generation ledger and refuses totals above 3,000,000 micro-USD/problem;
4. runs one target and zero or more transfer compiler commands as tokenized argv, without a shell;
5. repeats compiles, records bounded stdout/stderr digests, exit codes, local wall time, source hashes, and a deterministic lexical proof-token approximation;
6. computes a local Pareto front across target validity, transfer passes, proof size, and repeated local wall time;
7. emits a deterministic result package and SHA-256 commitment; and
8. verifies the package, optionally rerunning compiler pass vectors.

The selector is deliberately conservative: among locally Pareto-valid proofs it prefers more transfer-toolchain passes, then fewer local lexical tokens, then lower repeated target wall time. **That is not the organizer’s official scoring function.**

## Trust boundary

Compiler commands execute local generated Lean code. The harness strips ambient environment variables down to a small deterministic set, uses a temporary HOME/TMPDIR, applies basic CPU/file/process limits on POSIX, and never invokes a shell. These controls are useful for reproducibility but **are not a security sandbox**; model-generated Lean may exercise metaprogramming, so real runs belong in a dedicated container/VM or other isolation boundary.

This source carrier itself:

- does not call an LLM or model API;
- does not hold API keys;
- does not register for or submit to the competition;
- does not contact organizers;
- does not purchase compute or spend money;
- does not claim an official score, rank, prize, acceptance, or payment.

## Run format

Top level:

```json
{
  "schema": "vericodegen.refactor-run/v1",
  "task": { "...": "strict task object" },
  "toolchains": [ "... one target + optional transfer configs ..." ]
}
```

A task binds `task_id`, `origin_ref`, `origin_digest`, `preamble`, `declaration`, `baseline_proof`, and 1–64 candidate records. A candidate contains only the proof body plus exact generation provenance (`model`, integer `api_cost_microusd`, attempt/seed, request/response SHA-256 commitments). Duplicate candidate IDs or duplicate proof payloads fail closed.

Each toolchain supplies a label, role (`target` or `transfer`), argv token list containing exactly one `{file}` placeholder, timeout, and repetition count. For example, a wrapper may use `['lake','env','lean','{file}']`. For real generated code, point this at an isolation wrapper rather than assuming subprocess limits are a sandbox.

## Commands

From repository root:

```bash
PYTHONPATH=. python3 -m unittest -v revenue.vericodegen_lean_refactor.test_harness
PYTHONPATH=. python3 -O -m unittest -v revenue.vericodegen_lean_refactor.test_harness
python3 revenue/vericodegen_lean_refactor/cli.py --input run.json --output result.json
python3 revenue/vericodegen_lean_refactor/cli.py --verify result.json --expected-digest <sha256>
python3 revenue/vericodegen_lean_refactor/package.py --dest /tmp/vericodegen-package
```

`--rerun-compilers` on verify recompiles all proofs and compares pass vectors, while intentionally not requiring nanosecond timing equality.

## Validation status of this carrier

The cloud image used to build this carrier had **no `lean`, `lake`, or `elan` executable**. The regression suite therefore uses deterministic fake compiler adapters to validate orchestration, failure/timeout behavior, statement immutability, budget enforcement, Pareto selection, commitments, and replay. Passing those tests is not a claim that any proof compiles under Lean.

See `REPORT_TEMPLATE.md` for the evidence fields a later authorized real benchmark run should retain.
