# Submitted V4 funding-policy causal screen

Evidence-only V5 gameplay discriminator for the owner-reported submitted V3.1 > submitted V4 regression.

## Exact source boundary

- submitted V3.1 source: `a90d888f03987ef0b35cfd20ec3519c6144db08a`
- submitted V3.1 archive SHA256: `5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361`
- submitted V4 source: `4af1113154e78c662780e6658cd920daac7902e3`
- submitted V4 archive SHA256: `4d9601552b5e25d02d8a33961c0bed54ed92d032dbcd4a72f6ab8e03515ed21b`

V3.1 uses the simple selected-SELL floor

```python
minimum=current[item] if farm['money']<budget else 0
```

and explicitly preserves later SELL positions rather than moving a sale ahead of a cash-dependent purchase.

Submitted V4 adds two always-on funding mechanisms outside the four public V4 flags and outside E05 joint-SELL composition:

1. `funded_minimum_now(...)` computes a funding-preserving current-sale minimum by simulating the represented acquisition prefix and a stressed BUY_PRODUCT inventory case.
2. after ordinary `materialize_sales(...)`, `fund_same_turn_acquisition(...)` may move already-selected same-turn SELL units from a later row into an earlier empty or same-product SELL row so that the first failing fixed acquisition executes. Total selected same-turn sale quantity remains unchanged, but market interleaving changes.

## 2x2

Every treatment begins from the exact submitted-V4 archive and changes only `frozen_selected.py`.

| arm | V3.1-style minimum rule | disable V4 same-turn SELL reorder |
|---|---:|---:|
| `control` | no | no |
| `min_v31` | yes | no |
| `no_reorder` | no | yes |
| `funding_pair_v31` | yes | yes |

Axis A intentionally retains V4's `item_budget`; it does **not** rewind E08's event-aware horizon. Axis B leaves `materialize_sales` intact and only suppresses the later queue-moving funder. Thus this screen does not reconstruct V3.1, disable the four public flags, or touch E05 joint composition.

`ablation.py` fails closed on submitted-source callsite/provider drift, archive membership changes, and unexpected changed members. `test_queue_witness.py` executes the exact submitted-V4 helper from a detached source worktree and proves safe HIRE funding, no-prefix-slot refusal, BUY_PRODUCT barrier refusal, already-funded identity, and sale-quantity conservation.

## Matched engine screen

`paired.py` reuses the Git-blob-authenticated V5 joint-liquidity evaluator/opponent harness (`719e3514d72bc7ea4c3e505836d16fcddae11019`). It single-reads and SHA256-authenticates both submitted archives, snapshots the evaluator/loader/opponent bank, and runs five arms per matched opponent/seed/seat cell:

- exact V3.1 reference;
- intact V4 control;
- the three V4 funding-policy treatment arms.

The default development grid is Apex + Arlene, seeds `2051966578,1378040481`, both seats: eight matched cells / forty official-engine games. Results retain own score, rival score, margin, treatment deltas versus intact V4, V3.1-vs-V4 reference delta, and the A×B interaction term. Whole-game trace divergence is diagnostic only; it is not candidate-returned-action activation authority.

Example mounted-fleet invocation:

```bash
python paired.py \
  --kg-root /path/to/revenue/kaggriculture \
  --engine-dir /path/to/pinned/engine \
  --v31-baseline /path/to/exact-v31.tar.gz \
  --v4-baseline /path/to/exact-v4.tar.gz \
  --output /fresh/output/directory
```

## Boundary

This carrier changes no gameplay runtime, feature default, canonical config, current archive, release pointer, provider, Kaggle submission, or leaderboard state. A green source workflow proves only that the causal arms are exact and executable. A complete matched panel is still non-authorizing; any useful arm must be consumed into the single staged V5 and pass current-V5 activation/economics plus the canonical release transaction before policy changes.
