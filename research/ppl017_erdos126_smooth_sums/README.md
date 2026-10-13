# Erdős126: smooth pair sums and finite maximum cliques

This directory provides a reusable index for sets of distinct nonnegative integers whose pair sums use a chosen finite prime palette. It factors each distinct sum once, reuses those records across graph views, and retains a complete include/exclude search trace with proper-color upper bounds.

The recorded consumer searches the candidate universe **0 through 127**.

| Allowed prime set | Graph edges | Exact finite maximum | One witness |
|---|---:|---:|---|
| {2, 3, 5} | 1278 | 5 | {0, 8, 24, 72, 120} |
| {2, 3, 5, 7} | 2035 | 7 | {0, 4, 12, 20, 36, 60, 108} |

Each maximum is exact for its own declared finite graph. The corresponding actual prime unions are respectively {2,3,5} and {2,3,5,7}. Under the inspected natural-number convention these witnesses give f(5)<=3 and f(7)<=4. No claim is made that these are new best-known bounds or the exact global values of f.

## Files

| File | Contents |
|---|---|
| [smooth_sum_clique_index.cjs](./smooth_sum_clique_index.cjs) | CommonJS compiler, graph cache, bounded exact search, saved continuation and retained-result readers |
| [SMOOTH_SUM_CLIQUE_API.md](./SMOOTH_SUM_CLIQUE_API.md) | API contract, factor-source custody, complete search proof, limits, recorded results and work accounting |
| [interval0_127_prime_support_cliques.json](./interval0_127_prime_support_cliques.json) | Complete portable consumer evidence and supported saved-index snapshot |

The implementation is **37494 UTF-8 bytes**, Git blob **983a039c73d48035cbaf7bcfe5ef34ea2ebc21ac**, and was frozen before its first actual consumer.

The complete consumer artifact is **869513 UTF-8 bytes**, Git blob **e92c77a8e5095ae58e30c340f75305f060075f12**. It contains every new factor division, all 8128 unordered-pair rows, both adjacency views, all 234 processed search nodes, every branch and color class, incumbent histories, saved-handoff evidence and the nine fresh reader results.

## Reuse and exact completion

One compilation factored the **253 distinct sums 1 through 253**, using **660 exact divisions** from the already accepted least-factor basis. The first search processed 64 nodes and returned incomplete with one pending state. A saved open processed 13 new states to finish its 77-node proof; no previous state was searched again.

A separate saved open built the {2,3,5,7} graph from the retained factors and completed its own 157-node proof. A final saved reader returned both maxima, six pair witnesses and all 253 sum rows with **zero new factor divisions, graph construction, coloring or search**.

Incomplete searches preserve a pending stack. An exhausted stack yields one witnessed maximum; equal-bound pruning does not enumerate all tied maximizers. Hard capacity stops remain explicitly incomplete.

## Source conventions and qualification

The exact inspected [formal problem definition](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/126.lean), blob **b193747601aea2ef1f5f3f04805b4991112b6aff**, uses finite sets of natural numbers, so zero is allowed. Its ordered off-diagonal product repeats each unordered pair sum twice and therefore has the same distinct prime support.

That source annotates the main divergence question as research solved with answer True while keeping a local "by sorry" body. Its external pinned Lean resolution was not read, run or independently audited here. The separate f(n)=o(n/log(n)) variant is annotated research open in the inspected file. Those annotations are attributed source metadata; this finite consumer does not independently settle either asymptotic statement.

The accepted factor source is [the saved interspersion-row artifact at revision 8bcf059ef0fda877c0975f7a89a2ae565e71a3b8](https://github.com/woahwhattheheck/commons/blob/8bcf059ef0fda877c0975f7a89a2ae565e71a3b8/research/ppl040_kimberling_interspersion_primes/row493_columns10001_22000.json), blob **7decf4b5cbf9945cf707d392e0c7d3d68e4a75bd**, field snapshot.basis. It covers 0 through 16384 with 1900 accepted primes and 16385 least-factor entries. Its sieve and prior row calculation were not replayed.

Saved opens validate bounded structure and reference integrity; they do not independently verify factorization, adjacency, coloring or clique proofs. They require custody of state emitted by the published implementation. Complete evidence is retained for review.

No existing source artifact, other problem module, test suite, fixture family or workflow was changed. No native runtime probe was used.
