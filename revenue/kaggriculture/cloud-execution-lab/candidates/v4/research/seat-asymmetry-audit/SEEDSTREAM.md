# TITAN V4 SEEDSTREAM — multi-day public RNG inference

**Disposition: bounded research evidence only. No runtime/controller/default/config/COMPOSITION/INTEGRATION/archive/Kaggle mutation.**

SEEDSTREAM extends the existing `research/seat-asymmetry-audit/` authority. It does not create a sibling V4 or replace the already-landed `SEED-IDENTIFIABILITY`, `TOWN-RNG`, or `SHOPSTREAM` results.

## Why this exists

`SEED-IDENTIFIABILITY` correctly killed the stronger claim that one day-0 weed pattern reveals the hidden episode seed. The authenticated engine emits only Bernoulli threshold outcomes, and a common no-weed opening remains massively ambiguous.

The same engine also resets a deterministic RNG every EOD with:

```text
Random((seed * 1_000_003) ^ day)
```

and consumes that *same daily stream* in this source order:

1. one `rng.random() < weedSpawnChance` test for every currently empty tile on farm 0, then farm 1;
2. if the next day is a shop-unlock boundary and the town is below `MAX_SHOP_INSTANCES`, one `rng.choice(sorted(SHOPS))` whose result is public.

That means **multiple days of public evidence can be intersected without guessing hidden actions or reading the seed**.

## Public-evidence contract

`seed_stream_identifiability.py` accepts only evidence that can be reconstructed from public state:

- the exact pre-EOD empty tiles for both farms, in engine farm/y/x order;
- which of those exact empty tiles became a `WEED` after EOD;
- the public `town.unlocked_shops` list before and after EOD.

The snapshot helper fails closed if a pre-EOD empty tile becomes anything other than `None` or `{"kind": "WEED"}`. History rows must be consecutive and their shop lists must join exactly. On a source-predicted unlock day, exactly one public shop append is required; off schedule (or after the eight-instance cap) no append is permitted. Shop duplicates remain valid because the engine draws with replacement.

The code pins the official interpreter as both:

- Git blob `3c202c7ee921da239356789e266b694635103fc4`
- SHA-256 `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`

and preserves predecessor provenance to `seed_identifiability.py@19ce8936451a20dbf0eaa9944b8a918f41fb3cbc`.

## Bounded candidate inference

For each explicitly bounded candidate seed, SEEDSTREAM regenerates only the public daily signature and intersects survivors across days.

The bounded result is one of:

- `NO_MATCH_IN_BOUNDED_DOMAIN`
- `AMBIGUOUS_IN_BOUNDED_DOMAIN`
- `BOUNDED_UNIQUE_NOT_GLOBAL`

Even one survivor **never** becomes a global-identifiability claim unless another authority proves the complete seed domain itself.

### Reproducible source-level panels

With the no-action public EOD generator (spawned weeds remain occupied), true seed `1` gives:

| searched domain | day 0 | day 1 | day 2 |
|---|---:|---:|---:|
| `[0, 4096)` | 3,190 | 15 | **1** |
| `[0, 65536)` | 51,083 | 205 | **1** |

This is the useful result: the day-0 falsifier and the multi-day bridge are both true.

The guard is not ceremonial. True seed `255` over `[0,4096)` remains ambiguous after six EODs:

```text
3190 -> 2500 -> 237 -> 194 -> 152 -> 28
```

so SEEDSTREAM must carry the whole candidate set rather than silently selecting one seed.

## Consensus-only forecast

`consensus_forecast()` may expose a future public prediction only from the complete surviving bounded set.

It reports separately whether:

- every survivor predicts the same weed bit-vector;
- every survivor predicts the same public shop append;
- the full public signature agrees.

If survivors disagree, the component is withheld. No MAP guess, first-candidate guess, or single-seed shortcut is allowed.

This is deliberately weaker than a gameplay policy. It can become a safe input to RNGREACH/SHOPSTREAM only after a current-native consumer proves:

1. the bounded seed domain is legitimate for that environment;
2. public history capture is complete;
3. the intended occupancy change is itself legal/source-real;
4. all surviving candidates agree on the decision-relevant consequence; and
5. paired gameplay evidence shows positive value.

## Validation

Authored-byte source-independent gate:

```text
PASS 19/19 seed-stream-identifiability tests
PASS 19/19 under python -O
py_compile PASS
```

The checkout-only engine-authentication test executes automatically when the canonical repository layout is present. This cloud seat had no mounted Git checkout, so the local claim is limited to the pure gate above; hosted/current-repo execution remains the merge gate.

## Authority boundary

- `decision_authority = false`
- `runtime_mutation_authority = false`
- `global_identifiability_proved = false`
- `production_seed_cracker_authorized = false`

SEEDSTREAM is a bridge from public observations to bounded source inference, not permission to read or assume a hidden seed.
