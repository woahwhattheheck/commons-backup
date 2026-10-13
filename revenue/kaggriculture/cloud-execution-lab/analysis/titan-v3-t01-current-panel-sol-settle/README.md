# TITAN v3 — T01 exact-current terminal settlement (SOL-SETTLE)

This additive lane closes the missing gameplay evidence for the existing
`candidates/v3-terminal-settlement/terminal_settlement.py` certificate. It was
originally authored against `2e2e7e52fd2d5c62117ac49c7f1eabb505078ffb` and was
mechanically replanted on 2026-09-12 onto exact parent
`b986558e41938d34fcb4ab28b08c517be51203dc`. The fresh exact-head workflow, not
the historical result, is authoritative for the replanted carrier.

The candidate intercepts only exact-current controller construction. Each fresh
current `FinalPressureAgent` receives one instance-local wrapper around
`_early_capital_selected`: the original method completes first, including final
market pressure, and then the existing settlement certificate sees that returned
action. This is the source patch's intended order inside
`TitanAgent._finish_production`, so cold source load, projection, and settlement
all remain inside canonical `main.agent` and its one-second outer deadline.
Canonical construction, persistent state, planner, inner deadline, fallback,
post-deadline reconstruction, and entrypoint return stay authoritative.

The paired runner reuses the pinned official-engine harness and injects a narrow
evaluator receipt at step 718. For each matched opponent/seed/seat cell it stores
the pre-resolution candidate observation, configuration, candidate action, and
opponent action. The auditor then:

1. proves baseline and candidate observations/configurations are identical before
   the terminal action;
2. proves the opponent's simultaneous terminal action is identical;
3. recomputes the T01 certificate from the baseline action and exact current
   `scheduler.post_units` projector;
4. requires the candidate's returned action to equal that recomputation;
5. requires every activated cell's observed own terminal-cash delta to meet or
   exceed the certificate's literal minimum;
6. rejects any negative own-cash or margin cell, any negative opponent×seat own
   or margin mean, and every W→T, W→L, or T→L outcome regression.

The development grid is eight immutable seeds against Arlene and submitted V1 in
both seats: 32 paired cells, 64 official games. `ADVANCE` additionally requires
positive global mean and median own cash, positive global mean margin, no negative
cell, zero outcome regressions, and at least one action-bound activation. Zero
activation is a rejection.

The exact-parent workflow runs source and carrier contracts plus current
`build_integrated.py --check` before the game step, so unresolved canonical
package/import drift burns zero panel games. The original 2026-09-10 base rebuilt
canonical archive `5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1`
and source manifest `3249398b6aa56d1b3464db8d0cce5aa35e8edee397fc4341bd710d1f74dad469`;
those identities are historical context only and do not authorize this replant.

`ADVANCE` authorizes only a separate one-tree composition experiment. This lane
never edits canonical runtime/config/archive/pointer bytes, rebases the V3
publication tree, submits to Kaggle, mutates provider state, or claims leaderboard
strength.
