# Current TITAN 87d7 vs exact frozen SELL — development shard 9969055

This additive result evaluates the exact canonical TITAN archive against its strongest direct same-package frozen-SELL control on one previously unused development seed in both seat orders. It changes no controller, configuration default, canonical archive, CURRENT pointer, workflow, or provider state.

## Result

- Independent seeds: **1** (`9969055`)
- Mirrored seat records: **2**
- Current candidate: **2W / 0T / 0L** across the two seat records
- Current cash: **125,508** in each seat
- Frozen-SELL control cash: **125,268** in each seat
- Margin: **+240** in each seat
- Candidate maximum call: **0.153250 s**
- Candidate maximum evaluator RPC: **0.156962 s**
- Failures/timeouts: **0**

The mirrored seats are a symmetry check around one independent seed, not two independent samples.

## Causal action difference

Every farmer action and every hand action is identical between the current candidate and the frozen control. Their complete actions differ only in two WHEAT seed-purchase slots:

| Step | Frozen control | Current candidate | Incremental cash | Cumulative cash |
|---:|---|---|---:|---:|
| 600 | `BUY_SEED WHEAT 17` | `BUY_SEED WHEAT 2` | +150 | +150 |
| 624 | `BUY_SEED WHEAT 9` | preserved empty slot `[]` | +90 | +240 |

All other market slots are identical, including the seven HIRE orders at step 600 and the eight HIRE orders at step 624. The +240 persists to terminal cash without changing the control's worker tape.

## Exact inputs

- Canonical archive SHA-256: `87d7b8bf7c4e9467f4b6b46887abe2eb03735c42453cdbf4f2cac12c5962acc7` (292,007 bytes)
- Candidate `main.py` SHA-256: `a4ecdb513b48fa51877fe509597a84dd753dfe71d2d76a406ee3dc51475a9008`
- Frozen-control wrapper SHA-256: `55cd3a1ac560e12209d7d708d549efcbfff167576b181b2b45338aeb0d754633`
- Official engine pin: `kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`
- Canonical source-manifest SHA-256: `30f229d43bf4e6cbc8941fb91e5be4d521b5859c6c0f60bd626adda8009bba9f`
- Source artifact: GitHub Actions run `34198994016`, canonical artifact `10045029291`

The control is constructed from the same immutable archive as:

```python
TitanAgent(Features(
    consumer="frozen",
    seed=False,
    funding=False,
    committed=False,
    terminal_route=False,
    redundant_hire=False,
    terminal_history=False,
    budget_seconds=1.0,
    reserve_seconds=0.01,
))
```

`results/RESULTS.json` retains scores, complete daily banks, actor timings, source identities, and lossless trace hashes. The two ordered-action traces are retained in Library packet `/TITAN-ALDER-current-87d7-frozen-9969055-20260908.zip` and bound by `results/VERIFICATION.json`.

## Verification

```bash
python -B verify_result.py \
  --results results/RESULTS.json \
  --trace-dir /path/to/evidence/traces \
  --output /tmp/current-87d7-frozen-verification.json
```

The verifier requires exact source/archive/control identities, two complete 719-transition records, seat-normalized action and economic symmetry, exactly the two seed-order differences above, identical worker actions, and the +150 then +90 cash bridge.

## Reproduction

`run_frozen_shard.py` composes the existing repository `cloud-eval` process-isolated evaluator with the pinned official interpreter. It calls each supplied agent once per decision through fresh actor processes and captures ordered joint actions in a read-only interpreter wrapper.

```bash
python -B run_frozen_shard.py \
  --evaluator /path/to/cloud-eval/evaluate.py \
  --loader /path/to/offline-agent/evaluate.py \
  --engine-dir /path/to/pinned/engine \
  --candidate /path/to/extracted-87d7/main.py \
  --control /path/to/extracted-87d7/control_frozen_sell.py \
  --archive /path/to/titan-current.tar.gz \
  --seed 9969055 \
  --output-dir /tmp/current-87d7-frozen
```

This is cloud development evidence. It is not a hosted leaderboard result and does not imply an additional independent seed from the mirrored seat record.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
