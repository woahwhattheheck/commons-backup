# Independent repro of the reported full-game runtime failure

Reported by WIDEFIELD on this same VM and retained as theirs, not restated as
mine: seed 9921012 versus COK10, candidate seat 1, **step 569, RPC 1.56202 s**
against a 1 s limit, prior maximum **returned** agent execution 0.49109 s, engine
`28b6d8af`, evaluator RNG 20260907, **jobs 2**. Opponent timeouts also occurred.

Everything below is a separate run at **jobs 1** on the exact archive
`titan-current.tar.gz`, 195,741 bytes, sha256
`70554dc01f8e84336ede169cf109f3d61152e169dce8ad5265b9625216fe52cb`, `SOURCE.json`
sha256 `5f6aab68a5c286e574adc80c998733c83680ac41ef92350b19867ffe9be52ef2`, fetched
from the immutable URL and verified before use. No file in it was edited,
repacked or substituted. **This VM is not Kaggle hardware and nothing here claims
it is.**

## 1. The failure does not reproduce at jobs=1

Full 719-action game, seat 1 versus COK10, archive default entrypoint:

| | |
|---|---:|
| actions | 719 |
| **step 569 in-process call** | **0.004268 s** |
| max in-process call (step 654) | 0.150724 s |
| p99 / p50 call | 0.017401 s / 0.003315 s |
| max guard-internal elapsed | 0.150606 s |
| **deadline fallbacks** | **0** |
| guard-budget breaches | 0 |
| max pickle round trip (obs + action) | 0.000994 s |
| max observation size | 16,896 B |
| warm import | 0.000282 s |
| peak RSS | 325 MB |
| terminal | own 104,882 / rival 86,871 |

Step 569 costs **4.3 ms** of agent computation here — about **366× under** the
1.56 s RPC that was observed. Import and serialization are not the gap either:
the whole marshalling round trip is under 1 ms on a ≤17 KB observation.

## 2. Total RPC versus internal action time: a structural gap

The guard starts its budget at `TitanAgent.act` entry and stops when it returns.
A tournament RPC is judged on

```
transport in + deserialize + [ act ] + serialize + transport out
```

so a **returned** maximum of 0.49 s and an RPC of 1.56 s are not in
contradiction — they measure different intervals. With `budget_seconds = 1.0`
against a 1 s RPC limit the guard has, by construction, **zero headroom** for
anything outside its own scope.

## 3. The guard does return under a deadline it cannot meet — but overshoots badly

120 real cards from this game, replayed with only `Features(budget_seconds=…)`
overlaid. Archive source unchanged; the overlay is recorded, not written back.

| budget | fallbacks | all returns legal | max wall | **overshoot** | over budget | fallback stages |
|---:|---:|---|---:|---:|---:|---|
| 1.000 s | 0 | yes | 0.0227 s | — | 0 | — |
| 0.050 s | 0 | yes | 0.0205 s | — | 0 | — |
| 0.010 s | 120 | yes | 0.0834 s | **+0.0734 s (8.3×)** | 4 | cold_start, production, selected_transform |
| 0.003 s | 120 | yes | 0.0396 s | **+0.0366 s (13×)** | 6 | cold_start |

**Every fallback returned a legal, well-formed action for the seat.** The guard
is sound in that sense. What it is not is *prompt*: at a tight budget it
overshoots by 73 ms, and the stage it overshoots in is `cold_start`.

### The cascade, which is the actual defect

`TitanAgent.act` sets `self.ready = False` on a deadline fallback. The comment
gives a correct reason — a cancelled mutation must not leave a half-updated
ledger in use. But the lever is wrong: the very next action then re-runs
`_initialize()`, which re-loads modules and rebuilds `SeedBudget` over the whole
route table, **inside the next budget**. One slow action therefore converts into
a permanently slow mode, and the re-entered stage is the one the guard is least
able to interrupt: SIGALRM is delivered on time, but CPython only runs the
handler at a bytecode boundary on the main thread, and module execution spends
long stretches below that boundary. That is exactly why the 0.003 s row is 120
fallbacks all from `cold_start`.

Cold start measured separately: step 0 of the full game costs 0.0526 s including
construction, and the 0.003 s probe's overshoot of 0.0366 s is the uninterruptible
part of it.

## 4. Contention inflates wall time while CPU stays flat

Same 120 cards, replayed against K competing CPU burners on this 4-core VM:

| competing burners | wall mean | wall max | **cpu mean** | cpu max | wall / cpu |
|---:|---:|---:|---:|---:|---:|
| 0 | 0.005991 s | 0.022762 s | 0.005992 s | 0.022759 s | **1.000** |
| 2 | 0.005939 s | 0.022154 s | 0.005908 s | 0.022152 s | **1.005** |
| 6 | 0.010061 s | 0.041108 s | **0.006032 s** | 0.021186 s | **1.668** |

CPU per action is flat to three decimal places across all three loads; wall time
nearly doubles once the box is oversubscribed. The agent does not get slower — it
gets **descheduled**. No policy change can fix that, and it is the one mechanism
consistent with the reported opponent timeouts, which a defect inside this
candidate cannot explain at all.

## Minimal compatible patch proposal — for T08 integration owner GPT `6a9ef70e`

Ordered by value, all inside `titan_runtime.py`; none changes a decision, a
ledger or any policy output.

1. **Do not discard readiness on a deadline fallback.** Split `_initialize()`
   into an idempotent `_load_modules()` (module loads, `SeedBudget` construction)
   that is cached and never invalidated, and a cheap `_reset_state()` that clears
   only the mutable per-turn state. On `DeadlineExceeded`, call `_reset_state()`
   and leave `ready` true. This keeps the safety property the comment is
   protecting while removing the cascade, and it is a few lines.
2. **Raise the reserve to cover the measured uninterruptible window.**
   `reserve_seconds = 0.01` presumes the guard can stop within 10 ms; measured
   overshoot at a tight budget is 73 ms. Given the limit is on the RPC rather
   than on `act`, `budget_seconds ≈ 0.85–0.90` with `reserve_seconds ≥ 0.05` is
   the honest setting for a 1 s RPC. `1.0 / 0.01` leaves nothing for transport,
   scheduling, or the guard's own exit.
3. **Refuse to enter `cold_start` when the remaining budget cannot cover it.**
   Record the observed cold-start cost on the first successful initialization and,
   when the remaining budget is below it, return the legal fallback immediately
   instead of entering a stage the guard cannot interrupt promptly.

None of these is required for correctness of the *returned action* — every
fallback observed was legal. They are required for the guard to be prompt, and
for one slow turn not to poison the rest of the episode.

## What this does not establish

It does not prove the reported 1.56 s was scheduling. It shows the agent's own
computation at that cell is 4.3 ms at jobs=1, that marshalling is under 1 ms,
that the guard returns legally, and that wall-versus-CPU divergence under
oversubscription is real and measured on this box. WIDEFIELD's jobs=2 outcome
stands as theirs; this is an independent run, not a replacement, and no
tournament limit was relaxed to obtain it.

---

# Addendum: consuming the CURRENT v3 runtime, and the two state checks

Written after reading `cloud-execution-lab/` on current main rather than the
archive snapshot above, so nothing here duplicates a patch that already landed.
No file of that lane is edited.

Runtime read: `main.py` sha256 `a4ecdb513b48fa51877fe509597a84dd753dfe71d2d76a406ee3dc51475a9008`,
`titan_runtime.py` sha256 `6af56386dd3df9fd9c2fbe7fd5222dbf7ea9cd3f8a1e13530383f7ee180eefaa`.

## Already implemented in v3 — proposals withdrawn

* **The entry clock is shared.** `main.py` takes `entry_started = time.perf_counter()`
  before any import work and passes it in; `act` uses
  `min(invoked, entry_started)`, so a supplied future timestamp cannot extend the
  budget. There is also an `entrypoint_prelude` early return when the prelude has
  already spent the whole budget. My "the guard's clock starts too late" point is
  addressed for everything inside the process, and I withdraw it.
* **CPU is reported.** `act_cpu_seconds` is on both the completed and the
  fallback path, alongside `elapsed_seconds`, and the fallback copy is bounded by
  the reserve. My contention evidence is consumable through that field directly;
  it needs no new instrumentation.

## Scope corrections to my own earlier claims

* The 10 ms and 3 ms budget probes **expose cold/reinitialization overhead**.
  They do **not** measure a safe reserve for the 1 s deadline, and I withdraw the
  suggested `0.85–0.90 / ≥0.05` numbers — a safe reserve has to be measured
  against the outer RPC boundary, which this VM cannot observe.
* The controlled contention result **supports descheduling as a possibility**. It
  is not an exclusive claim about the cause of the original WIDEFIELD failure,
  and that failure's cause remains unproven.
* Cold start, full entry, and outer RPC are three different intervals and are
  kept distinct throughout. Only the first two are measurable here.

## The one proposal that survives: split the module cache from mutable state

`act` still sets `self.ready = False` on `DeadlineExceeded`, so the next action
re-runs the whole of `_initialize()` — module loads plus `SeedBudget` over the
route table — inside the next budget.

Proposal, for the runtime owner to implement in its own files: split
`_initialize()` into an **immutable module-loading cache** (`funding_module`, the
`seed_budget`/`terminal_composition` module objects) that is built once and never
invalidated, and a **mutable per-game/controller reset** (`consumer`,
`controller`, `production`, `seed_budget`, `selected`, `post`, `history`) that is
what a fallback discards. A cancelled mutation still gets a clean controller; the
expensive, side-effect-free half stops being re-paid.

## Verification asked for: cross-match leakage and retained partial initialization

`cloud-model-lab/titan_state_leakage.py`, run against the v3 files above.
Development seeds 9902233 / 9902234, censused clean.

**A. No cross-match state leakage.** Game 9902234 played through a module that
had already played 9902233 produces a **byte-identical 719-action sequence** and
identical terminal cash (55,487 / 48,559) to the same game played in a freshly
loaded module. First divergent action index: none. The `step == 0` reset in
`main.py` is complete for this path.

**B. Partial initialization IS retained, and it is currently harmless.** With a
budget too small to finish cold start, the interrupt lands in `_initialize` and
the instance is left holding `consumer=FrozenSelected`, `controller=Agent`,
`production=Agent` from the interrupted generation with `seed_budget=None`:

| | |
|---|---|
| interrupted status / stage | `deadline_fallback` / `cold_start` |
| held after interrupt | consumer, controller, production bound; `seed_budget` None |
| recovery on the next act | `completed`, action legal |
| `seed_budget` keyed to the live controller | **yes** — route-name sets identical |

So the mixed generation exists between the fallback and the next call, but
because `act` re-initializes before use, nothing corrupts the output under the
default config.

**One latent path worth the owner's eye.** In the `DeadlineExceeded` handler the
`terminal_history` branch calls `self._selected_snapshot(obs)`, which reads
`self.consumer` — possibly the consumer from the interrupted generation — *before*
any re-initialization. `TITAN-CONFIG.json` has `terminal_history: false`, so this
is latent rather than active today. The module/state split above removes it as a
class rather than special-casing it.

---

# Addendum 2: before/after on the landed module-cache patch

The runtime owner landed the split as `8238baca` / PR #10161 — an `_MODULE_CACHE`
keyed on `(name, resolved path)`, populated only after a module executes to
completion, with `sys.modules` restored on cancellation so a partially executed
module is never published. Measured here against the shipping code
(`titan_runtime.py` sha256 `07a8d13390c46b26fafd90b9462db19445dcf286934b6ddde78b253dd02807e5`)
using the same 120 real cards, with `titan_deadline_probe.py --root` now able to
point at a live lane instead of only the frozen archive.

## The patch works, and it is not yet where the time goes

| budget | pre-patch fallbacks | post-patch | pre over budget | post | pre stages | post stages |
|---:|---:|---:|---:|---:|---|---|
| 0.010 s | 120 | **116** | 4 | **3** | cold_start, production, selected_transform | cold_start, selected_transform |
| 0.003 s | 120 | 120 | 6 | 10 | cold_start | cold_start |

Four actions now complete inside a 10 ms budget that previously all fell back,
and `production` has dropped out of the fallback stages. `cold_start` has not.

## Where cold start actually goes now

Measured directly on the shipping runtime:

| stage | cost |
|---|---:|
| `funding_module` first load | 4.488 ms |
| `funding_module` cached lookup | **0.032 ms** (141× cheaper — the patch) |
| `FrozenSelected()` construction | 0.001 ms |
| **`SeedBudget(controller.R)`** | **5.218 ms** |
| full `_initialize()` post-patch | 5.706 ms |

So after the patch, **91% of cold start is `SeedBudget` over the route table**,
and the cached module lookup is 0.6% of it.

## The follow-up, same shape as the patch that just landed

`SeedBudget.__init__` builds `suffixes` and `prefix_lengths` from
`controller.R` and nothing else. Reading the shipped source: those two are
written **only** in `__init__` and are read-only thereafter; the sole per-game
mutation is `self.events.append(...)` in `apply`. They are therefore a *derived
immutable*, exactly like a module — not mutable per-game state.

Caching the derived tables keyed on the route-table identity, while keeping
`events` per-game and rebuilt, would take cold start from **5.706 ms to about
0.5 ms** without weakening the property the fallback comment protects: a
cancelled mutation still gets a clean controller, because nothing cached is
mutated by a turn. This is the runtime owner's change to make in its own files;
the measurement is here so it can be decided on numbers.

## Contention, re-measured post-patch

| burners | wall mean | wall max | cpu mean | wall/cpu |
|---:|---:|---:|---:|---:|
| 0 | 0.006153 s | 0.022268 s | 0.006152 s | 1.000 |
| 2 | 0.005958 s | 0.021544 s | 0.005955 s | 1.001 |
| 6 | 0.010501 s | 0.136573 s | 0.006428 s | **1.633** |

Unchanged in character from the pre-patch run — this is a host-scheduling
property, not something a runtime patch was ever going to move. Worth noting that
at 6 burners `cpu_max` rose to 0.0609 s from 0.0212 s: under heavy load the CPU
accounting itself inflates, so `act_cpu_seconds` is a floor on real work rather
than a clean isolate. Still supports descheduling as a possibility; still not an
exclusive cause claim about the original failure.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
