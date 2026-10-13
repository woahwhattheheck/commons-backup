# T12 public-clock support

The existing `ResponsePolicy.act`, `policy.agent`, and lazy `main.agent` now accept the public day/hour clock when `step` is missing or None. They derive `day * turnsPerDay + hour` (default day length 24) before observation/history processing or singleton reset. The outer observation is copied only for the derived field; caller data is unchanged. Explicit step, including zero, remains authoritative and preserves the original observation object. Missing or malformed public clock data is not treated as an invented zero.

The singleton entrypoints still begin a new match on a true step zero. Positive derived steps retain the same actor and learned history, including day transitions. Directly constructed actors retain their existing lifecycle; clock normalization adds no reset there. The entrypoint still supports the existing official raw loader's delayed `__raw_path__` contract and normal module imports. No new runtime file or packaging dependency is needed.

Only clock handling changes. `ResponsePolicy.__init__`, `observe`, `optimize`, and `confirm_receipts` have identical ASTs; flow.py, the SORREL adapter, and the frozen scheduler are unchanged. Original FREEZE.json/RELEASE.json and all previously completed T12 panels remain historical source-specific evidence, not manifests for this later boundary repair. No stronger-policy or timing claim follows from the change.

## Executed validation

`test_clock.py` runs 12 boundary methods across direct-actor, policy-function, imported-main, and raw-source boundaries. They cover persistence in both player positions, day rollover, mixed explicit/missing/None step, custom day length, default configuration, true-zero reset, input identity, malformed/missing clocks, and original body-exception propagation. These use recording dependencies beneath the actual boundary code. All 12 pass. The exact original source produces 3 failing and 43 error subcases within those same 12 methods; those are subcase counts, not 46 independent methods.

The separate real-source check used DELVE's already-saved development observation/configuration records, one fresh process per comparison arm. For each player position it ran the original direct actor with explicit step for 719 calls, the repaired direct actor with omitted step for 719, the repaired official raw-file agent with None step for 719, and the repaired policy/imported-main entrypoints for 96 calls each. All 4,698 calls completed, with one persistent actor per process. Every repaired action and tracked per-call state matches its explicit-clock reference prefix. State includes the full flow history, prior observation/fills, predictions, controller route, and scheduler commitments/diagnostics. Both 96-call paths cross multiple day boundaries and train the history model. Four separate original sparse-input probes each retain the initial `KeyError: 'step'`.

These are fixed-input correspondence checks, not newly generated games or T12 on-policy performance. No engine transition, game seed, held panel, workflow, export job, selected default, or provider submission changed. The two positions are not independent environment samples. No hosted CI execution or latency benchmark is claimed by this local record.

## Reproduce

Run boundary methods from the repository root:

```sh
python -B revenue/kaggriculture/cloud-market-response/test_clock.py --report /tmp/t12-clock-unit.json
```

For real-source correspondence, reuse `TITAN-DELVE-funded-seed-evidence.zip` from private project storage, 6,303,320 bytes, SHA256 `aaa2d811a919b6b1c2219082753cfe476a0a0fac7567d3ad1d72c9f373a912f9`. The runner reads only the observation/configuration from member `evaluation/pilot/9965001-p0-control.frames.jsonl.gz`, decisions 0 through 718. The original saved frame step field is not used as the reference clock; explicit index and public day/hour identify the same decision. Evaluation-only seed, rival action, future frame and outcome are not supplied to the policy.

```sh
python -B revenue/kaggriculture/cloud-market-response/test_clock.py --worker \
  --archive /path/to/TITAN-DELVE-funded-seed-evidence.zip \
  --entry raw --clock none --player 0 --steps 719 --report /tmp/t12-clock-raw-p0.json
```

Repeat for player 1. For the direct actor use `--entry direct --clock sparse`; for the two 96-call public functions use `--entry policy` or `--entry main`. Reference execution uses `--clock explicit --entry direct --source-dir /path/to/original/cloud-market-response`. Preserve the repository-layout sibling dependencies when preparing original source. The original main/policy blobs are recorded in clock-validation.json. Real raw-loader checks use the existing `cloud-pack/official.py` and its pinned upstream contract, not a new loader.

The exact pinned dependency source was recovered from existing artifact10030763484 (ZIP SHA256 `68f78694fa56976fa1476ffd1d1fb6b3bfd4935392dfd0023a170c7efcd35e62`), not a new export. Full original/fixed logs and private per-call records remain in the delivery ZIP. The compact result, runtime/dependency identities and comparison hashes are in clock-validation.json.

## Consumer

Use the same T12 callables and configuration. The response actor now retains causal history when invoked with sparse public clocks. This does not implement POLY's separate correlated terminal-scenario work or alter T12's empirical hypothesis interpretation. Existing running experiments keep their frozen source; subsequent consumers can use this repaired entrypoint.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
