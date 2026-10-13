# Memory Dynamics V2

`memory_dynamics.py` is a deterministic successor layer for KylinMemBench. It keeps the landed literal scorer as the scoring authority while adding the parts needed to measure whether an agent's memory behavior remains correct across adversarial updates and repeated runs.

## What V2 adds

- **18 deterministic adversarial scenarios by default** (three variants across each of the six sponsor dimensions): delayed retention, exact recall, conflicting updates, near-neighbor interference, sensitive-memory boundaries, and task reuse with distractors.
- **Generation binding.** Every evidence trial names the exact SHA-256 of `dataset.jsonl`; drifted or transplanted evidence is rejected before scoring.
- **Repeated-trial comparability.** Every agent must present the same trial-index set. Duplicate identities, missing trials, mixed generations, and malformed sets fail closed.
- **Stability evidence.** Reports include mean/min/max/population standard deviation by overall score and dimension, per-family summaries, and the count of unique dimension-score vectors.
- **Targeted error rates.** Assertions can carry one of three explicit risk tags: `harmful_recall`, `interference`, or `stale_retention`. V2 reports failures/total/rate for each tag instead of hiding them inside a single score.
- **Replay receipts.** The final receipt binds the dataset, suite manifest, every evidence file, and the stability summary by SHA-256 and can be verified later from exact bytes.
- **Deterministic Debian package.** `packaging/build_deb.py` creates a normalized `.deb` containing both the baseline scorer and V2 CLI, then independently verifies archive membership, paths, modes, and normalized metadata.

## One-command synthetic demonstration

From this directory:

```bash
python3 -B memory_dynamics.py build-demo --out-dir build/memory-dynamics-v2 --variants 3 --trials 5
```

This generates a deterministic scenario suite, five stable-agent and five intentionally volatile-agent trials, a stability/risk summary, aggregate radar chart, and a replay receipt. The fixtures are deliberately synthetic; they are an executable benchmark demonstration, **not** evidence that any real agent was run on openKylin.

Verify the exact result later:

```bash
python3 -B memory_dynamics.py verify \
  --suite-dir build/memory-dynamics-v2/suite \
  --evidence-dir build/memory-dynamics-v2/evidence \
  --result-dir build/memory-dynamics-v2/results
```

## Debian package

```bash
python3 -B packaging/build_deb.py --out build/kylin-memory-benchmark_0.2.0_all.deb
python3 -B packaging/build_deb.py --verify build/kylin-memory-benchmark_0.2.0_all.deb
```

Installed commands are `kylin-memory-bench` and `kylin-memory-dynamics`. The package is architecture-independent and depends only on Python 3.10+.

## Adapting real agents

A real adapter should preserve the existing evidence-bundle contract and add these V2 root fields:

```json
{
  "schema": "kylin-memory-dynamics/v1",
  "agent": "agent-name",
  "trial_id": "trial-000",
  "trial_index": 0,
  "suite_sha256": "<exact dataset.jsonl SHA-256>",
  "records": []
}
```

The benchmark never needs an agent credential or network token. Raw dialogue/memory/action/file evidence can remain local to the openKylin machine; only a chosen evidence bundle needs to be scored.

## Truth boundary

This repository successor establishes source, synthetic benchmark, reproducibility, package, and receipt mechanics. It does **not** establish real openKylin desktop execution, real KylinBot/OpenClaw/Hermes runs, the required 3–5 minute desktop recording, competition registration/submission, organizer score, finalist status, award, payment, or revenue. Those require separate environment/provider receipts.
