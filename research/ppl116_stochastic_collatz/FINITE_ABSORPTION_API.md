# Finite absorption index for stochastic odd Collatz moves

This package constructs an exact stopped Markov chain on a bounded odd interval, retaining its transitions, strongly connected components, terminal-path witnesses, rational absorption probabilities and expected stopping times. Its separate reader uses the saved results without rebuilding transitions, components or the linear system.

## Primary problem and finite contract

[Ingo Althöfer's primary page](https://althofer.de/collatz-prizes.html), updated September 21, 2026, defines independent fair choices between \(\operatorname{odd}(3n-1)\) and \(\operatorname{odd}(3n+1)\), where every factor of two is removed. State 1 is absorbing under both choices. The source conjectures almost-sure convergence to 1 for every positive odd start. Its mixed stochastic variant and alternating-player game are separate questions. The author's request not to send proof attempts is preserved; this work involves no contact or submission.

For an odd cap \(M\), this API uses \(D=\{1,3,\ldots,M\}\). It stops at the first of:

1. reaching 1;
2. moving to a value outside \(D\);
3. entering a closed strongly connected component within \(D\) other than \(\{1\}\).

A closed component has both outgoing coin moves of each of its states inside the component. It is therefore closed for the original process as well. The API can represent such a class without assuming that none exists. The actual \(M=139\) input has no other closed class.

An exit is **not a failure to reach 1 in the original process**. The original process may return from that outside state and later reach 1. The retained quantities are first-exit probabilities and stopped-time expectations, not simulated frequencies or unknown continuation probabilities.

The conventional absorbing-chain formulas are stated in Grinstead and Snell, [*Introduction to Probability*, §11.2, printed pages 416–420](https://math.dartmouth.edu/~prob/prob/prob.pdf), Theorems 11.3–11.6. The accessible CHANCE version is dated July 4, 2006 and identifies the AMS second edition. It requires an absorbing state reachable from every state, gives \(Q^k\to0\), \(N=(I-Q)^{-1}\), absorption matrix \(NR\), and expected time \(N\mathbf1\). The application below establishes the reachability requirement for its own stopped process. It is not an application of a finite-state theorem to the entire infinite Collatz chain.

## Finite termination and exact equations

Transitions are stored in increasing state order. Each state has a minus edge and a plus edge, each with probability \(1/2\). Edges keep their signs even if their targets coincide, so multiplicity is retained.

The internal graph includes only edges whose targets remain in \(D\). Its strongly connected components are computed, and all closed components other than 1 are designated terminal. Every remaining state can reach a terminal event. Otherwise following the finite component DAG from an unreachable component would reach a closed sink component that should have been designated terminal, a contradiction. An edge to an outside target is also a terminal event.

Reverse breadth-first traversal retains one decreasing-distance edge from each nonterminal state. Let \(L\) be the maximum retained distance. Starting from any state not yet stopped, following its chosen path has probability at least \(2^{-L}\), and reaches a terminal event within \(L\) moves. For \(L>0\),
\[
\Pr(\tau>kL)\le(1-2^{-L})^k,\qquad
\mathbb E[\tau]\le L2^L.
\]
Repeated applications use fresh independent coin choices. If \(L=0\), all starting states are terminal and \(\tau=0\). Thus the stopped time is finite almost surely, with finite expectation. This reasoning does not say that the original chain reaches 1 almost surely.

Let \(T\) be the nonterminal states. Let \(C_{ij}\in\{0,1,2\}\) count coin edges from \(i\) to \(j\in T\), and let \(B_{ia}\) count coin edges from \(i\) into terminal outcome \(a\). Outcomes are 1, each distinct outside value separately, and each other closed class separately. With \(Q=C/2\) and \(R=B/2\),
\[
(I-Q)H=R,\qquad (I-Q)t=\mathbf1.
\]
Equivalently, the integer system is
\[
(2I-C)H=B,\qquad (2I-C)t=2\mathbf1.
\]
Rows are starting states; outcome columns have the order retained in the snapshot. The final right-hand-side column is expected stopped time.

The path argument implies \(Q^k\to0\), so \(I-Q\) is invertible. One elementary uniqueness argument is to iterate a homogeneous solution \(z=Qz\): \(z=Q^kz\to0\). The inverse is the convergent nonnegative sum \(\sum_{k\ge0}Q^k\). Hence a nonnegative rational solution with exact residual zero is the unique solution to the stated absorption problem.

The implementation performs fraction-free elimination on the integer augmented matrix, checking every division is exact. It then back-substitutes using normalized BigInt fractions. It retains the original augmented matrix, final upper matrix, each elimination pivot/row choice/previous divisor, and every final equation residual. Intermediate matrices at all elimination stages are not stored. Correctness of a completed result is independently tied to the original equations and uniqueness; no unchecked numerical pivot tolerance is used.

For terminal input states, the corresponding outcome has probability 1 and expected stopped time 0. Every result row is checked to have nonnegative probabilities at most 1 summing exactly to 1. The implementation refuses a negative solved quantity, nonexact division, singular pivot or nonzero residual.

## Relationship to the infinite process

Write \(h(n)\) for the actual, generally unknown probability that the original infinite process eventually reaches 1. Let \(p_1(n)\) be the saved probability of hitting 1 before other terminal events and \(p_x(n)\) the probability of first exiting at \(x\). Entry into a closed class avoiding 1 contributes zero. The Markov property and almost-sure finite stopping give
\[
h(n)=p_1(n)+\sum_x p_x(n)h(x).
\]
Consequently
\[
p_1(n)\le h(n)\le p_1(n)+\sum_x p_x(n).
\]
For this input there is no other closed class, so the upper bound is 1. The useful output is the exact lower bound and the resolved distribution of the unknown continuation mass.

The reader's boundary operation substitutes explicitly supplied values \(b_x\in[0,1]\) into this formula. It is a Dirichlet evaluation, not an estimator for \(h(x)\). It equals \(h(n)\) only when those supplied values are the actual continuation probabilities. The actual demonstration assigns every exit value \(1/2\) and labels that input hypothetical.

Mixtures are convex combinations of the saved starting-state results. Their weights must sum exactly to 1. Expected time remains the time until the defined stop, not until an eventual return to 1 after an exit.

## Public interface

The plain CommonJS module has no dependencies or I/O and exports:

- `ABSORPTION_LIMITS`
- `compileFiniteAbsorption({max_odd, provenance?})`
- `openRetainedAbsorption(snapshotOrJSONString)`

Construction returns `{status, snapshot, work, snapshot_chars}` with schema `commons.finite_fair_collatz_absorption/v1`. The domain is always the complete odd interval from 1 to `max_odd`; arbitrary sparse sets and biased coins are not accepted.

The saved reader provides:

| Operation | Result |
| --- | --- |
| `summary()` | Domain, component/transient/outcome counts, termination certificate and validation scope |
| `source()` | Outward copy of source provenance |
| `state(n)` | Both saved coin transitions and the complete probability/time row |
| `page({start?,limit?})` | Increasing-state solution rows; default start 0 and limit 16 |
| `outcomes({start?,limit?})` | Terminal outcome definitions in column order |
| `mixture(entries)` | Exact convex-mixture hit enclosure and expected stopped time |
| `boundary(n,values)` | Explicit conditional boundary-value calculation |
| `snapshot()` | Outward copy of the complete snapshot |
| `statistics()` | Outward copy of reader work; not counted as a query |

A fraction has the JSON shape `{numerator:"243731074", denominator:"280829761"}`. Numerators must be canonical nonnegative decimal strings; denominators canonical positive decimal strings. Returned fractions are reduced. The saved reader accepts fraction values without recomputing gcd normalization; query arithmetic normalizes newly computed fractions.

A mixture entry is `{state:n, weight:fraction}`. States must be distinct, valid odd members of the domain; there can be at most one entry per state. Weights may be zero, must lie in \([0,1]\), and must sum exactly to 1. A boundary entry is `{state:x, value:fraction}`, with exactly one entry for every retained outside outcome and no duplicates. All values must lie in \([0,1]\).

State, domain, position and page-limit arguments are safe integer Numbers. No even state, out-of-domain state, negative start or wraparound is accepted. Pages allow start equal to the table length and limit 0; both yield empty records, with no implicit progress for a zero limit.

### Hard bounds and refusal

| Quantity | Limit |
| --- | --- |
| Domain | At most 128 odd states, so odd cap at most 255 |
| Integer augmented matrix | 65,536 cells |
| Preflight fraction-free updates | 8,000,000 |
| Fraction numerator/denominator | 1024 decimal characters |
| Snapshot serialization | 4,000,000 JavaScript characters |
| Provenance serialization | 16,384 characters |
| Page rows | 0 through 32 |

The augmented dimensions and planned elimination count are checked before solving. Snapshot and serialized fraction limits are checked before successful return; a failure throws rather than presenting an incomplete result as complete. The source's bounded small transition arithmetic uses safe Numbers; the elimination and rational arithmetic use BigInt. Internal integer intermediates are not floating-point values. No cap is automatically increased.

### Saved-reader trust boundary

The loader checks serialization/schema, model labels, odd cap, table shapes and lengths, state ordering, transition field bounds/sign ordering, saved fraction encodings/ranges, terminal-index/component bounds, and basic enclosure ordering. It checks the finite-termination bound is a positive probability and checks transient-state ordering.

It does **not** recompute \(\operatorname{odd}(3n\pm1)\), SCCs, shortest paths, exact divisions, linear equations, residuals, probability normalization, or provenance. It does not independently establish that saved outcome classes and labels are correct. Those are identified constructor premises. Structural success alone cannot authenticate a malicious or corrupted mathematical snapshot. This is explicitly reported in the summary.

All exposed source, snapshot, table and statistics objects are outward copies. New mixture/boundary rational arithmetic is counted separately from zero constructor or solve replay.

## Actual odd-cap-139 result

The actual input uses 70 odd states, reusing only scalar 70 from released Commons #31507 `input.length`. The source record is `research/ppl165_primitive_word_index/length70_words.json`, blob `8a0efdcbe0f447ec7aba6f42ea9e5a1ee4695774`. No primitive-word or earlier NFA operation is repeated.

Executed source was frozen at `4661428b7c467422f6c1fe7e5bc73e0fb69ae485`. Its one construction records:

- 70 states and 140 signed transitions, with 279 down-halvings;
- 32 strongly connected components, of which only \(\{1\}\) is closed;
- 69 transient states and 24 outcomes: hit 1 plus 23 distinct outside values;
- maximum retained terminal-path length 4, hence conditional stop probability at least \(1/16\) within four moves;
- a 69-row integer system with 24 outcome columns and one time column;
- all 1725 equation residuals equal to zero and all 70 probability partitions equal to one.

The 23 first-exit values are
\[
143,145,149,151,155,157,161,163,167,169,173,175,
179,181,185,187,191,193,197,199,203,205,209.
\]
These are exact destinations, not a single undifferentiated overflow symbol.

| Start | Hit 1 before exit | First-exit probability | Expected stopped steps |
| --- | --- | --- | --- |
| 1 | \(1\) | \(0\) | \(0\) |
| 27 | \(243731074/280829761\) | \(37098687/280829761\) | \(2225556383/280829761\) |
| 69 | \(350047675/561659522\) | \(211611847/561659522\) | \(1734626919/280829761\) |
| 139 | \(265200523/561659522\) | \(296458999/561659522\) | \(2345118279/561659522\) |

For a uniformly selected state in this 70-state domain, the exact eventual-hit lower bound is
\[
189955952649/314529332320,
\]
with upper bound 1. The mean stopped time is
\[
7761650134877/1258117329280.
\]
This uniform starting distribution is an explicitly chosen finite query, not a distribution specified by the original conjecture.

For start 139 with all hypothetical exit values \(1/2\), the reader returns
\[
826860045/1123319044.
\]
It is not asserted to be the actual eventual-hit probability.

### Complete retained work

The constructor made 165784 fraction-free cell updates, each with an exact division, no row swaps, 58650 back-substitution terms, 651290 gcd divisions, 4450 nonzero-coefficient residual terms and 1725 residual checks. These are actual new computation counters, not a test suite or replay of an accepted artifact.

A fresh module context opened the saved snapshot and made 12 queries: summary, source, states 1/27/69/139, three pages exporting all 70 solution rows, all 24 outcomes, the uniform mixture, and the hypothetical boundary calculation. All arguments and outputs are retained. Reader work was 70 saved state rows, 2031 saved fraction fields, 94 returned page rows, 70 mixture terms, 23 boundary terms and 7105 gcd divisions. It made zero compiler calls, transition/SCC recomputations, elimination updates or equation-residual recomputations.

Observed constructor/load/query times were 87 ms, 3 ms and 12 ms in one connected V8 session. They are observations, not repeated performance measurements.

Before execution the source was checkpointed as a native Git object. Before reader queries, the complete constructor packet was banked at `0ff1c6db821efb9da1e3e3eca0554d60956d07c2`, 551,077 bytes. The complete final packet, including every query, is `49292324248673869e9f47a06158e1dab0174647`, 860,756 bytes. It retains all 140 transition records, components, outcomes, path witnesses, probability/time rows, both matrix endpoints, complete pivot journal, all residual rows and full query receipts. No missing output was recreated.

Only this domain and these queries ran. Other domains, malformed-input cases, nontrivial closed-class handling and the row-swap branch were source-inspected, not claimed as executed. No native executor, proof assistant, synthetic suite, old deterministic Althöfer trajectory, word-index computation, sponsor contact or prize submission was used.

## Saved use

The example below is illustrative, not another recorded execution:

```javascript
const api = require("./finite_absorption.cjs");
const record = require("./odd139_absorption.json");
const index = api.openRetainedAbsorption(record.constructor.snapshot);
const start27 = index.state(27);
const rows = index.page({start: 32, limit: 32});
```

A connected V8 consumer may evaluate the same CommonJS source with `new Function("module","exports",source)` and provide the parsed snapshot. The module itself performs no network or file action.

This contribution is a reusable exact finite stopped-process index. Neither the lower probabilities, the finite termination certificate nor the absence of another closed class within this one domain proves almost-sure convergence of the original infinite process.
