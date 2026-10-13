# Affine restricted-sum-avoidance index

This complete parameter index covers every A=λ{1,...,19}+τ for nonzero signed integer λ and integer τ. It counts and navigates subsets S whose sums of distinct selected elements avoid the entire ambient A.

Read [the exact conventions, derivation and API](AFFINE_SUM_AVOIDING_API.md). This differs from ordinary sum-freeness: unselected ambient targets still forbid a pair, while diagonal sums are omitted.

- [Compiler and saved reader](affine_sum_avoiding_index.cjs)
- [Literal pair/binomial input and provenance](input_affine19.json)
- [Complete 53 critical graphs, generic class and shared DAG](affine19_sum_avoiding_index.json)
- [All 43 reader requests and outputs](saved_reader_queries.json)

There are 1,039 shared DAG nodes. The smallest maximum within this affine family is 5, at ratio τ/λ=−10 only, with 4 maximum subsets and 124 total admissible subsets. All other noncritical ratios have the edgeless graph and permit all 524,288 subsets.

The reader exports every central subset, records 12 inverse matches and navigates huge signed integer parameters. It uses saved sums/graphs/coefficients, with fresh parameter and affine-value arithmetic explicitly counted. No old pair-sum, Pascal or prior B2-family calculation was replayed.

This finite-host affine classification does not settle Green 2 or establish a worst case among arbitrary integer sets, a new asymptotic theorem, or a prize claim.
