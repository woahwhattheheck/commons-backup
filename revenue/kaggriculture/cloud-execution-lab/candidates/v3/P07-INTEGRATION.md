# P07 — observation-certified joint actor assignment

## Why this lane exists

The landed V2 route-divergence audit identifies an assignment error, not merely an
illegal-action error.  In episode `107130860`, the route requested four executable
`HIRE` orders, only three appeared in the next public farm state, and the unchanged
route then emitted 23 commands for a fourth hand that did not physically exist
(steps 26–48).  The engine's natural truncation gives the physical new hands the first
represented suffix lanes.  That is deterministic, but it can discard a more valuable
represented lane.

P07 observes what actually happened and changes only the assignment:

1. Count `HIRE` orders in the exact executable market prefix
   (`max(1, int(maxMarketOrdersPerTurn))`).
2. On the next consecutive observation, compare public physical hand count with the
   pre-HIRE baseline.
3. Activate only when the completed count is strictly below the requested count and
   the current route exposes exactly `baseline + requested` logical lanes.
4. Preserve logical indices of every pre-existing hand.
5. Rank only the requested new-hand suffix from the unchanged route interval and bind
   the completed new hands to the best represented lanes.  The mapping is selected
   once and remains stable.

The lexicographic rank is route-only: productive commands, logistics commands,
non-PASS commands, then earlier productive/non-PASS work.  Exact ties keep the lower
logical index.  No money, inventory, HIRE, purchase, farmer command, market command,
route choice, or producer call is added.

## Correct seam

P07 is called immediately after `self.production.act(obs)` and before
`FrozenSelected.transform` or any selected post-unit snapshot.  A later returned-action
rewrite is unsound here: it would make the seller's projected farm, spatial receipts,
and emitted hand assignment disagree.  The selected action consumed by every existing
stage therefore already carries P07's assignment.

The producer is still called exactly once.  A deadline fallback and every
`ready=False` reconstruction reset P07's receipt state; it never guesses across an
unconsumed action, cancellation, or reconstruction.

## Fail-closed boundaries

P07 returns the identical action object unless all evidence is present.  It declines on
late join, malformed observations/actions, malformed market limits, route switches,
repeated/reordered steps, step gaps, day reset, unexpected actor deltas, logical or
physical cardinality drift, malformed route commands, and future HIRE/cardinality
boundaries.  After an ambiguous interval it remains blocked until a day/route reset.

## Package contract

`p07_materialize.py` is bound to:

- main: `2e2e7e52fd2d5c62117ac49c7f1eabb505078ffb`
- canonical archive SHA-256:
  `5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1`
- canonical archive size: 428,158 bytes

Without `--enabled`, the output is a byte-for-byte copy of the canonical archive.  With
`--enabled`, exact-once anchors wire the module, add the default-off `Features` field,
flip the materialized candidate's deterministic `TITAN-CONFIG.json` key to true, update
`SOURCE.json`, and include the focused tests.  Anchor drift and archive identity drift
are hard failures.

## Verification

```bash
cd revenue/kaggriculture/cloud-execution-lab/candidates/v3
python -m unittest -v \
  overlay/checks/test_p07_joint_actor_assignment.py \
  overlay/checks/test_p07_materialize.py

python p07_materialize.py \
  --base ../../exports/titan-current.tar.gz \
  --output /tmp/titan-v3-p07.tar.gz \
  --enabled --tree /tmp/titan-v3-p07 \
  --receipt /tmp/titan-v3-p07-receipt.json
```

Focused local result at publication: 27/27 contracts pass.  The workflow additionally
materializes the exact repository archive, proves disabled byte identity, compiles the
wired runtime, executes the packaged P07 tests, and requires an observed action change
from the four-request/three-completion witness.  No game-strength or leaderboard claim
is made for these changed bytes until a paired hosted panel exists.
