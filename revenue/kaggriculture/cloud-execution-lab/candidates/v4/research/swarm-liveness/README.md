# TITAN V4 Swarm Liveness / Orphan Recovery

`claim_liveness.py` is a dependency-free, read-only auditor for the fast-moving
multi-agent claim stream. It exists to answer a narrow coordination question:
**which claims are actually live, which are closed, which collided, which
became stale after a session disappeared, and which normalized claimant was
first?**

It belongs to the existing canonical `main:candidates/v4` workspace. It does
not create a sibling V4, does not mutate gameplay, and has no Slack/GitHub
credentials.

## Normalized event contract

One JSON object per line:

```json
{"ts":1789183752.102079,"lane":"ASTRA-LANTERN","session":"ASTRA","event":"CLAIM","scope_key":"dead-feed-care","canonical_root":"main:revenue/kaggriculture/cloud-execution-lab/candidates/v4","writes_repo":true,"requires_artifact":true}
```

Required fields are `ts`, `lane`, `session`, and `event`. Supported events are
`CLAIM`, `HEARTBEAT`, `COMPLETE`, `RELEASED`, `BLOCKED`, `REJECTED`, and
`SUPERSEDED`. `ts` may be Unix seconds or timezone-aware ISO-8601.

Repository-writing events must bind `canonical_root` exactly to the workspace
being audited. A repo-writing event with no root, or any event that explicitly
names a different root, remains visible as anomaly evidence but is quarantined
from lease authority. Read-only events may omit `canonical_root` for legacy
compatibility. `requires_artifact` lets a claim require a durable artifact
before `COMPLETE`. Optional `event_id`, `artifact`, `channel`, and `thread_ts`
preserve provenance.

`scope_key` is also optional. It is an **operator-supplied normalization key**
for claims that are known to describe the same ownership surface under
different lane names. The auditor never derives or guesses a scope key from
names or prose. Legacy events without one keep exact-lane behavior and do not
enter cross-lane scope groups.

JSONL is parsed fail closed: duplicate object keys are rejected recursively
before event normalization. A line cannot smuggle competing `event_id`,
`canonical_root`, or nested provenance values and rely on parser "last key
wins" behavior.

## Safety semantics

- `STALE_CLAIM` is **routing evidence only**, never overwrite/merge authority.
- A fresh owner blocks recovery of stale owners for the same lane or explicit
  scope group.
- Two fresh owners on an exact lane produce `COLLISION`.
- Two distinct fresh sessions that explicitly declare the same `scope_key`
  produce a scoped `COLLISION` even when their lane names differ.
- Multiple alias lanes for the same session and scope collapse to one owner;
  the earliest still-active claim epoch is retained for precedence.
- For normalized exact lanes and explicit scope groups, collision arbitration
  uses the timestamp of the currently-active `CLAIM`, not its latest heartbeat.
  The unique earliest fresh claimant is reported as an **advisory**
  `preferred_owner`; later fresh claims are `yield_candidates`.
- Equal earliest claim timestamps fail closed: no preferred owner is emitted;
  the tied sessions are listed in `tied_earliest_claimants`.
- Re-claiming after a terminal event starts a new ownership epoch and therefore
  gets a new claim timestamp.
- A heartbeat or terminal event that supplies a different `scope_key` than the
  active CLAIM emits `scope_key_drift`; it never silently rekeys ownership.
- Arbitration is never overwrite, merge, validity, or promotion authority.
- A fresh owner plus an old silent owner produces `ACTIVE_WITH_STALE_OWNER`.
- An event whose explicit `canonical_root` differs from the audited root is a
  `noncanonical_root` anomaly and cannot create, refresh, close, or reopen a
  canonical lease.
- Any `writes_repo=true` event is authoritative only when `canonical_root`
  exactly equals the audited root. A missing binding emits
  `repo_write_without_root` and is quarantined.
- A repo-writing CLAIM binds the active ownership epoch to its opening
  `canonical_root`. HEARTBEAT and terminal follow-ups must carry that exact
  root to refresh or close the epoch even when the follow-up itself has
  `writes_repo=false`.
- A quarantined foreign-root, unbound repo-write, or writer-epoch follow-up does
  not reserve its `event_id`, so it cannot shadow a later valid canonical row
  carrying the same provider ID.
- If two or more otherwise-authoritative, epoch-eligible rows carry the same
  provider `event_id`, the **entire conflicting ID group is quarantined**. Raw
  export line order therefore cannot choose which duplicate CLAIM, HEARTBEAT,
  or terminal row gets lease authority. Duplicate diagnostics remain visible.
- Read-only rootless epochs remain authoritative for backwards compatibility;
  this exception is explicit in the report policy.
- Heartbeats without a live claim and terminal events without a claim are
  anomalies rather than silently repaired history.
- A claim marked `requires_artifact` cannot complete cleanly without one.

## Run

```bash
python -B claim_liveness.py adversarial-events.jsonl \
  --as-of 2000 --ttl-seconds 100 > report.json
python -B -m unittest -v \
  test_claim_liveness.py test_claim_arbitration.py test_scope_keys.py
python -O -B -m unittest -v \
  test_claim_liveness.py test_claim_arbitration.py test_scope_keys.py
```

The report is canonical compact JSON: deterministic lane/scope/anomaly
ordering, explicit recovery candidates, claim-epoch timestamps, advisory
arbitration, summary counts, and policy booleans that make the non-authority
boundary machine-readable. `scope_groups` contains only explicitly keyed
active ownership groups; the tool never creates semantic aliases by inference.

## Integration boundary

The tool deliberately consumes **normalized exported events** rather than
talking to Slack directly. Live connector sessions can translate claim and
closure messages into this schema, audit them, then route stale/collision
findings back to peers. `lane` remains the exact-name ownership boundary.
`scope_key` is a separate explicit declaration for already-known equivalence;
it is not a semantic classifier. That keeps workspace credentials out of the
repository and prevents a timestamp rule from pretending to discover scope
equivalence.

It does not decide whether a gameplay mechanism is valid, strong, mergeable,
or promotable. It only closes coordination ambiguity around ownership and
liveness.
