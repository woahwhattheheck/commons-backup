# TITAN V5 P02 — goose capacity economy

This directory is the **single P02 research carrier** for the canonical
`production-v3` V5 family. It does not create a sibling V5 and does not modify
CURRENT, defaults, release state, or Kaggle submission state.

## Hypothesis

The prior SPARK herd sweep said herd 20 was the oracle peak while herds >=50
went negative, but that was not full gameplay. P02 therefore tests only the
smallest observable extension: **one** extra GOOSE into an already-built empty
COOP, capped below 20 total geese.

The carrier uses the official-engine facts that a goose costs 300, first
produces after four day-boundaries, produces daily, holds at most four EGG,
FEED gates the CARE bonus, and animal PLACE consumes one carried animal. It
does not assume free feed or free service.

## Exact production-v3 composition

The control is the deterministic 92-member production-v3 archive SHA256
`20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239`.
That archive already contains its own `baseline_main.py`; P02 preserves that
member byte-for-byte. The builder authenticates exact production-v3 `main.py`
SHA256 `b98aec64f83ea9a216def7ab1fef320a6498ae37816f506af1f891c934027035`,
patches the single public return seam so P02 sees the fully composed parent
action, and adds only `goose_capacity_economy.py`. The candidate therefore has
93 members: one changed existing member (`main.py`) and one new helper member.

This intentionally avoids a second wrapper stack. P02 runs after the parent's
outer `DeliveryChoice` commit and never substitutes the older embedded
`baseline_main.py` for production-v3.

Materialization consumes the exact archive, not an extracted-directory digest:

```
python build.py \
  --baseline production-v3.tar.gz \
  --tar p02.tar.gz \
  --receipt p02-receipt.json
```

Archive and receipt are create-exclusive. Both reservation descriptors remain
open through final pathname/inode and byte verification, parent directories are
fsynced, and failure removes only still-owned outputs.

## Workforce custody

P02 reuses the R04 V233 principle instead of competing with the route:
`_v219_native_day` determines the active route's authored hand count and last
HIRE for each day. P02 may add hands only after hour 4 and after the last native
HIRE, so V233's hour<=2 and V219's hour<=3 dynamic expansion windows have
already closed and their hands are visible in the observation. Its actors
therefore live strictly after the parent's actual hand rows.

Initial deployment uses two added hands so PLACE can execute before FEED on the
same callback. Later service uses one added hand to harvest, feed, and care.
No SELL rows are added; canonical sale/delivery logic keeps ownership of egg
monetization.

## Fail-closed gates

The treatment returns the exact parent action unless all of these are source-
observable and valid:

- exact standard configuration and active R04 native plan;
- day 12..18, total geese <20, and an observed empty COOP;
- route-compatible HIRE/market-slot schedule through the horizon;
- conservative shed-capacity and cash reserve;
- projected egg revenue (20% price haircut) clears goose + buffered WHEAT +
  route-indexed added-HIRE cost by at least 100;
- requested purchase/hire state is observed on the next callback.

Ambiguity, target drift, purchase shortfall, capacity pressure, late native
HIREs, or same-step retry all fail closed.

## Native success criterion

Source tests are only custody. Promotion requires natural engagement on exact
`production-v3`, confirmed extra-goose placement, harvested/delivered EGG, and
matched own-score/margin improvement. Oracle-only benefit or an idle extra
goose is a kill.
