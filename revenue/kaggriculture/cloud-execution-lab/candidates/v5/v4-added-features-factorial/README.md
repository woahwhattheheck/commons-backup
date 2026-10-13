# TITAN V5 — submitted-V4 four-feature factorial

Evidence-only self-ablation of four selected boolean mechanisms in the **exact submitted V4** package. It is motivated by the owner-reported submitted V3.1 > submitted V4 regression, but it does **not** reconstruct, approximate, or claim equivalence to submitted V3.1. It does not change a runtime default, republish `titan-current`, or create a second V5 policy tree.

## Causal boundary

This experiment starts only from exact submitted V4:

- V4 source: `4af1113154e78c662780e6658cd920daac7902e3`
- exact submitted V4 archive: `4d9601552b5e25d02d8a33961c0bed54ed92d032dbcd4a72f6ab8e03515ed21b`
- exact V4 `TITAN-CONFIG.json` SHA256: `ba18563683125fd89d5473ddb8a5c3e9431db1787a3046f618a9e03af2cb44af`

The four selected submitted-V4 mechanisms are:

1. `idle_fertilizer`
2. `crop_release`
3. `early_capital`
4. `town_procurement`

The harness asks whether disabling these mechanisms, individually or together, improves V4. Because exact submitted V3.1 is a separately assembled package with its own overlays / route behavior, no arm here is labeled or interpreted as V3.1. Exact V3.1↔V4 comparison belongs to the `archive-version-bridge` / top30-union gauntlet and the R04 recovery evidence.

## Hard experiment contract

Every arm is created in memory from the **exact submitted V4 archive**. Archive membership is invariant. All non-config members are byte-identical. An experimental arm may change only `TITAN-CONFIG.json`, and within that file it may change only the four booleans above.

The submitted-V4 archive is read once, SHA256-authenticated from that captured buffer, and parsed only through a private snapshot. The shared `candidates/v5/joint-liquidity-bench/paired.py` helper is Git-blob authenticated at `fbc5e320b8a2ee63af11dc9856c956a679823409` and executes from its captured source bytes. The helper-created evaluator, packer, reference-policy bridge and candidate loader are each captured once against the authenticated harness receipt before execution. Evaluator, packer and bridge execute from those captured buffers; the loader is republished from its captured bytes to a separate private runtime-only path. Opponent adapters bind that same private authenticated runtime root for the entire panel. Caller-visible `.harness-snapshot` is copied only as evidence and is never an execution authority. The run receipt records exact evaluator/packer/bridge/loader SHA256 values and the private-runtime execution mode. The dedicated PR workflow checks out and asserts the exact carrier head rather than a synthetic merge checkout.

## Screen design

`--design screen` runs six canonical arms per seed / seat / opponent cell:

- `v4`: TTTT, byte-identical submitted V4 baseline
- `all_four_off`: FFFF, a V4 self-ablation of the four selected mechanisms
- `off_idle_fertilizer`
- `off_crop_release`
- `off_early_capital`
- `off_town_procurement`

For compatibility, explicit CLI input may still spell the FFFF arm as `v31_flags`; it is immediately canonicalized to `all_four_off`, and `v31_flags` never appears as experiment/report identity.

The baseline is run once per cell, not once per comparison. Arm order rotates across cells. The default two seeds are the already-known Sian/Gracie loss-rematch seeds `2051966578,1378040481`, both seats, against authenticated `apex_v7` and `arlene_v14`.

If the screen shows interactions, `--design full` runs all 16 masks (`mask_0000` through `mask_1111`) with the same byte-custody contract.

## Interpretation

- If `all_four_off` materially beats `v4`, some effect within these four selected V4 mechanisms or their interaction is worth isolating further.
- The single-off arms localize main effects; the full factorial resolves interactions.
- If `all_four_off` does not improve V4, stop blaming this four-toggle set and spend effort on exact V3.1↔V4 returned-action / source differences instead.
- This package produces evidence only. No arm is eligible for a production default change without separate current-V5 natural-engagement and promotion gates.

## Run

```bash
cd revenue/kaggriculture/cloud-execution-lab/candidates/v5/v4-added-features-factorial

python3 -B paired.py \
  --kg-root /workspace/commons/revenue/kaggriculture \
  --engine-dir /workspace/engine \
  --baseline /workspace/titan-v4-4af11131-rebuilt.tar.gz \
  --output /workspace/results/v4-added-feature-screen
```

Full factorial:

```bash
python3 -B paired.py ... --design full --output /workspace/results/v4-added-feature-full
```

Source gates:

```bash
python3 -B -m py_compile paired.py test_paired.py
python3 -B -m unittest -v test_paired.py
python3 -O -B -m unittest -v test_paired.py
```
