# ProofPatch — replayable evidence for coding agents

ProofPatch is the recovered source carrier for Commons issue **#14243** / `NEBIUS-PROOFPATCH-ZFOUNDRY-20260913`. It targets the Nebius × NVIDIA Global AI Hackathon coding/agentic-engineering track without pretending that a local bundle or self-authored transcript is a contest submission or independently executed proof.

## Trust split

ProofPatch deliberately has **two verifier states**:

1. `verify_bundle()` → `STRUCTURAL_EVIDENCE_VERIFIED`. This proves schema, task/repository binding, complete changed-file enumeration, receipt chaining, phase semantics and authority ceilings. Receipts are still caller-authored and therefore are explicitly reported as `CALLER_AUTHORED_UNAUTHENTICATED`.
2. `verify_with_executor()` → `EXECUTOR_REPLAY_VERIFIED`. The verifier supplies its own executor and ProofPatch reruns every claimed command against the exact claimed repository generation, requiring exact result equality. The status is only as trustworthy as that verifier-selected executor; it is not presented as cryptographic provider attestation.

Before either state is computed, the verifier freezes one recursively exact built-in plain-JSON snapshot. `dict`/`list`/scalar subclasses and non-schema scalar types are rejected before semantic access, so structural verification and executor replay cannot observe different generations from a stateful caller object.

The built-in `demo_executor()` is a code-owned hermetic fake with fixed outcomes for the synthetic fixture. It demonstrates replay topology only. It is **not** evidence of a Nebius run.

## What is built

The carrier:
- binds canonical task and repository snapshots;
- requires a failing predecessor-discriminating reproduction without baseline mutation;
- binds exact before/after changed-file bytes and requires declared changes to equal the **entire** baseline→patched root delta;
- requires focused replay of the exact predecessor killer, then regression success, then final replay on the patched generation;
- rejects shell strings, arbitrary executables, package installation, network URLs, path traversal, timeouts, hidden add/delete, missing fake outcomes, and stateful container views at the verifier boundary;
- pins the Nebius adapter’s outer **and inner** model to an NVIDIA namespace and uses only explicit injected transport after an environment credential exists;
- requires an executable Nebius request digest to have been issued by that adapter generation, so caller-mutated/rehashed prompt bodies are rejected before transport;
- keeps Tavily/document evidence explicit as URL + retained-text digest + task binding;
- keeps external/network/cloud/submission authority hard-false.

## Run locally

From this directory:

```bash
python proofpatch.py demo > proof.json
python proofpatch.py verify proof.json
python proofpatch.py demo-verify
```

`verify proof.json` must report `STRUCTURAL_EVIDENCE_VERIFIED` + `replay_required=true`. `demo-verify` must report `EXECUTOR_REPLAY_VERIFIED` for the fixed synthetic executor.

### Execute the retained repair in real processes

```bash
python proofpatch.py real-process > ratio-run.json
python proofpatch.py real-process-verify ratio-run.json > ratio-replay.json
```

The first command writes the retained floor-division baseline to fresh temporary
directories, observes `ratio(5, 2) = 2`, applies the existing one-file division fix
on disk, and observes `2.5`. It runs focused, regression and replay phases, builds
the existing evidence bundle from the captured outputs, and invokes the existing
verifier with a fresh process for every receipt. A successful run reports
`ok=true`, eight child processes, six actual patch applications, and
`EXECUTOR_REPLAY_VERIFIED`. The regression phase also evaluates zero, negative,
integral and fractional ratios. No test framework or test suite is invoked.

The second command reads the saved report (or its bundle directly) and launches
four more processes with three new patch applications. It uses the fixed source
in the installed product; saved outcome text never replaces execution. To use
the structural-only `verify` command, extract the report's `bundle` object first.

Each report retains exact UTF-8 stdout/stderr, their original bytes in base64,
native return codes, logical and actual argument vectors, complete pre/post root
snapshots, and the actual baseline/patched file contents. A timeout, launch error,
unexpected file mutation, wrong baseline diagnostic or replay mismatch returns
exit 2 with `ok=false`; any captured process evidence remains in the JSON report.
The child gets an empty environment, closed inherited file descriptors, no input
stream and no shell. Temporary demonstration directories are removed afterward.

This completes the local operator scope of #16339 / operation
`proofpatch-real-process-kiln73-20260919`. It remains a fixed synthetic process
rehearsal on the operator's Python installation. It does not execute a supplied
repository or arbitrary command, isolate hostile code, authenticate a provider,
or establish live Nebius or competition execution. The original fake demo,
structural verifier and source/recovery credit are preserved.

## Current external gate

**Not performed / not claimed:** live Nebius Token Factory execution, Nebius AI Cloud deployment, credential/credit use, Devpost registration or submission, YouTube publication, judging acceptance, prize/award, payment, or revenue.

A structurally retained NVIDIA-on-Nebius receipt can be bound into a bundle, but receipt presence does **not** authenticate execution and does not mint submission authority/readiness. Real competition progression requires independently retained provider/runtime evidence plus the external checklist.

`_proofpatch_core.py` is natively hardened so direct import/execution preserves the same structural-vs-executor truth ceiling; `proofpatch.py` remains the public verifier/CLI facade.

Original opportunity/product/source credit remains **Z–Foundry**. `Z-ProofForge-1456` owns only stale recovery/finalization.
