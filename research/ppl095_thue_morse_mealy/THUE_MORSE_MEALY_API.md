# Thue–Morse outputs of all binary two-state Mealy machines

## Outcome

The complete family of **256 labelled binary two-state letter-to-letter transducers**, with initial state 0 and no initial output, produces exactly **104 distinct infinite output streams** when fed the Thue–Morse stream.

This is equality of entire streams, including their initial symbols. It is not a comparison of finite prefixes, identification up to graph isomorphism, or classification of finite-state transduction degrees.

The one atlas compilation used 16 shared transition-table kernels, containing 143 states in total. The largest kernel has 17 states. Each of the 104 output classes has a canonical minimal deterministic finite automaton with output (DFAO) reading the binary digits of an index; the largest such DFAO has nine states.

The complete certificate retains:

| Retained object | Count |
| --- | ---: |
| Labelled transition tables | 16 |
| Output tables for each transition table | 16 |
| Complete machine tables | 256 |
| Infinite output classes | 104 |
| Shared kernel states | 143 |
| Shared kernel edges | 286 |
| Machine-to-minimal-DFA quotient-map entries | 2,288 |
| State-pair distinguishing words for the minimal DFAs | 1,650 |
| Total states across the 104 minimal output DFAs | 598 |

The class-size distribution is:

| Machines with exactly the same infinite output | Number of classes |
| ---: | ---: |
| 1 | 84 |
| 2 | 8 |
| 4 | 4 |
| 5 | 4 |
| 30 | 4 |

The four 30-machine classes are the constant-zero stream, the complement of Thue–Morse, Thue–Morse itself, and the constant-one stream, in class order 0, 1, 2 and 3.

## Sources and scope

Shallit's [official problem slides](https://cs.uwaterloo.ca/~shallit/Talks/bc4.pdf), printed slides 36–37, ask whether the Thue–Morse word is prime under finite-state transduction: every infinite transduct should be ultimately periodic or mutually transducible with the original word. The [current author talks page](https://cs.uwaterloo.ca/~shallit/talks.html) supplied no Problem 11 resolution update in this bounded source check. This is not an exhaustive current-status assessment.

Endrullis, Grabmayer, Hendriks and Zantema, [*The Degree of Squares is an Atom (Extended Version)*](https://arxiv.org/pdf/1506.00884), June 2015, §3, use complete deterministic sequential transducers whose transitions may output arbitrary finite binary words, including the empty word. Their degrees concern infinite streams, and their nonzero-atom convention excludes the ultimately periodic bottom degree. The paper's mutual-transduction example for Thue–Morse and period doubling is established prior context.

The present family has a fixed state bound and emits exactly one bit per input bit. Its 104 classes concern **exact output equality within that finite family**. They are not transduction degrees. The calculation neither searches every reverse transducer nor classifies ultimate periodicity or unrestricted primeness. It makes no current global-resolution, external-frontier, prize or novelty claim.

## Two different automata

The input stream is \(T=t_0t_1\cdots\), the fixed point starting in 0 of

\[
\mu(0)=01,\qquad \mu(1)=10.
\]

Equivalently, \(t_n\) is the parity of the binary digit sum of \(n\). Indexing starts at zero.

| Machine | Input | Output |
| --- | --- | --- |
| Original Mealy transducer | Successive stream symbols \(t_0,t_1,\ldots\) | One output bit per stream symbol |
| Retained index DFAO | Binary digits of one integer \(n\), least significant first | The single output bit at position \(n\) |

The original transducer has two labelled states. Its index DFAO may have more states. The latter provides random access to the former's infinite output; it is not a proposed reverse transducer or a change in the original machine's state bound.

An original machine is \((Q,0,\delta,\lambda)\), with \(Q=\{0,1\}\),

\[
\delta:Q\times\{0,1\}\to Q,\qquad
\lambda:Q\times\{0,1\}\to\{0,1\}.
\]

If \(q_n\) is the state before reading \(t_n\), then

\[
q_0=0,\quad q_{n+1}=\delta(q_n,t_n),\quad
y_n=\lambda(q_n,t_n).
\]

Unreachable states and their table entries remain part of the labelled enumeration. Different machine tables can therefore belong to the same infinite-output class.

## A finite kernel for every index

The following derivation applies to a finite state set of size \(q\); the executable family is capped at \(q\le2\).

Write \(\delta_a\) for the function \(s\mapsto\delta(s,a)\). Function composition \(f\circ g\) means apply \(g\) first and \(f\) afterward. Let \(F_a(k)\) be the transition function obtained by reading the entire block \(\mu^k(a)\). Since

\[
\mu^{k+1}(a)=\mu^k(a)\,\mu^k(1-a),
\]

we have

\[
F_a(k+1)=F_{1-a}(k)\circ F_a(k).
\]

Suppose the lowest \(k\) binary digits of the queried index have been read, and let their value be \(n<2^k\). Let \(G_a(k,n)\) be the transition function for the first \(n\) symbols of \(\mu^k(a)\). Store both full-block functions \(F_0,F_1\), both prefix functions \(G_0,G_1\), and the digit-sum parity \(p\).

The initial state, before any index digit, is

\[
(F_0,F_1,G_0,G_1,p)
=(\delta_0,\delta_1,\operatorname{id},\operatorname{id},0).
\]

On reading the next, higher binary digit \(b\), the new prefix length is \(n+b2^k\). Both full-block functions update by the displayed recurrence. The prefix functions update by

\[
G'_a=
\begin{cases}
G_a,&b=0,\\
G_{1-a}\circ F_a,&b=1,
\end{cases}
\qquad p'=p\mathbin{\mathrm{xor}}b.
\]

For \(b=1\), the prefix first reads all of \(\mu^k(a)\), followed by \(n\) symbols from \(\mu^k(1-a)\); this explains the composition order.

After all index digits have been read, the original transducer's state before position \(n\) is \(G_0(0)\), and \(t_n=p\). Thus the output attached to the kernel state is

\[
\lambda(G_0(0),p).
\]

There are \(q^q\) functions \(Q\to Q\). The tuple therefore has at most

\[
2(q^q)^4
\]

possible values. At \(q=2\), this gives a finite bound of 512 states for each transition table. The complete reachable graph describes every index, without generating a prefix of the Thue–Morse stream.

Appending a higher zero digit changes the full-block functions but leaves the prefix functions and parity unchanged. It therefore leaves the current output unchanged. Every finite binary word can be interpreted as an index, with high zero padding allowed. The empty digit word denotes index zero. Equality of the rooted output automata on all finite digit words is consequently exactly equality of the indexed infinite streams.

This finite-kernel argument establishes the semantic meaning of the saved graph. The actual construction is bounded to the declared machine family; no claim of priority for automatic-sequence or transducer methods is made.

## Encoding the complete family

A function \(f:Q\to Q\) has code

\[
\sum_{s=0}^{q-1}f(s)q^s.
\]

Put \(M=q^q\). A transition table has code \(f_0+Mf_1\), where \(f_a\) encodes \(\delta_a\). An output table has bit \(2s+a\) equal to \(\lambda(s,a)\). Finally,

\[
\text{machine code}
=\text{transition code}\cdot2^{2q}+\text{output code}.
\]

For \(q=2\), transition codes run from 0 through 15, output codes from 0 through 15, and machine codes from 0 through 255. This covers every labelled table once.

The compiler constructs a kernel once for each transition table. All 16 output assignments reuse that graph. Kernel states are discovered in breadth-first order with digit 0 before digit 1.

Output classes are ordered by the first machine code assigned to each class. Members inside each class are in increasing machine-code order. These are interface conventions, not isomorphism or degree quotients.

## Exact infinite equality and its certificates

For each output assignment, the compiler refines the finite kernel's states by their output bits and the classes of their two successors. Initially, states are partitioned by output. At each stage, a pair is split if some digit leads to states already separated at the preceding stage.

After \(r\) refinement stages, states in the same block have the same outputs on every digit word of the corresponding bounded length. A stable partition preserves outputs and both successors, so equality extends inductively to every finite word. Conversely, every split is accompanied by a distinguishing word: prepend the splitting digit to an earlier distinguishing suffix.

The stable quotient is then numbered by breadth-first search from its root, digit 0 before digit 1. The resulting minimal DFAO is a canonical finite representation of the infinite output stream.

The artifact retains two complementary certificate types:

1. **A quotient map for every machine.** It maps each reachable kernel state onto a state of the selected minimal DFAO, preserving the root, output and both digit transitions. Thus the original kernel and the class DFAO have identical output at every index.
2. **A distinguishing word for every pair of distinct states of every minimal DFAO.** Following that word from the two states ends at different output bits. This proves that no two retained minimal states can be merged.

Every class DFAO is accessible and in canonical breadth-first order. Two different retained canonical minimal forms represent different streams. Together with all 256 quotient maps, these records certify the complete equality classification.

The compiler performed 256 minimizations and 611 refinement rounds. It found 8,540 distinguishing pairs in the unminimized kernels while compiling, and retained the 1,650 pair certificates needed for the 104 shared minimal DFAs. The latter, along with every quotient map, are in the complete data file.

The distribution of minimal index-DFAO sizes is:

| States | Output classes |
| ---: | ---: |
| 1 | 2 |
| 2 | 4 |
| 3 | 10 |
| 4 | 18 |
| 5 | 14 |
| 6 | 16 |
| 7 | 8 |
| 8 | 24 |
| 9 | 8 |

## Saved equality and difference queries

Machines 10 and 250 both belong to class 2 and output exactly Thue–Morse. The saved reader establishes this from their common certified canonical DFAO; it does not compare generated prefixes.

Machine 198 has

\[
\delta(s,a)=a,\qquad \lambda(s,a)=s\mathbin{\mathrm{xor}}a.
\]

Its output begins with \(y_0=0\), and for \(n\ge1\),

\[
y_n=t_{n-1}\mathbin{\mathrm{xor}}t_n.
\]

Thus it is an initial zero followed by the established adjacent-bit-difference/period-doubling stream. The initial zero is retained in exact stream equality. The source paper's transducer example allows an initial empty emission; that convention is different from the letter-to-letter family here.

The reader's product-automaton query for machines 10 and 198 returns a difference at index 2: the respective output bits are 1 and 0. It retains the five discovered product states, the four expanded states and the witness digit word `01`, read least significant digit first.

Difference queries use breadth-first search with digit 0 before digit 1. They return a shortest distinguishing digit word, breaking ties in that digit order. This is not a general claim that the reported index is numerically least.

A shared class is a certificate of stream equality. Different classes do not imply different transduction degrees.

## Exact counts below a large index

Random access follows one path in the saved minimal DFAO. Prefix counts use a digit dynamic program on that same automaton.

For a bound \(N\), process its binary digits from least significant to most significant. A DP state contains an automaton state and a comparison value: smaller than, equal to, or greater than the portion of \(N\) read so far.

When the next candidate digit \(b\) differs from the next bound digit \(B\), that higher digit determines the comparison. If \(b=B\), the previous comparison remains:

\[
c'=
\begin{cases}
<,&b<B,\\
>,&b>B,\\
c,&b=B.
\end{cases}
\]

The automaton state follows its transition labelled \(b\). After all digits, each padded binary word represents exactly one integer in the full digit range. Summing states with comparison \(<\) and output 1 counts precisely the ones at indices \(0\le n<N\). High-zero output invariance justifies padding. Counts are BigInt integers.

The actual new query bound is

\[
N=10^{1000}+19.
\]

The scalar 19 comes from the identified field `finite_findings.maximum_cardinality` in the released Erdős 99 data, blob `b56eef4c114eb2fa1eb3bde83df1e8987ae449c3` at merge `67c3a1d4db46e9f8f67e014379a28e25e19ad552`. It only selects a reproducible new input; no relation between lattice packing and transduction is asserted, and no packing work was repeated.

The saved query gives:

| Machine | Stream description | Output at \(N\) |
| --- | --- | ---: |
| 10 | \(T\) | 0 |
| 5 | \(1-T\) | 1 |
| 198 | Initial 0, then adjacent-bit differences | 1 |
| 204 | Initial 0, then \(T\) | 1 |

For machine 198 on \(0\le n<N\), the exact retained totals can be written compactly as

\[
\#1=\frac{2N-7}{3},\qquad
\#0=\frac{N+7}{3}.
\]

These are compact forms of this one query's complete decimal totals, not identities asserted for arbitrary \(N\). The data contains the full 1,000-digit counts and all four final DFA-state rows, each with its smaller/equal/greater counts.

This prefix query used 3,322 digit layers and 39,842 DP transitions. Its intermediate layers are not retained; the complete final response and final state distribution are retained. Neither the input stream nor its output prefix was generated.

## Public interface

The module performs no I/O and imports no dependencies.

| Export | Purpose |
| --- | --- |
| `compileThueMorseMealyAtlas(input)` | Construct all labelled machines at the specified state count and their complete infinite-output equality atlas. |
| `openRetainedThueMorseMealyAtlas(saved)` | Verify and open the retained finite certificates for exact queries. |
| `THUE_MORSE_MEALY_LIMITS` | Published arithmetic and resource limits. |

The compiler accepts `state_count` equal to 1 or 2. An optional `max_kernel_states` can lower the default and hard bound of 512 states per kernel. The actual input used two states and the full bound.

The compiler returns `snapshot` and `summary`. A kernel or certificate-budget failure carries an `ATLAS_BUDGET` exception with the completed records and current incomplete state under `partial`. This is an incomplete custody record, not a complete equality atlas or a supported resumable snapshot. A snapshot-character failure retains the completed snapshot under `completed_snapshot`. No budget failed for the actual input.

### Reader verification

The reader copies the supplied object or parses a JSON string. It checks:

- The Thue–Morse input convention and complete machine-code coverage.
- Every function encoding, composition-table entry and kernel recurrence edge.
- Reachability of every retained kernel state.
- Every machine quotient map's root, outputs, transitions and surjectivity.
- Accessibility and canonical breadth-first numbering of every class DFAO.
- Every pairwise distinguishing word, proving minimality.
- Unique canonical class forms and complete ordered membership lists.

These are finite certificate checks. They do not construct new kernel states, run output minimization or expand any stream symbols.

The reader exposes:

| Method | Contract |
| --- | --- |
| `summary()` | Family size, class count, kernel size and interpretation. |
| `classSummary(id)` | Representative, number of machines, minimal-DFA size and constant output when the DFA has one state. |
| `classDetails(id)` | The complete detached class, member list, minimal DFA and distinguishing certificates. |
| `machine(code)` | Decode the original transition and output tables. |
| `rankMachine(code)` | Class ID and rank within its increasing machine-code member list. |
| `selectMachine(classId, rank)` | Decode a machine at the supplied class rank. |
| `classesPage(start, limit)` | A bounded page of class summaries. |
| `machinesPage(classId, start, limit)` | A bounded page of original machines in one class. |
| `output(code, index)` | Exact output bit at a nonnegative integer index. |
| `difference(left, right)` | A shared-class equality certificate or a bounded product-automaton difference witness. |
| `prefixOnesBelow(code, bound)` | Exact zero/one counts on indices below the bound, with the final digit-DP state distribution. |
| `snapshot()` | A detached copy of the complete retained atlas. |
| `statistics()` | Certificate and query work counters. |

Natural-number queries accept exact nonnegative Numbers, BigInts or canonical decimal strings. Decimal input is capped at 2,048 digits. Zero is valid; index zero uses the empty digit word, and a bound of zero has empty prefix counts.

Page sizes are capped at 256. Difference searches are capped at 4,096 product states; a cap exception retains its partial search and does not assert equality. Snapshot text is capped at 16,000,000 characters, and retained state-pair certificates at 262,144 rows. These are implementation limits, not a classification of larger machine families.

All returned objects and arrays are detached from the internal retained state.

### Connected V8 use

With the published file contents available as `moduleText` and `dataText`:

```js
const module = { exports: {} };
new Function("module", "exports", moduleText)(module, module.exports);

const data = JSON.parse(dataText);
const atlas = module.exports.openRetainedThueMorseMealyAtlas(data.snapshot);

atlas.summary();
atlas.classesPage(0, 40);
atlas.difference(10, 198);
atlas.output(198, data.retained_consumer.query_index);
```

The complete saved atlas is directly usable. Neither the compiler nor a Thue–Morse prefix generator is needed for these queries.

## Actual execution and custody

The public source was frozen before the single atlas compilation at Git blob

`301e11b501f67eeae9cea6f746edfdfaac7da0e6`

and was not changed afterward.

A fresh reader instance made 16 queries. Three class pages exported all 104 class summaries; one machine page exported all 30 machines in the exact Thue–Morse class. It also decoded machine 198, performed a class rank/select, answered two equality/difference queries, evaluated four streams at the new index, counted one prefix and returned the adjacent-difference class certificate.

The loader checked 286 kernel edges, 2,288 quotient states, 4,576 quotient edges and all 1,650 distinguishing words. Those words used 2,788 finite DFA transitions during checking. Query work included 13,288 digit steps for the four random-access outputs and the 39,842 prefix-DP transitions already described.

The saved reader's counters for kernel graph construction, output minimization and input-stream expansion all remained zero. The original compiler likewise expanded zero Thue–Morse symbols.

One connected V8 observation took 12 ms to compile, 5 ms to load the retained certificates and 22 ms for the fresh queries. These are single observations, not a statistical benchmark or timing guarantee.

The one-state compiler path, lowered budgets, corrupt-input refusal, oversized inputs and difference-cap exception were inspected in the source but not separately exercised. No synthetic test suite, earlier sequence computation or accepted proof was replayed.

## Complete deliverables

- `thue_morse_mealy_index.cjs`: the public compiler and certified saved reader.
- `two_state_infinite_output_atlas.json`: the complete machine family, all kernels, quotient maps, minimal DFAs, distinguishing words, source boundaries, actual requests, full responses and counters.
- `README.md`: the result and direct entry points.
- This guide: the finite-kernel derivation, certificate argument, exact API contract and distinction from the unrestricted prime-degree question.

No finite prefix or selected reverse-transducer failure is used as evidence of an infinite non-equivalence claim.
