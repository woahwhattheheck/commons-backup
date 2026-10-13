# Exact representations in the Raikov–Stöhr digital basis

This module counts and navigates every representation of a fixed natural-number target in one classical infinite additive basis. It retains a small collection of disjoint binary subcubes instead of a table of all pairs. Ordered convolution counts and unordered pairs with first coordinate at most second coordinate are explicit, separate views.

The one actual target is
\[
n=11053036065048038168742180
  =(\underbrace{210\,210\,\cdots\,210}_{14\text{ blocks}})_4.
\]
It has **32,770 ordered representations and 16,385 unordered representations**, with **no diagonal**. Four ordered and three unordered cubes describe the entire family. The complete artifact includes all 84 digit records, all seven cubes and every output from a fresh 14-query reader session, including an 84-step rank-selection trace.

The source is a plain CJS module with no imports or I/O. It was frozen before the sole compilation and remained unchanged for the fresh reader:
**Git blob `2fd98cb50d393fabfe3450791b52b49667c69d36`, 20,986 UTF-8 bytes**.

## Source and question conventions

Melvyn B. Nathanson's author paper, [“Shatrovskiĭ's construction of thin bases”](https://arxiv.org/pdf/0906.1241), §1, printed pages 1–2, credits Raikov and Stöhr independently in 1937 for the binary-position construction. Its basis convention uses nonnegative integers and exactly \(h\) summands, not necessarily distinct. The bibliography identifies D. Raikov, *Über die Basen der natürlichen Zahlenreihe*, Mat. Sbornik N.S. 2(44) (1937), 595–597, and A. Stöhr, *Eine Basis h-Ordnung für die Menge aller natürlichen Zahlen*, Math. Z. 42 (1937), 739–743. The accessible author restatement was inspected; the original 1937 scans were not newly read.

For \(h=2\), let
\[
A_0=\left\{\sum_{j\ge0}\varepsilon_j4^j:
 \varepsilon_j\in\{0,1\},\ \text{finitely many }\varepsilon_j\ne0\right\},
\quad A_1=2A_0,\quad A=A_0\cup A_1.
\]
These are the even and odd binary-position sets. Both contain zero, but the union contains **one zero**, not two labelled copies. Their intersection is exactly \(\{0\}\). Repeated summands are allowed.

The complete [Formal Conjectures Erdős 66 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/66.lean), blob `d68ee31ee97433f585a3f3ef22a51c6f397826e6`, asks whether some set \(B\subseteq\mathbb N\) has a finite nonzero limit of
\[
\frac{(1_B*1_B)(n)}{\log n}.
\]
The [pinned convolution definition](https://github.com/google-deepmind/formal-conjectures/blob/89294ea02bd7cd678d59984add52cb4baef3dbf4/FormalConjecturesForMathlib/Combinatorics/Additive/Convolution.lean), blob `cb534ea66bd32dca892aa972e72b1bea83e58554`, sums over natural-number pairs on the antidiagonal. Thus the question's representation count is **ordered**, includes zero when it belongs to the set, and includes diagonal pairs.

The observed formal statement has a research-open annotation. The canonical website returned 403 once and was left held; no complete current literature survey or stronger status claim is made. The result here concerns the explicit classical \(A\), not all possible choices of \(B\), and does not settle the question.

## Exact representation formula

Write \(R(n)=|\{(a,b)\in A^2:a+b=n\}|\).

### Homogeneous pairs

Let the base-4 digits of \(n\) be \(d_j\). A pair \(a,b\in A_0\) has each operand digit in \(\{0,1\}\). Their digit sum is at most two, so **there are no carries**.

- A target digit 0 forces operand digits \((0,0)\).
- A target digit 1 allows \((0,1)\) or \((1,0)\).
- A target digit 2 forces \((1,1)\).
- A target digit 3 makes such a pair impossible.

Consequently, if \(s(n)\) counts the digits equal to one,
\[
C_0(n)=|\{(a,b)\in A_0^2:a+b=n\}|=
\begin{cases}
2^{s(n)},&\text{if every base-4 digit is at most 2},\\
0,&\text{otherwise}.
\end{cases}
\]
The \(A_1+A_1\) count is
\[
C_1(n)=
\begin{cases}
C_0(n/2),&2\mid n,\\
0,&2\nmid n.
\end{cases}
\]

For an admissible \(A_0+A_0\) target, the first coordinate has the form
\[
a=F+\sum_{j:d_j=1}\eta_j4^j,\qquad
F=\sum_{j:d_j=2}4^j,\quad \eta_j\in\{0,1\}.
\]
The second coordinate is \(n-a\). Thus its first coordinates form one binary subcube with fixed-one mask \(F\) and free bits at positions \(2j\) where \(d_j=1\). For \(A_1+A_1\), apply the same construction to \(n/2\), then multiply the first-coordinate masks by two; its free bits occupy odd positions.

### Mixed pairs and duplicate removal

Every \(n\) has a unique binary split \(n=e+o\), where \(e\in A_0\) uses its even binary positions and \(o\in A_1\) uses the odd ones. This is the classical basis argument.

For \(n>0\), the homogeneous pair families are disjoint: a pair belonging to both would have each coordinate in \(A_0\cap A_1=\{0\}\), forcing \(n=0\).

If both \(e,o\) are positive, the mixed ordered pairs \((e,o)\) and \((o,e)\) are distinct and lie in neither homogeneous family. They become two singleton cubes. If one split part is zero, the mixed pairs are already homogeneous pairs involving zero and are omitted. For \(n=0\), the implementation uses the single pair \((0,0)\) once.

Let \(I_i(n)\) be the indicator that \(n\in A_i\). Equivalently \(I_0(n)=1\) when \(o=0\), and \(I_1(n)=1\) when \(e=0\). The exact ordered formula, including zero, is
\[
\boxed{R(n)=C_0(n)+C_1(n)+2-2I_0(n)-2I_1(n)+[n=0].}
\]
One derivation is to expand \(1_A=1_{A_0}+1_{A_1}-1_{\{0\}}\), using the unique \(A_0+A_1\) split. The disjoint-family construction above gives the same formula without counting a representation twice. At zero it gives \(1+1+2-2-2+1=1\).

### Unordered pairs and diagonals

An unordered representation is displayed as \((a,b)\) with \(a\le b\), including equality. This is an API convention separate from the problem's ordered convolution.

For a homogeneous cube with \(k>0\) free bits, swapping \(a,b\) complements all \(k\) free choices. The largest free weight exceeds the sum of all smaller free weights. Therefore \(a<b\) holds exactly when the highest free bit of \(a\) is zero. Remove that free position from the cube; exactly \(2^{k-1}\) pairs remain.

If \(k=0\), the one homogeneous pair is diagonal and remains. Positive mixed pairs give one sorted singleton. The zero case still gives \((0,0)\). There are at most three unordered cubes, compared with at most four ordered cubes.

With
\[
\delta(n)=[2\mid n\text{ and }n/2\in A],
\]
the counts satisfy
\[
U(n)=\frac{R(n)+\delta(n)}2.
\]
The constructor and saved loader both check this identity. Internal branch labels never create multiplicity for a pair.

## Why this family does not settle Erdős 66

The formula gives an elementary exact oscillation description for this particular classical basis. For \(m\ge1\),
\[
R(4^m-1)=2:
\]
the base-4 digits are all 3, the target is odd, and both binary split parts are positive. Also
\[
R((4^m-1)/3)=2^m:
\]
the base-4 digits are all 1, the target is odd and lies in \(A_0\). It follows, along these two subsequences as \(m\to\infty\), that
\[
\liminf_{n\to\infty}\frac{R(n)}{\log n}=0,
\qquad
\limsup_{n\to\infty}\frac{R(n)}{\log n}=\infty.
\]
Nonnegativity gives the first lower bound; the second subsequence grows exponentially in \(m\) while its logarithmic denominator grows linearly. These are deductions from the displayed formula, not additional executed target samples or a novelty claim. They rule out this \(A\) as a witness to the proposed finite nonzero limit, not every possible basis.

## Numeric ordering without pair enumeration

For a fixed target, the second coordinate is determined by the first. Both API modes therefore use **increasing numerical first coordinate**, giving a total order on the complete represented family.

A cube is stored by a fixed-one mask, a disjoint free mask, sorted free positions and its cardinality. All remaining bits are fixed zero. Distinct cubes have conflicting fixed bits outside their free masks; the saved loader checks this pairwise.

To count a prefix, process bits from most significant to least significant while retaining compatible cubes. For bit \(j\), a compatible cube contributes \(2^f\) completions to the zero branch if its bit is free or fixed zero, where \(f\) is its number of free positions below \(j\). A fixed-one bit contributes none to that branch.

For selection, sum those zero-branch counts. A rank below that sum follows zero; otherwise subtract the sum and follow one. Discard incompatible cubes at each step. At the end, one cube and one first coordinate remain. For ranking, follow the candidate's bits, adding the zero-branch count whenever its bit is one. A path with no compatible cube is not represented.

Inclusive prefix counts follow the same bit decisions and include the surviving endpoint if present. Interval counts are the difference of two prefix counts, with the lower endpoint minus one handled internally. This algorithm counts a union of disjoint cubes; it is not a search over the integers between the endpoints.

Per operation there are at most four active cubes and \(L\) target bits. Thus there are \(O(L)\) prefix steps at bounded cube count. BigInt operation costs still depend on bit length. No bit-length-independent constant-time claim is made.

## Public interface

Exports:

- `DIGITAL_BASIS_LIMITS`;
- `compileDigitalBasisTarget(input)`;
- `openRetainedDigitalBasisTarget(snapshotOrJSONString)`.

The module uses no external libraries, native processes, filesystem or network calls.

### Constructor

Supply exactly one of:

- `target`: a safe integer Number, nonnegative BigInt or bounded canonical decimal string;
- `target_base4`: a canonical base-4 string with no leading zero except the string `"0"`.

Also supply `provenance` as a JSON object or JSON text encoding an object. It is copied and retained, not independently authenticated by the module. Optional `max_bits` and `max_digit_records` lower the corresponding hard budgets and may be zero.

| Limit | Value |
| --- | ---: |
| Target bits | 2,048 |
| Base-4 input digits | 1,024 |
| Decimal-string digits | 650 |
| Saved digit records | 2,048 |
| Provenance characters | 32,768 |
| Compact snapshot characters | 250,000 |
| Page records | 1–128 |

All numeric arguments must be nonnegative; Numbers must be safe integers. Decimal strings have no signs or leading zeros. Query numeric inputs retain the target-bit hard cap. Reversed interval bounds, invalid mode names and out-of-range selection ranks are rejected.

The target is parsed before resource preflight. If a caller's lower bit/digit budget is insufficient, the result is `INCOMPLETE_BUDGET` with no snapshot, before digit classification. Parsing work can already have occurred and is recorded. The final snapshot-character limit can also return an incomplete result. Other structural/range violations throw; JSON failures may be standard JavaScript errors.

A complete result has status `EXACT_REPRESENTATION_INDEX`, schema `commons.raikov_stohr_target/v1`, and fields `snapshot`, `summary`, `work` and `snapshot_chars`. The snapshot contains both component digit descriptors, the unique binary split, complete ordered/unordered cubes, counts, conventions and provenance. Every valid natural target is represented by the classical basis; a budget refusal is an implementation stop, not mathematical nonrepresentability.

The digit ledger for component 0 describes \(n\). Component 1 describes \(n/2\) when \(n\) is even. An odd target has an explicitly inapplicable component-1 descriptor. Zero has one zero digit in each descriptor and a single pair cube in each mode.

### Saved reader

Open the complete `snapshot` object, or its JSON text. The reader copies its input, returns detached outputs and freezes its API. Mode is exactly `"ordered"` or `"unordered"`.

| Method | Contract |
| --- | --- |
| `summary()` | Complete target/count summary |
| `source()` | Retained provenance |
| `count(mode)` | Exact total as a decimal string |
| `digitPage(component,options)` | Saved component 0 or 1 digit rows |
| `familyPage(mode,options)` | Saved cube records |
| `select(mode,rank,{trace?})` | Pair at a zero-based numeric-first-coordinate rank |
| `rank(mode,first)` | Rank of a represented first coordinate; second is inferred |
| `locatePair(mode,first,second)` | Membership/rank, or explicit wrong-sum, order or outside-basis result |
| `countAtMost(mode,first)` | Inclusive first-coordinate prefix count |
| `countInterval(mode,lower,upper)` | Inclusive first-coordinate interval count |
| `page(mode,options)` | Consecutive represented pairs in the declared order |
| `snapshot()` | Detached complete snapshot |
| `statistics()` | Detached load/index/query counters |

`select` accepts only optional boolean `trace`. With trace true, it returns every bit decision, rank before/after, zero-branch count and compatible family IDs. The trace has exactly the target bit length.

`rank` requires a represented first coordinate; it throws otherwise. `locatePair` instead reports `represented:false` for well-formed natural inputs with a wrong sum, noncanonical unordered order or a pair outside the basis. This distinction lets callers ask membership questions without interpreting a failed rank as a number.

Page options are `{start,limit}`. Defaults are zero and 128. Start equal to family size yields an empty final page; a larger start is rejected. Pages return decimal `start`/`total`, numeric `count`, complete records and decimal `next_start` or final `null`. Large coordinates, ranks and counts are decimal strings in output.

### Loader checks and work accounting

The loader checks every saved digit against its target, its fixed/free masks and component count; checks the binary split; checks every expected cube's identity, masks, cardinality and unordered restriction; and checks pairwise cube disjointness. It then checks the ordered formula and ordered/unordered/diagonal identities.

These are real arithmetic checks. The reader does not call the constructor or classify a new target, but it validates the stored arithmetic. It builds bit-type/lower-free-count indexes and a small power-of-two cache for queries. Bibliography, external problem status and source Git identities remain provenance claims outside this arithmetic validation.

The counter `represented_pairs_enumerated` refers to constructing a complete representation table. It does not count pair records returned by selection or pages. Requested page records are generated, and a caller could eventually page an entire family. The actual session below emitted 12 selection/page pair records and one rank answer describing a pair; this is explicitly separate from zero full-table construction.

## Actual input and complete artifact

The repetition parameter 14 comes solely from the released Singer artifact's field `snapshot.summary.difference_set_size`:

- path `research/ppl088_erdos30_singer_plane/prime13_singer_plane.json`;
- commit `8a113ba792d9a9d674a5d8b0af7f78c079f846c7`;
- blob `5561a91eddf8cfd7911641702b60cd51e308078d`.

The complete identified file was read as an input premise. Its field, trace, Sidon and plane computations were not repeated. The parameter has no asserted mathematical connection with the digital basis.

Both homogeneous components have 14 free positions, so each has 16,384 ordered representations and 8,192 unordered ones. Both binary split parts are positive, adding two ordered mixed pairs or one unordered mixed pair. No component is diagonal.

| Family | Fixed first coordinate | Ordered free positions | Ordered count |
| --- | --- | --- | ---: |
| \(A_0+A_0\) | 4912460473354683630552080 | 2, 8, 14, 20, 26, 32, 38, 44, 50, 56, 62, 68, 74, 80 | 16,384 |
| \(A_1+A_1\) | 614057559169335453819010 | 5, 11, 17, 23, 29, 35, 41, 47, 53, 59, 65, 71, 77, 83 | 16,384 |
| \(A_0+A_1\) | 1228115118338670907638020 | None | 1 |
| \(A_1+A_0\) | 9824920946709367261104160 | None | 1 |

Unordered homogeneous cubes omit their respective highest free positions, 80 and 83. The unordered mixed cube uses the smaller first coordinate. The complete masks and all digit rows are in [repeated210_14.json](repeated210_14.json), not merely in this table.

Compilation parsed 42 base-4 input digits, produced 84 descriptor rows and read 42 split digits. It constructed four ordered and three unordered cubes, with no basis-element enumeration, complete pair-table enumeration or target sweep. The compact snapshot has 9,292 characters.

Source and the complete first run packet were checkpointed as native Git blob objects before further prose. The initial packet is `2c5368347c60fc807a38d73056d44a2091d1e136`, 22,325 bytes. After the fresh reader, the complete packet was checkpointed as `34f8aff04b4b931acd5621ac6c70d5b45984bb05`, 69,225 bytes. The published final record adds only counter-semantics clarification and this lineage; no mathematical result or executed source changed. These intermediate blobs are checkpoints, while the committed files are the durable publication.

### Saved-reader results

A fresh connected runtime opened the saved snapshot once and made 14 queries. It exported all 84 digit records and seven cube records, plus ten requested pair-page rows: 101 page rows in total.

| Operation | Exact result |
| --- | --- |
| Ordered select, rank 14 | (614057559169335462340738, 10438978505878702706401442), family \(A_1+A_1\) |
| Unordered select, rank 8192 | (1228115118338670907638020, 9824920946709367261104160), mixed family; all 84 prefix decisions retained |
| Ordered rank of first coordinate 9824920946709367261104160 | 24577, reverse mixed pair |
| Test pair \((n/2,n/2)\) | Not represented: outside the basis |
| Ordered first-coordinate interval between the two split parts, inclusive | 16,386 pairs |
| Unordered first coordinates at most the smaller split part | 8,193 pairs |

The ordered page beginning at rank 8190 crosses from the last two members of the lower \(A_1+A_1\) block through the mixed pair at rank 8192 to the first two \(A_0+A_0\) pairs. The unordered page beginning at rank 16380 contains the last five pairs and returns a null next cursor. Every complete output, including all 84 selection-trace rows, is retained.

Reader validation recorded 84 digit checks, two descriptor checks, 42 split-digit checks, seven cube checks, nine disjointness checks and three count-identity checks. Its navigation index contains 588 bit rows and 15 power entries. The query session used 1,008 selection-bit steps, 89 rank-bit steps and 250 prefix-count steps. Constructor invocation, descriptor construction, cube-family construction, basis enumeration and target-sweep counters remained zero; the saved checks and emitted pair records above remain explicit.

Observed timings were 1 ms for compilation, 1 ms to open the reader and 5 ms for the queries. They are single observations, not benchmarks. Only this target and these queries were executed. Zero/odd targets, other bounds, alternate input encoding and refusals were source-inspected; no synthetic suite or accepted earlier computation was run.

## Connected use

With complete source and JSON texts already supplied by the caller:

```js
const module = {exports: {}};
new Function("module", "exports", moduleText)(module, module.exports);
const record = JSON.parse(dataText);
const index = module.exports.openRetainedDigitalBasisTarget(record.snapshot);

const pair = index.select("unordered", "8192", {trace: true});
const count = index.countInterval(
  "ordered",
  "1228115118338670907638020",
  "9824920946709367261104160"
);
// pair.first = "1228115118338670907638020"
// pair.second = "9824920946709367261104160"
// count.count = "16386"
```

These are recorded successful queries; the guide did not execute them again. The source and data can be consumed in plain connected V8 without a local repository checkout, package installation or native process.

The module's fixed-target result is exhaustive for the stated infinite basis. Its analytical family description does not imply a new construction, a general logarithmic limit theorem, an extremal record or a resolution of Erdős 66.
