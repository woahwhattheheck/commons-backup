# Positive Pell mixed-sum index

This package indexes the established family \(u_i+a u_j\), with both indices positive and integer \(a\ge2\), through one finite numerical cap. It retains the recurrence and one monotone boundary per first index. Count, decode, numeric rank, selection and pages operate on this implicit family without constructing its quadratic pair table.

The one actual Pell input uses \(a=2\) and
\[
B=10^{200}+11053036065048038168742180.
\]
It has **273,005 distinct sums**. The snapshot contains **525 recurrence terms, including a boundary sentinel, and 523 frontier rows**. The saved reader's 14 complete outputs include two selection traces and ten requested sum-page records. No prime test was performed.

The executed source was frozen before the sole construction and remained unchanged for the fresh reader: **Git blob 5ca1c9e99351fd72ebc941eb247d1401266dedf9, 17,092 UTF-8 bytes**.

## Source and scope

Zhi-Wei Sun's [*Mixed sums of primes and other terms*, author preprint v3 (2009)](https://arxiv.org/html/0901.3075v3), Conjecture 1.7, asks whether every integer \(N>5\) is an odd prime plus \(P_s+2P_t\), with \(P_0=0,P_1=1,P_{k+1}=2P_k+P_{k-1}\), and states the stronger version requiring both Pell terms positive.

Theorem 1.9 treats \(u_0=0,u_1=1,u_{k+1}=a u_k+u_{k-1}\), integer \(a>1\). With first index nonnegative and second positive, it gives uniqueness except \(a=2,x=4\), from \((0,2)\) and \((2,1)\). Consequently both-positive indices have no exception. Corollary 1.11 states the Pell specialization; Sun credits Qing-Hu Hou's observation. Equal indices are allowed.

This package adopts **both indices positive**. It does not extend the theorem to a zero weighted index: Remark 1.10 records the recurrence collision in that direction. The coefficient-one and coefficient-\(a\) roles are distinct. These are not unordered pairs.

The uniqueness theorem is an identified prior premise, not a new pair-collision census or a proof audited here. The finite sum index does not establish the conjecture's odd-prime remainder condition, a current literature frontier or a new uniqueness theorem.

## Finite completeness from a linear recurrence prefix

For integer \(a\ge2\), the positive terms increase strictly. Fix a natural-number cap \(B\). A permissible first index satisfies \(u_i+a u_1=u_i+a\le B\), so \(u_i\le B-a\). Retain the sequence through the **first** term exceeding \(B-a\). Let \(K\) be the preceding index. The terms are \(u_0,\ldots,u_{K+1}\), with \(u_{K+1}\) the sentinel.

If \(B<a+1\), the family is empty, \(K=0\), and the two seed terms suffice. Otherwise any permissible second index satisfies
\[
u_j\le (B-1)/a\le B-a,
\]
where the last inequality follows from \(B\ge a+1\). Thus \(j\le K\) as well. No omitted later term can participate.

For each first index \(i=1,\ldots,K\), define
\[
r_i=\max\{j\ge1:u_i+a u_j\le B\}.
\]
The minimum second index is feasible by the definition of \(K\), so \(r_i\ge1\). The row boundaries are nonincreasing. Starting at \(j=K\), one downward pointer finds every \(r_i\), with at most \(K\) decrements in total. The saved row records certify both
\[
u_i+a u_{r_i}\le B,\qquad u_i+a u_{r_i+1}>B.
\]
Together with strict growth, these inequalities establish the full row and its exclusion boundary.

The finite family is exactly
\[
\{(i,j):1\le i\le K,\ 1\le j\le r_i\}.
\]
Its size is \(\sum_i r_i\). Sun's positive-index theorem makes this also the number of **distinct numerical sums**. The constructor does not establish uniqueness by finite collision comparison.

Construction takes \(O(K)\) recurrence/frontier steps and retains \(O(K)\) large integers and rows. Integer sizes remain part of the cost; no constant-cost claim is made for unbounded BigInt arithmetic.

## Counting, decoding and ranking

All ranks are zero-based in increasing numerical sum. They are not lexicographic pair ranks.

For \(x\le B\), a downward second-index pointer counts the sums at most \(x\). As the first index increases, the largest feasible second index cannot increase. This requires at most \(K\) first-index visits and \(K\) downward movements. At the compiled cap, counting returns the saved total.

An inclusive interval \([l,u]\) contains \(C(u)-C(l-1)\) sums, with \(C(-1)=0\). The rank of a supplied permissible pair is \(C(u_i+a u_j-1)\).

To decode a target, start at \((i,j)=(1,K)\). If the sum is too small, increase \(i\); if too large, decrease \(j\). Strict row and column increase justifies the discarded region each time. The path has at most \(2K\) steps and returns the unique pair or an explicit negative result. This is membership in the mixed-sum family, not a prime-plus-mixed-sum test.

## Selection by weighted row pivots

Numeric selection avoids both a complete pair table and bisection through every bit of a huge numerical range.

Maintain a contiguous active interval \([\ell_i,h_i]\) in each row, local rank \(q\), and remaining entry count \(W\). Initially these are the full frontier rows, requested rank and total.

For each nonempty row, take its lower middle index and corresponding sum. Weight that middle value by the active row length. Sort the middle values and choose the first whose accumulated weight is at least \(W/2\).

Rows with middle value at most the pivot carry at least half the total weight. Each contributes at least half its entries at most its middle. Thus at least \(W/4\) entries are at most the pivot. The symmetric argument for rows with middle value at least the pivot shows that at least \(W/4\) entries are at least the pivot.

Per-row binary searches obtain the counts strictly below and at most the pivot. Positive-sum injectivity makes these counts differ by one. The implementation checks this difference at every selected pivot; these local checks are not a new proof of global uniqueness.

- If \(q\) is below the strict count, retain only entries below the pivot.
- If \(q\) is at least the inclusive count, retain entries above the pivot and subtract that count from \(q\).
- Otherwise return the pivot.

Every nonterminal round removes at least a quarter of the entries. The invariant preserves exactly the requested rank in the surviving row intervals, so the returned numerical rank is exact.

With \(K\) rows and \(R\) sums, this direct implementation uses \(O(K\log K\log(R+1))\) comparisons/binary-search work and \(O(K)\) working row storage, apart from a requested trace. BigInt costs remain explicit. A trace retains round totals, local ranks, full pivot value and indices, strict/inclusive counts and branch decision; it does not save every transient row interval.

The term limit gives \(K\le4094\) and \(R<2^{24}\). Quarter removal makes the hard cap of 128 rounds ample. A caller may lower it deliberately, producing an explicit incomplete query rather than an invented selection.

## Sorted pages

A page first selects its starting rank, then binary-searches each row for the first entry at least that anchor value. These row heads initialize a min-heap. Remove the least head and advance only its row.

The heap always contains the least unreported eligible member of every nonempty row, so its least element is the next global sum. Sun's theorem excludes equal keys; a deterministic row tie-break in the implementation does not quotient or add multiplicity.

Only requested page records are created. A caller could eventually page the entire family. The claim is that this constructor and recorded consumer did not materialize its full table.

## Public interface

The plain CJS file exports **PELL_SUM_LIMITS**, **compilePositiveMixedSums(input)** and **openRetainedPositiveMixedSums(snapshotOrJSONString)**. It has no imports, filesystem/network calls or native dependency.

### Constructor

| Input | Contract |
| --- | --- |
| parameter | Safe integer Number from 2 through 1,000,000 |
| cap | Nonnegative BigInt, safe integer Number, or canonical decimal string |
| provenance | JSON object, or JSON text encoding an object |
| max_terms | Optional Number from 2 through 4096, lowering the term budget |

Provenance is copied and retained, not authenticated. Canonical decimal strings have no sign, whitespace or leading zeros except "0". Negative values and unsafe Numbers fail.

| Hard limit | Value |
| --- | ---: |
| Parameter | 1,000,000 |
| Cap/query decimal digits | 1,000 |
| Saved term decimal digits | 1,008 |
| Terms, including seeds and sentinel | 4,096 |
| Compact snapshot characters | 2,000,000 |
| Provenance characters | 32,768 |
| Page records | 1–128 |
| Selection rounds | 128 |

The larger saved-term allowance accommodates the excluded sentinel, which can exceed the cap by a parameter-related factor. Given the parameter and target limits, 1,008 digits suffice; the target/query allowance remains 1,000.

A complete result has status **EXACT_POSITIVE_MIXED_SUM_INDEX**, with snapshot, summary, work and snapshot_chars. Its schema is **commons.sun_positive_mixed_sum_index/v1**.

A term-budget or snapshot-character stop returns **INCOMPLETE_BUDGET**, a reason, actual work and snapshot:null. Already-performed work is retained honestly. Invalid types/ranges throw; malformed JSON may raise a standard error. A resource refusal is not mathematical nonrepresentability.

### Saved reader

| Method | Result |
| --- | --- |
| summary() | Complete cap/count/boundary summary |
| source() | Detached provenance |
| termPage(options) | Saved indexed recurrence terms |
| frontierPage(options) | Saved boundaries and exclusion sums |
| countAtMost(x) | Count through x |
| countInterval(lower,upper) | Inclusive interval count |
| decode(sum) | Unique pair or represented:false |
| rank(firstIndex,secondIndex) | Numeric rank of a permissible pair |
| select(rank,options) | Sum/pair at rank, optional trace |
| page(options) | Consecutive sums from rank |
| snapshot() | Detached complete snapshot |
| statistics() | Detached counters |

Query bounds and decoded sums must be between zero and the compiled cap. Above-cap queries and reversed intervals fail. Pair indices must be Numbers inside the saved frontier.

Selection ranks are canonical natural inputs strictly below the total. Returned ranks, counts and large values are decimal strings; indices and bounded record counts are Numbers.

Selection options are **{trace, max_rounds}**. Trace must be boolean if supplied. max_rounds is a Number from 0 through 128. A lower-round stop returns **INCOMPLETE_QUERY**, reason, original rank, remaining count, local rank and completed rounds, plus a requested trace. It is not a successful selection.

Page options are **{start,limit}**, defaulting to zero and 128. Sum-page start is a rank; term/frontier start is a zero-based array position. Start equal to size gives an empty final page; larger starts fail. A successful page returns total, count, complete records and next cursor or final null.

The reader copies input, returns detached records and freezes the API object. External provenance cannot replace the stated mathematical hypotheses.

## Loader checks and work accounting

The loader checks both seeds, all saved recurrence equations, the first excluded term and preceding boundary, every row's index/nonincreasing endpoint/count, its inclusive/exclusive sums, summary totals and conventions.

These are real arithmetic checks on saved records. The reader does not call the constructor or append/rebuild the recurrence/frontier. It indexes the saved values and endpoints. The source theorem is not mechanically certified by this step.

**pair_records_created** includes internal page anchor selections even when not separately returned. **page_rows_returned** includes term/frontier pages. Both differ from **complete_pair_tables_materialized**.

The constructor's pairs_enumerated concerns construction of the whole family table. Query rows do not retroactively alter it. Zero full-table enumeration does not mean zero pair-valued outputs.

## Actual finite consumer

The smaller cap summand is the retained snapshot.target from Commons #31491:

- path research/ppl098_erdos66_digital_basis/repeated210_14.json;
- commit 806f8523a04e70b56b750905e86ec149fc032bd4;
- blob 9a18698d7765ad36d495f9b914f73c9661a9832b;
- value 11053036065048038168742180.

It only chooses the new cap; no digital-basis calculation was repeated.

Terms \(P_0,\ldots,P_{524}\) are retained, with \(P_{524}\) the first excluded first-coordinate term. The rows satisfy
\[
r_1=\cdots=r_{522}=522,\quad r_{523}=521.
\]
Hence the exact count is \(522^2+521=273005\). The maximum is at pair \((523,521)\); the minimum is \(P_1+2P_1=3\).

All complete term, frontier and exclusion values are retained as decimals in [pell_cap200.json](pell_cap200.json). The compact snapshot has 343,142 characters. Construction used 523 recurrence steps, 523 frontier rows and two pointer decrements, with no pair table or primality tests.

The complete initial packet was immediately checkpointed as Git blob **b04462cf7b16d09a54fae63ae932c0ca0935e2ee**, 419,729 bytes. The final 14-query packet was checkpointed as **a54d8385fc3916f35ac3917739c9a5831b1d4e43**, 470,744 bytes, before guide composition. The committed source/data are the publication; these checkpoints preserve the once-only execution lineage.

### Fresh-reader results

| Query | Exact result |
| --- | --- |
| Summary and provenance | Both full records |
| Last eight terms | Indices 517–524, including sentinel |
| Last five frontier rows | First indices 519–523 |
| Count through \(10^{100}\) | 68,381 |
| Count in \([10^{199},B]\) | 2,089 |
| Select rank 136502 | Pair (370,343), 17 rounds, full trace |
| Select rank 273004 | Pair (523,521), 21 rounds, full trace |
| Rank pair (14,521) | 270933 |
| Decode \(P_{523}\) | Pair (521,522) |
| Decode B | Not a positive mixed sum |
| Five sums from rank 136500 | Ranks 136500–136504, next 136505 |
| Last five sums | Ranks 273000–273004, final cursor null |
| Decode smaller cap summand | Not a positive mixed sum |

Summary/provenance are two queries, giving **14** in total. Negative decoding concerns pure mixed sums only; it does not make either number a counterexample to the odd-prime conjecture.

Every complete output and all 38 explicit selection-trace rows are retained. Page operations also select internal anchors; all explicit/internal selections total 75 rounds.

Loading made two seed checks, 523 recurrence checks, one excluded-boundary check and 523 frontier checks, indexing 525 terms and 523 rows. Query work records 1,307 count-row steps, 1,569 downward count movements, 1,636 decode steps, 20,017 row midpoints, 21,990 midpoint-sort comparisons, 109,604 binary comparisons and 669 heap comparisons. The two heaps initially contained 525 row heads in total.

The 23 page rows comprise eight terms, five frontier rows and ten sums. Sixteen pair records were created: two explicit selections, two internal anchors, ten paged pairs, one rank output and one successful decode. Constructor calls, new recurrence terms, rebuilt frontier rows, complete pair tables and prime tests were all zero in the reader.

Observed times were 20 ms for construction, 15 ms for loading and 36 ms for queries: single observations, not benchmarks. Only this cap and these queries ran. Other parameters, small/empty caps, lower-budget refusals and page endpoints were source-inspected. There was no synthetic suite or accepted earlier input replay.

## Connected use

With full source and JSON texts supplied:

~~~js
const module = {exports: {}};
new Function("module", "exports", moduleText)(module, module.exports);
const record = JSON.parse(dataText);
const index = module.exports.openRetainedPositiveMixedSums(record.snapshot);

const selected = index.select("136502", {trace: true});
const upperSlice = index.countInterval(
  (10n ** 199n).toString(),
  record.snapshot.cap
);
// selected.first_index === 370
// selected.second_index === 343
// upperSlice.count === "2089"
~~~

These are documented successful operations, not repetitions made while composing this guide.

This is an exact finite index for Sun's established positive mixed-sum family. The prime-remainder condition, unrestricted universal conjecture, current external status and any prize process remain separate.
