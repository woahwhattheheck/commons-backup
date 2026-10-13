# Current TITAN 87d7 vs Apex — development shard 9969019

This additive result evaluates the exact current canonical TITAN archive against the retained Apex opponent on one previously unused development seed in both seat orders. It does not alter the controller, default configuration, canonical archive, or provider state.

## Result

- Independent seeds: **1** (`9969019`)
- Mirrored seat records: **2**
- Candidate: **2W / 0T / 0L** across the two seat records
- Candidate cash: **112,839** in each seat
- Apex cash: **109,760** in each seat
- Margin: **+3,079** in each seat
- Candidate maximum call: **0.097285 s**
- Candidate maximum evaluator RPC: **0.141463 s**
- Failures/timeouts: **0**

The two seat records are a symmetry check around one independent seed, not two independent samples. Candidate actions, Apex actions, public bank trajectory, statuses, rewards, and daily banks match exactly after seat normalization.

## Exact inputs

- Canonical archive SHA-256: `87d7b8bf7c4e9467f4b6b46887abe2eb03735c42453cdbf4f2cac12c5962acc7` (292,007 bytes)
- Candidate `main.py` SHA-256: `a4ecdb513b48fa51877fe509597a84dd753dfe71d2d76a406ee3dc51475a9008`
- Official engine pin: `kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`
- Apex `main.py` SHA-256: `1f7cd5fb8a16585936d2562a3667f85bb6661688718ef58f73006de66148354a`
- Apex compiled bridge SHA-256: `859857b1e6139026460fd50ee83bfe9022d4f73f01c40b7cca4aeea4d9af673c`
- Source artifact: GitHub Actions run `34198994016`, canonical artifact `10045029291`

`results/RESULTS.json` retains scores, complete daily banks, actor timings and source fingerprints. The lossless ordered-action traces are in Library `/TITAN-ALDER-current-87d7-apex-9969019-20260908.zip` (359,666 bytes; SHA-256 `104377e78628dd694067b069810ba7aa3f5f06ed1d63c7114a4c8517816e3640`) and are bound here by `results/RESULTS.json` and `results/VERIFICATION.json`.

## Verification

From this directory, with the evidence packet's `traces/` directory available:

```bash
python -B verify_result.py \
  --results results/RESULTS.json \
  --trace-dir /path/to/evidence/traces \
  --output /tmp/current-87d7-apex-verification.json
```

The verifier requires the exact result/source identities, both complete games, 719 ordered transitions per seat, exact gzip trace hashes, normalized action symmetry, and mirrored public economic trajectories.

## Reproduction

`run_apex_shard.py` composes the existing repository `cloud-eval` process-isolated evaluator with the pinned official interpreter. It calls each supplied agent once per decision through fresh actor processes and captures ordered joint actions in a read-only interpreter wrapper. Example:

```bash
python -B run_apex_shard.py \
  --evaluator /path/to/cloud-eval/evaluate.py \
  --loader /path/to/offline-agent/evaluate.py \
  --engine-dir /path/to/pinned/engine \
  --candidate /path/to/extracted-87d7/main.py \
  --apex /path/to/apex/main.py \
  --archive /path/to/titan-current.tar.gz \
  --seed 9969019 \
  --output-dir /tmp/current-87d7-apex
```

This is cloud development evidence, not a hosted leaderboard result or a claim about additional independent seeds.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
