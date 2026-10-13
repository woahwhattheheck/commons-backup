# Finite alternating-game certificates

A plain-JavaScript compiler and saved policy reader for an explicit two-choice alternating game. The actual consumer reinterprets the retained #31513 transition graph on odd states 1 through 139 under Althöfer's mover-wins-on-producing-1 rule.

The one new closure records terminal 1, **33 winning, 14 losing and 22 unresolved positions**, with proof depth through 13. It represents **8,388,608 labelled stationary policies** without enumerating them. A fresh reader made 27 queries, including full policy rank/select and complete play traces, with no successor generation, SCC, stochastic-system or game-classification replay.

State 1 is terminal; its predecessor artifact's self-loops remain source provenance only. Outside targets are unresolved in the original game. The finite W/L certificates are valid regardless of those continuations, but remoteness and the fastest-win/max-delay policy family describe the explicitly censored finite game. No initial winner is inferred for an input already equal to 1.

Start with [FINITE_GAME_API.md](FINITE_GAME_API.md) for the derivation, source attribution, public API, bounds and exact scope.

| File | Purpose |
| --- | --- |
| [finite_game_index.cjs](finite_game_index.cjs) | Compile a new explicit graph or reopen a saved one. |
| [odd139_game_certificates.json](odd139_game_certificates.json) | Full graph, classifications, proof layers, policy products and 27 query outputs. |
| [FINITE_GAME_API.md](FINITE_GAME_API.md) | Mathematical contract, proof and usage. |

The input is constructor.snapshot.nodes from research/ppl116_stochastic_collatz/odd139_absorption.json, Git blob 49292324248673869e9f47a06158e1dab0174647, accepted in [#31513](https://github.com/woahwhattheheck/commons/pull/31513). No prior stochastic result was recomputed.

The [author's Prize 3 page](https://althofer.de/collatz-prizes.html) reports earlier finite analysis and a manuscript under checking; those reports are credited rather than independently certified. This artifact establishes no infinite-game theorem or new range record and makes no sponsor submission.
