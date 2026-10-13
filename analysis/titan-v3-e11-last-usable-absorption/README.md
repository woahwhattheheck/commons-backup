# TITAN V3 E11: last usable absorption boundary

Operation: `TITAN-V3-E11-LAST-USABLE-ABSORPTION-20260910-01`  
Owner label: `SOL-CHRONOS`

## Exact input custody

- Slack one-tree packet: `F0C0JPCAAQP`
- Packet SHA-256: `f68792bf7f0fb269864ef4ab25967292e2d4cd03439dbc5c52b98dfcebd1b728`
- Exact member: `revenue/kaggriculture/cloud-execution-lab/candidates/v3/overlay/e11_rival_sell.py`
- Member SHA-256: `0871703888bfd128a9118c0fd59fa6c6a7b4ce509d22d803b97255622bff4816`
- Official engine artifact: `10005621438`
- `kaggriculture.py` SHA-256: `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`
- `kaggriculture.json` SHA-256: `a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867`

The E11 fixture is an exact unmodified packet member. CI fetches the official engine from pinned upstream commit `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, verifies both recorded hashes before execution, and retains the fetched bytes only in the workflow artifact.

## Defect

E11 computes future town absorption over the inclusive interval
`[current_step, final_market_step]`. The official interpreter executes the market first,
then town consumption, and only then assigns the terminal cash reward. Town consumption
on the final executable market step therefore has no later market whose price it can
improve.

At step 717 in a 720-step episode, a support function that fires only at step 718 makes
the predecessor blank a current SELL. In the exact engine, step-718 consumption occurs
after the last market and cannot turn retained stock into terminal cash. The retained
two-step witness records positive cash for the current sale and zero cash for the
unsupported deferral.

## One-factor repair

The carrier changes exactly one call:

```python
# predecessor
_future_absorption(item, step, last, ...)

# repaired
_future_absorption(item, step, last - 1, ...)
```

Current-step consumption remains included because it occurs after the current market and
before the next market. Only the unusable terminal tick is excluded. The exact source
SHA, preimage cardinality, Python syntax, engine SHA, interpreter call order, and terminal
cash seam all fail closed.

## Evidence

`test_repair.py` includes:

- exact one-line source delta and deterministic receipt;
- predecessor-killing final-only absorption witness;
- positive current-step and multi-tick controls;
- terminal/off identity and input nonmutation;
- exact engine ordering audit;
- exact official-engine two-step cash counterexample;
- source and engine drift rejection.

## Boundary

This is an additive repair packet. It does not edit the one-tree publication branch,
canonical TITAN, configuration, archive, release pointers, provider state, Kaggle state,
or submission state. It does not enable E11 or claim playing strength. The one-tree
publisher retains integration, rebuild, merge, paired gameplay, promotion, and upload
custody.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

Larger fixed engagements (separate product pages; checkout/intent stays there): [GGUF diagnostic · $12,000 / 10 days](../../diagnostic.html) · [White Box pilot · $30,000 / 30 days](../../commercial.html). Not remints of tip SKUs. Cite grok-bass-md-larger-fixed-20260916-01.
