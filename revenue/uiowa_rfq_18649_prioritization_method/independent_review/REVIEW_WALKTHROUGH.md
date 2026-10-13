# UIOWA-029: reading horizons without inventing a plan

**Fictional rehearsal only.** These are test records, not University observations,
staff assignments, capacity estimates, agreed priorities, or promised dates.

This is an independent review companion to OP5-KELVIN's existing method, not a
second ranking or scheduling engine. KESTREL-62D owns the canonical source repair
and integration. ZZ-RIVET-8F31 / GPT-6 Astra Pro owns this observer and review.
The original source is commit `cf8b451a7f459ab34116f1e9a4521ed41f15a6a1`,
`method.py` blob `8b48e1a5531e7bf690e02ef005edf955c7898d28`.

## Three different questions

An **effort estimate** says whether the work has been sized. A **declared horizon**
is a person's current placement. A **proposed horizon** is the method's rule-based
suggestion. An item can have an estimate and a proposal but no declaration.
Calling that item `NEEDS_ESTIMATE` sends the reviewer to do the wrong work.

The tests deliberately preserve declarations. A disagreement is not permission
to rewrite somebody's choice. Neither a declaration nor a proposal demonstrates
that staff capacity, a dependency's completion, or a delivery date is available.

## Worked review 1: an unsized item with a missing prerequisite

Fictional `A` has no effort bounds, no declared horizon, and prerequisite
`MISSING`. There is no record with that ID.

The original method proposes `NEEDS_ESTIMATE` and reports **zero violations**.
Its early return for unknown effort skips the missing-reference check. These are
two independent questions: sizing is missing **and** the prerequisite is absent.
Estimating A does not resolve the absent prerequisite, and locating the
prerequisite does not estimate A. The repaired result needs to retain both.

The independent panel exercises this across three partial/unknown estimate
shapes, four declaration states, two missing-reference arrangements and both
record orders: **48 original-source failures**. The test requires a
`DANGLING_PREREQUISITE` diagnostic on the affected recommendation; an unrelated
warning on another record does not satisfy it.

## Worked review 2: estimated but not placed

Fictional `A` has effort 2-5 days, a positive assessed quality effect, no
prerequisites, and no declaration. The original method proposes `0-90` but puts A
in the declared-view `NEEDS_ESTIMATE` bucket. There is already an estimate.

The next action is **review placement**, not invent another estimate or
silently accept the proposal. KESTREL's declared repair vocabulary uses
`UNASSIGNED` for this condition. The observer does not demand that spelling;
it demands that sized work not be mislabeled as needing an estimate and that
every supplied record appear exactly once in the bucket view.

Four complete estimate shapes, four dependency arrangements and both row orders
produce **32 original-source failures** in the undeclared case. All other panel
states retain their distinct meanings; a known declaration is never overwritten.

## Worked review 3: proposals are not a transitive delivery plan

Use the exact dependency list, avoiding ambiguous arrow notation:

| Item | Effort | Prerequisites | Declared | Original proposal |
| --- | --- | --- | --- | --- |
| A | 70-90 | none | unassigned | 180+ |
| B | 2-5 | A | unassigned | 90-180 |
| C | 2-5 | B | unassigned | 90-180 |

All six permutations of these records produce the same proposals and no rule
violations. The original dependency lookup reads **declared** horizons, not the
other rows' proposals. This observation is **not a failed contract case**:
changing it would choose a new propagation policy. The canonical repair keeps
the declaration-only policy and exposes its limit.

Do not copy these three proposals into a roadmap and call the result feasible.
Review the missing declarations and dependencies in the existing roadmap flow.
UIOWA-084 remains responsible for ranking; this observer neither invokes nor
certifies it. UIOWA-085/115 integration is separate and has not been executed by
this review. No capacity or calendar commitment follows from the table.

## Reproduce the exact review

From this directory, with an already trusted local checkout of the selected
source (the replay does not download or fetch code):

```sh
python -m unittest -v test_horizon_replay
python -O -m unittest -v test_horizon_replay
python replay_horizons.py --source /path/to/method.py \
  --expected-blob 8b48e1a5531e7bf690e02ef005edf955c7898d28 \
  --out /new/path/original.json
python -O replay_horizons.py --source /path/to/method.py \
  --expected-blob 8b48e1a5531e7bf690e02ef005edf955c7898d28 \
  --out /new/path/original-optimized.json
```

For the original source the two replay commands **exit 1**, because the observer
finds the documented defects: **224 distinct contract cases, 144 passing, 80
failing**. Each case checks eight observable properties. These are not 224
passing tests, not 448 distinct cases, and not a general proof. The six
three-record policy observations are reported separately and never padded into
the pass count.

The observer's **19 unit methods pass normally and under `-O`**. Those unit tests
check the observer, including corruption controls, source-binding failure,
missing runtime API, record conservation and failure accounting. They do not
claim the original method is repaired. OP5-KELVIN's original 36-test receipt
remains attributed to that source author; KESTREL's independent replay of those
36 tests remains KESTREL's execution, not this seat's.

To review a repaired source, run the same commands with its actual Git blob.
Do not retain the old expected blob while silently loading a new implementation.
The output binds both Git blob and SHA-256 to the exact captured source bytes.
A contract failure exits 1; inability to execute or publish the output exits 2;
only a nonempty all-pass contract panel exits 0. Output creation is exclusive:
an existing report is not overwritten.

## Retained evidence and integration boundary

`original_observations.json.xz` contains the complete 224-case report plus all
six policy observations. Decompress with Python's standard `lzma` module or
`xz -dc`. Its uncompressed SHA-256 is
`8e43d4e9d4b596950b51c235587cf980dcd5dca3dfdce112dcc4f57c73451338`.
`SOURCE_RECEIPT.json` binds the tested source, observer, tests and archived
observations. `EXECUTION_LOGS.txt` retains literal unit-test outputs.

The ordinary and optimized original-source reports are byte-identical.
`case_results_sha256` is
`a456c9e302647040a7e1d1e42e095b5eaf9ba54815c839eef11847c1c212e341`.

This additive companion does not edit `method.py`, the example backlog, the
scoring model, roadmap, workbench or workflows. It is usable before and after
canonical integration because the source path is explicit. Its publication or
merge is **not** a receipt that the runtime repair merged, that hosted CI is
green, or that University data has been collected.
