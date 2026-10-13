# TITAN V5 R04 same-step state custody

This is one additive materializer for the existing `selective-carrot` / production-v3 family. It does not mint another controller or edit the authenticated submitted-V3.1 R04 donor files.

## Source defect

The active R04 stack contains multiple state machines that treat `step <= last_step` as reset. The top-level `Policy.act()` resets `DayState`, and retained sublayers such as V233, fertilizer-hand, and terminal-fertilizer have equivalent same-step reset behavior. A repeated public callback can therefore erase the route selected at step 144 plus queue/debt/auxiliary state before returning an action.

V5 already admits same-step retries at outer recovery boundaries. Fixing one inner dict is insufficient because a retry traverses the whole R04 stack.

## Treatment

`materialize_r04_retry.py` accepts only the exact production-v3 archive SHA256 `20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239`. It changes exactly one member, `reference/next-panel/vendor/arlene.py`, at the exact adapter injected by `production_recovery_overlay.txt`.

For each player, the adapter caches the last normalized observation, production configuration, and returned R04 action. On an identical same-step retry with intact donor state it returns a deep copy of the cached action **without calling R04 again**. That preserves every nested R04 state machine at once.

A same-step callback with changed observation/configuration, or a same-step callback whose donor `last_step` no longer matches the cached step, does **not** re-enter or reset R04 and does not throw through the public production callback. Instead it returns a deep copy of the vendored Arlene canonical legal `PASS = {"farmer": ["PASS"], "hands": [], "market": []}`. The materializer source-binds that exact PASS definition before patching, so authority drift fails closed. Existing plan/queue/debt state is left untouched and the next strictly increasing callback delegates once from the last committed donor state. A strictly backward step clears only the wrapper cache and delegates to the donor's existing reset behavior.

Strictly increasing callbacks remain one donor call and have no policy/route/economics change.

## Gate

Focused source contracts cover:

- nonzero step-144 route survives identical step-145 retry;
- no duplicate donor call on retry;
- queue and sale-debt state are unchanged by retry;
- cached actions are copy-isolated from caller mutation;
- changed observation/configuration at the same step returns canonical legal PASS before donor mutation;
- same-step donor-state drift returns canonical legal PASS without mutation;
- the next increasing callback after a changed-evidence PASS continues the prior route with one donor call;
- backward step delegates to donor reset;
- both players remain independent;
- forced plan 2 at step 648 is replay-safe;
- missing/duplicate transform seams or missing canonical PASS authority fail closed;
- transform changes only the vendored Arlene member.

The publisher reserves archive+receipt create-exclusively as one owned pair, rejects path aliasing, fsyncs both payloads, and rolls back its owned paths on publication failure.

## Hold

This carrier is source/mechanics only until an exact-head source test rerun and a repo-mounted seat materialize it from the exact `20f20116...` archive, verify 92-member custody + one-member delta, compile the result, and run an exact callback witness showing both identical replay and changed-evidence containment do not re-enter R04. Native economic games are not required to prove retry correctness, but this does not authorize CURRENT/default/release/Kaggle mutation.
