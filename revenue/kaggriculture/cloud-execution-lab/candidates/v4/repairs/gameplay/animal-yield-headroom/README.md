# TITAN V4 ANIMAL-HEADROOM — pre-EOD animal-product cap rescue

**Disposition: source-bound / default-OFF / no activation or economic-strength claim.**

This package closes one narrow existing-herd loss mechanism in the single canonical V4.
It does **not** buy animals, scale herd size, choose FEED/CARE policy, schedule sales,
move actors, or create a second controller.

## Source theorem

The official Kaggriculture engine is bound to Git blob
`3c202c7ee921da239356789e266b694635103fc4`.

For a surviving animal whose production is due at end of day, the engine computes
`gain = 1 + pending_care_bonus` on a fed production day (otherwise base `1`) and then
stores:

`yield_units = min(max_held, yield_units + gain)`

with `max_held = 4` for GOOSE and `6` for COW/SHEEP. `HARVEST` clears the animal's
currently held product into the standing actor's inventory before that end-of-day
refresh. Therefore already-held product can occupy cap headroom and cause part of a
due production increment to be silently clipped. A pre-EOD HARVEST can recover only
the portion of that clip attributable to the already-held product; if `gain` itself
exceeds `max_held`, its intrinsic excess remains unrecoverable.

A concrete reachable witness is a GOOSE placed day 0 that first produces by EOD day 3
and remains unharvested at cap. On EOD day 4, another due production clips at the cap;
an otherwise-idle actor already standing there can harvest the held eggs first and
preserve the recoverable increment.

## Admission contract

`plan_animal_headroom_harvest()` fails closed unless all required state is directly
observable:

- exact final callback of the day;
- literal authored `PASS` for the actor; no existing action is stolen;
- unique actor positions (co-located execution order is refused);
- actor is already standing on a valid current animal;
- the animal survives EOD and its production is due;
- positive **recoverable** clipping, bounded by current held product;
- current animal state is not already above engine `max_held`;
- end-of-day capacity remains safe after current private goods, candidate HARVEST
  cargo, other authored HARVEST/COLLECT cargo, and legal same-turn shed buys;
- SELL/DROP/FEED/other consumption receives **zero** speculative capacity credit.

`apply_animal_headroom_harvest(..., enabled=False)` returns the original action object
unchanged. When enabled and proved safe, it changes only selected literal PASS rows to
`HARVEST`, preserving farmer/hand cardinality and every market row.

## Boundaries

- **HERDSCALE** retains BUY_ANIMAL / herd-size / service-capacity economics.
- **FERTDEADLINE** retains fertilizer-availability overwrite rescue.
- ongoing-crop **HEADROOM** retains TOMATO/STRAWBERRY crop-cap rescue.
- W2 / STARVE / FASTING retain FEED/CARE policy and economics.
- CARRYBANK / capacity owners retain general shed/carry throughput.

This source theorem is **not** a promotion claim. Before any runtime/default activation,
the existing current-native assembler should run a both-seat natural-engagement gate
and report: eligible/rewrite counts, recoverable units, EOD capacity refusals, realized
product later deposited/sold, terminal own cash, rival cash, and margin. Zero natural
rewrites means **COLD**, not a reason to broaden the admission contract.

## Reproduce

From this directory:

```bash
python -m unittest -v test_animal_headroom_harvest.py
python -O -m unittest -v test_animal_headroom_harvest.py
python -m py_compile animal_headroom_harvest.py test_animal_headroom_harvest.py
```

Authored exact bytes were validated with 21/21 tests in normal mode, 21/21 in optimized
mode, and `py_compile` PASS before publication. Hosted CI/current-native games are not
claimed by this source carrier.
