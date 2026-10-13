# STICKY — shared obligation custody for Gemini blocked descendants

Status: **SOURCE-ONLY / RESEARCH-ONLY / DEFAULT-OFF / NO RUNTIME AUTHORITY**.

This package is not another controller. It is one fail-closed proof contract for the two Gemini/Antigravity ideas that current V4 evidence leaves blocked for the same architectural reason:

- **ALTWATER / HYDRA**: the source theorem that an established ongoing crop can survive one missed WATER is real, but the current final-action `WATER -> PASS` helper is field-falsified. PASS still consumes the unit callback, so it realizes no productive action saving, and the helper owns no durable next-day WATER commitment. The authenticated current-native falsifier in #12837 produced 25 day+2 WEED conversions in each tested seat and large negative margins.
- **HOIST / CARRYBANK**: carried inventory can move pressure out of SHED, but the current-route census in #12886 found 27 structural candidates across 25 route-step cells and **0 corrected-safe raw-route admissions**. Future PICKUP/COLLECT/HARVEST can consume the same FEED/FERTILIZE sink capacity and DROP/EOD are lossy boundaries.

The shared missing primitive is therefore **sticky obligation custody across replans**, not two new exploit controllers.

## Contract

`sticky_obligation.py` issues deterministic SHA-256-bound obligations and proves normalized continuation evidence. It never selects an action, mutates a route, persists scheduler state, or emits `allow`/`choose`/promotion authority.

### Recovery WATER

A WATER exchange can mint a recovery obligation only when the caller supplies an authenticated `replacement_effectful=True` witness and the replacement op is neither `PASS` nor `WATER`. This directly kills the unsafe HYDRA predecessor: skipping WATER for PASS is not an action saving.

The obligation is **site-bound** and due during the following day. Proof requires WATER on that exact site inside the due window. A site-changing `DIG`, `PLANT`, `HARVEST`, `BUILD_COOP`, or `BUILD_PASTURE` before recovery invalidates the proof. If no next-day executable callback exists, issuance fails closed.

The existing HYDRA/source owner still owns crop eligibility: established ongoing crop, prior streak, fertilizer-bonus boundary, planting-day exclusion, and all engine-source predicates. STICKY does not duplicate those rules.

### CARRY consumption

A proactive WHEAT/FERTILIZER pickup can mint an obligation only up to caller-proved SHED capacity pressure. The obligation is **actor-local** and may not cross end-of-day.

Proof reserves FEED/FERTILIZE capacity only after debiting:

- inventory already carried by that actor;
- later same-item PICKUPs;
- `COLLECT_FERTILIZER` for fertilizer custody.

A same-actor `DROP` before discharge invalidates proof. A same-actor WHEAT `HARVEST` makes future WHEAT acquisition unknown and therefore invalidates proof unless a future projection owner supplies exact item-level yield. Sinks belonging to another actor do not discharge the obligation.

The existing CARRYBANK owner still owns SHED adjacency, PICKUP legality, projected capacity pressure and its source semantics. STICKY only adds cross-replan sink custody.

## Replan custody

`carry_across_replan(previous, carried, now=...)` accepts only an exact semantic copy with the same deterministic digest and an in-window replan boundary. Field/key/digest drift fails closed. A scheduler integration must therefore explicitly carry the obligation rather than rediscovering or silently weakening it after replanning.

## Why this belongs in the existing V4 scheduler/LOOM authority

Current `COMPOSITION.json` already has authenticated composed `scheduler.py` ownership through the funding/capacity stack and scoped construction. A viable successor should consume this proof contract at that sanctioned scheduler boundary, not post-process the final returned unit action.

This branch intentionally does **not** write a scheduler postimage. Source-only admission semantics come first; a runtime composer must separately pin its scheduler preimage/postimage, prove obligation persistence through the real replan graph, and then run current-native both-seat economics.

## Tests / predecessor killers

`test_sticky_obligation.py` covers the unsafe predecessor families and custody edges, including:

- PASS/WATER/unauthenticated replacements cannot mint WATER obligations;
- exact next-day site recovery, wrong-site and late recovery rejection;
- site mutation before recovery;
- deterministic serialization/digest and tamper rejection across replans;
- same-day-only CARRY custody and EOD crossing rejection;
- preexisting inventory and later acquisition burden;
- actor-local sinks;
- DROP and unknown WHEAT-HARVEST invalidation;
- fertilizer collection burden;
- bool poison, malformed key sets and unsorted projection rejection;
- explicit `research_only=True`, `decision_authority=False`, `runtime_mutation_authority=False` proof reports.

## Promotion gates

A future production consumer must, at minimum:

1. authenticate the current scheduler/LOOM preimage and publish an exact reversible postimage;
2. show an obligation survives every relevant branch/replan rather than only a static suffix;
3. for HYDRA, substitute real productive work and recover WATER with zero WEED/plant-loss regressions;
4. for CARRYBANK, prove the same actor consumes the hoisted inventory before DROP/EOD after all intervening acquisitions;
5. preserve exact OFF identity;
6. pass current-native both-seat economic gates.

Until those gates exist, STICKY is a research proof primitive only.
