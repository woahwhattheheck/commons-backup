# TITAN V5 fertilizer-floor arbitrage current ABI

`TITAN-V5-FERT-FLOOR-ARBITRAGE-CURRENT-ABI-REAUTHOR-WIDE` is a fresh current-V5 re-author, **not** a recovery of the lost `r04_fert_arbitrage` payload.

## Durable authority

The source-real mechanic is already merged and corrected in the repository:

- mechanism research PR: #13057;
- corrected follow-up commit: `d8fa49ccbedf2a51c65431bae51a7f99e648da20`;
- current `fert_floor_apply.py` Git blob: `a32160a2298e9d92a824b52bc272535583a85a67`;
- authenticated official engine blob: `3c202c7ee921da239356789e266b694635103fc4`.

That authority proves the official interpreter path `BUY_PRODUCT FERTILIZER -> shed -> PICKUP -> FERTILIZE -> WATER -> legal HARVEST -> sale`. It also proves an important pricing detail: `BUY_PRODUCT` is charged at the **post-buy inventory** quote, not the currently displayed quote.

The historical positive policy family was recorded as `buy_price=2 floor-only`; the high-price `buy_price=45` path was strongly negative and is intentionally absent. Historical uplift is motivation only, not current-V5 promotion authority.

## Source-real price boundary

For the authenticated default engine's FERTILIZER linear market:

- pre-buy FERT inventory `10489` is the first inventory whose one-unit **post-buy** quote is at most `$2`;
- pre-buy inventory `10494` is the first inventory whose one-unit post-buy quote is the `$1` engine floor;
- the public quote itself rounds to `$1` starting at inventory `10493`, so a policy trigger based on `public_price == 2` is not equivalent to the historical `buy_price=2` transaction ceiling.

The adapter therefore binds both public price and market inventory to these authenticated boundaries. It refuses custom `marketParams` rather than projecting the constants onto a different market model.

## Current ABI theorem

The adapter is selected-action-only and never invokes or mutates a producer/controller. It may do exactly two things:

1. **Low-price acquisition:** append one `BUY_PRODUCT FERTILIZER 1` only when the authenticated one-unit post-buy quote is at most `$2`, the observed public quote agrees with the pinned source boundary, the farm can fund that source quote, a market slot exists, the farm owns no fertilizer, the parent has no fertilizer market intent, and a live plant needs fertilizer.
2. **Application:** replace only a literal actor `PASS` with `FERTILIZE` when that same actor already carries fertilizer and is standing on an eligible live plant.

It never invents `PICKUP`. If current V5 does not naturally move bought fertilizer from shed to a worker, engagement should be zero and the candidate should die rather than grow a second route/controller.

Malformed observation/action/cardinality/inventory/price/config evidence fails closed. Inputs are deep-copy safe; non-PASS parent commands are never overwritten. Extremely large numeric evidence is handled without float coercion/overflow and gains no price authority.

## Natural-engagement receipt

`fert_floor_engagement.py` consumes a source-bound ordered tape of **real returned actions plus the next public observation**. A returned command by itself is not engagement. `engaged=true` requires one complete naturally executed chain:

1. source-authorized low-price `BUY_PRODUCT FERTILIZER 1`, followed by one unit arriving in shed custody;
2. parent-returned `PICKUP FERTILIZER`, followed by that unit leaving shed and entering one actor inventory;
3. parent-returned `FERTILIZE` by the same actor on an eligible plant, followed by one unit being consumed and `fertilized_until_day` increasing through the official window.

The receipt records the observed public quote, authenticated post-buy quote, and pre-buy market inventory. The tape must be contiguous for one player and binds exact `source_sha`, `engine_id`, and canonical row SHA-256. A second fertilizer market action during an active chain makes provenance ambiguous and aborts that chain. Failed commands, skipped callbacks, player changes, malformed evidence, and unconfirmed engine effects cannot produce engagement.

This receipt authorizes **only the next evidence spend**. It is not an economics, promotion, or activation receipt.

## Promotion path

This directory is research/source only. It makes no runtime/default/TITAN-CONFIG/CURRENT/archive/release/Kaggle changes.

Before any integration or activation:

1. authenticate the exact current V5 selected-action/source identities consuming this adapter;
2. obtain a natural-engagement receipt proving low-price acquisition -> real pickup custody -> official fertilizer effect;
3. require matched OFF/ON both-seat economics against current V5 and the exact V3.1 champion floor;
4. reject promotion if the only positive cells rely on constructed idle callbacks or if displaced current actions dominate the fertilizer gain.

## Focused contract

```bash
python -B -m py_compile \
  fert_floor_current.py fert_floor_engagement.py \
  test_fert_floor_current.py test_fert_floor_engagement.py
python -B -m unittest -v \
  test_fert_floor_current.py test_fert_floor_engagement.py
python -O -B -m unittest -v \
  test_fert_floor_current.py test_fert_floor_engagement.py
```
