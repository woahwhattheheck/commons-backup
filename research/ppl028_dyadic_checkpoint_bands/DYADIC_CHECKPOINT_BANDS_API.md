# Dyadic checkpoint height bands for an inherited nine-map cylinder

This package supplies exact joint band counts and numeric parameter/seed navigation for one declared family of seeds of the accelerated nine-map. It consumes the accepted affine-block record from [Commons #31444](https://github.com/woahwhattheheck/commons/pull/31444). It does not extend that orbit.

The current author page [Collatz prizes](https://althofer.de/collatz-prizes.html), displayed update 21 September 2026, defines odd(m) by removing every factor of two and uses this operation after X*n+1. Prize 2 fixes X=9 and starts at 1. Thus the map here is T_9(x)=(9x+1)/2^{v_2(9x+1)} on positive odd x. The introductory stop-at-one sentence concerns the original three-map. No stop at one is imported into the nine-map. The author’s phrase “leads to infinity” is left as its wording; this finite consumer supplies no divergence or current prize-solution assertion. [PPL028](https://prizeproblems.org/problems/028/) is the catalogue binding.

## Exact input and inherited premise

The old immutable merge is bd9f9db732c8c05f0349b97f0a3fa202b9abaa70. Complete data nine_start1_orbit.json, blob bf333e3fd8229bec05adbedce300b8b8ee18ee74 (898,739 bytes), and guide ODD_ORBIT_AFFINE_API.md, blob 1e852e295d6be6695c97b224a700fedc69ec0ae2 (35,668 bytes), were acquired and independently matched. The old source, constructor and reader were not invoked. The prior 256 transitions, 257 states, dyadic blocks, accepted queries and proof calculations remain inherited premises.

The seed is x=r+M*t with r=1 and the exact modulus M stored in input.json, equal to the saved 2^475 cylinder modulus. The parameter domain is the closed integer interval 1<=t<=10^500. The original seed 1 corresponds to t=0 and is excluded from this new family. Parameter order and seed order agree because M>0.

Only nine zero-start blocks and the full block’s cylinder are copied:

| Coordinate | Checkpoint | Source block | Saved shift S |
|---:|---:|---:|---:|
| 0 | 0, initial state | none | not applicable |
| 1 | 1 | 0 | 1 |
| 2 | 2 | 2 | 2 |
| 3 | 4 | 6 | 7 |
| 4 | 8 | 14 | 15 |
| 5 | 16 | 30 | 29 |
| 6 | 32 | 62 | 58 |
| 7 | 64 | 126 | 133 |
| 8 | 128 | 254 | 252 |
| 9 | 256 | 510 | 474 |

For a selected block with inherited affine identity y_j(x)=(A_j*x+B_j)/2^S_j and saved observed endpoint u_j=y_j(r), substitution gives

    y_j(r+M*t) = u_j + v_j*t,    v_j = A_j*(M/2^S_j).

The new compiler checks that each denominator divides M and that v_j is positive. It copies u_j instead of re-evaluating the old anchor. For coordinate 0, u_0=r and v_0=M. The inherited full cylinder supplies the claim that this valuation pattern applies to these seeds; this consumer does not independently reprove that earlier record. There is no new orbit stepping, valuation, anchor recomputation or affine-block composition.

## Bands and event construction

Let H_1=10^200, H_2=10^400 and H_3=10^600. The four bands are:

| Band | Value interval |
|---:|---|
| 0 | [0,H_1) |
| 1 | [H_1,H_2) |
| 2 | [H_2,H_3) |
| 3 | [H_3,infinity) |

Threshold equality enters the higher band. For each coordinate and threshold H, the first possible parameter in the higher band is ceil((H-u_j)/v_j). Mathematical signed ceiling is used; the result is then clamped to the lower parameter bound 1. This preserves thresholds already crossed at the start of the window.

Events after the upper bound are omitted from the cut list. Equal event times are grouped before a cell is emitted. A cell is [left,next_event-1], and the last is [left,10^500]. Its size is right-left+1. An event exactly at the upper endpoint therefore retains a final singleton cell. These are parameter intervals, not orbit-time intervals.

The once-only construction produced 30 threshold records, 30 nonempty cells and ten affine lines. One threshold is already active at t=1; the initial band vector is [0,0,0,0,0,0,0,0,0,1]. The last vector is [3,3,3,3,3,3,3,3,3,3]. The first cell’s entry_events list is empty by convention: events already active at the lower bound are represented in the event table and its band vector. Later entry_events hold the threshold-record indices activated at that cell’s lower endpoint.

Constructor work was 9 saved block copies, 9 new slopes, 30 threshold-entry divisions, 111 sorting comparisons and 30 new cells. Orbit steps, valuations, anchor recalculations and block compositions were all zero.

## Reader contract

Use the saved certificate directly. The constructor is retained for provenance; reproducing the accepted construction is not required to answer queries.

```javascript
const { createReader } = require("./checkpoint_bands.cjs");
const certificate = require("./certificate.json");
const reader = createReader(certificate);
const selected = reader.condition({
  min_bands: [0,0,0,0,2,0,0,0,0,0],
  max_bands: [3,3,3,3,2,3,3,3,3,3]
});
```

All parameters, seeds, ranks and counts use canonical nonnegative decimal strings, with an input length limit of 2,048 characters. Band bounds are integer arrays of length ten with entries 0 through 3. The module is a trusted-certificate reader; checking the schema string is not an authentication or adversarial validation mechanism. Returned objects and cached arrays must be treated as immutable by callers.

| Method | Behavior |
|---|---|
| summary() | Returns ten coordinates, nine dyadic checkpoints, cell/event counts and the declared parameter interval. |
| condition(q) | Intersects inclusive lower/upper parameter bounds with the declared interval and applies inclusive min_bands/max_bands coordinate constraints. Omitted bounds use the full domain. Returns exact parameter count and admitted closed cell fragments with zero-based cumulative rank_start. |
| select({...q,rank}) | Selects in increasing numeric t order, equivalently increasing seed order. Returns t, r+M*t, cell and band vector; rank>=count returns OUT_OF_RANGE. |
| rank({...q,parameter}) | Returns the zero-based rank when admitted, otherwise OUTSIDE_DECLARED_WINDOW or NOT_IN_CONDITION. |
| rank({...q,seed}) | First requires the full-cylinder residue, then the declared parameter window and condition. Seed takes precedence if both seed and parameter are supplied. Wrong residue returns NOT_IN_CYLINDER. |
| state({parameter}) | Evaluates the ten saved affine lines at a new declared parameter. Returns the peak and all tied peak coordinates among these ten coordinates only. |
| firstCheckpoint({parameter,at_least_band,include_initial}) | Scans saved dyadic times 1,2,4,...,256 in order. The initial state is considered only when include_initial is literally true and is then returned with kind initial, checkpoint 0. No hit gives NO_SAVED_CHECKPOINT. |
| marginals(q) | Counts parameters in each band at every coordinate, using admitted fragment lengths. It does not count cells. |
| snapshot(), work() | Return saved condition records and accumulated reader work, respectively. |

The optional name field used by the driver is only a response label and does not affect the cache key. Keys use clipped interval bounds and the two band arrays. Reversed/disjoint parameter bounds and incompatible band constraints produce empty selections. For valid empty conditions select returns OUT_OF_RANGE. Invalid scalar or band syntax raises a TypeError; the saved production driver did not run a synthetic malformed-input suite. Numeric membership and bounds are exact BigInt operations. There is no scan through 10^500 parameters.

## First actual reader use

The prepared driver ran once after its source/plan checkpoint. Every actual request, response, latest condition cache and work record was retained before the next call. It completed 129 responses without an exception. Twenty-three selected parameters were inverted through both parameter and seed interfaces: all 46 comparisons matched the requested rank. Twelve condition records are retained, along with six state queries (60 affine evaluations), 24 first-checkpoint queries and three complete marginal tables.

In the following table, cell identifiers are zero-based. Complete decimal counts, all endpoints, selections and rank responses are in saved_reader.json; no numeric count is rounded.

| Condition | Admitted source cells | Parameter count |
|---|---|---|
| full | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29 | 10^500 |
| initialBand0 | 0, 1, 2, 3, 4, 5, 6, 7, 8 | Exact decimal retained in saved_reader.json |
| finalBand1 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9 | Exact decimal retained in saved_reader.json |
| allBand2 | 19 | Exact decimal retained in saved_reader.json |
| initialLowFinalHigh | empty | 0 |
| time8Band2 | 15, 16, 17, 18, 19, 20, 21, 22, 23, 24 | Exact decimal retained in saved_reader.json |
| parameterMiddle | 10, 11, 12, 13, 14, 15, 16, 17, 18, 19 | 10^300 − 10^200 + 1 |
| beforeFirstEvent | 0 | 1 |
| atFirstEvent | 1 | 1 |
| reversedParameterRange | empty | 0 |
| allBand3 | 29 | Exact decimal retained in saved_reader.json |
| incompatibleBands | empty | 0 |

The beforeFirstEvent and atFirstEvent queries are adjacent singleton parameters on opposite sides of the first internal cut. At t=1, the first saved dyadic checkpoint in band at least 1 is 256. At the first internal cut, it is 128; just before that cut it is 256. These are first hits among the saved dyadic times only.

For an all-band-3 state, the default firstCheckpoint answer is checkpoint 1. With include_initial:true it is coordinate 0, kind initial. The original seed 1 returned OUTSIDE_DECLARED_WINDOW; seed 2 returned NOT_IN_CYLINDER. These are membership responses, not an evaluation of the accepted original orbit.

Reader work:

```json
{
  "conditionsBuilt": 12,
  "conditionHits": 86,
  "cellsScanned": 330,
  "bandComparisons": 2285,
  "selectedIntervals": 73,
  "selectionIntervals": 151,
  "rankingIntervals": 302,
  "seedProjections": 29,
  "seedResidueChecks": 25,
  "lineEvaluations": 60,
  "firstCheckpointInspections": 139,
  "marginalCells": 41,
  "newEvents": 0,
  "newOrbitSteps": 0,
  "newValuations": 0,
  "blockCompositions": 0
}
```

The 330 cell scans and 2,285 band comparisons build conditions from saved event cells. Selection and ranking inspect saved fragments. The 60 affine line evaluations are new parameter queries; they do not step the map. The reader creates no new events, orbit steps, valuations or block compositions. Marginal counts weight each fragment by its number of parameters. Time0 is explicitly distinguished from dyadic checkpoints.

## Files and checkpoint custody

- checkpoint_bands.cjs: new compiler and trusted-certificate reader.
- input.json: exact inherited fields and declared parameter/band domain.
- construction_plan.json and SOURCE_QUALIFICATION.md: frozen scope and source boundary.
- certificate.json: complete 30-cell construction, event table, affine lines and work.
- reader_consumer.cjs and reader_plan.json: prepared first actual consumer.
- saved_reader.json: all 129 actual responses, twelve caches, six states, three marginals and work.
- public_checkpoints.json: native acknowledged public blob/manifest identities for source/input/plan, result, reader plan and complete reader.
- README.md: entry point.

The original source/input/plan manifest is a94ffb8c044196f41a4dfc453e013de782480535. The result manifest is 84140f2b08c39e3fc717a2a8860ed68f990ba21e. The reader-plan manifest is 2d7cb1c4656ae12567029a226d08a1e35cbd769b. The complete reader manifest is 6317df3b7db361005cbb0a825e5bae352b6bc156. These are native acknowledgements, not merely computed hashes. Public manifests contain no private provider journals. Native blob acknowledgement alone does not establish indefinite retention or a branch publication.

Final source-qualification and construction-plan prose receives spacing cleanup in the publication packet; the originally checkpointed bytes and their identities remain unchanged in the checkpoint chain. The full frozen publication spec is checkpointed separately before any branch write. That later spec manifest cannot be included in its own files.

## Mathematical limit of the result

The family has exactly 10^500 parameters because its window has that many integers. Every result concerns the inherited full cylinder and nine selected transition counts plus the initial state. It supplies exact navigation over a very large finite seed family, conditional on the saved affine identities. It gives no assertion about intermediate odd-map times, primitive operations, a full trajectory maximum, a first hit between checkpoints, eventual behavior or the original seed’s divergence. No known example, proof calculation or accepted query was replayed. No claim of novelty, sponsor acceptance or prize progress is made.
