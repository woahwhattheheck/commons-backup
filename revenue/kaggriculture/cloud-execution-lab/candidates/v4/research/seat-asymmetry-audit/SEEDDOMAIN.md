# TITAN V4 SEEDDOMAIN — episode-seed provenance and finite-panel consensus

**Disposition: research-only source/provenance closure inside the existing `research/seat-asymmetry-audit/` authority. No runtime/controller/default/config/COMPOSITION/INTEGRATION/archive/Kaggle mutation.**

SEEDDOMAIN is the source-bound successor to merged SEEDSTREAM #13090. It answers the prerequisite left open by #12898 and #13090: *what seed domain, if any, is actually complete enough to enumerate?*

## Pinned source theorem

The pinned Kaggle seed utility (`utils.py` Git blob `91c8822ee6201ba4a5a8416c7dbe34f95dd61c87`) resolves an episode seed in this order:

1. preserved `env.info["seed"]`;
2. explicit `configuration.seed`;
3. caller fallback, otherwise `random.randrange(2**31)`.

It then clears the seed from configuration and persists the resolved value in `env.info`.

The source contract byte-authenticates the official interpreter (`kaggriculture.py` blob `3c202c7ee921da239356789e266b694635103fc4`) as well as the pinned Kaggriculture config (`kaggriculture.json` blob `b354d06b742fe48402513792253f1a5c29366b20`). The config declares `seed` only as `integer | null`, default `null`; it contains **no `minimum` or `maximum`**. Therefore the pinned engine schema itself supplies no finite complete domain for an explicitly provided seed (nor for a seed already preserved in `env.info`).

The fallback path is different: when it is genuinely taken and no custom fallback is supplied, source gives the complete finite interval:

```text
0 <= seed < 2**31
```

That is 2,147,483,648 candidates. Its finiteness is a provenance fact, **not** authorization to brute-force it in production.

The pinned offline evaluator (`evaluate.py` blob `1fb6b655bb4ca1e1684be165a8ef513e2e6c2325`) explicitly executes:

```text
cfg.seed = seed
engine.interpreter(...)
assert cfg.seed was scrubbed
```

so an offline experiment can use a smaller finite candidate domain only when an external runner/provenance authority independently proves that exact seed panel was precommitted; this helper can then byte-bind those declared bytes. Byte binding itself does not prove precommit. The candidate agent still never receives the seed itself.

## Why this changes SEEDSTREAM's boundary

Merged SEEDSTREAM correctly says a singleton from an arbitrary bounded search is only `BOUNDED_UNIQUE_NOT_GLOBAL`. SEEDDOMAIN makes the provenance classes explicit:

| provenance | complete finite domain from pinned source? | permitted conclusion |
|---|---|---|
| implicit default fallback | yes: `[0, 2**31)` | source-complete fallback interval only |
| explicit `configuration.seed` | **no** | external provenance required |
| preserved `env.info.seed` | **no** | external provenance required |
| byte-bound declared panel manifest | not by byte binding alone | declared finite set; external precommit provenance still required |

Nothing here proves which provenance path a hosted Kaggle episode uses. Hosted/global seed authority remains false unless that runner provenance is independently authenticated.

## Byte-bound declared finite-panel set

`seed_domain_provenance.py` defines a minimal byte-bound research receipt:

```json
{
  "schema": "titan.v4.byte-bound-offline-seed-panel/v1",
  "seeds": [1, 7, 255],
  "evaluator_git_blob": "1fb6b655bb4ca1e1684be165a8ef513e2e6c2325",
  "engine_git_blob": "3c202c7ee921da239356789e266b694635103fc4",
  "seedstream_git_blob": "c02ab05ed7684508f02e383fa3281f29e2f60fa6"
}
```

The complete manifest bytes are SHA-256 bound before use. Duplicate JSON keys, wrong source blobs, empty/duplicate seeds, bool/float/string seed poison, extra fields, or byte drift fail closed. This is an immutability check only: a caller can still create a new manifest, so the helper never treats the digest itself as evidence of when or by whom the panel was declared.

A byte-bound panel is labeled only `BYTE_BOUND_DECLARED_OFFLINE_PANEL_SET_ONLY`. Byte binding proves the bytes did not change; it does **not** prove the list was precommitted or came from the evaluator. `panel_precommit_proved`, `panel_origin_authenticated`, and `finite_domain_authority_proved` all remain false. Independent runner provenance is required to upgrade that status.

## Public-evidence filtering and consensus

SEEDDOMAIN does **not** reimplement the RNG. It captures merged `seed_stream_identifiability.py@c02ab05...` once, Git-blob authenticates those exact bytes, and compile/executes only that captured buffer (no verify→reopen path). It then applies the same public-only EOD evidence to just the declared finite seed set.

Possible results are:

- `NO_MATCH_IN_DECLARED_PANEL_SET`
- `AMBIGUOUS_IN_DECLARED_PANEL_SET`
- `DECLARED_PANEL_SET_UNIQUE_NOT_GLOBAL`

Even the last verdict keeps all of these false:

```text
panel_precommit_proved = false
panel_origin_authenticated = false
finite_domain_authority_proved = false
hosted_seed_domain_proved = false
global_identifiability_proved = false
production_seed_cracker_authorized = false
```

Future predictions are delegated to SEEDSTREAM's all-survivor consensus primitive. No first-candidate, MAP, or guessed-seed shortcut is introduced.

## Intended use

This closes two opposite failure modes at once:

1. **false omniscience** — treating a convenient `[0,N)` developer search as the hidden game's complete seed domain;
2. **throwing away declared finite experimental structure** — a byte-bound offline seed set can still be partitioned by public observations for research, while the helper refuses to claim that the set was genuinely precommitted unless an external runner/provenance authority proves it.

A later RNG-sensitive gameplay experiment may consume this only as offline evidence. Turning it into a live policy would require a separate theorem that the live environment exposes an authenticated complete domain and that no test-bank overfit is introduced.

## Validation

Authored-byte gate before publication:

```text
PASS 15/15 seed-domain-provenance tests
PASS 15/15 under python -O
py_compile PASS
```

The checkout-aware source-auth test runs automatically when the canonical repository layout is mounted. A repo-mounted exact-head source-auth + CLI receipt remains the publication gate because this cloud seat does not carry the repository checkout.
