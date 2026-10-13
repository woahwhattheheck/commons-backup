# Exact Hesse SIC probability compatibility

This finite package decides whether specified probability vectors for the known Hesse qutrit SIC reconstruct positive semidefinite states. It retains all 511 nonempty uniform outcome supports and their seven principal-minor polynomials under depolarizing noise. It does not construct a new SIC, establish another dimension, or resolve the infinite-dimension prize problem.

At visibility 1, exactly 22 of the uniform distributions are physical: 12 supports of size 6 reconstruct pure states, nine supports of size 8 reconstruct rank-two states, and the full support reconstructs the maximally mixed state. The saved reader additionally finds all 511 supports physical at visibility 1/4 and 202 at visibility 1/2. These are results for this explicitly labelled measurement and probability family, with no novelty claim.

## Sources and fixed input

The [PPL145 card](https://prizeproblems.org/problems/145/) links the [official KCIK award page](https://kcik.ug.edu.pl/kcik-awards/) and Horodecki, Rudnicki and Życzkowski's [Five open problems in theory of quantum information](https://kcik.ug.edu.pl/wp-content/uploads/2021/12/2002.03233.pdf), dated 21 December 2020. Section II.A defines a SIC by N² normalized vectors with squared pairwise overlaps (N delta + 1)/(N+1). The problem asks for explicit constructions along an infinite sequence of dimensions; the award page also allows proving finiteness. Its displayed award and application terms concern 2023 and January 2024, with an annual renewal clause. No current submission window, eligibility, award or progress toward that prize is claimed. No sponsor was contacted.

The concrete coordinates and reconstruction are from Blake C. Stacey, [SIC-POVMs and Compatibility among Quantum States](https://arxiv.org/html/1404.3774v4), v4, 7 June 2016, §II, Eqs. 14, 16 and 17. Write w = exp(2 pi i/3), so w² = -1-w. The nine normalized vectors are the successive columns, indexed 0 through 8, of 1/sqrt(2) times this matrix:

| Row | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | -1 | 1 | 0 | -1 | 1 | 0 | -1 | 1 |
| 1 | 1 | 0 | -1 | w | 0 | -w | w² | 0 | -w² |
| 2 | -1 | 1 | 0 | -w² | w² | 0 | -w | w | 0 |

With Pi_i the rank-one projector for column i, the source's qutrit formulas are

    rho = 4 sum_i p_i Pi_i - I,
    p_i = tr(rho Pi_i)/3.

These known SIC coordinates and identities are premises. The consumer forms their outer products as prerequisites for new probability-vector work; it does not run an SIC Gram check, repeat a proof of equiangularity, or construct mutually unbiased bases. The source's nearby probability examples, classified subsets and MUB examples were not imported.

The declared input is in input.json. The compiler is specialized to a nine-outcome, three-dimensional SIC premise; merely supplying an arbitrary 3-by-9 array does not establish that premise. Its basic token and shape checks are not a SIC verifier.

Ownership searches were bounded: the math-channel search for SIC returned only the original intake, and the Commons PR search returned no result. Retained-custody checks named no prior same consumer. This is not a proof that no related work exists. Previously completed MUB work remains protected. SOURCE_QUALIFICATION.md records those distinctions.

## Probability family and exact algebra

For a nonempty support S subset of {0,...,8}, let k = |S| and set p_i = 1/k on S and zero elsewhere. The empty support is excluded. At rational visibility t in [0,1], the full specified vector is

    p_i(t) = t p_i + (1-t)/9,
    rho_S(t) = t rho_S + (1-t) I/3.

Thus t=1 is the original uniform-support distribution, and t=0 is the maximally mixed state. At t<1 every outcome has positive probability. The support mask labels the original uniform component; it is not the support of the noisy distribution. This is not reconstruction from unknown missing observations, nor a claim that discarding measurement results physically implements the reconstructed state.

All calculations use exact integers in Z[w]. An entry a+bw is stored as two integer strings. Multiplication uses w²=-1-w; conjugation sends (a,b) to (a-b,-b). No floating-point eigenvalue, tolerance or numerical square root is used.

Let v_i be an unnormalized source column, Q_i = v_i v_i*, and Pi_i = Q_i/2. The compiler forms

    A_S = 4 sum_(i in S) Q_i - 2k I,
    rho_S = A_S/(2k),
    H_S(t) = 3t A_S + 2k(1-t)I,
    rho_S(t) = H_S(t)/(6k).

It saves A_S and each of the seven nonempty principal-minor polynomials of H_S(t): three of order one, three of order two and one of order three. Although entries use Z[w], these determinant coefficients are real integers because H_S(t) is Hermitian. The implementation retains this real-coefficient condition explicitly.

For every fixed t, rho_S(t) is positive semidefinite exactly when those seven principal minors are nonnegative. Necessity follows from principal restrictions. For sufficiency, det(xI+M) has as coefficients the sums of principal minors of each order. If they are nonnegative, that polynomial is strictly positive for x>0. A negative eigenvalue of a Hermitian M would give a positive root, a contradiction. For a positive semidefinite matrix, the largest order of a positive principal minor is its rank. This elementary argument supports the finite certificate; it is not a reviewed proof from the cited paper.

A negative principal minor is an explicit nonphysicality witness. The reader reports its vertex subset, exact numerator, positive denominator and reduced value. Nonphysical matrices get rank=null: the API does not report their algebraic rank as a physical state rank. Rank one means a pure state because the SIC premises give trace one.

The inherited overlap identity also yields tr(rho_S²)=12/k-1. Under noise the saved-reader purity formula is

    tr(rho_S(t)²) = 1/3 + t² (12/k - 4/3).

That value alone is not used as a substitute for all principal-minor tests.

## Complete construction and finite results

The one construction formed nine Q_i matrices using 81 field-product entries, then 4,599 subset-matrix entry additions. It retained 3,577 principal polynomials, using 33,066 polynomial field products and 9,592 coefficient additions at t=1. Old SIC Gram checks and old MUB calls are both zero.

| Support size | Physical at t=1 | Physical rank | Nonphysical |
|---:|---:|---:|---:|
| 1 | 0 | — | 9 |
| 2 | 0 | — | 36 |
| 3 | 0 | — | 84 |
| 4 | 0 | — | 126 |
| 5 | 0 | — | 126 |
| 6 | 12 | 1 | 72 |
| 7 | 0 | — | 36 |
| 8 | 9 | 2 | 0 |
| 9 | 1 | 3 | 0 |

The saved reader's complete t=1/2 condition has 202 physical masks, distributed by support size as 72 of size 5, all 84 of size 6, all 36 of size 7, all nine of size 8 and the full size-9 support. The t=1/4 condition contains all 511 masks. At t=3/4, exactly 12 size-six supports pass. The separate t=2/3 query for size-four supports within outcomes 0 through 7 has no member. These are queried rational slices; no maximal visibility or entire interval boundary was computed.

The source input and exact state formulas do not turn these finite counts into a theorem about SIC existence in unbounded dimensions. In particular the 12 pure outputs are not credited as a new construction of a classical configuration.

## Saved reader API

```javascript
const {loadSavedIndex} = require('./load_saved_index.cjs');
const index = loadSavedIndex();
const family = index.condition({visibility:'1/2', size:5});
const first = index.select(family.key, 0);
const inverse = index.rank(family.key, first.mask);
const state = index.state(511, '1');
```

The committed evidence is the actual reader manifest and its classification shards. The example explains calls; no application or runtime command was rerun after production.

| Method | Meaning |
|---|---|
| summary() | Retained construction summary and noiseless profiles |
| classify(mask,t='1') | Exact seven principal-minor values, physical flag, state rank and first negative witness |
| state(mask,t='1') | Reconstructed matrix, all nine probabilities, purity and physicality information |
| condition(filter) | Cached mask family, count and counts by support size |
| select(key,rank) | State at zero-based rank in the chosen family |
| rank(key,mask) | Inverse rank, or null when absent |
| exportCaches() | Complete classification and condition caches |
| work() | Actual saved-data and fresh arithmetic counters |

Visibility accepts a nonnegative rational string such as '3/4', '0', or '1'. Integer numeric inputs must be safe integers; fractional JavaScript numbers are rejected. Rational strings are reduced, and values outside [0,1] are rejected. Arbitrarily large numerators and denominators are supported through BigInt. The actual consumer uses two visibilities with denominator 10^100+1.

A mask is the ordinary nine-bit integer with bit i selecting source outcome i. The available/include/exclude condition fields use masks in [0,511]; include and exclude must be disjoint subsets of available. The size filter, if present, ranges from 1 to 9. psd may be true, false, or null (no positivity restriction); rank, if supplied, requests a physical rank 1,2 or 3. An empty admissible family is retained with count zero, and the consumer schedules no rank selection for it.

All family ranks use increasing integer mask, preserving labelled outcomes. This is not an orbit count, a basis permutation quotient, or lexicographic order of probability coordinates.

For a polynomial c_0+...+c_d t^d at t=n/q, the reader uses homogeneous Horner arithmetic to produce the exact numerator sum_i c_i n^i q^(d-i), with denominator q^d. The principal-minor denominator additionally contains (6k)^r for order r. At t=1 it reuses the retained construction value. It never regenerates an outer product, subset matrix or determinant polynomial.

The state method computes fresh affine entries from saved A_S. It returns each matrix entry as {a,b} meaning a+bw, with reduced rational strings, and explicitly counts those new evaluations. The reader performs structural setup and trusts the saved certificate's mathematics; it is not a replaying proof verifier.

## Actual consumer evidence

The reader completed 102 responses and 40 inverse comparisons, all equal. All 22 physical noiseless states were exported completely. Nine condition caches and 1,691 classification records are retained, including the queried negative witnesses and large-denominator states.

Fresh work comprised:

- 511 structural rows and 4,599 condition-row scans.
- 8,260 saved-polynomial evaluations and 13,872 homogeneous Horner steps.
- 1,207 classification-cache hits and 207 rank comparisons.
- 40 selected records, 432 affine matrix-entry evaluations, 432 probability entries and 48 purity evaluations.
- Zero new projector outer products and zero new principal polynomials.

These counters describe the one production consumer. No error occurred and no accepted response was rerun.

## Checkpoints and file assembly

The new public source, literal input, construction plan and source qualification were native-blob checkpointed before construction. Their compact recovery manifest is 56b0b3d64803e09110c8d8a84199ff3a52d46533.

The complete construction was acknowledged before reader use as Git blob 367eff988b4da4cd7404a5dd589e1825c3b287b7, 1,271,755 UTF-8 bytes; its recovery manifest is 089cbf4096db5612f838ba2c2f31fa34b041a24e. The reader source and plan were checkpointed next under manifest d09287b1c598caebaa6fb0a76d6f42e45f2c3373. The complete compact reader evidence was acknowledged as 59b65bdff3059e8f9912fd4ffa5cf8667071e472, 1,328,890 bytes, under manifest 7808a4ea16d818e4568fc9d73893f8ce89c7a85d.

Every reader request was retained before invocation, and every returned result, cache state and work state immediately afterward. Public manifests omit private provider and Slack envelopes. Acknowledged unreferenced Git objects do not carry a claim of indefinite retention; ordinary repository publication is separate.

For bounded repository files, certificate_manifest.json stores the base object and four 128-record shards; the first record is the null sentinel at mask zero. reader_manifest.json stores the full outputs, comparisons, conditions, exports and other caches, while seven shards retain all classification records in original order. The saved loader assembles these objects. Serializing the certificate with two-space JSON indentation and a final newline exactly reproduces 367eff98..., while compact serialization plus newline of the reader exactly reproduces 59b65bdf.... Both full byte identities were checked from the assembled pieces without redoing mathematics.

The frozen publication spec is checkpointed separately before any branch write. The exact publication receipt supplies the resulting commit and file identities. No private native journal is part of this source package.
