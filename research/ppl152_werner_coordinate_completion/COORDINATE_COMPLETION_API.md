# Exact coordinate-constrained completions of a saved Werner form

This package solves a new constrained optimization problem inside the already certified left support from Commons #31452. It retains eight inverse columns and all 256 coordinate-constraint profiles, then supplies exact minimizers for arbitrary complex rational coordinate targets. One actual reader run produced 316 responses, including 256 distinct optimizers for a consistent fixture, two additional target optimizers, and 21 matching conditional inverse ranks.

The objective is the **unnormalized form** v* K v. The returned unit-vector state expectation is its value at that minimizer; it is not the minimum of a Rayleigh quotient. This fixed-support, two-copy result does not certify NPT bound entanglement or all-copy nondistillability.

## Source and preserved input

Horodecki, Rudnicki and Życzkowski, *Five open problems in theory of quantum information*, dated December 21, 2020, https://kcik.ug.edu.pl/wp-content/uploads/2021/12/2002.03233.pdf , distinguishes NPT from nondistillability in Problem 4. Distillability requires some finite copy number and suitable rank-two projectors; nondistillability negates all such choices. Nothing below supplies that universal conclusion. Historical award statements do not establish current sponsor eligibility.

The precise input is the complete saved certificate from [Commons #31452](https://github.com/woahwhattheheck/commons/pull/31452), immutable merge 3e7fc1e5912eb8ff533eb805fa95914e4b1172b5:

| Input | Git blob | Bytes |
|---|---|---:|
| WERNER_FIXED_SUPPORT_API.md | 5adec73fdf1e1979fa415c5ab93dc626720e1b72 | 22020 |
| diagonal_shift_support_certificate.json | 4271b18c70007c485c641112747b23c47a8bd1cf | 147936 |

Both complete bodies were acquired and independently hash-matched. This package copies their K, L, D, support Gram, coordinate convention and scaling. It does not reconstruct the form, repeat LDL elimination, replay the old factor-direction/evaluation queries, or audit an external proof. The prior guide's reported July 2026 claim about the full two-copy theorem remains a reported claim, not a proof endorsement.

The inherited representation is C=U V^T with two fixed real left columns and arbitrary complex right columns. The transpose does not conjugate V. Flatten v as V_0[0..15] followed by V_1[0..15], using row-major pairs inside each 16-coordinate block. The saved positive-definite 32-by-32 real symmetric form satisfies K=L D L^T and v* K v=4q(C). The state's unnormalized-vector expectation is v* K v / 784. The represented-state squared norm is computed from the copied two-by-two support Gram, not from the Euclidean norm of v.

Only the following eight right-factor coordinates are eligible for constraints, in this fixed local bit order:

| Local bit | Global coordinate |
|---:|---:|
| 0 | 0 |
| 1 | 5 |
| 2 | 10 |
| 3 | 15 |
| 4 | 16 |
| 5 | 21 |
| 6 | 26 |
| 7 | 31 |

A mask selects any subset of these eight coordinates. Constraint values are supplied in increasing local-bit order. Masks are coordinate labels, not code-equivalence classes or quantum measurements.

## The new continuous optimization certificate

Let E_J select the eight columns of the identity matrix named above. The new constructor performs only eight right-hand-side solves:

A=K^{-1} E_J = L^{-T} D^{-1} L^{-1} E_J,
Q=E_J^T A.

Each solve consists of a forward unit-triangular substitution, division by the saved positive diagonal, and a backward substitution. These inverse columns were not part of the old factor-direction evaluations.

For each selected subset S, let Q_SS be its principal submatrix. Since the inherited K is positive definite and the coordinate selectors are independent, Q and every nonempty Q_SS are positive definite. The new profile is B_S=(Q_SS)^{-1}. The empty profile is the empty matrix.

Profiles are built in numeric mask order. Each nonempty mask removes its largest selected bit to obtain an already constructed parent. If its new coordinate has off-diagonal column h, parent inverse B and diagonal a, define u=B h and s=a-h^T B h. Then s>0 and the new inverse is the block matrix with upper-left B+u u^T/s, last column and row -u/s, and last diagonal 1/s. All 255 newly calculated Schur pivots were strictly positive. This is elimination on new principal inverse-coordinate profiles, not a repetition of the old 32-by-32 LDL elimination.

For a complex target g on S, define

lambda=B_S g,
v_star=A[:,S] lambda,
minimum=g* B_S g.

These expressions use conjugate transpose in complex energies. They satisfy K v_star=E_S lambda and (v_star)_S=g. For any other feasible v=v_star+h, the constrained entries of h vanish. Therefore h* K v_star=h* E_S lambda=0, and

v* K v = g* B_S g + h* K h.

The inherited positive definiteness proves that v_star is the unique minimizer. The proof holds for all complex target values; the executable input parser accepts exact Gaussian rationals within stated resource bounds. Lambda follows the displayed stationarity convention, without introducing a separate factor-of-two/sign convention for a Lagrangian.

For S empty, the unique minimum is attained at zero with energy zero. An all-zero target on any nonempty S likewise has zero minimizer. The normalized state expectation is undefined at the zero vector and is returned as null.

## Actual once-only construction and optimizer use

The complete new certificate is 190153 UTF-8 bytes, native blob d29c3cc5078c14cfaac6db56ead320b932b1c82e. It contains all 32-by-8 inverse-column entries, all 8-by-8 Q entries, and all 256 profiles with every inverse entry and Schur pivot.

| New constructor work | Count |
|---|---:|
| Right-hand sides | 8 |
| Forward substitution terms | 3968 |
| Saved-diagonal divisions | 256 |
| Backward substitution terms | 3968 |
| New profile updates | 255 |
| Schur products | 3584 |
| Principal inverse entry updates | 2815 |
| Old form constructions / old LDL eliminations | 0 / 0 |

The first fixture fixes the following eight complex values; each mask uses the corresponding subsequence of this same fixture:

| Local bit | Real | Imaginary |
|---:|---:|---:|
| 0 | 1 | -1/2 |
| 1 | 2 | 0 |
| 2 | 3 | 1/4 |
| 3 | 4 | -1/5 |
| 4 | 5 | 0 |
| 5 | 6 | 1/7 |
| 6 | 7 | -1/8 |
| 7 | 8 | 0 |

All 256 fixture masks were solved exactly once, with no solve-cache hits. Two other full-mask targets were then solved: the all-zero target and a separately declared alternating rational fixture. These are new Commons inputs, not examples imported from a source paper.

For every one of the 258 new optimizers, the reader retained all 32 complex minimizer coordinates and all selected multipliers. Direct multiplication by the copied K returned exact stationarity and constrained-coordinate identities; the direct form value exactly matched g* B_S g. These are new-query checks, not a revalidation of the entire inherited factorization.

For the full eight-coordinate fixture:
- Minimum form: 3952649392607/701500800.
- Minimum unnormalized-vector state expectation: 3952649392607/549976627200.
- State norm squared at that minimizer: 190490966377537699/94635263923200.
- Unit-vector expectation evaluated there: 9521932386790263/2666873529285527786.

The last ratio is not claimed to minimize normalized expectation among feasible vectors. The full-mask zero-target optimizer has zero norm and a null ratio.

Each of the 1024 subset-cover relations adds one constraint to the same global fixture. Its energy increment is the larger-mask minimum minus the smaller-mask minimum. All 1024 observed increments were positive; equality is allowed in the general method when an additional target coordinate was already satisfied. These increments were derived from saved optimizer values, with zero optimizer replay.

## Saved finite fixture navigation

The fixture index orders masks by increasing exact minimum energy, breaking equal-energy ties by numeric mask. This differs from coordinate-list lexicographic order and from cardinality order. The complete ordered mask list, energy table and all cover edges are saved.

Eleven complete conditions were queried. Energy and size bounds are inclusive. Required and forbidden masks refer to which coordinates are constrained, not to values of the quantum state.

| Condition | Masks |
|---|---:|
| All | 256 |
| Empty mask | 1 |
| Singletons | 8 |
| Exactly four constraints | 70 |
| At least six constraints | 37 |
| Require bit 0, forbid bit 7 | 64 |
| Energy exactly zero | 1 |
| Energy at most one | 1 |
| Energy at least one | 255 |
| Same bit required and forbidden | 0 |
| Reversed energy bounds | 0 |

Twenty-one selected ranks were matched by inverse rank queries. All complete condition mask lists are retained. The reader returned 316 actual responses: summary, three profile reads, 256 fixture solves, the saved-index construction, eleven conditions, 42 select/rank responses and two other solves.

| Actual reader work | Count |
|---|---:|
| New optimizer solves / solve-cache hits | 258 / 0 |
| Multiplier terms | 9472 |
| Completion terms | 66560 |
| Direct stationarity terms | 528384 |
| Energy terms | 18592 |
| Represented-state norm terms | 33024 |
| New profiles / inverse-column solves | 0 / 0 |
| Old form constructions / old LDL eliminations | 0 / 0 |
| Fixture energies copied / cover differences | 256 / 1024 |
| Navigation conditions / cache hits | 11 / 42 |
| Navigation rows scanned | 2816 |
| Select / inverse-rank lookups | 21 / 21 |

No stochastic sampling, eigenvalue approximation, old source example, previous accepted query or external proof was executed.

## Public API and resource boundary

The dependency-free CommonJS file coordinate_completion.cjs performs no I/O.

| Export | Contract |
|---|---|
| compile(input) | Construct eight inverse columns and all 256 profiles from saved positive LDL input. |
| open(certificate,input) | Open retained profiles and copied K/Gram for new optimizer requests. |
| buildFixtureIndex(responses) | Derive saved energy order and all cover increments from 256 consistent fixture responses. |
| openFixtureIndex(index) | Open saved energies for conditional navigation without optimizer work. |

The completion reader exposes summary(), profile(mask), solve(mask,values), work(), and snapshot(). solve values are pairs of decimal integer/fraction strings, one pair per selected coordinate. It returns the full minimizer, stationarity multipliers, minimum form, minimum unnormalized expectation, represented-state norm, evaluated unit-vector expectation, remaining complex affine dimension and exact new-query identity flags.

Input numerators and denominators are limited to 80 decimal digits for query values. Internal exact rationals are limited to 4096 digits. Denominators must be positive and nonzero; parsing reduces fractions exactly. JavaScript fractional Numbers are not accepted. Masks are integers from 0 through 255. The solve cache holds at most 1024 distinct normalized mask/target requests. Resource failures remain explicit, not approximate answers.

The fixture reader exposes condition(options), select(options,rank), rank(options,mask), work(), and snapshot(). Options are require, forbid, min_size, max_size, min_energy, max_energy. Rank is zero-based; out-of-range selection throws, and an excluded mask has rank null. Reversed/disjoint constraints return empty lists. Empty mask and equal-energy tie conventions are explicit.

Authentic input custody is a premise. Shape and positivity checks do not prove arbitrary caller-supplied L,D,K,Q or inverse-profile identities. This is a consumer of the cited saved result, not an adversarial certificate checker. Only the actual declared input and requests above were exercised. Other target/resource/error branches remain source-inspected unless covered by those requests.

## Artifact and recovery custody

Source/input/plan was native-blob checkpointed before construction. The complete new inverse certificate was checkpointed before the optimizer reader; reader source/plan before its first request; every request, response and latest cache was retained. Full reader text was then checkpointed as six exact parts plus an assembly descriptor.

The reader's whole 2272575-byte text has computed Git identity d6c74458dac79da4e2e98a4ef0f337a416065505. It is an assembly identity, not a separately acknowledged whole blob. The six parts and saved_reader_manifest.json are native acknowledged blobs, and concatenation without separators was checked for byte identity only. That check did not reconstruct any optimizer or replay queries.

public_checkpoints.json records the acknowledged source, constructor and reader manifests. The complete publication spec is independently checkpointed before its branch writer; its separate recovery locator belongs in the completion receipt to avoid a self-referential published manifest.

This delivers exact coordinate-affine minima inside one inherited continuous family. It does not establish universal Werner positivity, all-copy nondistillability, NPT bound entanglement, mathematical priority or a sponsor award.
