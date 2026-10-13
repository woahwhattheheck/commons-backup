# SHOPSTREAM — farm-tile RNG cursor can change public shop unlocks

Status: **source mechanism + exact-checkout execution confirmed; policy reachability/economics not assessed**.

Canonical home: `main:revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/seat-asymmetry-audit`.
This is an additive extension of the existing shared-RNG/seat-asymmetry source authority, not another
controller, feature key, runtime transform, composition edge, V4 root, archive, or Kaggle submission.

## Authenticated custody

The exact official engine source used by the oracle is:

- `reference/engine/kaggriculture.py`
  - Git blob `3c202c7ee921da239356789e266b694635103fc4`
  - SHA-256 `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`
- adjacent engine metadata required by that real import/execution path, `reference/engine/kaggriculture.json`
  - Git blob `b354d06b742fe48402513792253f1a5c29366b20`
  - 6002 bytes
  - SHA-256 `a82c89c106c84f00ec9842f49cb253b1a2f82a3d57ad205659ae9e45ceb3cc0d`

The exact source/test blobs exercised by the repo-mounted receipt were unchanged after execution:

- `town_shop_rng_oracle.py`: `5dc6d31789833e16296dff8da575a73366702c83`
- `test_town_shop_rng_oracle.py`: `b637105e6957292c94fbbd8b499e2e421e3b7d1c`

## Mechanism

The authenticated official engine creates one end-of-day RNG from
`(episode_seed * 1_000_003) ^ day`. It then processes farm 0 and farm 1 in order. `_spawn_weeds`
consumes one `rng.random()` call for every tile that is `None` when scanned. After both farms have
consumed that shared stream, the same RNG object is used for `rng.choice(sorted(SHOPS))` when a
town-shop unlock is due.

Consequently, **tile occupancy changes the RNG cursor seen by the public shop draw**. The important
quantity for the shop cursor is the number of empty tiles scanned before the draw, not whether a weed
actually spawns. Setting `weedSpawnChance=0` prevents weed creation but does not prevent `rng.random()`
from being evaluated on each empty tile, so it does not remove this coupling.

This is distinct from the existing seat-asymmetry oracle's proven fact that farms receive different
segments of the shared weed RNG stream. SHOPSTREAM binds the downstream *public town state* consequence:
a source-real change to empty-tile count can change which shop is appended.

## Exact-engine witness and execution receipt

`town_shop_rng_oracle.py` authenticates the official engine bytes and executes its real `_end_of_day`
function on a complete checkout. A static `COOP` is used as the one-tile occupancy toggle so
plant/animal refresh cannot confound the witness. `weedSpawnChance=0` is deliberate.

At day argument 2 (unlock of next day 3), with only the default NW quadrant unlocked:

- baseline: both farms have 25 empty NW tiles, so 50 weed-scan RNG draws precede the shop draw;
- variant: one NW tile on farm 0 is a static `COOP`, so 49 draws precede the shop draw;
- seed 5: baseline unlocks `PIZZA_SHOP`; the one-tile variant unlocks `BRUNCH_SPOT`.

The exact repo-mounted receipt on the source/test blobs above passed:

- `python -B test_town_shop_rng_oracle.py`: **9/9 PASS**;
- `python -O -B test_town_shop_rng_oracle.py`: **9/9 PASS**;
- `py_compile` for oracle + test: **PASS**;
- exact-engine report `shopstream.json`: 4151 bytes, SHA-256
  `d1831707a4c33a6a819bec64936617858d83654283949aade0961b174dad944c`.

The exact 512-seed sweep (seeds 1..512) returned:

| Result | Cells |
| --- | ---: |
| total cells | 512 |
| shop changed after one static-tile toggle | **337** |
| shop unchanged | 175 |
| pure cursor-model mismatches vs exact engine | **0** |
| mismatch when the same one filled tile is moved from farm 0 to farm 1 | **0** |

The last control matters: for public shop choice, `(24 empty, 25 empty)` and `(25, 24)` consume the
same total of 49 `random()` calls before `choice`, even though the farms themselves receive different
segments of that stream.

## Strategic boundary

This is a mechanism receipt, not a policy recommendation. It does **not** establish that:

- the episode seed (or enough RNG state) is observable/predictable by the live agent;
- current TITAN naturally reaches a safe, output-changing occupancy decision immediately before an unlock;
- keeping, adding, digging, harvesting, or planting a tile for RNG position is free;
- a preferred shop can be selected reliably against opponent occupancy;
- any such choice improves score, margin, or hosted win rate.

The next useful gate is therefore **reachability before strategy**: replay-capable owners should look
only at callbacks immediately preceding shop-unlock EODs, record the exact post-refresh empty-tile count
for both farms and whether TITAN had a source-legal, otherwise-neutral occupancy choice. If such a
witness exists, town/route owners can evaluate economics. Do not add a standalone SHOPSTREAM controller.

## Reproduce

From this directory in a complete Commons checkout with both authenticated engine files present:

```bash
python -B test_town_shop_rng_oracle.py
python -O -B test_town_shop_rng_oracle.py
python -B town_shop_rng_oracle.py --output /tmp/shopstream.json
python -B -m py_compile town_shop_rng_oracle.py test_town_shop_rng_oracle.py
```

The oracle fails closed on official-engine source-byte drift or on reordering/removal of the source
anchors that bind RNG creation, weed scans, and shop choice. The adjacent `kaggriculture.json` identity
above is part of the explicit exact-execution custody contract even though the oracle's source-anchor
check is intentionally focused on the Python interpreter bytes.
