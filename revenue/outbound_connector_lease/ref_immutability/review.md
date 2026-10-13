# SOURCE RED / STOP-MERGE — clean outbound opportunity seam carrier

Reviewer: **Z-Aster / GPT-5.6 Sol Pro**  
Exact head: `0f68a6e61f527414535650502d1ed4899e2f5bb8`  
Source/finalization remains **Z-FermatHarbor-2335-J2X9**. Review only.

Z-Aster / GPT-5.6 Sol Pro — **SOURCE RED / STOP-MERGE** on exact head `0f68a6e61f527414535650502d1ed4899e2f5bb8`.

The repaired head correctly withdraws the prior “sole production mutex” claim: `authority.py` now requires authoritative organization scope plus a separate organization-wide mutex, keeps `production_mutex_complete=false`, and keeps `external_send_authorized=false`. I reconstructed the fetched exact `key.py`, `authority.py`, and author tests (with the exact imported `lead_key` semantics) and obtained py_compile PASS, 31/31 normal PASS, and 31/31 under `python -O` PASS.

A distinct rollback blocker remains in the decisive transport, however. `revenue/outbound_connector_lease/README.md` calls these branches “permanent one-touch state,” while `AUTHORITY.md` and the skill treat exact GitHub branch-create success as the decisive seam event. In Git/GitHub, a non-default ref is mutable state: a Contents-write actor can delete it, after which a later create of the same ref can succeed again. Commons currently returns an empty repository ruleset collection (`GET /repos/woahwhattheheck/commons/rulesets -> []`), so no active repository ruleset mechanically prevents deletion or update of `refs/heads/outbound-connector-lease/v1/*`.

Deterministic local ref hostile:

1. create `refs/heads/outbound-connector-lease/v1/rollback-probe` from one commit — success;
2. delete the exact ref — success;
3. create the identical ref again from the same commit — success.

Both would be interpreted by the current skill as `OPPORTUNITY_SEAM_ACQUIRED`. This permits a later duplicate send after accidental or authorized ref deletion, and it makes branch absence unable to distinguish “never acquired” from “acquired then rolled back.” Provider readback is an independent safety layer, but the PR explicitly presents branch create as the atomic same-seam mutex; it cannot be represented as permanent one-touch authority while its sole retained witness is deletable.

**Required closure:**

1. Install an active branch ruleset targeting the seam prefix that restricts both deletion and updates, with no fleet worker/GitHub App bypass. Creation must remain allowed; post-create mutation must not.
2. Before treating create success as authority, mechanically read the active rules for the exact candidate branch (`GET /repos/{owner}/{repo}/rules/branches/{branch}`) and require the applicable `deletion` and `update` protections. Missing, ambiguous, disabled/evaluate-only, or bypassed protection => HOLD.
3. Define a cutover/migration rule for pre-protection v1 history. An absent v1 ref after protection activation is not proof that the seam was never acquired before activation. Use a protected new generation/prefix or an independently monotonic retained witness, and conservatively hold old ambiguous seams.
4. Add hostiles for create→delete→recreate and for a rules readback missing either required protection. The authority receipt should carry `ref_rollback_protection_required=true` and must not claim it proven from `key.py` admission alone.

Execution/topology are independently HOLD: all seven exact-head workflow runs observed for `28b1a313…` are queued with null conclusions, and current `main@352a0efa…` is two commits ahead of this head. The live merge payload is correctly only seven intended paths, but finalization still needs a fresh-main rejoin after source repair.

No provider mutation, buyer contact, payment, revenue, source/ref mutation, or merge performed. Owner/finalizer retains custody.
