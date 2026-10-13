# Residue-covering counts and CRT navigation

This package compiles one complete period for supplied pairwise-coprime moduli, then indexes every choice of one residue class per modulus that covers an initial interval. Its saved gap representation supports exact threshold counts, assignment rank/select, pages and translated divisibility witnesses.

The actual prime input is \(2,3,5,7,11,13,17\). The maximum gap 26 and maximum covered length 25 are established published values. The contribution is the reusable finite family index, complete threshold data and retained query outputs; it makes no new maximum or asymptotic claim.

## Sources and conventions

The [PPL137 catalogue](https://prizeproblems.org/problems/137/) states Erdős 687 in terms of the largest \(y\) for which one class modulo each prime \(p\le x\) covers every integer in \([1,y]\), and asks for asymptotic upper estimates. This is a question about all such choices, not just the zero classes.

Ziller and Morack, [*Algorithmic concepts for the computation of Jacobsthal's function*, arXiv:1611.03310v2](https://arxiv.org/pdf/1611.03310), Definitions 1.1–1.4, define \(j(P)\) as the largest consecutive-coprime gap and \(j(P)-1\) as the largest intervening noncoprime run. Table 1, row \(n=7,p_n=17\), already gives \(h(7)=26\). Their Proposition 1.3 and Remark 1.2 discuss CRT covering equivalence in a condensed odd-prime/nonzero-residue formulation. The unrestricted phase bijection below is stated directly; its zero residues are not excluded by that normalization.

[OEIS A048670](https://oeis.org/A048670), by Jan Kristian Haugland, has \(h(n)=j(p_n\#)\), while [A058989](https://oeis.org/A058989), by Jud McCranie, has the reduced value one smaller and credits earlier term calculations. Both mathematical indices start at 1. Thus the supplied seventh-prime input has published gap 26 and covering length 25. The paper's separate condensed value and sequence-count columns are not silently used as this API's general assignment counts.

For this prime specialization,
\[
Y(x)=j\!\left(\prod_{p\le x}p\right)-1.
\]
The empty-prime case is not implemented: the API requires at least one modulus of size at least 2. The generic interface permits pairwise-coprime composite moduli. Its survivors avoid divisibility by every whole supplied modulus; they need not be coprime to the product. The term “totative” applies to the actual distinct-prime input only. No primality tests occur.

The canonical FormalConjectures 687 path returned 404 on the one current read and was held without retry. This does not determine the mathematical status. No linked proof, old prize-crosswalk source or accepted mathematical computation was rerun.

## Complete CRT correspondence

Let \(m_1<\cdots<m_k\) be pairwise-coprime integers at least 2 and \(P=\prod_i m_i\). A residue assignment is the vector
\[
(a_1,\ldots,a_k),\qquad 0\le a_i<m_i.
\]
The Chinese remainder theorem gives a unique phase \(t\in[0,P)\) with
\[
t\equiv-a_i\pmod{m_i}\quad\text{for every }i.
\]
Conversely each phase gives exactly one assignment. There are \(P\) assignments, including assignments with zero residues. They are not identified under reflection, rotation, translation or any graph/set isomorphism.

An offset \(r\) is covered precisely when \(r\equiv a_i\pmod{m_i}\) for some \(i\), equivalently when \(t+r\) is divisible by at least one supplied modulus. Therefore the complete family can be navigated by a fixed zero-class marking table and translation of its phase.

The constructor stores for each modulus its cofactor \(M_i=P/m_i\) and inverse \(u_i=M_i^{-1}\pmod{m_i}\). The inverse conversion is
\[
t\equiv-\sum_i a_iM_iu_i\pmod P.
\]
The minus sign is part of the contract. Rank order is increasing \(t\), not lexicographic order of the residue vector.

## Gaps, coverage and counts

Mark residues divisible by a supplied modulus. Write the remaining residues as
\[
1=u_0<u_1<\cdots<u_{s-1}=P-1,
\quad u_s=P+1.
\]
The two endpoints follow because no modulus divides 1 or \(P-1\). Let \(d_i=u_{i+1}-u_i\); then the cyclic gaps sum to \(P\).

For a phase between consecutive survivors,
\[
u_i\le t<u_{i+1},
\]
the first uncovered offset is \(u_{i+1}-t\), and the covered initial length is
\[
c(t)=u_{i+1}-t-1.
\]
Each gap of length \(d\) therefore contributes one phase of each coverage length \(0,\ldots,d-1\). The cyclic last gap handles phase 0 by reduction modulo \(P\).

Consequently the number of assignments covering at least the first \(y\) offsets is
\[
N(y)=\sum_i\max(d_i-y,0),\qquad y\ge0.
\]
The maximum covered length is \(\max_i d_i-1\). A histogram of gap lengths evaluates the complete count profile with suffix counts and weighted sums. In particular \(N(0)=P\), and \(N(y)=0\) once \(y\) reaches the maximum gap.

For positive \(y\), a contributing gap yields the inclusive phase interval
\[
[u_i,u_{i+1}-y-1],
\]
of length \(d_i-y\). These intervals are disjoint and sorted. They do not wrap past \(P-1\): the last gap ends at \(P+1\), and positive \(y\) keeps its permitted endpoint at most \(P-1\). For \(y=0\) the implementation directly uses the single interval \([0,P-1]\), including phase 0.

A saved coverage slice stores each interval as \([start,end,countBefore]\). Selection binary-searches cumulative counts and adds the residual rank to the interval start. Ranking binary-searches interval starts, returns the within-interval rank when present, and otherwise returns a null family rank plus the insertion rank. These are exact operations on the saved finite interval union.

## Divisibility certificates and large shifts

A signed integer shift \(T\) uses phase \(t=T\bmod P\), normalized to \([0,P)\). Its coverage pattern is identical to phase \(t\). The classifier locates the first saved survivor strictly after that phase, with cyclic continuation when needed.

For every covered offset it supplies the first dividing modulus in the sorted input, the exact integer \(T+r\), and the quotient \((T+r)/m_i\). For the first uncovered offset it supplies every nonzero modulus remainder. These computations use BigInt and make the requested witnesses explicit; they do not repeat the period marking.

“Uncovered” means uncovered by the selected residue classes. It does not mean prime. For general signed shifts the integer may be zero or negative, so the generic output asserts divisibility, not a positive proper-divisor statement. The actual large positive shift has positive values larger than every modulus, so its 25 displayed divisors are proper.

## Interface and saved-data scope

The module is plain CommonJS, without imports or I/O. Exports:

- `COVERING_LIMITS`
- `compileResidueCoverings({moduli, provenance?})`
- `openRetainedCoveringWheel(snapshotOrJSONString)`
- `openRetainedCoverageSlice(snapshotOrJSONString)`

Construction returns `{status,snapshot,work,snapshot_chars}`, schema `commons.residue_covering_wheel/v1`. It validates pairwise coprimality, computes CRT coefficients, marks every multiple of each modulus over the full period, scans the full period for survivors, then records all cyclic gaps, their histogram and the complete coverage-count profile.

### Saved period reader

| Method | Return |
| --- | --- |
| `summary()` | Moduli, period, survivor/max-gap counts and validation scope |
| `source()` | Outward copy of provenance |
| `profile()` | Every threshold count and gap-histogram entry |
| `crt()` | Every retained cofactor/inverse/coefficient row |
| `count(y)` | Exact number of assignments covering offsets 1 through \(y\) |
| `slice(y)` | Complete saved phase-interval representation for that threshold |
| `classifyShift(T)` | Phase/residue assignment, complete covered witnesses and first uncovered witness |
| `classifyResidues(a)` | Same classification after CRT conversion of the residue vector |
| `snapshot()` | Outward copy of the full saved period |
| `statistics()` | Outward copy of counters, without incrementing query count |

Opening this reader checks the schema, conventions, modulus product, CRT row shapes/cofactor products, sorted survivor bounds, every gap-to-neighbor relation, gap endpoint/sum identities, histogram/count field bounds and profile endpoints. It does not remark multiples, establish survivor completeness, verify saved inverse congruences, recompute histogram counts or reconstruct count-profile arithmetic. These remain identified constructor premises.

Threshold slice creation really scans the saved gap list. This is counted work, distinct from a new period sieve. Classification really recomputes the requested short divisibility witnesses and refuses contradictions with the supplied saved boundaries. It does not certify all other saved rows.

### Saved slice reader

| Method | Return |
| --- | --- |
| `summary()` | Threshold, period, assignment total, interval count and ordering |
| `source()` | Original period provenance and completeness qualification |
| `select(rank)` | Rank, phase and complete residue assignment |
| `rankPhase(t)` | Membership, family rank or null, and insertion rank |
| `rankResidues(a)` | Same after CRT conversion |
| `page({start?,limit?})` | Consecutive assignment ranks and continuation position |
| `snapshot()` | Outward copy of the saved slice |
| `statistics()` | Outward copy of counters |

The slice loader checks sorted disjoint interval bounds, cumulative counts and total, together with CRT structure and threshold/order conventions. It does not scan the original gap list or authenticate coverage completeness. Successful structural loading is not an independent mathematical verification of an untrusted file.

Slice ranks are zero-based in increasing phase order. Selections require rank less than the total. Page start may equal the total; limit 0 is allowed and makes no progress. Defaults are start 0 and limit 16. Phase inputs lie in \([0,P)\). Residues must be canonical safe integer Numbers with \(0\le a_i<m_i\) in the exact stored modulus order. Arbitrary shift inputs may be negative; threshold/rank inputs may not.

Large integers accept BigInt, safe integer Number or canonical decimal strings. Unsafe Numbers, leading-zero spellings other than `"0"`, negative zero strings and nonintegers are refused. Outputs use strings for arbitrary-size shift values and exact quotients; bounded ranks, phases, interval counts and moduli use safe Numbers.

### Bounds

| Quantity | Hard bound |
| --- | --- |
| Number of moduli | 1 through 16 |
| Product \(P\) | At most 1,000,000 |
| Maximum observed gap | At most 1024 |
| Snapshot serialization | 8,000,000 JavaScript characters |
| Saved slice intervals | At most 500,000 |
| Integer input length | 1000 decimal digits excluding a minus sign |
| Provenance | 16,384 characters |
| Page output | At most 32 assignments |

Moduli are strictly increasing integers at least 2. Pairwise coprimality is checked in construction; primality is not. A bound failure throws without claiming a completed index. The gap and snapshot bounds may be encountered after marking, so a refused construction is not a partial mathematical result. There is no automatic cap increase.

## Actual complete period and queries

The literal prime input is \([2,3,5,7,11,13,17]\), product 510510. Its relationship to the seventh primorial is an identified input premise; no prime-generation or primality computation was repeated. The one construction used frozen source `c03b7acfc3af836b159224df627977357b6bb4c0`.

It retains all 92,160 surviving residues and all 92,160 cyclic gaps. The histogram gives the known maximum gap 26, reduced coverage 25, and a 27-row count profile for thresholds 0 through 26.

| Required covered prefix | All assignments | Saved intervals |
| --- | ---: | ---: |
| 20 | 248 | 100 |
| 24 | 4 | 2 |
| 25 | 2 | 2 |
| 26 | 0 | Empty family by the complete profile |

The complete four assignments for threshold 24 are:

| CRT phase | Residues modulo 2,3,5,7,11,13,17 |
| ---: | --- |
| 217127 | [1,1,3,6,2,12,14] |
| 217128 | [0,0,2,5,1,11,13] |
| 293357 | [1,1,3,6,2,1,12] |
| 293358 | [0,0,2,5,1,0,11] |

Only phases 217127 and 293357 cover 25 offsets. The explicit rank query for phase 217128's residue assignment in the threshold-25 slice returns nonmembership, null rank and insertion rank 1. This demonstrates the boundary between two recorded finite families, not an inference about larger prime sets.

All 248 threshold-20 assignments, all four threshold-24 assignments and both threshold-25 assignments were paged out and retained, 254 selected records in total. They are not a new enumeration of all 510510 vectors. The first threshold-20 assignment has phase 9439; its separate witness query shows actual covered length 21 and first uncovered offset 22.

The large-shift query uses
\[
T=217127+510510\cdot10^{100}.
\]
It preserves the first threshold-25 residue assignment, returns all 25 exact divisor/quotient witnesses, and stops at offset 26. The nonzero remainders of \(T+26\), in modulus order, are
\[
[1,1,3,6,2,1,12].
\]
No primality assertion is made for that first uncovered integer.

### Execution and complete custody

The constructor made 57 gcd divisions, 13 inverse divisions, 716167 marking visits, marked 418350 distinct residues, scanned 510510 positions, and created 92160 gap rows plus 27 profile rows. It enumerated no residue-assignment vectors and performed no prime test.

The period reader made nine queries: summary, source, profile, CRT rows, three slices and two witness classifications. It checked 92160 saved gap relations and 54 saved profile fields, scanned 276480 saved gaps to construct the three slices, and created 104 slice intervals. It made 33 binary comparisons, 116 witness modulus tests, 46 covered witness rows and seven CRT terms. It performed no marking or compiler call.

Fresh slice readers made nine, two and three queries respectively for thresholds 20,24,25, giving 23 actual queries overall. They checked 100/2/2 interval rows and selected 248/4/2 assignments. Their binary comparisons were 1672/6/5; the final reader additionally used seven CRT terms. They made no global-gap scans or marking visits.

Observed construction, saved-period loading and combined query times were 90 ms, 25 ms and 25 ms in one connected V8 session. They are not a repeated benchmark.

The frozen source was banked before computation. The complete constructor packet was checkpointed as `0d9871e212fcbcb675ba4c7cd8b4a6122db6435e`, 825,937 bytes. The final compact JSON packet is `18c48c14b2da0777caed5c8ff7df0d68024867e9`, 861,702 bytes. It retains every survivor/gap/profile/CRT row, every query argument/output, all three complete slice snapshots and all 254 selected assignments. Compact formatting saves space without dropping records.

Only this modulus set and the stated actual queries ran. Other modulus sets, negative shifts, zero-threshold slicing and error branches were source-inspected only. No synthetic suite, native executor, accepted artifact replay, sponsor contact, proof submission or prize claim was used.

## Saved use

This illustrates the interface without another recorded run:

```javascript
const api = require("./residue_covering_index.cjs");
const record = require("./primes_through17.json");
const wheel = api.openRetainedCoveringWheel(record.constructor.snapshot);
const sliceSnapshot = wheel.slice(24);
const slice = api.openRetainedCoverageSlice(sliceSnapshot);
const assignments = slice.page({start: 0, limit: 4});
```

Connected V8 callers may evaluate the same CommonJS source and pass saved objects directly. All returned source/snapshot/statistics objects are outward copies. The module does not perform network or filesystem operations.

This finite phase classification neither improves the published Jacobsthal maximum nor supplies either requested asymptotic estimate for Erdős 687.
