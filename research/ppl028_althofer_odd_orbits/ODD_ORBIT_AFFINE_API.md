# Positive odd orbits and finite affine seed classes

This module computes a bounded prefix of an accelerated odd `Xn+1` orbit, preserves every new transition, and builds a dyadic index of affine blocks. A saved reader can retrieve odd or auxiliary primitive states, compose an arbitrary contiguous block, and count, rank, select, or jump positive seeds having exactly the block's observed halving sequence.

The delivered input is `X=9` and `n0=1`. It produced 256 accelerated transitions, 257 odd states, and 511 dyadic blocks. A fresh reader composed the 176-transition range `[37,213)` from nine saved blocks and used its residue class modulo `2^334` for a finite seed-interval query. This is finite orbit and finite cylinder data. Neither the large final value nor completion of a requested prefix proves divergence.

## Source and mathematical scope

[Ingo Althöfer's Collatz prize page](https://althofer.de/collatz-prizes.html), read on 2026-10-04 with a displayed update of 2026-09-21, defines an accelerated odd map by forming `Xn+1` and removing **all** factors of two. Prize 2 asks about the orbit for multiplier nine and start one. Prize 1 allows a choice of odd multiplier at least five and odd start. These questions motivate the module; its single delivered trajectory uses only nine and one.

The API explicitly restricts the domain to positive odd integers and fixes one odd multiplier throughout a snapshot. This is the usual positive Collatz setting, stated here as an implementation contract. The page does not provide the module's budgets, saved-record schema, cycle protocol, or auxiliary primitive index. Its introductory ordinary `3n+1` stop-at-one convention must not be imported into the nine-map: this module does **not** stop merely because a state equals one.

The complete rendered author page was read. Linked prize-zero proof material, game content, and unrelated manuscript claims were not analyzed. No author contact, proof submission, prize application, payment claim, or literature priority claim accompanies this contribution.

All arithmetic that creates orbit values, affine coefficients, moduli, counts, and seed outputs uses JavaScript `BigInt`. Indices and bounded counters use safe integer `Number` values. The module needs no package dependency, filesystem, network, clock, random source, native executor, or external process.

## Files and custody

| File | Role |
|---|---|
| `odd_orbit_affine.cjs` | Dependency-free CommonJS implementation. |
| `nine_start1_orbit.json` | Complete constructor and 64-step checkpoints, complete final saved snapshot, both advance receipts, all 15 reader arguments/results/work records, timings, and literal custody checks. |
| `ODD_ORBIT_AFFINE_API.md` | This contract, derivation, actual workload, limits, and continuation instructions. |
| `README.md` | Entry point and result scope. |

The executed source is Git blob `249b9c136081cc3f502c8c327a5193a7d98c2a3d`, 47,805 UTF-8 bytes. It was statically reviewed and frozen before its first constructor call. The same source handled the first advance, saved resume, and saved reader; no source revision occurred between those operations.

The JSON exposes three useful locations:

| JSON location | Contents |
|---|---|
| `constructor.snapshot` | Initial state only, before any orbit transition. |
| `initial_checkpoint.snapshot` | Independently openable 64-transition state, with its complete history. |
| `saved` | Complete 256-transition state plus the two cached ranges and the completed reader session. |
| `resume_receipt` | Full second advance result, summaries, opening checks, and timing. Its resulting orbit is exactly `saved.orbit`. |
| `saved.sessions[2].queries` | All 15 successful reader calls, including exact arguments, exact results, and per-call work. |
| `custody` | Literal retained-JSON identity checks across append and reader boundaries. |

The 65 earlier odd states, 64 transitions, 127 blocks, initial first-value table, initial advance, and initial session were preserved literally by resume. Reader operations preserved the entire final orbit and the two earlier sessions literally. These are source-custody comparisons. They do not independently prove a trajectory, authenticate an imported certificate, or rerun accepted mathematics.

## The accelerated map

For fixed odd `X >= 5` and positive odd `n_j`, define

$$
a_j=v_2(Xn_j+1),\qquad
n_{j+1}=\frac{Xn_j+1}{2^{a_j}}.
$$

Here `a_j >= 1`, and the output is positive and odd. A prefix of `m` accelerated transitions contains **`m+1` odd states**, including its initial state.

Each transition retains:

- Its zero-based transition index and the input and output odd values.
- The exact even numerator `Xn_j+1` and its binary length.
- The exact number of removed factors of two.
- Auxiliary primitive start, raw-numerator, and end addresses.

The constructor retains only the requested initial state. An `advance` call starts from the last saved odd state. It never rebuilds earlier transitions or recomputes their valuations. It does load the saved first-value table to make future repeated-state lookups possible; that loading is counted separately.

### Auxiliary primitive addresses

For navigation, one primitive operation forms `Xn+1`, and each halving consumes one additional primitive operation. Thus a transition with exponent `a` spans `a+1` primitive operations. The initial odd state has primitive address zero.

This is an explicit auxiliary convention. It is not another interpretation of the author's accelerated step count.

A primitive query locates the first saved transition whose end address is at least the requested address. It then shifts that transition's **saved** numerator by the required number of halvings. Shared odd endpoints have one address; they are attributed to the preceding transition. Address zero is returned directly.

The query does not form `Xn+1` again, enumerate prior even intermediates, or recalculate the valuation. Its binary-search comparisons and new right shift are reported as query work.

## Dyadic affine blocks

Consider a contiguous sequence of `m` recorded exponents `a_0,...,a_(m-1)`, starting at any saved odd state. Put

$$
S_0=0,\quad N_0(x)=x,\quad
S_{j+1}=S_j+a_j,\quad
N_{j+1}(x)=XN_j(x)+2^{S_j}.
$$

Inductively,

$$
N_m(x)=A_mx+B_m,\qquad A_m=X^m,
$$

and the block's formal output is

$$
F(x)=\frac{A_mx+B_m}{2^{S_m}}.
$$

The empty block has `A=1, B=0, S=0`. A one-transition leaf has `A=X, B=1, S=a`.

Suppose a first block has `(A_1,B_1,S_1)` and the immediately following block has `(A_2,B_2,S_2)`. Substitution gives

$$
A=A_2A_1,\qquad
B=A_2B_1+B_2\,2^{S_1},\qquad
S=S_1+S_2.
$$

The order matters: the left block runs first. The implementation binds a block to one source, one multiplier, a half-open transition interval, and its observed start and end states. It never combines unrelated sources or noncontiguous ranges.

Every new transition creates one leaf. While the last two forest roots have equal lengths, the implementation merges them. This binary-carry process retains every leaf and every newly formed internal node. It does not replace or mutate earlier nodes. With 256 transitions, the actual forest is the single root `510` covering `[0,256)`, and all 511 nodes remain available.

A leaf's anchor record refers to its already computed transition numerator. Each newly formed internal node computes its affine numerator at the observed start once and checks that shifting gives the retained observed end. The numerator and equality result are saved. Opening a saved snapshot does not repeat these products or equalities.

### Arbitrary ranges and caching

A range uses zero-based half-open transition addresses `[from,to)`. Both endpoints are valid odd-state indices, so the observed output is state `to`.

The forest traversal chooses an ordered, nonoverlapping canonical cover of the requested range:

- An empty range returns the literal identity and the class of positive odd seeds.
- A range equal to one existing block reuses that block's affine and anchor records.
- A range requiring `k` saved blocks performs `k-1` new left-to-right compositions, computes its new cylinder, and performs one new anchor equality.
- A later request for the same endpoint pair uses the cached range. Seed count/rank/jump arithmetic remains new work even on a cache hit.

The actual `[64,128)` range used the existing block `253` without a new affine composition. The actual `[37,213)` range used:

| Block ID | Transition interval | Length |
|---:|---:|---:|
| 71 | `[37,38)` | 1 |
| 75 | `[38,40)` | 2 |
| 92 | `[40,48)` | 8 |
| 124 | `[48,64)` | 16 |
| 253 | `[64,128)` | 64 |
| 381 | `[128,192)` | 64 |
| 412 | `[192,208)` | 16 |
| 419 | `[208,212)` | 4 |
| 420 | `[212,213)` | 1 |

Those nine blocks required eight new range compositions. The range spans 176 accelerated transitions and 509 primitive operations, with cumulative halving exponent 333.

## Why one residue class gives the exact valuation sequence

For a nonempty observed block with coefficients `A,B,S`, the correct finite cylinder is

$$
Ax+B\equiv 2^S\pmod{2^{S+1}}.
$$

This requires the formal final numerator to have **exactly** valuation `S`. A congruence only modulo `2^S` would permit extra factors of two and would not state the same finite itinerary.

Since `A=X^m` is odd, multiplication by `A` is invertible modulo `2^(S+1)`. Therefore there is exactly one input residue class modulo that power of two. The observed block-start state realizes the recorded exponents, so its residue modulo `2^(S+1)` identifies that class. The implementation saves this observed-start residue; it does not recompute a modular inverse.

Necessity follows by following the observed finite itinerary. For sufficiency, suppose the displayed congruence holds, so `v_2(N_m(x))=S_m`. Work backward through

$$
N_{j+1}(x)=XN_j(x)+2^{S_j}.
$$

Because `S_(j+1) >= S_j+1`, exact valuation `S_(j+1)` gives

$$
XN_j(x)\equiv -2^{S_j}\pmod{2^{S_j+1}}.
$$

Oddness of `X` implies `v_2(N_j(x))=S_j`. Induction recovers each intermediate exact valuation. Dividing consecutive numerators by `2^S_j` shows that the accelerated transition removes exactly `a_j` factors of two at each step. Positive input, positive `X`, and the recurrence give positive intermediate states.

Thus membership in the saved residue class is necessary and sufficient for **this finite exponent sequence**, assuming the recorded source transitions and affine construction are authentic. It says nothing about the tail after the block. It also does not promise that another seed has no repeated state before finishing the block; the map remains mathematically defined even if a cycle would cause this module's orbit builder to stop.

For the empty block, every positive odd seed qualifies. Its stored identity is `A=1, B=0, S=0` and residue one modulo two.

### Delivered cylinder

The actual range `[37,213)` has

$$
A=9^{176},\quad S=333,\quad
x\equiv 24792588637277\pmod{2^{334}}.
$$

The exact 168-digit `B`, exact `A`, power-of-two modulus, and anchor numerator are retained in `saved.ranges[1]`. Its observed input residue is much smaller than its modulus. A qualifying seed jumps to `(Ax+B)/2^333` in one affine evaluation, representing exactly 176 accelerated transitions and 509 auxiliary primitive operations.

## Finite interval navigation

Intervals are inclusive: `[lower,upper]`. Their endpoints are bounded canonical unsigned decimal strings. The module intersects them with the positive domain by taking `L=max(lower,1)`. It rejects reversed endpoints.

Let the cylinder have canonical odd residue `r` and modulus `M=2^(S+1)`, with `0<r<M`. The first qualifying seed at least `L` is

$$
f=r+\max\!\left(0,\left\lceil\frac{L-r}{M}\right\rceil\right)M.
$$

If `L>upper` or `f>upper`, the interval is empty. Otherwise,

$$
c=\left\lfloor\frac{upper-f}{M}\right\rfloor+1,\qquad
\ell=f+(c-1)M.
$$

The implementation uses the positive-integer ceiling formula only when `L>r`, avoiding negative-division ambiguities.

Selection is zero-based: rank `k<c` returns `f+kM`. A rank outside the interval count returns `found:false` rather than fabricating a seed. Ranking first checks the positive interval and then residue membership. For a qualifying seed `x`, its rank is `(x-f)/M`.

Jumping checks residue membership before evaluating the affine expression. A seed in a different residue class returns `realizes_recorded_block:false` with expected and observed residues and no output. Such a rejection says only that the seed does not realize this saved finite exponent sequence.

Increasing a qualifying input by `M` increases the output by

$$
\frac{AM}{2^S}=2A.
$$

Therefore the image of all qualifying seeds in a finite interval is an exact arithmetic progression. `imageSeeds` evaluates its first valid input once and derives the last output using this stride; it does not enumerate every seed or run their individual trajectories.

### Actual large interval

The reader queried `[10^500,10^520]` for the range `[37,213)`. It retained the exact 420-digit count, first seed, and last seed. The chosen zero-based rank was `12345678901234567890`, which the retained count showed was inside the interval.

The selected seed has 501 decimal digits. Its affine output has 568 decimal digits. The reader also ranked that selected seed and retained the exact input and output progression. These are separate requested consumer operations with their own recorded arithmetic; the rank call is not presented as a free or independent verification of the select call.

Because both powers of ten are multiples of `2^334` and the saved residue lies strictly between zero and that modulus, the count can also be expressed as

$$
\frac{10^{520}-10^{500}}{2^{334}}.
$$

This expression explains the finite count structurally. The delivered receipt retains the directly calculated decimal count; no additional trajectory computation was used to state this formula.

## Public API

The CommonJS export is frozen and contains `SCHEMA`, `LIMITS`, `createOddOrbit`, and `openOddOrbit`. Each returned engine is a frozen object. Results and snapshots are plain copied JSON values, so caller mutation does not alter the engine's internal record.

### Construction and saved opening

~~~js
const {
  createOddOrbit,
  openOddOrbit,
  LIMITS
} = require("./odd_orbit_affine.cjs");

const engine = createOddOrbit({
  source_id: "my-new-orbit-input",
  multiplier: 9,
  start: "1"
});
~~~

`source_id` must be a nonempty string of at most 512 characters. The multiplier must be an odd safe integer from five through 65,535. The start must be a positive odd canonical decimal string under the common decimal-input and bit bounds.

Construction creates the initial state and initial first-value entry. It performs no orbit transition and creates no block.

To consume the delivered saved data:

~~~js
const fs = require("node:fs");
const record = JSON.parse(
  fs.readFileSync("./nine_start1_orbit.json", "utf8")
);
const reader = openOddOrbit(record.saved, {
  source_id: "my-distinct-saved-consumer"
});
const summary = reader.summary();
const finalOddState = reader.getState({ odd_index: 256 });
const knownRange = reader.rangeCertificate({ from: 37, to: 213 });
~~~

The filesystem belongs only to this illustrative caller. The module itself has no I/O. These instructions are examples; they were not separately executed to produce the shipped receipt.

A saved opening preserves the original input's source ID and adds a new session under the supplied distinct ID. Reusing an existing session source ID is rejected. The original multiplier and start cannot be changed through a saved opening.

### Method reference

| Method | Arguments | Result and scope |
|---|---|---|
| `advance` | `{odd_steps}` | Adds at most the requested number of new accelerated transitions; may stop earlier on a repeat or an orbit bound. Returns the advance ID, before/after totals through its stored receipt, current endpoint, stop, and work. |
| `getState` | `{odd_index}` | Copies one retained odd-state record. Valid indices are zero through the completed transition count. |
| `pageStates` | `{offset,limit}` | Pages retained odd states, including state zero. |
| `getTransition` | `{odd_index}` | Copies transition `odd_index`. Valid indices are zero through one less than the completed transition count. |
| `pageTransitions` | `{offset,limit}` | Pages full retained transition records. |
| `primitiveState` | `{primitive_step}` | Retrieves an auxiliary primitive address using a saved numerator and at most one new shift. |
| `getBlock` | `{block_id}` | Copies one saved dyadic node with child references, interval, affine coefficients, cylinder, and anchor. |
| `pageBlocks` | `{offset,limit}` | Pages saved nodes in append order. |
| `rangeCertificate` | `{from,to}` | Returns or creates the finite cylinder/affine record for a contiguous transition range. |
| `countSeeds` | `{from,to,lower,upper}` | Counts positive seeds in an inclusive finite interval and gives its first/last members. |
| `selectSeed` | `{from,to,lower,upper,rank}` | Returns the qualifying seed at a zero-based decimal rank, or `found:false`. |
| `rankSeed` | `{from,to,lower,upper,seed}` | Returns membership and rank, or an explicit interval/class rejection. |
| `jumpSeed` | `{from,to,seed}` | Checks the finite cylinder and, if it matches, evaluates the affine jump. |
| `imageSeeds` | `{from,to,lower,upper}` | Gives the exact finite arithmetic progression of outputs for all qualifying interval seeds. |
| `summary` | None | Copies current orbit, session, counter, and opening-validation summaries. It does not add a query event. |
| `snapshot` | None | Copies the complete resumable record, including query and advance histories. It does not add an event. |

`advance.odd_steps` is a safe integer from one through 256. Each page has a safe integer `offset` from zero through its current total and a `limit` from one through 64. Offset equal to the total returns an empty final page. Page results contain `offset`, `total`, `records`, and `next_offset`; a null next offset means that particular array is exhausted.

Range endpoints, block IDs, odd indices, and primitive addresses are safe integer Numbers. Decimal quantities are strings: starts, interval endpoints, seed values, and ranks. A canonical unsigned decimal string is exactly `"0"` or a nonzero leading digit followed by digits. Signs, spaces, leading zeroes, fractions, and exponent notation are rejected. `jumpSeed` requires a positive odd seed. `rankSeed` accepts a nonnegative seed so that an out-of-domain value can receive an interval or class disposition.

A range can be empty: `from===to`. It returns the positive-odd identity cylinder. Ranges must lie inside the retained prefix; the module never silently extends an orbit to answer a query.

### Continuation without rebuilding an accepted prefix

The delivered final orbit remains extendable. A subsequent real consumer can open `record.saved` under a new session ID, then request a genuinely new suffix with `advance`. New leaves and internal nodes append to the existing arrays; prior query caches continue to describe their original unchanged intervals.

The earlier 64-transition checkpoint is retained as a precise custody artifact. Repeating its already delivered 192-step suffix is unnecessary for consuming this contribution. Use the final saved prefix for new suffix work, or use the already retained final records for inspection.

A new multiplier or initial state requires a genuinely new `createOddOrbit` input with its own source identity. Importing a snapshot and changing its original request would break the source contract.

## Stop meanings and finite cycle records

The orbit has three status values:

| Status | Meaning |
|---|---|
| `extendable` | The retained finite prefix may be extended within the module's remaining bounds. Completion of the latest requested prefix is not a mathematical stopping theorem. |
| `cycle_found` | The most recent appended odd state is the first repeated value in this recorded trajectory. The snapshot includes its earlier position and finite period data. |
| `bound_reached` | The total transition, raw-numerator bit, or cumulative-halving bound stopped further orbit work. This is an implementation boundary. |

A requested prefix finishing normally has termination `requested_prefix_complete` and status `extendable`. It retains `stop:null`. That is what happened in both delivered advances.

Cycle detection stores the first index of each distinct odd state. After a new transition, it checks whether the next odd value already appears. At the first repeat, prior recorded states are pairwise distinct, and determinism gives a finite preperiod and period. The record contains odd-step and primitive-step lengths, the two matching indices, and the repeated value. The repeated terminal state is retained, but it is not added as a new first occurrence.

Under the authenticity of the exact source transitions, the first-repeat construction supplies a finite cycle certificate and its minimal odd-state period. Opening a snapshot checks its first-value bindings and saved cycle addresses; it does not independently recompute the dynamics. No cycle branch was exercised by the delivered nine-map prefix.

If a raw numerator exceeds the value-bit bound, the attempted numerator and its bit length are retained in the stop record. If the cumulative-halving bound would be exceeded, the attempted numerator, observed halving count, and previous total are retained. An orbit bound is not evidence of infinity, convergence, or a missing cycle.

The coefficient, result, history, or aggregate-copy guards may instead throw before a successful transaction can commit. These resource failures must be distinguished from a committed `bound_reached` orbit record.

## What saved opening checks

Opening first makes a bounded JSON copy. It then checks structural fields and retained references, including:

- Schema, original source/request binding, positive odd start, multiplier range and oddness.
- Array counts, consecutive odd-state/transition/node IDs, canonical decimal fields, field bit bounds, and bounded addresses.
- Transition input/output references and their primitive-address relationships.
- Block interval lengths, dyadic levels, child adjacency, leaf-to-transition bindings, anchor input/output references, and forest coverage.
- Power-of-two modulus shape, cylinder exponent linkage, and canonical odd residue range.
- The first-value table's state bindings and uniqueness; saved first-repeat and period address bindings when present.
- The latest advance/current-orbit linkage, source IDs and event references.
- Range source IDs, ordered covers, endpoint/anchor bindings, primitive and shift linkage, and the literal empty-range identity.
- The complete declared work-counter key set and nonnegative safe integer counter values.

It does **not** recompute `Xn+1` transitions, valuations, affine coefficient products, cylinder residues, or anchor arithmetic. It does not re-establish extrema, authenticate every semantic field in a historical query result, or prove that supplied work counters reflect real execution. Structural acceptance is not mathematical proof authentication.

The emitted validation record makes this boundary explicit with zero replay counters and `mathematical_proof_authenticated:false`. It is intended for custody-preserved snapshots from the same implementation. Arbitrary externally edited snapshots require separate source authentication before their numerical claims are trusted.

### Transactions and errors

A successful advance or query operates on a copy and commits only after the complete resulting state can be copied within the aggregate bounds. Returned values are another copy. This prevents a successful method from leaving an internal state that immediately cannot be exported under those same aggregate bounds.

Normal consumer negatives, such as a seed in a different cylinder or a rank outside a finite count, are returned as explicit result records. Invalid inputs, exhausted histories, stopped orbits, bit limits, and internal invariant failures throw errors carrying a `code`.

Queries whose operation has begun try to append a failed-query event with the attempted work and error. Draft range/cache changes are discarded on failure. If even that failure record cannot fit within the copy bound, the previous state is preserved and the thrown error includes a retention error. Checks before operation entry, such as an unavailable session or invalid argument object, do not necessarily add an event.

An unsuccessful advance leaves the previous committed state unchanged. Arithmetic attempted inside a failed advance is not committed as a successful work receipt. Callers should retain the thrown error and last saved state and resolve its cause; blindly repeating a failed request is not a continuation protocol.

## Bounds and practical costs

| Bound | Value |
|---|---:|
| Odd multiplier | 5 through 65,535, odd only |
| Total accelerated transitions | 512 |
| Requested new transitions per advance | 1 through 256 |
| Odd value and raw numerator | 8,192 bits |
| Affine coefficient and cylinder fields | 16,384 bits |
| Intermediate seed/anchor result | 32,768 bits |
| Cumulative halving exponent | 16,382 |
| Decimal input string | 1,024 digits |
| Sessions in one snapshot | 32 |
| Query plus advance events per session | 256 |
| Advance history entries | 64 |
| Cached ranges | 128 |
| Page limit | 64 |
| Source ID | 512 characters |
| Aggregate copied values | 4,000,000 visits |
| Aggregate copied string/key characters | 32,000,000 |
| Copy recursion depth | 48 |

The stricter applicable bound controls. For example, an externally supplied start is also limited to 1,024 decimal digits even though the evolving orbit supports larger bit lengths. The raw numerator bound is deliberately enforced before division; a numerator that would shrink to a small odd state can still stop the computation.

Bounds are not independent promises that all maxima fit together. Large decimal records, many query results, and a long history can hit an aggregate copy bound before a smaller named count limit is reached.

There are at most `2m-1` saved nodes after a nonempty `m`-transition prefix. Binary-carry construction makes an amortized constant number of new nodes per appended transition and at most logarithmically many merges on one append. Coefficient arithmetic has operand-size costs; these node counts do not imply constant-time BigInt work.

The canonical range cover uses logarithmically many blocks and compositions. Primitive lookup uses logarithmically many transition-address comparisons. Finite seed interval operations use a bounded number of BigInt arithmetic operations once the range is available. Their bit complexity grows with the modulus, coefficients, and supplied interval digits.

**The complete public-call cost also includes copying retained data and histories.** This implementation copies the whole state for transactional isolation and result retention. An indexed lookup's internal search may be constant or logarithmic while the complete call still takes time and memory proportional to the copied record. Saved opening likewise scans retained structures and parses decimal fields. The delivered measurements include this practical cost; no throughput or asymptotic claim hides it.

The work counters cover named BigInt operations and explicitly tracked search/structure operations. They are not CPU instruction totals. Array management, ordinary Number index arithmetic, decimal conversion, JSON copying, allocation, module parsing, and wall-clock overhead are not exhaustively counted.

## Actual execution and results

One source was constructed at **2026-10-04T21:32:24.965Z**. Its first advance requested 64 new odd transitions. A fresh saved opening at **21:32:45.090Z** requested 192 additional transitions. A separate saved reader opened at **21:33:27.810Z**.

| Quantity | After first advance | After resumed advance |
|---|---:|---:|
| New transitions in that call | 64 | 192 |
| Total accelerated transitions | 64 | 256 |
| Retained odd states | 65 | 257 |
| Retained dyadic blocks | 127 | 511 |
| Cumulative halvings | 133 | 474 |
| Total auxiliary primitive operations | 197 | 730 |
| Final odd-state bit length | 71 | 338 |
| Status | `extendable` | `extendable` |
| Repeat found | No | No |

After 64 transitions, the endpoint is `1250460246531569810209`. The prefix's maximum at that stage is `2738306956218083651015` at odd index 53.

After 256 transitions, the endpoint is also the largest retained odd state, at odd index 256:

~~~text
457512727887953307748379078888167389922580135219353042452975606847787136791054573947744422186981727063
~~~

The minimum retained odd state is the initial one. These extrema range over the recorded odd states, not over every even primitive intermediate or every future iterate.

### Fifteen saved-reader operations

| Query ID | Consumer action | Retained result |
|---:|---|---|
| 0 | `getState(256)` | Final odd state. |
| 1 | `pageStates(240,17)` | All 17 states from 240 through 256. |
| 2 | `getTransition(37)` | Complete transition with input `24792588637277`. |
| 3 | `pageTransitions(64,8)` | Eight already saved transitions. |
| 4 | `primitiveState(111)` | Even numerator `223133297735494` at transition 37. |
| 5 | `primitiveState(112)` | Its odd endpoint `111566648867747`, odd index 38. |
| 6 | `getBlock(510)` | Whole-prefix root with child references and retained affine certificate. |
| 7 | `pageBlocks(504,7)` | Last seven saved block records. |
| 8 | `rangeCertificate(64,128)` | Existing block 253; no new affine composition. |
| 9 | `rangeCertificate(37,213)` | Nine-block cover, eight new compositions, exponent 333. |
| 10 | `countSeeds` on `[10^500,10^520]` | Exact 420-digit finite count and its endpoints. |
| 11 | `selectSeed` at rank `12345678901234567890` | Exact 501-digit qualifying seed. |
| 12 | `rankSeed` for that selected seed | Its exact finite-interval rank. |
| 13 | `jumpSeed` for that selected seed | Exact 568-digit output after the saved finite block. |
| 14 | `imageSeeds` on the full finite interval | Exact count, first/last outputs, and stride `2*9^176`. |

The reader returned 44 method-level records. That count includes page rows and individual result objects; it is not a count of every nested scalar or referenced child node.

### Declared work

| Counter | First 64-step advance | New 192-step suffix | Fifteen reader calls |
|---|---:|---:|---:|
| Multiplications | 253 | 768 | 29 |
| Additions | 190 | 576 | 29 |
| Subtractions | 0 | 0 | 18 |
| Divisions | 0 | 0 | 9 |
| Remainders | 127 | 384 | 4 |
| Left shifts | 190 | 576 | 10 |
| Right shifts | 127 | 384 | 5 |
| Bit-length inspections | 571 | 1,728 | 25 |
| Trailing-zero bit tests | 197 | 533 | 0 |
| Newly completed odd transitions | 64 | 192 | 0 |
| Removed factors of two | 133 | 341 | 0 |
| New leaves | 64 | 192 | 0 |
| New internal nodes | 63 | 192 | 0 |
| New anchor equalities | 63 | 192 | 1 |
| Cycle lookups | 64 | 192 | 0 |
| New first-value entries | 64 | 192 | 0 |
| Saved first-value entries loaded for advance | 1 | 65 | 0 |
| Range compositions | 0 | 0 | 8 |
| New range caches | 0 | 0 | 2 |
| Range cache hits | 0 | 0 | 5 |
| Block nodes visited by range selection | 0 | 0 | 36 |
| Blocks selected | 0 | 0 | 10 |
| Primitive binary-search steps | 0 | 0 | 16 |
| Finite interval count operations | 0 | 0 | 4 |
| New affine seed evaluations | 0 | 0 | 2 |
| Output progression images | 0 | 0 | 1 |

Constructor work is separate: one bit-length inspection and one initial first-value table entry. The second seed evaluation in the reader belongs to the first member of the full interval's image progression; it is separate from the selected rank's seed jump.

The full orbit totals are 1,021 multiplications, 766 additions, 511 remainders, 766 left shifts, 511 right shifts, 2,299 bit-length inspections, and 730 trailing-zero bit tests. It retains all 256 leaves, 255 internal nodes, and their arithmetic witnesses. The reader adds genuine range, count, and affine-jump arithmetic while performing zero new orbit steps, valuation computations, or old-block reconstruction.

### Saved-opening validation observations

| Check | Open 64-step checkpoint | Open 256-step prefix |
|---|---:|---:|
| Odd states | 65 | 257 |
| Transitions | 64 | 256 |
| Blocks | 127 | 511 |
| Existing cached ranges | 0 | 0 |
| First-value entries | 65 | 257 |
| Decimal fields parsed | 1,018 | 4,090 |
| Reference checks | 131 | 518 |
| Primitive-index relations | 385 | 1,537 |
| Power-of-two shape checks | 127 | 511 |
| First-value state bindings | 65 | 257 |
| Orbit steps replayed | 0 | 0 |
| Valuations recomputed | 0 | 0 |
| Affine products replayed | 0 | 0 |
| Cylinder residues recomputed | 0 | 0 |
| Independent mathematical proof authentication | No | No |

The two cached ranges were created afterward by the 15-query reader. Their saved-opening branch is specified in the source but was not exercised by an additional reopen of the already completed reader snapshot.

### Timing observations

| Operation | One observed wall-clock duration |
|---|---:|
| Initial constructor | 2 ms |
| First 64-step advance | 7 ms |
| Opening the 64-step checkpoint | 11 ms |
| Advancing 192 new steps | 24 ms |
| Opening the 256-step prefix | 31 ms |
| Fifteen-query loop including local receipt/snapshot retention | 486 ms |

Individual public query calls were observed between 16 and 22 ms. These are single connected-runtime observations and include record-copying costs. They are not benchmark distributions, native-runtime timings, or performance guarantees.

## Verification and unexercised behavior

Before computation, the complete candidate source was parsed and statically inspected. Four concrete structural/accounting changes were made before freezing: count the constructor's initial first-value entry; require complete work-counter keys; bind saved cycle period addresses; and bind cached range primitive/anchor fields plus the empty identity.

The first constructor, both nonoverlapping advances, and the 15 real saved-consumer operations then ran once under that frozen source. No constructor failure, query failure, trajectory retry, source substitution, or accepted-proof replay occurred. Every actual result and work receipt is retained in the JSON. JSON pretty-printing and literal identity checks changed no numerical value.

Only one original trajectory was executed. The general multiplier branches, a first-repeat termination, raw/cumulative budget stops, total 512-step boundary, invalid-input outcomes, empty-range query, negative membership results, and cache-containing saved reopening were not exercised as extra fixtures or tests. Their contracts are stated and statically derived, with the executed scope kept explicit.

Publication verification covers the delivered source/document/data texts, their Git blob identities, changed paths, and the resulting PR metadata and requested revision readbacks. It does not turn structural saved opening into independent mathematical authentication.

The contribution supplies a bounded orbit, exact finite-cylinder arithmetic, and a reusable saved index. It makes no proof of divergence for the nine-map, no proof that a multiplier/start satisfying Prize 1 exists, no universal termination theorem, no classification of all cycles, no optimal search claim, and no prize eligibility or payout assertion.
