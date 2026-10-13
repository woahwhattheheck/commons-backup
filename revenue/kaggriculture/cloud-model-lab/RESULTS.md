# Measured results

All numbers below were produced in this cloud VM. Nothing is asserted that was not
recorded by a run. Raw prompts, raw generations and per-record timing are in
`results/e4b-arm-comparison.json`.

## Environment

Ubuntu 24.04, x86_64 KVM, 4 vCPU (Intel Xeon @ 2.10GHz, avx512 + avx512_vnni),
15 GiB RAM, no GPU. `litert-lm` 0.16.1, CPU backend.

## Pins re-verified here

| File | sha256 | matches |
| --- | --- | --- |
| `kaggriculture.py` | `bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e` | LARK manifest |
| `kaggriculture.json` | `a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867` | LARK manifest |
| `utils.py` | `537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b` | LARK manifest |
| `gemma-4-E4B-it.litertlm` | `0b2a8980ce155fd97673d8e820b4d29d9c7d99b8fa6806f425d969b145bd52e0` | work-order pin; 3,659,530,240 bytes |

The PyPI `kaggle-environments` 1.32.7 install that is actually imported carries the
same three engine hashes, so the packaged install and the pinned fetch are
interchangeable here.

## Model load and footprint

| Quantity | Measured |
| --- | --- |
| Engine `init_time_in_second` (its own counter, cold) | 21.87 s |
| First decision after cold init, trivial prompt | 4.67 s wall |
| Second decision, same process | 1.00 s wall |
| Peak RSS of the process | 4506 MB |

`Runner.cold_load_s` times only the `Engine(...)` constructor and is **not** the
load figure: initialisation completes lazily on the first message. The engine's own
`init_time_in_second` is the authoritative number.

## Runtime API facts (litert-lm 0.16.1)

- Constrained decoding is available, but `response_format` is refused unless
  `create_conversation` is given `ConstrainedDecodingConfig(enable=True,
  provider=LL_GUIDANCE)`. `enable=True` alone raises.
- `create_session` does **not** accept a constrained-decoding config; only
  `create_conversation` does.
- A JSON schema whose array `items` are unconstrained does **not** bind content. The
  first constrained attempt returned
  `{"farmer":[{"name":"Farmer Giles","age":62,...}]}` — schema-valid and useless.
  The regex format over the exact turn grammar binds op names, arity and nesting.
- `BenchmarkInfo` populates `init_time_in_second`, `time_to_first_token_in_second`
  and the prefill/decode token **counts**. The tokens-per-second fields are
  accompanied by `Failed to get prefill/decode profile summary` warnings and are not
  used here. Unknown counters stay unknown.

## Arm comparison — 5 frozen cards x 4 arms = 20 decisions

Cards, engine instance, sampler (`temperature=0.0`, `top_k=1`, `seed=0`), KV cache
(`max_num_tokens=4096`), thinking (disabled) and output cap (`max_output_tokens=192`)
are identical across arms. Arms are run card-major, so no arm gets a warmer engine.
Arms differ only in the head of the prompt, and for `codec` in whether decoding is
constrained by the turn-grammar regex.

Evaluation cards: `s7700001-t150-p0`, `s7700001-t300-p0`, `s9900017-t200-p1`
(seat 1), `s8800001-t30-p0` and `s8800001-t45-p0` (both with **3 hired hands**;
the second at hour 21). Derivation card: `s4242001-t130-p0`. Derivation and
evaluation seeds are disjoint and `exemplars.build` refuses to run if they are not.

| arm | syntax ok | legal | mean wall | prompt tokens | decode tokens | mean non-no-op units |
| --- | --- | --- | --- | --- | --- | --- |
| baseline (instruction English) | **1/5** | 1/5 | 9.28 s | 604 | 53.2 | 1.00 |
| formal (8-part specification) | **3/5** | 3/5 | 17.99 s | 2091 | 42.2 | 1.00 |
| pattern (MVG exemplar surface) | **5/5** | 3/5 | 15.99 s | 1216 | 90.8 | 0.40 |
| codec (pattern + grammar regex) | **5/5** | **4/5** | **8.45 s** | 1216 | 12.0 | **0.00** |

Per-phase mean seconds:

| arm | state projection | constraint calc | prompt build | prefill (TTFT) | decode | decode+validate |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 0.0001 | 0.0207 | 0.0001 | 3.73 | 5.55 | 0.0003 |
| formal | 0.0001 | 0.0207 | 0.0002 | 14.09 | 3.90 | 0.0007 |
| pattern | 0.0001 | 0.0207 | 0.0001 | 7.46 | 8.52 | 0.0010 |
| codec | 0.0001 | 0.0207 | 0.0001 | 7.40 | 1.05 | 0.0010 |

State projection, constraint calculation and validation together cost ~21 ms, three
orders of magnitude below the model call. All of the latency is prefill and decode.

### What the raw generations show

These are behaviours, not labels; each is quoted from `results/e4b-arm-comparison.json`.

- **baseline fails on shape, not on content.** Four of five rejects are shape
  defects: a fenced ` ```json ` block, and `"farmer": "PASS"` as a bare string where
  the grammar needs a list. Its one accepted emission was legal.
- **The 8-part formal specification did not bind the emission shape.** On both
  multi-hand cards it produced `"farmer": "EAST"` (string) and then
  `"farmer": {"op": "EAST"}` (object). It is also the most expensive arm: 2091
  prompt tokens and 14.09 s of prefill, ~2x the pattern arm's prefill for a worse
  syntax rate.
- **The pattern arm's failure mode is exemplar copying.** On both multi-hand cards
  it echoed a derivation exemplar back verbatim, situation text and all —
  `Sigma:STOCK\nfarmer on [empty]; seeds CARROT1,WHEAT1; ... -> {"farmer":["PLANT","WHEAT"]}` —
  on a card holding **0** WHEAT seeds. The joint-turn contract caught it twice:
  `violations: farmer ['PLANT','WHEAT'] not admissible` plus
  `joint_blocks: PLANT WHEAT requested 1x across units but only 0 seed(s)`.
  The exemplar situations are rendered in the same format as the STATE block, which
  is the likely cause and is the next thing to change.
- **The codec arm buys legality with inertia.** It is the only arm that never fails
  syntax, the best on legality (4/5), the fastest (8.45 s, and the tightest spread:
  8.39-8.53 s) and the cheapest to decode (12 tokens vs 90.8). But its mean non-no-op
  unit count is **0.00** — four of its five emissions were `{"farmer":["PASS"],...}`.
  It is legal and does nothing.
- **Grammar binding is not admissibility binding.** The one illegal codec emission
  was `{"farmer":["WATER"]}` on a card where `WATER` is not admissible. The regex
  constrains the grammar only; admissibility stays a separate check, so a constrained
  decode cannot manufacture a legality result it did not earn.

### What this does and does not establish

It establishes, for this checkpoint, backend, sampler and card set: a monotone
syntax ladder from instruction English to exemplar pattern (1/5 -> 3/5 -> 5/5), that
the multi-hand cards are where the prose and formal forms break, that grammar-level
constrained decoding removes syntax failure entirely at the lowest latency measured
here, and that it does so while producing inert turns.

It does not establish a universal latency floor, an operator benefit on policy
quality, or anything about hosted play. n = 5 cards per arm. The 3.66 GB checkpoint
does not fit the 100 MiB hosted archive and a ~8-18 s decision does not fit the 1 s
action budget, so nothing here is a hosted submission candidate.

## Discriminating pairs

`discriminate.py` builds pairs from real cards that differ in exactly one field and
checks the engine-derived admissible set moves with it. 15/15 pass across three base
cards (seed stock, shed capacity with the BUY_SEED asymmetry, `watered_today`,
`fed_today`, maturity deadline).

## Joint-turn regressions

`tests/test_joint_turn.py`: 25/25 pass. Covers the atomic PLANT budget across
farmer and hands, unit-phase-before-market in both directions, quantity domains and
shared-cash market sequencing, the hour-22 vs hour-23 end-of-day difference,
overflow discard, cash-only terminal reward, and model-input leakage.

## Model-driven play in the official interpreter

`play.py` steps a real episode and hands the seat to E4B for a bounded number of
real turns. The actions the model authors are the actions the official interpreter
executes.

### Bounded segments, seed 7700001 seat 0

| run | examples | turns | legal | syntax rejects | non-PASS | mean inference |
| --- | --- | --- | --- | --- | --- | --- |
| from step 150 | six concatenated operator pairs, cue last | 14 | 14/14 | 0 | **0** | 19.7 s |
| from step 150 | same, `plan` moved ahead of the action | 10 | 10/10 | 0 | **0** | 18.6 s |
| from step 150 | class-matched bank, before the live state | 2 | 2/2 | 0 | 2 | 16.9 s |
| from step 3, lean20 warm-up | class-matched bank | 2 | 2/2 | 0 | **2** | 29.1 s |

A no-inference control over the identical step-150 window (the warm-up agent playing
it instead) ends on the same cash, 2990, so the window itself yields nothing; the
comparison is against that.

The concatenated-pairs arm emitted PASS on all 24 real turns while its authored plan
described the live tile correctly, so it was reading the state and not acting on it.
Moving `plan` ahead of the action did not change that on its own: the plan-order
hypothesis is disconfirmed alone.

### What the ported exemplar bank changed

`exemplar_bank.py` ports the LDA `ExemplarBank` mechanism (LDA
`54081cd58d2c45b868b4265c3dcb8990aa1cc9b4`): lean (state -> action) rows keyed by a
situation class, retrieval of the newest 1-2 for that class deduplicated by action
shape, placed immediately before the live state. Rows are labelled `model` or
`teacher:<name>`; a teacher row is never presented as a past model success.

Four defects were found and fixed by reading the first two decisions rather than by
running a longer batch:

1. **The advance predicate counted a state change as advancement.** Decision 1 was
   `DIG` while standing on the seat's own healthy age-0 CARROT, which the engine
   executed and which destroyed the plant. `constraints.advanced` now rejects a DIG
   that removes a live plant, rejects movement-only turns and rejects PLANT requests
   the joint seed budget drops; on the same card it scores `DROP` + `SELL CARROT 2`
   as `cash +70` and `DIG` as `DIG removed a live CARROT plant`. That action was not
   banked.
2. **The situation class was too brittle to retrieve anything.** Keying on the exact
   sorted set of admissible op names made `DGL` and `DL` different classes, so a
   single-farmer deposit turn matched zero rows while the bank held six of exactly
   that situation. The class is now orthogonal facts -- water/harvest/plant
   availability, carrying, on-shed-access, dying, ripe, shed-full -- and retrieval
   relaxes exact+context, exact, then any-unit-count.
3. **Retrieved rows have to be shape-compatible.** The relaxed pass offered an
   8-hand action to a one-unit turn, which the output grammar forbids anyway;
   retrieval now requires the row's hand count to equal the live one.
4. **Bank rows lacked the `plan` the emitted shape requires**, so the model filled it
   with `", "`. Rows now carry a plan and the plan field has a minimum length.

The map and accepted set were also corrected: a tile op is annotated with what it
acts on (`DIG (acts on (4,4) PLANT CARROT age0d ...)`), because the model had read
`weeds to DIG (3,4)` off the map and dug the plant under it at (4,4); and carried
goods are now printed as `CARRIED IN HAND (not on the tile)` separately from the tile
contents.

### The two decisions on a covered situation

Seed 7700001, seat 0, from step 3, lean20 as warm-up and opponent, class
`u4|can:-|carry|access|safe|unripe|shedroom`, two exact+context teacher rows from
`cloud-dispatch/candidate.py::agent`:

```
day0 h3  {"plan":"Expand livestock and start planting high-value crops",
          "farmer":["PLACE","SHEEP",1],
          "hands":[["PLACE","SHEEP",1],["NORTH"],["NORTH"]],
          "market":[["BUY_ANIMAL","COW",1]]}          legal, 39.2 s
day0 h4  {"plan":"Feed the existing sheep and prepare for expansion",
          "farmer":["CARE"],
          "hands":[["CARE"],["BUILD_PASTURE"],["CARE"]],
          "market":[["BUY_SEED","WHEAT",1]]}          legal, 19.1 s
```

Both turns author all three channels, are legal with no joint blocks, carry a
coherent plan across the turn boundary, and are **not** copies of either retrieved
example (those were `NORTH` and `FEED`). Cash after the two turns is 214 against the
opponent's 597, which reflects a 400-cost COW purchase inside a two-turn day-0
window and is not a score: terminal cash is.

Nothing here establishes a win against the pinned public opponents. FLORA's
`dispatch_balanced` remains the internal reference at 0/8 against Kaito v43 and Igor
MultiRoute; this lane has not played them.

## Renderer comparison and downstream value

Seed 3131017, seat 0, `cloud-market/main.py::agent` as warm-up and opponent. Both
comparison arms read the same frozen teacher-only bank and never write to it.

| render | model turns | non-PASS unchanged / emitted | waste rate | rejects | mean inference |
| --- | --- | --- | --- | --- | --- |
| verbose | 6 | 6 / 24 | 0.25 | 0 | 22.6 s |
| slots | 6 | 0 / 24 | 0.00 | 0 | 18.2 s |
| slots (through the daily refresh) | 24 | 0 / 70 | 0.00 | 0 | 18.7 s |

`cloud-frontier-trace/results/106392861` records 0 non-PASS unchanged effects for the
leader and 123 for its opponent, so waste rate is the comparable axis. The typed-slot
renderer reaches 0 and holds it over a 24-turn segment.

### Downstream continuation

Early cash is not the measure, so each candidate state is handed to the same pinned
policy, separately instantiated, which finishes the official game against the same
opponent, config and seed. The control is that policy playing from step 0.

| candidate | our cash | opponent cash | margin |
| --- | ---: | ---: | ---: |
| all-policy control | 33,214 | 35,469 | -2,255 |
| 6-turn slots segment + continuation | 36,745 | 36,111 | **+634** |
| 24-turn slots segment + continuation | **50,093** | 63,144 | **-13,051** |

The 24-turn segment produced 16,879 more cash than the control and still finished
about 11,000 worse on margin, because the opponent gained 27,675 over its own
control. The market is shared, so this seat's play moved prices in ways that helped
seat 1's policy more than it helped this seat.

**Zero waste did not produce a win.** Absolute cash is not the objective; margin is.
On this seed the short segment helps and the long one does not, which is a result
about one seed, one continuation policy and one opponent, not a general ranking.

### What the 24-turn segment did

Three `BUILD_PASTURE` (each recorded `pending`, since a structure pays nothing until
an animal is installed and fed), then `PICKUP COW`, then the workers spread apart,
then three animals installed in a single turn by the hands, then `SELL WHEAT` for a
realized +28. Outcomes: 13 neutral, 6 pending, 2 logistics, 2 production, 1
realized_revenue.

## Leader episode as teacher demonstrations

`seed_leader_bank.py` pairs ROWAN's landed decision cases for public episode
106392861 using that lane's reconciled convention -- the action recorded on a frame
was taken from the previous frame's observation, so a case pairs its `before_frame`
observation with its `after_frame` action. All 20 cases pair, none skipped. Rows are
labelled `teacher:ymg_aq:episode106392861`; that episode is excluded from evaluation
and the rows are never presented as this model's own results.

The paired actions reproduce the behaviour the trace describes: watering at hour 23,
the last hour before the daily refresh; a 12-13 worker plateau in the middle of the
episode; and a `DROP` with four market orders at step 718 into the cash-only terminal.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
