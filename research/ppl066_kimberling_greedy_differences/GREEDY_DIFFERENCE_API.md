# Greedy position and signed-difference continuation

This module continues the canonical Kimberling Rule 1 sequence from an identified accepted prefix. It retains four occupancy bitsets, exact blocking certificates for every new greedy choice, and the complete position/difference history. A saved state supports another append and finite occurrence/unused-value navigation.

One actual continuation consumes the published first 1,000 pairs and adds only indices 1001–1256. A fresh saved-state append adds 1257–1384. All 384 new choices are retained. The mathematical contribution documented here is a direct linear bound that makes the finite bitset universe complete; the finite data do not prove the position/difference permutation assertions or either infinite three-step sign assertion.

## 1. Primary source and canonical convention

[OEIS A131388](https://oeis.org/A131388), credited to Clark Kimberling, defines Rule 1. This API fixes its canonical seed a(1)=1,d(1)=0. At current position x=a(k), let A(k) and D(k) contain all positions and signed differences already used.

First search negative integers h satisfying

\[
1-x<h<0,\qquad h\notin D(k),\qquad x+h\notin A(k).
\]

Choose the greatest eligible h, meaning the one nearest zero. If none exists, choose the least positive h meeting the two unused conditions. Set d(k+1)=h and a(k+1)=x+h, then update both histories. Negative preference is absolute; a smaller positive magnitude cannot override an available negative move.

[OEIS A131389](https://oeis.org/A131389) identifies the corresponding signed-difference sequence. The two linked Kimberling tables give [positions 1–1000](https://oeis.org/A131388/b131388.txt) and [differences 1–1000](https://oeis.org/A131389/b131389.txt), ending at a(1000)=1099,d(1000)=445.

The strict negative boundary allows destinations 2 through x−1. Destination 1 is already visited in this canonical sequence. Consequently, requiring a positive unvisited destination gives the same choices here. This equivalence is not asserted for arbitrary initial seeds.

[Kimberling's section 13](https://faculty.evansville.edu/ck6/integer/unsolved.html) asks whether a(k) visits every positive integer, whether d(k) visits every integer, and whether each positive or negative difference is followed by another of its sign within three steps. The literal negative interval above resolves the positivity ambiguity in the older page. The inspected OEIS entries label the permutation assertions conjectural; no exhaustive current literature-status claim is made.

The published prefix is a mathematical premise. Its 1,000 greedy choices, adjacent-difference equations and earlier sign windows were not regenerated or rechecked by this continuation. Distinctness, bounded integer shape, canonical endpoints and complete source indices are structural input requirements.

## 2. A linear universe bound

For the canonical construction,

\[
a(j)\le 2(j-1)\qquad(j\ge2).
\]

The following counting argument supplies the finite executable universe without an arbitrary search cutoff.

At step k, write x=a(k). Let N_- and N_+ be the numbers of previously used negative and positive differences. Let L_x and U_x be the numbers of visited positions below and above x. Distinctness and the initial zero difference give

\[
N_-+N_+=k-1,\qquad L_x+U_x=k-1.
\]

Suppose no negative move is available and x>1. Every destination in {2,…,x−1} is either already visited or blocked by its negative difference. There are L_x−1 previously visited destinations in this range: the visited position 1 is excluded. Each used negative difference can block at most one destination. Therefore

\[
x-2\le (L_x-1)+N_-,
\qquad\text{so}\qquad x\le L_x+N_-+1.
\]

For a positive move, a candidate h can be forbidden by a previously used positive difference or by a visited position above x. Among the first N_++U_x+1 positive magnitudes, at least one is admissible. The chosen least positive magnitude thus satisfies

\[
h\le N_++U_x+1.
\]

Adding the two inequalities yields

\[
x+h\le N_-+N_++L_x+U_x+2=2k.
\]

At the initial x=1, the first positive move is available within the same bound. The position 1 cannot occur again because destinations are unused. Every later positive move therefore obeys the counting argument. A negative move decreases x, so induction preserves the bound.

This argument uses the canonical seed, distinct histories, exact negative preference and exact least-positive fallback. It is not a proof of eventual visitation: remaining forever inside a linearly growing universe does not imply that each fixed integer is eventually selected.

For a term cap K≥2, all positions through that cap lie in

\[
\{1,\ldots,B\},\qquad B=2(K-1).
\]

Every nonzero difference then has magnitude at most B−1. Searching this universe is exact for the canonical sequence. An empty positive availability mask before reaching K indicates an invalid premise or implementation state, not evidence that the infinite sequence has stopped.

## 3. Four bitsets and shifted destination tests

Bits are indexed by nonnegative integers. The stored bitsets are

\[
P=\sum_{v\in A(k)}2^v,\qquad
Q=\sum_{v\in A(k)}2^{B-v},
\]

\[
D_+=\sum_{\substack{h\in D(k)\\h>0}}2^h,\qquad
D_-=\sum_{\substack{h\in D(k)\\h<0}}2^{-h}.
\]

P is the ordinary position bitmap. Q is its reflection about the fixed universe bound. The two difference bitsets distinguish signs: using −m does not use +m. The initial difference 0 is retained in the history and occurrence map, but it is outside both positive-magnitude bitsets.

Define a finite positive-bit interval mask

\[
M(t)=\sum_{j=1}^{t}2^j=2^{t+1}-2
\]

for t≥1, with M(0)=0.

### Negative moves

At current position x, the bit at magnitude m in

\[
Q\mathbin{\texttt{>>}}(B-x)
\]

is set exactly when x−m has been visited. Right shifting discards positions above x. Restricting to M(max(0,x−2)) excludes the current position and the forbidden destination 1.

The available negative magnitudes are exactly

\[
M(\max(0,x-2))\ \&\
\neg\bigl(D_-\ \vert\ (Q\mathbin{\texttt{>>}}(B-x))\bigr).
\]

The least set bit gives the smallest eligible magnitude m, hence the greatest negative step −m.

### Positive moves

Only if the negative availability mask is empty, compute

\[
M(B-x)\ \&\
\neg\bigl(D_+\ \vert\ (P\mathbin{\texttt{>>}}x)\bigr).
\]

Bit m now tests the unused positive step m and unused destination x+m. The least set bit gives the required least positive step. The linear bound guarantees that a valid canonical continuation has an available positive bit within this finite range.

After choosing y=x+h, insert exactly three bits: y in P, B−y in Q, and |h| in the appropriate signed-difference bitset. No per-step reversal or rebuilding of all previous positions is needed.

All bitsets are BigInts. The finite interval mask controls the unbounded leading ones introduced by a BigInt complement. The operation is exact; no floating-point approximation or probabilistic membership structure is used.

Least-bit selection isolates `mask & -mask` and obtains its bit index from the hexadecimal length and the leading power-of-two nibble. Saved-state query selection instead scans hexadecimal nibbles with a four-bit population table, skipping complete groups by their counts.

The counters record logical shifts, masks, selections and insertions, not CPU instructions. A BigInt operation still depends on its bit length. The cap bounds all stored masks linearly in the maximum term count; the complete history and per-choice certificates add their own output cost.

## 4. Complete blocking certificates

For each greedy search, let t be the largest magnitude whose rejection must be explained:

- if a negative magnitude m is selected, t=m−1;
- if no negative move exists, t=max(0,x−2), the entire negative domain;
- for the selected positive magnitude m, t=m−1.

Let U be the appropriate used-difference bitmap and V the shifted visited-destination bitmap. The producer saves two disjoint masks:

\[
S=U\ \&\ M(t),\qquad
T=V\ \&\ M(t)\ \&\ \neg U.
\]

It requires

\[
S\vert T=M(t).
\]

Thus every earlier candidate is blocked. A bit in S supplies an already used signed difference. A bit in T supplies an already visited destination for a difference not blocked by S. The two masks are serialized as complete canonical hexadecimal strings, without truncation.

The selected difference and destination are separately required to be unused. If the selected step is positive, the complete negative-domain certificate is also retained. These facts establish both negative preference and minimal magnitude in the selected direction.

Each new event contains:

| Field | Meaning |
|---|---|
| `index` | One-based index of the appended term |
| `previous_position`, `difference`, `position` | The actual transition |
| `negative_search` | Selected-negative prefix certificate or complete no-negative certificate |
| `positive_search` | Selected-positive prefix certificate, or null after a negative move |
| `selected_destination_was_unused` | Producer checked the destination bit before insertion |
| `selected_difference_was_unused` | Producer checked the signed-difference bit before insertion |
| `linear_bound` | 2 times the preceding term count |
| `completed_window` | The new four-term sign window, when one has become complete |

A certificate records its search direction, full domain endpoint, covered prefix endpoint, selected magnitude or null, both masks and the full-prefix equality flag.

### Checking against history

An earlier event must be interpreted against the history **before that event**. The final occupancy bitmap contains later insertions and cannot replace the earlier state in a certificate check.

The complete occurrence histories make each bit's witness directly identifiable. For event index i:

- a used-difference bit m requires the occurrence of the appropriate signed difference to have index below i;
- an additional visited-destination bit m requires x−m or x+m to have occurrence index below i;
- the selected difference and selected destination first occur at i.

These checks can consume the recorded mask and occurrence indexes without rerunning the greedy choice algorithm. This artifact does not claim a second independent certificate-verification run; the producer formed the exact mask identities during the new construction.

## 5. Finite sign-window scope

A window beginning at j uses d(j),d(j+1),d(j+2),d(j+3). If d(j)>0, the positive condition asks for at least one positive value at offsets 1, 2 or 3. The negative condition is the analogous statement with negative signs. A zero starting difference is not an instance of either implication.

Appending term i completes only the window starting at i−3. Accordingly, this artifact records windows whose fourth term is new. It does not recheck complete windows lying entirely in the published prefix.

For the actual continuation, new term endpoints 1001–1384 correspond to window starts 998–1381. The final three starts 1382–1384 do not yet have all three future terms. A query for such an incomplete window is explicitly outside the retained completed-window index.

The saved event stores the four signs, initial sign, matching future offsets and the implication's result. Any failure would be retained with its exact starting index. A finite absence of failures does not prove either all-index three-step assertion.

## 6. Public API and state contract

The CommonJS module imports nothing and performs no I/O. It exports:

- `continueGreedyDifferences(request)`;
- `openRetainedGreedyDifferences(snapshot)`;
- `GREEDY_DIFFERENCE_LIMITS`.

### Initial continuation

```javascript
{
  source_id: "identifier-for-new-state",
  seed: {
    source_id: "identifier-for-accepted-canonical-prefix",
    positions: [/* complete a(1)..a(n) */],
    differences: [/* complete d(1)..d(n) */]
  },
  target_size,
  term_cap
}
```

The paired arrays have equal positive length, start at 1 and 0, and contain distinct positive positions and distinct signed differences. Only the initial difference may be zero. The seed must be the indicated canonical Rule 1 prefix; structural checks do not prove that premise.

The constructor builds occupancy masks from those supplied values and adds at least one new term. It does not regenerate the seed's greedy choices or verify every old adjacent-difference equation. The new source identifier must differ from the seed identifier.

A successful result is `{status:"COMPLETE", index}`. A target exceeding the cap returns `ABOVE_TERM_CAP` with a null index. Malformed data or a violated mathematical premise raises an error.

### Saved append

Every data file contains a complete directly loadable `.snapshot`. Open it and append with:

```javascript
const index = openRetainedGreedyDifferences(saved.snapshot);
const result = index.appendThrough({
  target_size: nextSize,
  source_id: "identifier-for-next-state"
});
const next = index.snapshot();
```

The actual 1257–1384 append is already retained in the final data file. Reader-only consumers should open that final snapshot directly.

An append updates the in-memory index, retains source lineage, and adds a segment with its exact new range and counters. It preserves the caller's input snapshot. Query results and exported snapshots are outward copies.

The term cap and reflected-universe bound travel together with the saved state. Changing a cap annotation without rebuilding the reflected representation is not a valid operation. A larger-cap continuation would require a new, explicitly identified initialization from the accepted complete history; that path was not exercised here.

A target below the current size is rejected. An equal target returns `NO_NEW_TERMS`. Term-cap and segment-cap results occur before mutation. If an unexpected arithmetic or invalid-premise exception occurs during an append, no rollback guarantee is made for that in-memory candidate; retain the previous saved snapshot and discard the failed candidate.

### Navigation

| Method | Result |
|---|---|
| `summary()` | Source lineage, size/cap, terminal pair, new-step/window statistics |
| `term(i)` | One retained position/difference pair and its seed/new provenance |
| `pageTerms(i,limit)` | A one-based consecutive term page |
| `eventAt(i)` | Complete certificate for a newly appended term |
| `positionOccurrence(v)` | Retained occurrence index or finite-prefix nonvisitation |
| `differenceOccurrence(h)` | Retained signed occurrence index, including h=0, or finite-prefix nonuse |
| `countUnused(kind,through)` | Number of unused positive magnitudes through a finite ceiling |
| `selectUnused(kind,rank,through)` | Zero-based rank in that finite unused set |
| `rankUnused(kind,value,through)` | Rank of an unused value, or explicit nonmembership |
| `pageUnused(kind,start,limit,through)` | A page of finite unused values |
| `windowAt(j)` | Saved completed window beginning at j, or explicit scope refusal |
| `snapshot()` | Complete state including history, masks, events and segments |
| `work()` | Counters for the current invocation |

The `kind` is `position`, `positive_difference` or `negative_difference`. All unused-set ordering is by increasing **magnitude**. Therefore negative-difference rank order is −1,−2,−3,…, not ordinary increasing order on signed integers. A negative-difference rank query takes the signed negative value.

The `through` argument is an explicit nonnegative magnitude ceiling within the fixed universe. It is at most B for positions and B−1 for differences. A ceiling of zero produces an empty set. Occurrence queries can accept any safe integer in their signed/positive contract; absence still means absence from this finite history, never permanent nonoccurrence.

Indices of terms and windows are one-based. Unused-set ranks and page offsets are zero-based. Out-of-range selection returns `OUT_OF_RANGE`. A used value or incompatible sign returns `NOT_IN_FINITE_UNUSED_INDEX` from the rank method. A window whose endpoint is old or not yet present returns `OUTSIDE_NEW_COMPLETED_WINDOWS`.

## 7. Limits and structural loading

The public maximum is 16,384 terms, with B≤32,766. The actual saved states use term cap 4,096 and B=8,190. Pages contain at most 128 records, at most 32 append segments are retained, and source identifiers contain at most 1,024 characters.

Positions, differences, term indices and counters stay within exact safe-integer Number bounds. BigInts implement bitsets and bit operations. Hexadecimal strings preserve every bit in JSON.

The loader checks paired-history shape, canonical endpoints, uniqueness/range, event identities, certificate-string bounds, window shape and required state dimensions. It parses the four saved occupancy masks and constructs occurrence maps from retained arrays. It does not rebuild occupancy from all positions, compare mirrored and ordinary sets by recomputation, prove the old greedy choices, re-evaluate prior windows or authenticate certificate flags against earlier histories.

In particular, a structural loader's acceptance is not an independent mathematical proof of a supplied snapshot. The source prefix and correctly produced saved state remain identified premises.

The actual canonical prefix, initial continuation, saved append and specified reader queries were exercised. Other prefixes/caps and unexercised error branches are source-inspected only. No synthetic fixture suite or claim of exhaustive behavioral coverage is made.

## 8. Actual data and work

The same executed source serves construction, append and final reader:

`dd665987ccdf33b8a124fb8239dd9aa1cfeff9db`.

There was no post-consumer source edit.

| Quantity | Initial continuation | Saved append only | Final retained new work |
|---|---:|---:|---:|
| New indices | 1001–1256 | 1257–1384 | 1001–1384 |
| New terms | 256 | 128 | 384 |
| Positive new steps | 128 | 64 | 192 |
| Negative new steps | 128 | 64 | 192 |
| Blocking certificates | 384 | 192 | 576 |
| Complete blocker masks | 768 | 384 | 1,152 |
| New completed windows | 256 | 128 | 384 |
| Positive-start windows | 128 | 65 | 193 |
| Negative-start windows | 128 | 63 | 191 |
| Sign-window violations | 0 | 0 | 0 |

The first new transition is 1099−448=651 at index 1001. The saved append begins with 1668−682=986 at index 1257. The final pair is a(1384)=1532,d(1384)=−658.

Among the new values, the maximum position is 2,197, reached at index 1379 by 1538+659. The greatest new step magnitude is 760; the recorded negative step −760 occurs at index 1347. These are finite new-range extrema.

The initial constructor reads 1,000 paired source records, builds occupancy once with 2,999 bit insertions, and indexes 2,000 occurrence references. Its new work performs 256 negative searches, 128 positive searches, 384 destination projections, 256 least-bit selections and 768 new bit insertions. The blocker strings contain 108,375 hexadecimal characters.

The append parses four saved occupancy masks, structurally reads 1,256 history pairs, 256 prior events and 768 certificate masks, and indexes 2,512 occurrence references. It rebuilds zero prior occupancy masks. New work adds 128 steps with 192 destination projections, 128 least-bit selections, 384 insertions and 66,819 blocker hexadecimal characters.

The complete final artifact retains 576 certificates and all 175,194 blocker hexadecimal characters. Every new event has its full position/difference transition and its completed sign window.

Observed time was 6 ms for the initial continuation, 10 ms for saved opening and 2 ms for the append. These are single connected V8 observations, not statistical benchmarks.

### Fresh final reader

One new invocation opens the final snapshot and executes 17 queries. It reports:

- 623 unvisited positions through 2,000;
- 307 unused positive differences through magnitude 1,000;
- 310 unused negative differences through magnitude 1,000;
- least unvisited position 893, with selected and recovered rank 0;
- least unused positive difference 657;
- least unused negative magnitude 526, returned as −526;
- +760 unused within the prefix, while −760 occurs at index 1347;
- position 2,197 at index 1379 and its complete positive-fallback certificate;
- the last newly completed window at start 1381;
- an explicit scope refusal for the incomplete window at start 1382;
- all 384 new position/difference pairs through three pages of 128 terms.

The first unused-position page is

`893, 894, 895, 897, 899, 900, 901, 903, 904, 905, 907, 908, 909, 911, 913, 914`.

These missing values may occur later. The index answers finite-prefix questions only.

The reader structurally loads 1,384 paired records, 384 events and 1,152 certificate masks, parses four saved state masks, and indexes 2,768 occurrence references. Queries inspect 2,508 hexadecimal digits for population counts and 750 for selection, decoding 407 records. They perform zero greedy steps, destination-shift projections, availability-mask constructions, least-bit greedy selections or occupancy rebuilds.

The final open took 15 ms and the query batch 1 ms in this observation. Saved-state reading and structural checks still do work; zero construction counters are not a claim of zero execution cost.

## 9. Files and retained lineage

| File | Purpose |
|---|---|
| `greedy_difference_bitset_index.cjs` | Continuation, saved append and finite navigation |
| `GREEDY_DIFFERENCE_API.md` | Source convention, linear bound, certificates, API and scope |
| `published1000_through1256.json` | Complete initial snapshot and execution receipt |
| `published1000_through1384.json` | Complete final snapshot, append and all reader outputs |
| `README.md` | Entry point and concise results |

The initial data blob is `c69e49a31c055c42166e51d5519f06a5dd05916d`. The final data blob is `261dfae6d26afdd491aba3daf5875cb00fb2d795`. Each file contains a directly loadable `.snapshot` with the complete original prefix and every new term. The final file identifies the initial data and source state as its parent.

This work preserves Kimberling's attribution and the canonical seed. It delivers a complete bounded continuation, exact recorded choices and a reusable saved-state interface. It does not prove either infinite permutation assertion, either all-index three-step assertion, or a new external record.
