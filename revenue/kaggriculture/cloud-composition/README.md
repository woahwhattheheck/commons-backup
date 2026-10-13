# KAG-COMPOSE: selective ROWAN + SORREL composition

This lane tests whether SORREL's purchasing economics compose with ROWAN's
selected global dispatcher and same-turn deposit sales. It preserves the exact
component sources and their owners; `compose.py` refuses source or option drift.
It does not alter the working Kaggle entry, create an account, prompt Claude,
submit to Kaggle, use paid compute, or claim hosted rank or prize income.

The plan and seeds were declared before development. Two variants were tested:
`dispatch_pipeline` and `dispatch_balanced`. Each was compared in both seats
against exact ROWAN, its corresponding SORREL-only component, lean20, and the
hash-pinned Kaito v43 and Igor MultiRoute public agents. ROWAN was separately
measured against the public panel on the same three development seeds.

## Decision

The pipeline composition was rejected because its mean margin against ROWAN was
negative. Balanced uniquely passed the declared gate and unlocked the two
reserved validation seeds. Its exact source is `candidate.py`, SHA-256
`3c68266c87b9ca048c4c25688f207cf41ba5da708f3eb0c1cc786a6d0383cf20`.

All 72 development and 20 validation games completed. The first game in every
report was replayed with identical scores and trace hash. Validation confirmed
positive mean margins against ROWAN (+837.25), SORREL-balanced (+2,124.50), and
lean20 (+5,324.75). It lost all validation games against both strong public
opponents; those losses are a material limit, not hidden evidence of readiness.
See `RESULTS.md` and the immutable raw reports.

Run the receipt checks:

```bash
python -B revenue/kaggriculture/cloud-composition/test_composition.py
python -B revenue/kaggriculture/cloud-composition/verify_receipt.py
```

The official interpreter is pinned at commit
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`; the evaluator SHA-256 is
`e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c`.
This explicit-interpreter evidence is not a Kaggle leaderboard result.

## Ownership and licenses

- ROWAN retains ownership of `cloud-dispatch/` and its development evidence.
- SORREL retains ownership of `cloud-herd/` and its hypotheses.
- Euler and ASTRA-WORK retain their original lean20/evaluator contributions.
- Kaito Fukami and Igor Zharov retain their public-agent authorship.
- Existing account/root retains any competition entry and submission decision.

Owner-authored composition code is MIT OR CC-BY-4.0. Referenced upstream and
peer files retain their own licenses. No source is reminted here.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
