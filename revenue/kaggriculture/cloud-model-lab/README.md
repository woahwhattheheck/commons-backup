# cloud-model-lab

TITAN offline model lane: an observation -> applicable-constraint -> complete-turn
-> decoded-legal-action loop for Kaggriculture, driven by the owner's model
(Gemma 4 E4B) on this cloud VM.

This directory does not modify `cloud-eval/`, `cloud-market/`, `cloud-dispatch/`,
`cloud-herd/`, `claude-handoff/`, LARK's `cloud-pack` or FLORA's
`cloud-composition`. Nothing here is built, downloaded or run on the owner's
machine.

## What is pinned

| Artifact | Pin | Verified here |
| --- | --- | --- |
| Engine | Kaggle/kaggle-environments `28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c` | `kaggriculture.py` `bc8a5487…ee653e`, `kaggriculture.json` `a82c89c1…6f4867`, `utils.py` `537b627b…52334b` — all three re-fetched and byte-identical to LARK's manifest, and identical again in the PyPI `kaggle-environments` 1.32.7 install actually imported |
| Model | `litert-community/gemma-4-E4B-it-litert-lm` @ `2eee7ac325f20eb8c9ac1d0e972f7c84663062da` | `gemma-4-E4B-it.litertlm`, 3,659,530,240 bytes, sha256 `0b2a8980…bd52e0` — downloaded and hashed in this VM |
| Runtime | `litert-lm` 0.16.1, CPU backend | 4 vCPU / 15 GiB VM, Ubuntu 24.04 |

## The loop

1. `cards.py` captures real NONTERMINAL turns from the official harness. A card is
   the observation the engine handed a seat, plus the configuration and the seat.
   Positions are never hand-built.
2. `constraints.py` derives what the engine will actually accept. It re-implements
   no rule: it enumerates the grammar and asks the pinned engine's own functions,
   and it executes a whole proposed turn through the pinned `interpreter`.
3. `operators.py` carries each operator twice — the eight-part semantic
   specification (header, definitions, admissible-set constraints, cost functions,
   priority, conditional, prohibitions, output contract), and the small-tier
   emitted surface, which is a header plus contrasting input->output exemplars with
   nothing narratable in it.
4. `exemplars.py` builds those surfaces from real derivation-card states and
   refuses to build if the derivation and evaluation seeds overlap.
5. `codec.py` decodes the model's emission into an engine action, reversibly and
   strictly. It rejects with a reason; it never repairs an invalid emission into a
   plausible one, and never substitutes a fallback while reporting it as a model
   decision.
6. `compare.py` runs the arms on frozen observations and records the exact prompt,
   the raw generation, per-phase timing and the separate scores.

## What is deliberately kept apart

Accepted syntax, engine effect, and economic quality are three different results
and are never merged into one number. `codec.legality` returns `violations`
(the engine will not act on this at all), `joint_blocks` (turn-level drops the
per-unit view cannot see) and `clamped` (quantities the engine silently reduces)
as separate fields. Whether a legal turn is a *good* turn is not answered there.

## Joint-turn contract

A per-unit probe is not the playable grammar. Four interpreter facts are modelled
explicitly, each with a regression test in `tests/test_joint_turn.py`:

- **Atomic PLANT budget** (interpreter 920-933): PLANT requests are summed across
  farmer and hands; if a crop's count exceeds its seed stock the engine turns
  *every* one of them into PASS. One seed with two planters is a different turn
  from two seeds with two planters.
- **Unit phase before market phase** (935-944): goods dropped into the shed this
  turn can be sold this turn; a seed bought this turn cannot be planted until the
  next one.
- **Quantities**: PICKUP/PLACE and market orders are not restricted to 1. Domains
  are exposed, model-chosen quantities are decoded, and sequential market orders
  share one cash balance and one shed capacity while repricing per unit.
- **End of day** (873-882) and **terminal reward** (960-963): at the last turn of
  a day carried goods drop to the shed with overflow discarded and hired hands are
  removed; the final score is cash only, so unsold stock scores nothing.

## Model input hygiene

Only player-visible fields reach the model. The episode seed, the opponent's
private state and the card wrapper's capture metadata are excluded by construction
(`constraints.visible_config`) and asserted by
`tests/test_joint_turn.py::test_no_leakage`.

## Reproducing

```sh
python -B tests/test_joint_turn.py
python -B discriminate.py --cards results/eval-cards.json --out results/discriminate.json
python -B compare.py --model <path>/gemma-4-E4B-it.litertlm \
  --eval-cards results/eval-cards.json --deriv-cards results/deriv-cards.json \
  --out results/e4b-arm-comparison.json
```

Measured results are in `results/` and in `RESULTS.md`. Nothing is claimed here
ahead of a recorded measurement.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
