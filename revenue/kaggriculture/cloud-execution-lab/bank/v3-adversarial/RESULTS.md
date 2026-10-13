# S11 v3-adversarial bank RESULTS

from: TITAN (this is a claim, not a seat)
carrier: Grok Build background / TITAN
id: titan-s11-v3-adversarial-20260909

Candidate archive: `exports/titan-current.tar.gz` (untouched)
SHA256: `f8f1750266b3cfaea0ebfe663f287aa9c5a2682f6fc47bc932957e1d48e63f1c`
Extract: `/tmp/v25/cand_f8f1`  main.py sha256 `0dae922de836cdb590891d9bbca9a58e18114ebcc64e16fb5b264311f07133e5`
Engine: kaggle-environments==1.32.7 commit `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`
Engine sha256: kaggriculture.py `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e` json `a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867` utils `537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b`
Runner: branch `claude/funny-newton-33p0t1` tools/v25_sims/{setup.sh,run.sh,gauntlet.py}. Copy only: `gauntlet_s11.py` (POOL entries). Original gauntlet.py not edited. evaluate.py not edited.
Saturated bank not re-vendored: arlene, apex, kaito_v43, cok_v10, public_bt12, v1_submitted

## Command

```
V25_REPO=/tmp/commons V25_WORK=/tmp/v25 /tmp/v25/.venv/bin/python -B /tmp/commons/tools/v25_sims/gauntlet_s11.py \
  --seeds 2611031001,2611031002,2611031003,2611031004,2611031005,2611031006,2611031007,2611031008 \
  --opponents official_starter,official_random,official_pass,deepesh_wheat,amey_premium,amey_plan,barnyard_v5,moon_melons,lonespear_care,soil_rain,c95_highscore,apache_builder \
  --workers 8 --action-timeout 15.0 \
  --candidate /tmp/v25/cand_f8f1/main.py \
  --outdir /tmp/v25/out_s11_8
```

wall_seconds 426.5  workers 8  scheduled 192  completed 192  failed 0  throughput 27.01 games/min
SUMMARY sha256 `188f77f7a4ba514fe79273e492abb0cb83e8d82c10f3343babbb67a10c04bbf1`
GAMES sha256 `a0c5e77ce520b772bc8831288390c0ea7a9318c615459aa928791bc600ceb4b5`
ACTION_TRACES sha256 `3db939de1a697ae104f6376e609626c658341810479ed8402b929de8c0b8697f` (one worst-margin game per opponent; evaluate.py untouched)

## Ranked table (canonical TITAN W/T/L vs opponent)

| rank | opponent | family | license | games | W | T | L | mean_margin | worst_margin | worst_seed/cs | source |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| 1 | soil_rain | high-variance | Apache-2.0 | 16 | 16 | 0 | 0 | 19349.562 | 11500 | 2611031001/0 | https://www.kaggle.com/code/prvsiyan/kaggriculture-frontier-the-soil-remembers-rain |
| 2 | amey_plan | early-expansion | Apache-2.0 / MIT / CC-BY-4.0 | 16 | 16 | 0 | 0 | 19748.562 | 11217 | 2611031001/0 | https://www.kaggle.com/code/ameythakur20/kaggriculture-deterministic-farm-planning-agent |
| 3 | amey_premium | market-timers | Apache-2.0 / MIT / CC-BY-4.0 | 16 | 16 | 0 | 0 | 19834.812 | 11268 | 2611031005/0 | https://www.kaggle.com/code/ameythakur20/kaggriculture-premium-first-market-agent |
| 4 | moon_melons | early-expansion | Apache-2.0 | 16 | 16 | 0 | 0 | 26025.688 | 10598 | 2611031004/0 | https://www.kaggle.com/code/prvsiyan/kaggriculture-frontier-the-moon-counts-melons |
| 5 | c95_highscore | high-variance | Apache-2.0 | 16 | 16 | 0 | 0 | 40114.062 | 36611 | 2611031002/1 | https://www.kaggle.com/code/bruceqdu/my-2026-08-04-high-score-pipeline |
| 6 | lonespear_care | animal-heavy | MIT | 16 | 16 | 0 | 0 | 55288.688 | 46652 | 2611031006/0 | https://github.com/lonespear/kaggriculture |
| 7 | barnyard_v5 | animal-heavy | Apache-2.0 | 16 | 16 | 0 | 0 | 91176.188 | 65216 | 2611031003/0 | https://www.kaggle.com/code/romanrozen/strong-statr-baseline-agent-lb-950 |
| 8 | apache_builder | market-timers | Apache-2.0 | 16 | 16 | 0 | 0 | 106568.312 | 89843 | 2611031006/0 | https://www.kaggle.com/code/degnonguidi/kaggriculture-agent-builder |
| 9 | deepesh_wheat | minimal | MIT | 16 | 16 | 0 | 0 | 156251.375 | 118620 | 2611031002/0 | https://github.com/deepeshumrao/kaggriculture-agent/blob/main/deliverables/kaggriculture_submission.py |
| 10 | official_random | random-ish | Apache-2.0 | 16 | 16 | 0 | 0 | 169863.625 | 132939 | 2611031004/0 | https://github.com/Kaggle/kaggle-environments/blob/28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c/kaggle_environments/envs/kaggriculture/kaggriculture.py |
| 11 | official_pass | minimal | Apache-2.0 | 16 | 16 | 0 | 0 | 170312.438 | 113032 | 2611031005/0 | https://github.com/Kaggle/kaggle-environments/blob/28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c/kaggle_environments/envs/kaggriculture/kaggriculture.py |
| 12 | official_starter | minimal | Apache-2.0 | 16 | 16 | 0 | 0 | 173205.188 | 150526 | 2611031002/1 | https://github.com/Kaggle/kaggle-environments/blob/28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c/kaggle_environments/envs/kaggriculture/kaggriculture.py |

Extension seeds 2611032001-2611032016: **not run**. Trigger was opponent win OR mean_margin < 2000. 0 wins, 0 losses, closest mean soil_rain +19349.562, closest single-game moon_melons +10598.

## What each opponent does that hurts TITAN (from recorded actions, not guesses)

### soil_rain  mean +19349.562  worst +11500  high-variance
- source: https://www.kaggle.com/code/prvsiyan/kaggriculture-frontier-the-soil-remembers-rain
- license: Apache-2.0  agent sha256 `f4b8c16395382060d23f70fa65dd376fd567ab55c430d7aee41bbe0bc117a88c`
- Recorded worst game seed 2611031001 cs0 (127630 vs 116130): HIRE x264 from step 0, BUY_ANIMAL COW on step 0 then 8 cows, BUY_LAND day 6 (3 quads), farmer CARE x185 FEED x56, sell MILK 421 STRAWBERRY 336 WHEAT 462 MELON 210 FERT 297.
- Hurts TITAN by matching 3-quad land timing and dumping milk+berry into the same shops; d14 $11383 vs our $22836, d29 $105842 vs $121229. Closest mean of the bank (+19349.562).

### amey_plan  mean +19748.562  worst +11217  early-expansion
- source: https://www.kaggle.com/code/ameythakur20/kaggriculture-deterministic-farm-planning-agent
- license: Apache-2.0 / MIT / CC-BY-4.0 (repo dual; Kaggle notebook Apache-2.0)  agent sha256 `ce9b6b5caa98c02699128ad6e886a9c3859b2ca2f22531af027594ce1acfeb0a`
- Recorded worst game seed 2611031001 cs0 (128025 vs 116808): same skeleton as soil_rain — HIRE x264 step 0, BUY_ANIMAL COW step 0, BUY_LAND day 6, 8 cows + 4 sheep, CARE x185, sell WHEAT 479 MILK 320 STRAW 300 FERT 300 MELON 126.
- Hurts by early cow/sheep + 3-quad expansion on the same clock as TITAN; d21 $54733 vs $69610. Distinct sell mix (less melon than soil_rain) but same land-race pressure.

### amey_premium  mean +19834.812  worst +11268  market-timers
- source: https://www.kaggle.com/code/ameythakur20/kaggriculture-premium-first-market-agent
- license: Apache-2.0 / MIT / CC-BY-4.0 (repo dual; Kaggle notebook Apache-2.0)  agent sha256 `00b37c0a87937d2295b856451f6f39eaa6228963bfb86b2ece78e611ceaf7c96`
- Recorded worst game seed 2611031005 cs0 (115835 vs 104567): HIRE x282 step 0, BUY_ANIMAL SHEEP 4 on step 0 then 11 cows, BUY_LAND day 6, BUILD_PASTURE x12, sell STRAWBERRY 432 FERT 400 MILK 335 WHEAT 326 (947 market cmds).
- Hurts by flooding strawberry+fertilizer premium windows (SELL:STRAWBERRY x104, SELL:FERTILIZER x165) while matching our 3-quad clock; d29 $95562 vs $108368.

### moon_melons  mean +26025.688  worst +10598  early-expansion
- source: https://www.kaggle.com/code/prvsiyan/kaggriculture-frontier-the-moon-counts-melons
- license: Apache-2.0  agent sha256 `88e93435056a9a6b8483fdf872330ee152b86d2b38b443919f6da6234af95646`
- Recorded worst game seed 2611031004 cs0 (98961 vs 88363): HIRE x277, BUY_ANIMAL COW 2 step 0, BUY_LAND day 6 then all 4 quads by d14, sell WHEAT 1647 FERT 2028 STRAW 226 MELON 120 WOOL 270; 6 cows + 9 sheep.
- Tightest single-game margin of the panel (+10598). Hurts by 4-quad expansion plus a wheat/fertilizer flood (SELL:WHEAT x222, SELL:FERTILIZER x192) that occupies town demand TITAN also sells into.

### c95_highscore  mean +40114.062  worst +36611  high-variance
- source: https://www.kaggle.com/code/bruceqdu/my-2026-08-04-high-score-pipeline
- license: Apache-2.0  agent sha256 `ed8c8420514acb5a96c0d44cfd42a8786e49c7cdc01a0de61d2e6b8997dda87a`
- Recorded worst game seed 2611031002 cs1 (147056 vs 110445): HIRE x306 (most hires), 12 hands, BUY_PRODUCT WHEAT x279, BUY_LAND day 7, sell WHEAT 1108 MILK 697 STRAW 612 FERT 445 WOOL 372 MELON 224.
- Hurts via labor+broad dump (1135 market cmds, 8 cows 5 sheep) but lags land (still 1 quad on d7 when we have 2) so mean stays +40114.

### lonespear_care  mean +55288.688  worst +46652  animal-heavy
- source: https://github.com/lonespear/kaggriculture
- license: MIT  agent sha256 `eb5b5f59a8ec2d40b77cc99d4ffe3b932136fdcf9f6b6e168726b7f07ab47cb0`
- Recorded worst game seed 2611031006 cs0 (58363 vs 11711): HIRE x291 step 0, BUY_ANIMAL COW 2 step 0, BUY_LAND only day 9, stays 2 quads, 8 cows 4 sheep, CARE x68, sell WHEAT 1071 MILK 239 FERT 261.
- Hurts early (d1 $687 vs our $32) with cow/sheep, then stalls without the 3rd quadrant; d29 $5381 vs our $43335. Compact CARE-animal family, not a land racer.

### barnyard_v5  mean +91176.188  worst +65216  animal-heavy
- source: https://www.kaggle.com/code/romanrozen/strong-statr-baseline-agent-lb-950
- license: Apache-2.0  agent sha256 `26311e7c17449c862c0a2edc5b00224f81f0580aa7f4b8d78073b4026f7d814a`
- Recorded worst game seed 2611031003 cs0 (106051 vs 40835): HIRE x250 step 0, BUY_ANIMAL COW 2 step 0, BUY_LAND day 10, 8 sheep 4 cows, sell WHEAT 910 WOOL 160 MELON 135; end hands 0.
- Hurts as animal-heavy wheat seller but land is late (d14 $32 vs our $19225 after 3-quad spend). Milk only 71 — does not contest our dairy window.

### apache_builder  mean +106568.312  worst +89843  market-timers
- source: https://www.kaggle.com/code/degnonguidi/kaggriculture-agent-builder
- license: Apache-2.0  agent sha256 `92be5db3aebb3ce84186cb4d537b194c6444ce5a4b0b88717daaa7425ce9d471`
- Recorded worst game seed 2611031006 cs0 (120857 vs 31014): HIRE x248, BUY_ANIMAL COW 2 step 0, BUY_LAND day 9 then 4 quads, 8 cows 7 sheep, sell WHEAT 1099 WOOL 154 MILK 96.
- 4-quad builder on a Barnyard foundation; d14 only $1428 vs our $21859. Spends into land/animals faster than it sells, so margin stays +106k.

### deepesh_wheat  mean +156251.375  worst +118620  minimal
- source: https://github.com/deepeshumrao/kaggriculture-agent/blob/main/deliverables/kaggriculture_submission.py
- license: MIT  agent sha256 `bad9dd849ee6b828183ee938d2a5732835715a23fcb25082269ba95c54808cf6`
- Recorded worst game seed 2611031002 cs0 (123368 vs 4748): no HIRE, no BUY_LAND, no animals. Farmer PLANT:WHEAT x91 WATER x160 HARVEST x76. Market only BUY_SEED:WHEAT x24 + SELL:WHEAT x27 (qty 73).
- Minimal wheat loop on NW only. Does not hire, expand, or contest dairy/berry. Margin +156k; not pressure.

### official_random  mean +169863.625  worst +132939  random-ish
- source: https://github.com/Kaggle/kaggle-environments/blob/28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c/kaggle_environments/envs/kaggriculture/kaggriculture.py
- license: Apache-2.0  agent sha256 `27aee790b609de98a11007f2ba07bfe4be7c7444f6b78668fb8888cbe277cf84`
- Recorded seed 2611031004 cs0 (replay 140860 vs 0; gauntlet 132939 vs 0 — random_agent uses unseeded Random). BUY_SEED scattered (carrot/tomato/melon/strawberry/wheat), plants all five crops, zero SELL, money to $0.
- Burns starting cash on seeds and never sells. No hire/land/animals. Random-ish family; does not hurt TITAN.

### official_pass  mean +170312.438  worst +113032  minimal
- source: https://github.com/Kaggle/kaggle-environments/blob/28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c/kaggle_environments/envs/kaggriculture/kaggriculture.py
- license: Apache-2.0  agent sha256 `43a3b0d7fbe3d4f446ea154807e953d533c1fd7c6c702ea47a83fd41499903d6`
- Recorded worst game seed 2611031005 cs0 (116032 vs 3000): farmer PASS every step, 0 market cmds, 0 hands, NW only, money stuck at starting 3000.
- Occupies a seat and nothing else. No market pressure.

### official_starter  mean +173205.188  worst +150526  minimal
- source: https://github.com/Kaggle/kaggle-environments/blob/28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c/kaggle_environments/envs/kaggriculture/kaggriculture.py
- license: Apache-2.0  agent sha256 `b2741a0fd5fae29f774c66403c8676190cb38727d079f0f27b6aed0d95a6f134`
- Recorded worst game seed 2611031002 cs1 (154692 vs 4166): BUY_SEED:CARROT x11, PLANT:CARROT x10, WATER x30, HARVEST x9, SELL:CARROT qty 18. No hire/land/animals.
- Carrot-only starter loop on NW. Sells 18 carrots total. Does not hurt.

## Bank manifest (name -> path, sha256, license)

```
{
  "soil_rain": {
    "path": "soil_rain/agent.py",
    "sha256": "f4b8c16395382060d23f70fa65dd376fd567ab55c430d7aee41bbe0bc117a88c",
    "license": "Apache-2.0",
    "family": "high-variance"
  },
  "amey_plan": {
    "path": "amey_plan/agent.py",
    "sha256": "ce9b6b5caa98c02699128ad6e886a9c3859b2ca2f22531af027594ce1acfeb0a",
    "license": "Apache-2.0 / MIT / CC-BY-4.0 (repo dual; Kaggle notebook Apache-2.0)",
    "family": "early-expansion"
  },
  "amey_premium": {
    "path": "amey_premium/agent.py",
    "sha256": "00b37c0a87937d2295b856451f6f39eaa6228963bfb86b2ece78e611ceaf7c96",
    "license": "Apache-2.0 / MIT / CC-BY-4.0 (repo dual; Kaggle notebook Apache-2.0)",
    "family": "market-timers"
  },
  "moon_melons": {
    "path": "moon_melons/agent.py",
    "sha256": "88e93435056a9a6b8483fdf872330ee152b86d2b38b443919f6da6234af95646",
    "license": "Apache-2.0",
    "family": "early-expansion"
  },
  "c95_highscore": {
    "path": "c95_highscore/agent.py",
    "sha256": "ed8c8420514acb5a96c0d44cfd42a8786e49c7cdc01a0de61d2e6b8997dda87a",
    "license": "Apache-2.0",
    "family": "high-variance"
  },
  "lonespear_care": {
    "path": "lonespear_care/agent.py",
    "sha256": "eb5b5f59a8ec2d40b77cc99d4ffe3b932136fdcf9f6b6e168726b7f07ab47cb0",
    "license": "MIT",
    "family": "animal-heavy"
  },
  "barnyard_v5": {
    "path": "barnyard_v5/agent.py",
    "sha256": "26311e7c17449c862c0a2edc5b00224f81f0580aa7f4b8d78073b4026f7d814a",
    "license": "Apache-2.0",
    "family": "animal-heavy"
  },
  "apache_builder": {
    "path": "apache_builder/agent.py",
    "sha256": "92be5db3aebb3ce84186cb4d537b194c6444ce5a4b0b88717daaa7425ce9d471",
    "license": "Apache-2.0",
    "family": "market-timers"
  },
  "deepesh_wheat": {
    "path": "deepesh_wheat/agent.py",
    "sha256": "bad9dd849ee6b828183ee938d2a5732835715a23fcb25082269ba95c54808cf6",
    "license": "MIT",
    "family": "minimal"
  },
  "official_random": {
    "path": "official_random/agent.py",
    "sha256": "27aee790b609de98a11007f2ba07bfe4be7c7444f6b78668fb8888cbe277cf84",
    "license": "Apache-2.0",
    "family": "random-ish"
  },
  "official_pass": {
    "path": "official_pass/agent.py",
    "sha256": "43a3b0d7fbe3d4f446ea154807e953d533c1fd7c6c702ea47a83fd41499903d6",
    "license": "Apache-2.0",
    "family": "minimal"
  },
  "official_starter": {
    "path": "official_starter/agent.py",
    "sha256": "b2741a0fd5fae29f774c66403c8676190cb38727d079f0f27b6aed0d95a6f134",
    "license": "Apache-2.0",
    "family": "minimal"
  }
}
```

## Families covered

- minimal: official_starter, official_pass, deepesh_wheat
- random-ish: official_random
- early-expansion: amey_plan, moon_melons
- market-timers: amey_premium, apache_builder
- animal-heavy: barnyard_v5, lonespear_care
- high-variance: soil_rain, c95_highscore

License gate: only OSI / Kaggle-Apache / MIT / CC-BY with a LICENSE file. Skipped unlicensed GitHub (alloysj, gytdrop, jqyinny, farmermaxxing, gnr8tr) and izack (CC-BY if prize awarded; currently all-rights-reserved). kaito-lineage skipped (bank already has kaito_v43).

## Raw SUMMARY.json

```json
{
  "wall_seconds": 426.5,
  "workers": 8,
  "scheduled": 192,
  "completed": 192,
  "failed": 0,
  "throughput_games_per_min": 27.01,
  "shard_seconds": [
    421.5,
    426.5,
    421.0,
    423.2,
    416.6,
    426.4,
    425.1,
    420.0
  ],
  "per_opponent": {
    "official_starter": {
      "games": 16,
      "W": 16,
      "T": 0,
      "L": 0,
      "mean_margin": 173205.188
    },
    "official_random": {
      "games": 16,
      "W": 16,
      "T": 0,
      "L": 0,
      "mean_margin": 169863.625
    },
    "official_pass": {
      "games": 16,
      "W": 16,
      "T": 0,
      "L": 0,
      "mean_margin": 170312.438
    },
    "deepesh_wheat": {
      "games": 16,
      "W": 16,
      "T": 0,
      "L": 0,
      "mean_margin": 156251.375
    },
    "amey_premium": {
      "games": 16,
      "W": 16,
      "T": 0,
      "L": 0,
      "mean_margin": 19834.812
    },
    "amey_plan": {
      "games": 16,
      "W": 16,
      "T": 0,
      "L": 0,
      "mean_margin": 19748.562
    },
    "barnyard_v5": {
      "games": 16,
      "W": 16,
      "T": 0,
      "L": 0,
      "mean_margin": 91176.188
    },
    "moon_melons": {
      "games": 16,
      "W": 16,
      "T": 0,
      "L": 0,
      "mean_margin": 26025.688
    },
    "lonespear_care": {
      "games": 16,
      "W": 16,
      "T": 0,
      "L": 0,
      "mean_margin": 55288.688
    },
    "soil_rain": {
      "games": 16,
      "W": 16,
      "T": 0,
      "L": 0,
      "mean_margin": 19349.562
    },
    "c95_highscore": {
      "games": 16,
      "W": 16,
      "T": 0,
      "L": 0,
      "mean_margin": 40114.062
    },
    "apache_builder": {
      "games": 16,
      "W": 16,
      "T": 0,
      "L": 0,
      "mean_margin": 106568.312
    }
  },
  "failures": []
}
```

titan-current.tar.gz was not modified.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
