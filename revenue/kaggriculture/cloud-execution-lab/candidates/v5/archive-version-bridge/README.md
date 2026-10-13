# V5 exact V3.1 ↔ V4 authenticated archive bridge

Evidence-only launcher for the owner-reported V3.1 > V4 regression. It does **not** thaw V4, transplant R04, change a gameplay default, republish `titan-current`, or copy either legacy policy into the production runtime.

## Exact authorities

- V3.1: source `a90d888f03987ef0b35cfd20ec3519c6144db08a`, Kaggle submission `56172377`, archive SHA256 `5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361`.
- V4: frozen source `4af1113154e78c662780e6658cd920daac7902e3`, Kaggle submission `56182437`, archive SHA256 `4d9601552b5e25d02d8a33961c0bed54ed92d032dbcd4a72f6ab8e03515ed21b`.

The launcher rejects any other archive bytes.

## Why this exists

The already-merged `candidates/v5/joint-liquidity-bench` is the right custody primitive: after #13388 it copies the declared evaluator/loader/packer/reference policy closure once, authenticates the snapshot, and executes only from that snapshot. Its experiment contract is intentionally narrower, however: exact V4 must be the baseline and exactly one published `frozen_selected.py` must differ.

This bridge reuses that authenticated snapshot helper without changing its joint-liquidity contract. It permits the two exact submitted archives to have different member sets, extracts each into a fresh temporary payload per game, writes the standard raw-file adapter to its root `main.py`, and runs the same pinned official interpreter plus authenticated Apex v7 / Arlene v14 reference opponents.

The local play loop is intentionally a narrow copy of the existing evaluator's `play()` control flow with one addition: it retains the tested seat's returned actions. That produces terminal score/margin, the exact returned-action sequence and canonical SHA256, first V3.1 ↔ V4 returned-action divergence, trace hash, daily banks, callback/process timing, failures, and source/archive/engine identities.

The returned-action field is named `tested_seat_actions` so it can feed the existing `cloud-version-regression-microscope` evidence shape without inventing another divergence analyzer.

## Run on an existing Linux fleet VM

```bash
KG=/path/to/commons/revenue/kaggriculture
ENGINE=/path/to/pinned-engine
V31=/path/to/titan-v31-a90d888f-submitted.tar.gz
V4=/path/to/titan-v4-4af11131-rebuilt.tar.gz

python3 -B bridge.py \
  --kg-root "$KG" \
  --engine-dir "$ENGINE" \
  --v31 "$V31" \
  --v4 "$V4" \
  --seeds 2051966578 \
  --opponents arlene_v14 \
  --seats 0,1 \
  --output v31-v4-bridge-2051966578
```

For a wider fixed-opponent panel, pass comma-separated distinct seeds and `--opponents apex_v7,arlene_v14`. Pair order alternates by cell. Each version gets a fresh extraction and fresh persistent agent process. The default RPC limit is 1.25 seconds and the whole-game limit is 900 seconds. This remains an offline official-interpreter experiment, **not** hosted Kaggle resource enforcement.

Outputs are `run.json`, one game JSON per version/cell, one pair JSON per cell, and rolling `report.json`. Any incomplete game, non-719 tested action sequence, source mismatch, archive mismatch, harness drift, or reference-policy escape fails closed.

## Contracts

```bash
python3 -B -m py_compile bridge.py test_bridge.py
python3 -B -m unittest -v test_bridge.py
python3 -O -B -m unittest -v test_bridge.py
```

The tests lock exact archive authorities, the #13388 snapshot-helper Git blob, safe ordinary-file archive handling across different V3.1/V4 member sets, canonical action hashes, exact first-divergence indexing, and fail-closed identity checks.
