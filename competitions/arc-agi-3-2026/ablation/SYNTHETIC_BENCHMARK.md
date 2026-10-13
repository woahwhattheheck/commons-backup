# Synthetic ablation benchmark receipt

This is a **data-free causal harness receipt**, not evidence of official ARC-AGI-3 game performance. It exists to pin hypotheses and accounting before any authorized public-game trace adapter is used.

Exact command from `competitions/arc-agi-3-2026`:

```bash
python -m ablation.benchmark --seeds 64 --budget 24 --output /tmp/arc3-ablation
```

Bundle digest:

`78a573d603ade9b02cce16674a934f937b7763980839d64a57b73a80cf79366a`

| Ablation | Pairs | Control success | Treatment success | Mean real-action delta (T-C) | Treatment offline/sim work | Receipt |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Full animation vs settled frame | 64 | 100.00% | 100.00% | -6.782 | 0 | `ab7ed5bceae5933ab55cade9de90159715922c43562aa9caad76a828a9cbe983` |
| Information gain vs random probes | 64 | 100.00% | 100.00% | -0.875 | 960 | `87c39927c7c90b58a4eb3c7099b22cf205b462d87a03edd2605db704ab3cc57d` |
| Coordinate reduction vs 64-cell superset | 64 | 34.38% | 100.00% | -12.110 | 4096 | `b92f78297bcfea00a3758c8533a7fe0fcfd1aabb5d09d45ff213d030ce0bc147` |
| Cross-level transfer vs cold start | 64 | 100.00% | 100.00% | -1.782 | 1536 | `78878032daa417065fe668bf368285fa72346ac5ab9d9548216e4c3894080a45` |

Additional pinned diagnostics from the exact receipt:

- full-animation action-delta bootstrap95: `[-7579, -5938]` milli-actions; evidence delta `+192`; invalid-action delta `-102`;
- information-gain bootstrap95: `[-1297, -438]`; evidence delta `+176`; invalid-action delta `-152`;
- coordinate reduction bootstrap95: `[-13235, -10954]`; control budget exhaustion `42/64`, treatment `0/64`; evidence delta `+704`;
- cross-level transfer bootstrap95: `[-2188, -1375]`; transfer reuse delta `+320`; evidence delta `+294`.

## Interpretation ceiling

These directions are intentionally manufactured from controlled synthetic scenario families so a test can tell whether the harness distinguishes the declared treatment. They **must not** be promoted to real-game effect-size claims. The high-value next step is to preserve this exact paired contract and replace only the scenario adapter with an authorized full-frame public-game trace corpus, retaining identical seeds/pair IDs where meaningful, real-action accounting, source digests, and the fail-closed authority boundary.

No official game action, Kaggle submission, leaderboard score/rank, prize, payment, cash, or revenue is claimed by this receipt.
