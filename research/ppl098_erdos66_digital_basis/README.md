# Exact digital-basis representation index

This package counts and navigates all representations of one natural-number target in the classical Raikov–Stöhr basis. It represents the family by at most four ordered or three unordered bit cubes, with exact BigInt counts, numeric rank/select, interval counts and pages. The plain CJS module has no imports or I/O.

| File | Contents |
| --- | --- |
| [digital_basis_index.cjs](digital_basis_index.cjs) | Bounded constructor and saved-snapshot reader |
| [DIGITAL_BASIS_API.md](DIGITAL_BASIS_API.md) | Derivation, conventions, API, limits, source identities and actual query results |
| [repeated210_14.json](repeated210_14.json) | Complete constructor snapshot and all 14 fresh-reader outputs |

Nathanson's [author paper](https://arxiv.org/pdf/0906.1241), §1, attributes the digital construction independently to Raikov and Stöhr in 1937. With A0 consisting of finite base-4 sums whose digits are 0 or 1, and A1 = 2A0, their union A includes zero once. Summands may repeat. The construction and its basis property are established prior material.

The API distinguishes ordered convolution representations from unordered pairs displayed with first coordinate at most second. Internal digital branches do not create extra copies of the same pair. For the one new target **11053036065048038168742180**, whose base-4 expansion is **210 repeated 14 times**, the exact counts are **32,770 ordered and 16,385 unordered representations, with no diagonal**. Four ordered and three unordered disjoint cubes retain this complete family. The parameter 14 reuses a released Singer-set cardinality solely to choose an input; no field or Singer computation was repeated.

The complete record preserves 84 digit rows, all seven cubes, all 14 saved-reader outputs and an 84-step selection trace. The reader exported requested digit, cube and pair pages without invoking the constructor. Its saved arithmetic checks and navigation-index construction are recorded as real work. The session emitted 12 selected/paged pair records plus one rank answer; zero complete pair-table construction does not mean that no pair records were generated.

The executed source was frozen at Git blob `2fd98cb50d393fabfe3450791b52b49667c69d36`. The source and complete computation packets were checkpointed in Git before publication. Only this target and the documented queries were executed; other branches were source-inspected, with no synthetic suite or accepted-input replay.

The formula also yields exact oscillation along two elementary infinite subsequences, showing why this particular basis has no finite nonzero logarithmic representation-count limit. These deductions do not resolve the separate existence question in [Erdős 66](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/66.lean), establish a new basis construction, or make a novelty claim.
