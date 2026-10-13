# Finite unary identities and an exact NFA separator

For the two equal-length binary words
\[
w=0^{65}1^5,\qquad x=0^51^{65},
\]
the retained computation gives the exact finite result
\[
\boxed{\operatorname{nsep}(w,x)=4.}
\]

The lower certificate contains all **512 Boolean relations on three labelled states**, and every one satisfies \(R^5=R^{65}\). The upper certificate is an explicit four-state NFA accepting \(w\) and rejecting \(x\). The complete data includes every Boolean-power/accumulator row, the upper machine and its endpoints, and all eleven fresh-reader outputs.

The plain CJS source was frozen before execution at **Git blob 34c6959f5ad5e251939de50d96971cee347853b9, 13,985 UTF-8 bytes**. It remained unchanged for the saved reader.

## Source, conventions and scope

Jeffrey Shallit's [*Open Problems in Automata Theory: An Idiosyncratic View*](https://cs.uwaterloo.ca/~shallit/Talks/bc4.pdf), printed slides 20–24, supplies a word family with \(t=n^2-3n+2\), \(L=\operatorname{lcm}(1,\ldots,t)\), and block lengths \(t-1+L\) and \(t-1\). It presents a \(2n\)-state separator using a numerical semigroup. At \(n=4\), \(t=6,L=60\), giving this pair.

Separation means accepting one word and rejecting the other under ordinary existential NFA acceptance. Initial and accepting choices matter; equality of entire terminal subsets is a sufficient obstruction for all accepting choices. State labels are retained, not quotiented by isomorphism. Empty transition sets and self-loops are allowed.

The historical Problem 3 asks for good general bounds on nsep for equal-length words; Problem 4 concerns its ratio with DFA separation. The present exact finite instance is not an asserted improvement to those general bounds or a claim of mathematical novelty. The source is the author's presentation; no comprehensive current-status survey or prize action was performed.

No arbitrary-matrix transient theorem is used. A bounded source check did not establish the required universal hypotheses for reducible matrices, so no primitive/strongly-connected bound is silently applied to them.

## Boolean relations and complete coverage

For \(k\) states labelled \(0,\ldots,k-1\), a binary relation is stored by \(k\) row masks. Bit \(j\) in row \(i\) means an edge from \(i\) to \(j\). Its code is
\[
\operatorname{code}(R)=\sum_{i=0}^{k-1}\operatorname{row}_i(R)(2^k)^i.
\]
Thus codes \(0,\ldots,2^{k^2}-1\) cover **every** labelled relation exactly once. Row zero is the least significant base-\(2^k\) digit. No determinism, outgoing-edge requirement or reachability condition restricts this universe.

Composition \(AB\) means first follow \(A\), then \(B\). Row \(i\) is the bitwise union of the rows of \(B\) indexed by the set bits in row \(i\) of \(A\). The identity relation has row \(i=2^i\).

The compiler retains \(R,R^2,R^4,\ldots\) through the largest exponent bit by repeated squaring. Starting from the identity, it processes selected exponent bits in increasing order and retains each accumulator. These operations establish the saved final rows. The data includes the base relation, every power row, selected-bit list, every accumulator, both final matrices, their rowwise XOR differences and an equality flag.

For this input the exponents are 5 and 65:
\[
5=1+4,\qquad65=1+64.
\]
Each relation retains seven binary powers and two accumulator steps for each exponent. The complete enumeration uses codes 0 through 511. All 512 rowwise differences are zero.

This is a finite executed identity certificate. Source and complete outputs are retained so its evidence is inspectable; there was no external proof-kernel check or separate rerun of the enumeration.

## Why the identity rules out every smaller NFA

Let \(A,B\) be the zero- and one-transition relations of any NFA on at most three states. Pad it with isolated unused states if necessary. The complete atlas gives
\[
A^5=A^{65},\qquad B^5=B^{65}.
\]
Consequently
\[
A^{65}B^5=A^5B^5=A^5B^{65}.
\]
The words therefore induce the same relation. From every initial subset they reach the same terminal subset, and every accepting subset accepts either both or neither. This includes the usual single-initial-state convention.

Epsilon transitions do not evade the argument. Let \(E^*\) be their reflexive-transitive closure. Replace the effective letter relations by \(E^*AE^*\) and \(E^*BE^*\), start from the epsilon closure of the initial subset, and retain the accepting states. These are still binary relations on the same states. Since \(E^*\) is idempotent, their products implement the original epsilon-NFA on the nonempty words here. The same universal relation identity applies without adding a state.

Thus no NFA with one, two or three states separates this pair. No enumeration of all two-letter NFA transition tables, initial states or accepting sets is required. The lower bound is for arbitrary nondeterminism and epsilon closure, not merely deterministic or complete machines.

## The four-state upper certificate

The retained machine has state set \(\{0,1,2,3\}\), initial state 0 and accepting set \(\{0\}\).

| State | Zero targets | One targets | Zero mask | One mask |
| ---: | --- | --- | ---: | ---: |
| 0 | {1} | {0} | 2 | 1 |
| 1 | {2} | empty | 4 | 0 |
| 2 | {0,3} | empty | 9 | 0 |
| 3 | {0} | empty | 1 | 0 |

Its zero-only closed walks at state 0 are concatenations of the length-three cycle \(0,1,2,0\) and length-four cycle \(0,1,2,3,0\). The branch at state 2 chooses the next return length. Hence the possible return lengths are exactly the nonnegative combinations of 3 and 4.

The accepted zero prefix has the compressed witness
\[
65=19\cdot3+2\cdot4.
\]
After returning to state 0, five one-transitions stay there. In contrast, \(5\) is not a nonnegative combination of 3 and 4: reduction modulo 3 would require the number of length-four cycles to be at least 2, contributing at least 8 already. Thus the five-zero prefix cannot return to state 0, and a following one kills every remaining path.

The complete Boolean endpoint calculation retains:
\[
\begin{array}{c|cc}
&\text{after zero block}&\text{after one block}\\
w&15&1\\
x&6&0
\end{array}
\]
in bit-mask notation. The first word accepts and the second rejects.

The one-loop is at the shared initial/accepting state. It also permits interleaved zero-cycle and one blocks. We do **not** claim this machine's whole language is exactly \(0^{\langle3,4\rangle}1^*\). Only the specified word pair needs to be separated.

Combining the explicit four-state upper bound with the universal three-state lower certificate gives the stated exact minimum. The upper constructor's own summary deliberately leaves claimed_minimum null; the minimum is established only in the combined record.

## A bounded family constructor

The source also includes an upper-certificate constructor for any caller-supplied \(4\le n\le24\). It computes \(t=n^2-3n+2\), \(L=\operatorname{lcm}(1,\ldots,t)\), \(F=t-1\), \(G=F+L\), and retains every gcd/lcm row.

Its zero graph has the cycle of length \(n\) and a chord producing a cycle of length \(n-1\), sharing the path from state 0 to state \(n-2\). A one-loop exists only at state 0. Exactly \(n\) states are used.

For the short exponent
\[
F=n^2-3n+1\equiv n-2\pmod{n-1},
\]
a representation by cycle lengths \(n-1,n\) would require at least \(n-2\) long cycles. Their contribution \(n(n-2)>F\) is impossible.

For \(G\), choose the count of long cycles as \(G\bmod(n-1)\); the remaining multiple of \(n-1\) is nonnegative. Indeed \(L\ge t=F+1\) and \(n\ge4\) give \(G\ge2F+1\ge n(n-2)\), which exceeds the largest possible long-cycle contribution selected this way.

This proves the constructed upper family directly. It supplies no general matching lower bound. Only \(n=4\) was executed and paired with a complete identity atlas. Other constructor sizes were source-inspected, not expanded for a larger headline.

## Public interface

The module exports:

- **UNARY_IDENTITY_LIMITS**;
- **compileUnaryPowerIdentity(input)**;
- **compileShallitCycleSeparator(input)**;
- **openRetainedUnaryPowerIdentity(snapshotOrJSONString)**.

There are no imports, filesystem/network calls or native dependencies.

### Generic identity constructor

Required inputs are **states**, **left_exponent**, **right_exponent** and **provenance**.

- states is a Number from 1 through 4.
- Exponents are nonnegative BigInts, safe integer Numbers or canonical decimal strings of at most 300 digits.
- Provenance is a JSON object or JSON text encoding one, bounded to 32,768 characters.
- Optional max_saved_cells is a Number from 0 through 2,000,000, lowering the storage budget.

Canonical strings have no sign or leading zero except "0". Exponent zero uses the identity relation and no selected multiplication bits.

Before enumeration, the constructor computes the complete relation count and required saved mask-cell count. The latter includes base rows, binary powers, accumulators, final rows and difference rows. If it exceeds the supplied/hard cap, the response is **INCOMPLETE_BUDGET** with snapshot:null and required_cells. A final 12,000,000-character snapshot cap also returns an incomplete result with actual work retained.

A completed atlas has status **COMPLETE_FINITE_IDENTITY_ATLAS** and schema **commons.unary_boolean_identity/v1**. Completion does not imply universal equality: summary.all_relations_equal, unequal_relations and first_unequal_code distinguish that question. An unequal row is a finite obstruction to the proposed unary identity, not a separator automatically synthesized by the API.

The hard relation limit is 65,536, attained at four states. Generic exponent/state combinations may fail the saved-cell budget long before this limit. Invalid input types/ranges throw; malformed JSON may raise ordinary JavaScript errors.

### Source-family upper constructor

**compileShallitCycleSeparator({states,provenance})** accepts integer Number states from 4 through 24. It returns a complete upper snapshot under schema **commons.shallit_cycle_separator/v1**.

The result includes full zero/one row masks, both unary binary-power ledgers, both word endpoint traces, all lcm steps, compressed accepted-cycle counts and the short-word obstruction. It never expands a word into individual symbols. Its minimum-state field remains null.

### Saved identity reader

| Method | Contract |
| --- | --- |
| summary() | Atlas totals and universal-equality flag |
| source() | Detached provenance |
| relation(code) | Complete stored relation and both power ledgers |
| power(code,side) | Saved evaluation for side 0 or 1 |
| applyPower(code,side,startMask) | Apply a saved final relation to a subset |
| compareSwappedBlocks(input) | Endpoints/acceptance of the two mixed blocks |
| page(options) | Complete records in increasing relation-code order |
| snapshot() | Detached complete snapshot |
| statistics() | Detached load/query counters |

All relation codes, row masks, state counts, side selectors and page indices are integer Numbers in the declared ranges. side 0 always denotes left_exponent and side 1 right_exponent; the generic API does not require the first exponent to be smaller.

compareSwappedBlocks input fields are zero_code, one_code, initial_mask and accepting_mask. It compares zero-to-right then one-to-left against zero-to-left then one-to-right, retaining both intermediate and final subsets. It evaluates only the supplied machine from saved powers. The universal lower conclusion comes from the complete atlas, not this single query.

Pages accept {start,limit}, defaulting to 0 and 128. Limit is from 1 through 128. Start equal to record count gives an empty terminal page; larger values fail. Pages return complete records, count, total and next_start, or null at the end.

The reader freezes its API, copies input and returns detached output. It rejects incomplete record coverage, wrong code encoding, malformed dimensions/masks, wrong selected-bit coverage or mismatched final-row equality metadata.

### Structural validation boundary

Loading validates row dimensions, encodings, binary-power coverage, selected-bit/accumulator coverage, final-row pointers, rowwise differences and summary totals. It does **not** multiply the saved binary powers or accumulators again. Therefore structural reopening does not independently certify the provenance or correctness of each matrix product.

applyPower and compareSwappedBlocks do perform new row unions using the saved final matrices. Their query_row_unions counter records that real work. Zero power recomputation is not a claim of zero arithmetic or zero output records.

## Actual construction and data

The one source-defined instance has \(n=4,t=6,L=60,F=5,G=65\), with both words of length 70.

The upper constructor retained six lcm rows and used 12 gcd divisions, 20 Boolean products and 100 row unions. Its zero and one ledgers each contain seven binary powers and both evaluations. No word or full path was expanded.

The lower atlas retained all 512 codes, 3,584 binary-power matrices and 2,048 accumulator matrices, with both final matrices and rowwise differences for each code. It used **5,120 Boolean products and 24,138 row unions**. All 512 equalities hold; there are no unequal codes. These products are the actual lower-certificate computation, not a claim of no computation.

No binary NFA table census, accepting-set census, earlier DFA instance or universal-length input was replayed. The finite atlas exploits the unary identity instead.

The complete first construction packet was immediately checkpointed as Git blob **0a305aac9e18d2be09674d08bacfcb8fbbf9b92d**, 1,151,186 bytes. After the fresh reader, the complete packet was checkpointed as **79f4d21be382497df830a2b93334f6b64ff6aecc**, 2,530,359 bytes. These native Git objects preserved the once-only calculation before prose; committed source/data are the publication.

## Fresh saved-reader consumer

A new connected invocation opened the complete atlas once and made eleven queries:

1. summary;
2. provenance;
3. complete relation code 106;
4. its fifth-power record;
5. its sixty-fifth-power record;
6. application of its fifth power to initial mask 1;
7. swapped-block comparison with zero code 106, one code 1, initial/accepting masks 1;
8. four pages at starts 0, 128, 256 and 384, each returning 128 complete relation records.

The last item represents four operations, so the total is eleven. The pages export the full 512-record atlas; the final cursor is null.

Code 106 has zero rows [2,5,1], the three-state shared-path graph with cycles of lengths two and three. Code 1 has one rows [1,0,0], only the state-zero self-loop. This is a saved-power consumer, not another power calculation. Both zero-block endpoints are mask 7 and both final endpoints mask 1, so this machine accepts both words and does not separate them. Applying its fifth power alone to initial mask 1 gives mask 7.

The reader made **5,632 structural row checks and 1,536 saved endpoint comparisons**. Its eleven queries used nine new row unions. Atlas compilations, recomputed Boolean-power products and expanded words remained zero.

Observed times were 19 ms for the two construction operations, 10 ms for reader loading and 23 ms for queries. They are single observations, not benchmarks. Other states/exponents, budget refusals and boundary pages were source-inspected; no synthetic suite ran.

All complete outputs are in [n4_pair_identity.json](n4_pair_identity.json), including the duplicate full atlas exported through the public page API. The payload is complete, not a summary or a selected set of favorable relations.

## Connected use

With full module and record texts already supplied:

~~~js
const module = {exports: {}};
new Function("module", "exports", moduleText)(module, module.exports);
const record = JSON.parse(dataText);
const reader = module.exports.openRetainedUnaryPowerIdentity(
  record.lower_bound.snapshot
);
const machine = reader.compareSwappedBlocks({
  zero_code: 106,
  one_code: 1,
  initial_mask: 1,
  accepting_mask: 1
});
// machine.same_terminal_subset === true
// machine.separates === false
~~~

This documented call was already executed in the retained session; guide composition did not repeat it.

The exact minimum applies to this particular pair. The reusable API, complete finite identity and constructed upper witness do not establish a new general nsep growth bound, an unrestricted automata classification, a current external frontier or a prize result.
