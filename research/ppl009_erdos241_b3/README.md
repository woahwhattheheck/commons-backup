# Erdős 241 — finite Bose–Chowla construction and saved triple decoding

Status: **PUBLIC CUBIC CONSTRUCTION / COMPLETE AFFINE ORBIT / SAVED TRIPLE DECODER / FINITE CERTIFICATES**.

Erdős 241 asks whether the largest $B_3$ subset of $\{1,\ldots,N\}$ has size asymptotic to $N^{1/3}$. A $B_3$ set permits repeated summands: equal three-term sums must have identical multisets, with reorderings treated as the same representation.

This directory makes the classical Bose–Chowla finite-field construction usable in connected V8. The API validates a monic cubic over a bounded prime field, certifies a primitive element and its degree-three basis, retains the complete power/discrete-log table, and maps its modular set to a short positive interval.

| File | Purpose |
|---|---|
| [bose_chowla_b3.cjs](bose_chowla_b3.cjs) | Public bounded constructor, exact field/order/degree evidence and largest-gap interval lift. |
| [BOSE_CHOWLA_B3_API.md](BOSE_CHOWLA_B3_API.md) | Source conventions, classical construction argument, exact mapping, input/resource limits and actual results. |
| [prime13_cubic_b3_construction.json](prime13_cubic_b3_construction.json) | Complete request, all 2,196 power-cycle entries, every candidate/offset/gap witness, output set and source identities. |
| [prime13_affine_orbit_minimum.json](prime13_affine_orbit_minimum.json) | Complete accepted affine-orbit coverage, gaps and optimal positive lifts. |
| [bose_chowla_triple_decoder.cjs](bose_chowla_triple_decoder.cjs) | Decode a modular or ordinary three-term sum from the identified saved construction, including repeated terms. |
| [TRIPLE_DECODER_API.md](TRIPLE_DECODER_API.md) | Decoder proof, API, source contract, exact source identities, bounds and complete work accounting. |
| [prime13_saved_triple_decoding.json](prime13_saved_triple_decoding.json) | One new open, six query results, four monic cubics and all 44 quotient/remainder records. |

## Original constructed set

For $p=13$ and $F(T)=T^3-2$, the constructor selects $\theta=7+\alpha$ in $\mathbb F_{13}[\alpha]/(\alpha^3-2)$. It gives

$$
B=\{1,75,214,574,616,724,862,963,1322,1408,1454,1527,1802\}
$$

and therefore the finite lower bound

$$
f(1802)\ge13.
$$

The set is $B_3$ modulo 2196, hence also under ordinary integer addition. The classical polynomial argument certifies all 455 unordered triples with repetition. Their sums are not enumerated. A largest cyclic gap of 395 gives interval length 1802, optimal only among cuts of this particular residue set.

The original constructor call used 2,368 field multiplications. Every field-cycle entry and all 13 base-field-offset/discrete-log identities are retained, so a later consumer can reuse them directly. No accepted example, earlier Sidon enumeration or asymptotic bound was rerun.

## Exact optimization of the retained affine orbit

The same module now exports a generic finite cyclic-set optimizer. It verifies supplied translation/reflection symmetries, covers every unit multiplier through disjoint symmetry cosets, and retains every representative gap plus every optimal unit/cut witness. The accepted field constructor and complete power dataset are unchanged.

For the retained source modulo 2196, the six-element subgroup reduces all 720 units to 120 classes. The complete search finds maximum gap 1153, uniquely at representative 257, with six optimal unit/cut witnesses. Its selected positive lift is

$$
\{1,13,32,66,169,174,396,416,756,858,915,1016,1044\},
$$

giving $f(1044)\ge13$ by the accepted modular $B_3$ premise. Endpoint 1044 is minimal only in this specified affine orbit. The 120 transformed residue sets, all 1,560 gaps, complete 720-unit coverage and six optimum parameters are in [prime13_affine_orbit_minimum.json](prime13_affine_orbit_minimum.json).

No field, power-cycle or triple-sum computation was replayed. The generic optimizer does not certify a supplied set's $B_3$ property; this application inherits it from the identified complete construction. Details and bounds are in Section 8 of the existing guide.

## Decode a sum from the saved construction

The new `openBoseChowlaTripleDecoder` API uses the original construction's
`result` object and explicit source/affine identifiers. For the accepted
optimal lift it uses unit `257` and translation `1952` modulo `2196`. It reads
the saved powers, changes to the basis `1, theta, theta^2` and constructs the
unique monic cubic associated with a normalized sum. Factoring that cubic over
the 13-element base field recovers the unique triple, including multiplicity.

A modular query decodes its residue. An ordinary integer query additionally
compares the actual sum of the positive representatives. The recorded consumer
shows why that distinction matters:

| Query | Result |
|---|---|
| Integer `1042` | `13 + 13 + 1016` |
| Modular `10^500 * 2196 + 1042` | Same triple, reusing its cached polynomial |
| Integer `3132` | `1044 + 1044 + 1044` |
| Integer `936` | Rejected as an integer sum: its unique modular triple sums to `3132` |
| Modular `1830` | No representation; all 13 offset remainders are retained |
| Integer `1464` | `32 + 416 + 1016` |

The actual consumer used one decoder open, four integer queries and two
modular queries. It created four polynomials, reused two, and performed 44
synthetic divisions. All 182 new base-field scalar products and 176 scalar
additions are accounted for. Source construction, primitive tests, cycle
generation, extension-field multiplication, field powers, affine-orbit search
and triple enumeration were all zero in this consumer.

The complete source datasets remain unchanged and separately identified. The
decoder checks structure and references, then relies on their established
mathematical premises. Its activity snapshot retains every new polynomial and
query; it is not a cache-restoration format. See
[TRIPLE_DECODER_API.md](TRIPLE_DECODER_API.md) for the proof, API, exact limits
and the distinction between source validation and source authentication.

## Attribution and scope

The construction is due to **R. C. Bose and S. Chowla**, *Theorems in the additive theory of numbers*, Comment. Math. Helv. 37 (1962/63), 141–147. The guide links their original author report and Nathanson's precise author-primary restatement. It binds the positive-set/multiset convention to the inspected FormalConjectures source.

This implementation covers prime fields of degree three within explicit runtime limits. It does not claim an exact extremal value, a new external record, an asymptotic improvement, the full conjecture, or priority for the classical method. No sponsor submission or payment is involved.
