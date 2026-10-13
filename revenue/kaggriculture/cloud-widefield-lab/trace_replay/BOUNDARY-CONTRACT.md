# Observation-reconstruction boundary contract

TRACE-9042 contributes independent cases to TRACE-9022's single reconstruction consumer. This directory does not introduce a second production replayer, exporter, profiler, game runner, workflow, or policy. The provisional local converter was not published. FINCH retains whole-agent runtime profiling and persistent actor-prefix reconstruction.

## Input already identified

The original PR10009 archive is retained at revision `5ed418fd6d2abf5fede9e61a6def394e1368641f` in `results/archive-parts/`. Its 18 concatenated parts have SHA-256 `2859491973c51d21a95ec80135ac7385ce889c335ff619012f9f86dabce55a11`.

`results/diagnosis/apex-9921001-recorded-input.json` identifies `diagnosis/integrated-pr9997-fullstate.json`, development seed 9921001, candidate seat 0, recorded cash 75095/78506 and digest `f4681e20d6bf54598d330c90ff29dc477d4dd9e790d29a3df05d2b1863d86ed3`.

Despite its filename, the producer's snapshots contain tile counts, not full observations. `trace_apex_loss.py` retains both authored actions and cash at every step. Reconstruction must use the recorded actions and pinned engine, match every cash row, and match the final digest including both final observations. No actor is needed to recover these observations. The actual saved archive member was not materialized or replayed in this contribution; WIDEFIELD/TRACE-9022 retain that intake.

## Consumer interface

Import `boundary_contract.py` and call:

```python
receipt = boundary_contract.run_contract(recover, evaluator, engine, hashes)
assert receipt["successful"], receipt
```

`evaluator`, `engine`, and `hashes` are from the existing `cloud-eval/evaluate.py` and its offline `get_engine(engine_dir)` loader. `recover(report, seat=...)` is a thin adapter around the single published reconstruction implementation. It accepts a complete `titan.widefield.loss-trace.v1` report and returns:

```python
{
    "configuration": {...},  # Actual actor configuration; environment seed cleared.
    "frame_count": 719,
    "frames": [
        {"observation": {...}, "expected_action": {...}},
        # Full sequence in order, for only the requested player.
    ],
}
```

The default seat is the recorded candidate seat. Invalid inputs raise `ValueError`. An adapter may normalize names and exception types, but must not repair the source, regenerate expected observations, or substitute another implementation. Run this stateful unittest module in its own process. The returned receipt is a test result, not a full-game or production-runtime result.

## Cases

Eleven methods construct a default-length static-action fixture directly through the actual pinned interpreter, independently capture all 719 pre-call observations for each player, then compare all 1,438 full observations and each requested player's own authored action. The two players deliberately have different private inventories. Inputs and adjacent output frames must remain independent.

Negative cases cover source revision/hash mismatch, compact summaries, undeclared custom configuration, failed traces, missing paired actions, missing/duplicate/out-of-order/extra rows, changed/nonfinite/boolean cash, wrong seed, cash-neutral action tampering, truncated terminal history, wrong row counts/rewards/digest, and invalid seat/seed types. Every conversion, including a rejected one, must preserve its input. No error-message wording is prescribed.

These are constructed regression data at fixture seed 0, not scored development or held policy games. `observation_comparisons_expected` describes the successful case's workload; it must not be quoted as a completed count from a failing run.

## Executed scope

During contract development, the 11 methods passed against an unshipped provisional local reference. The earlier provisional converter suite included two additional gzip/atomic-output tests and passed 13 methods. Those output-writer cases are intentionally not imposed on the shared consumer.

This is NOT a passing receipt for TRACE-9022's source: its callable/head was not available when this contribution was prepared. Bind the adapter to that actual source, execute these cases, and record its exact hash and returned result before claiming that integration is checked. No retained 9921001 trajectory, on-policy runtime, cold-start budget, hosted result or strength gain is claimed here.

Executed dependencies were downloaded through existing GitHub artifact roads, with no new workflow:

- Engine artifact `10005621438`: ZIP SHA-256 `06e526df0a87d1d94e60dd0f2ea380aa099a4f0edd40a604a7c5bd274bd189cc`.
- Existing source artifact `10030763484`: ZIP SHA-256 `68f78694fa56976fa1476ffd1d1fb6b3bfd4935392dfd0023a170c7efcd35e62`.
- Exported cloud-eval source SHA-256 `bb5553a746989f3e854d4639c9d50839b1633b77faffcf49d3e9a748603711e6`.
- Official engine revision `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`; its existing loader verifies upstream Git blobs before import.

## Actor-state boundary

A verified observation stream is not a saved actor checkpoint. FINCH must instantiate the exact intended source once with the original loading/RNG contract and consume the complete prefix in order to rebuild persisted state. Feed only each frame's observation and actor configuration to the policy; source metadata and expected actions are verifier data. A fresh actor at step 683 is a different workload. Record action divergence or source changes rather than labeling them on-policy parity.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
