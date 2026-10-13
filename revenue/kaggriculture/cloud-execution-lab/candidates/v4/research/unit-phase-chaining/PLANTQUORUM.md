# ASTRA-PLANTQUORUM — atomic PLANT collateral relief

This is a default-OFF admission experiment inside the existing canonical `research/unit-phase-chaining/` authority. It does not add a controller, runtime hook, feature/config key, composition edge, archive, or Kaggle behavior.

## Engine theorem

The official engine (`kaggriculture.py` Git blob `3c202c7ee921da239356789e266b694635103fc4`) performs a callback-wide seed preflight **before** any unit action executes:

1. collect every authored `PLANT <crop>` row from farmer + hands;
2. count demand by crop without checking whether the actor exists or whether its current tile is plantable;
3. if same-crop demand is greater than the observed seed count, replace **every** `PLANT` row for that crop with `PASS`;
4. only then execute actor 0, actor 1, ... sequentially.

The existing UNITPIPE admission intentionally preserves the raw PLANT multiset and therefore refuses this condition. PLANTQUORUM covers only a stricter collateral case: a row that cannot possibly plant can still contribute to the preflight count and suppress a different authored row that is guaranteed legal.

## Strict admission

`plant_quorum_admission.py` may rewrite an authored `PLANT` row to `PASS` only when that row is source-certain to no-op for one of two reasons:

- the action vector contains a hand row for an actor that does not exist in the current farm state; or
- the actor is the **only** actor currently on its tile and that tile is non-empty (including `LOCKED`). No other actor can clear that tile before this PLANT because tile operations act only on the actor's own standing tile.

Even then, the helper engages only when removing all such poison rows for a crop is sufficient by itself to make remaining demand `<= available seeds`, and at least one remaining authored row belongs to a unique actor on an empty tile. Therefore the helper never chooses among competing legal PLANTs. It preserves actor order, every surviving PLANT row, every non-PLANT unit row, the full market vector, crop identities, quantities, movement and observed seed count.

Ambiguous co-location is a hard refusal: a co-located earlier actor might mutate the tile before a later PLANT, so PLANTQUORUM will not label either row source-certain poison from the initial tile alone. Zero-seed callbacks also remain unchanged because removing poison cannot create a productive plant without seed inventory already present before the unit phase.

## Why this is mechanically different from seed funding

Market orders execute **after** all unit rows. A same-callback `BUY_SEED` cannot fund a PLANT in that callback. PLANTQUORUM never moves or invents a purchase; it only prevents a provably dead PLANT row from poisoning the engine's pre-existing seed quorum when enough seed is already physically present.

## Validation boundary

The source theorem is exact; economic value is not. A current-native gate must authenticate current action producer/runtime bytes and census natural callbacks satisfying the strict admission. Zero engagements closes the lane COLD. Positive engagements require paired OFF/ON official-engine execution and terminal economics before any runtime wiring discussion.
