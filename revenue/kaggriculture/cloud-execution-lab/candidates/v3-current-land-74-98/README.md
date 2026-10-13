# TITAN V3 current land-74/98 candidate

This package ports one measured gameplay mechanism onto the **exact current V2.5 archive** without touching the canonical runtime, config, export pointer, or submission state. The candidate appends `BUY_LAND` at route steps 74 and 98 when the row has a free market slot and no existing land order.

## Why this arm

The historical L01 six-opponent panel completed 192 games per arm. Its LAND arm changed the Arlene stratum from 24–8 with mean margin −2418.219 to 32–0 with mean margin +1631.031; the other five aggregate opponent summaries were unchanged. The current archive is different (`a055fd56…`) and has zero full games attributable to all of its changed bytes, so those historical results are **mechanism evidence only**, not a score claim for this candidate.

## Isolation improvement

The original research overlay mutates controller route objects in place. This port uses copy-on-write:

- the source route mapping and nested rows are not mutated;
- aliases between route keys remain aliases in the candidate bank;
- untouched route lists and rows retain object identity;
- only admitted rows 74 and 98 receive new market lists;
- duplicate, full-slot, and short-route cases fail closed;
- the patch is idempotent per controller and is reapplied after TITAN replaces its controller at an episode deadline;
- existing fallback `BUY_LAND` rows at 150 and 265 remain byte-for-byte unchanged.

That lets a control and candidate coexist in one interpreter without route-bank contamination.

## Exact base

`CURRENT-BASE.json` pins commit `d71617dde24f48969d1a54ba5dff28f45b64e4f5`, archive SHA-256 `a055fd56ca5821208096f37787f77dbdddc2f65c14c24132d6e219a05e6f02ba`, canonical `main.py`, config, source manifest, Git blob, byte count, and entrypoint.

## Build and verify

From this directory:

```bash
python build_candidate.py \
  --base ../../exports/titan-current.tar.gz \
  --output /tmp/titan-current-land-74-98.tar.gz

python verify_candidate.py \
  --base ../../exports/titan-current.tar.gz \
  --candidate /tmp/titan-current-land-74-98.tar.gz \
  --report /tmp/titan-current-land-74-98.verify.json
```

The builder rejects any base-archive, entrypoint, or config hash drift. The verifier requires exactly one changed existing member (`main.py`), exactly three additions (`canonical_main.py`, `land_overlay.py`, `LAND-74-98.json`), and byte identity for every other runtime member. Builds are deterministic: identical inputs produce identical compressed bytes.

## Tests

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

The tests cover copy-on-write isolation, alias preservation, exact insertion sites, fallback preservation, duplicate/full/short-route decline, per-controller install idempotence and deadline reinstallation, deterministic archive construction, path traversal rejection, hash-pin failure, and the official extracted engine's first and second land costs/unlock order.

## Required game gate

`PANEL-PLAN.json` reserves unseen seeds `2611062001`–`2611062016`, six exact opponents, and both candidate seats: 192 paired cells for the candidate and 192 for the unchanged current control. Promotion requires complete/error-free cells, no negative opponent or seat stratum, and an exact trace for any negative pair. No leaderboard or current-strength claim is made until that panel is complete.
