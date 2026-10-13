# Bose–Chowla B3 construction in a cubic prime-field extension

Status: **PUBLIC CONNECTED-V8 CONSTRUCTOR / COMPLETE FINITE-FIELD CERTIFICATE / EXPLICIT POSITIVE-INTEGER SET**.

The actual new input in this package gives

$$
B=\{1,75,214,574,616,724,862,963,1322,1408,1454,1527,1802\}.
$$

Every equality between two sums of three members of $B$, with repetitions allowed, identifies the same multiset of summands. Thus, with the Erdős 241 convention,

$$
f(1802)\ge13.
$$

This is a finite instance of the classical Bose–Chowla construction. It does not identify $f(1802)$ exactly, improve an asymptotic bound, or establish an external construction record. The saved artifact includes the entire 2,196-entry field-power cycle and every map used to obtain $B$.

The downstream optimizer in Section 8 now reduces this retained construction's interval endpoint to 1044 by exact unit-orbit search. Its complete source and finite optimality boundary are recorded separately.

## 1. Source and representation conventions

The [FormalConjectures statement of Erdős 241](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/241.lean), read at blob `da73dfa46653a1f32f47defc09eb53e5836f4c69`, defines $f(N)$ as the largest cardinality of a subset of $\{1,\ldots,N\}$ whose three-term sums have no nontrivial coincidences. Its definition compares multisets of cardinality three. A coordinate may therefore repeat; different orders of the same three summands are the same representation. Zero is not an element of the final positive-integer set.

The asymptotic question $f(N)\sim N^{1/3}$ is distinct from producing one such set. The formal source credits Bose and Chowla for the known lower construction. This delivery uses that construction and leaves the asymptotic equality open.

**Original credit:** R. C. Bose and S. Chowla, *Theorems in the additive theory of numbers*, Commentarii Mathematici Helvetici 37 (1962/63), 141–147, DOI [10.1007/BF02566968](https://doi.org/10.1007/BF02566968). Their [November 1960 author report](https://www.cs.umd.edu/~gasarch/COURSES/858/S13/BoseChowla.pdf), Theorem 1, gives the finite-field exponent construction; its Example 1 explicitly allows repeated summands. That example is not rerun here.

For a clear author-primary restatement, see Melvyn B. Nathanson, [*The Bose-Chowla argument for Sidon sets*, Journal of Number Theory 238 (2022), 133–146](https://www.theoryofnumbers.com/melnathanson/pdfs/nath2022-198.pdf), Theorem 1. It assumes a degree-$h$ extension of a field of prime-power order $q$ and a multiplicative generator $\theta$, and obtains $q$ residues with unique $h$-term sums modulo $q^h-1$, up to permutations. The signs $\theta+\lambda$ and $\theta-\lambda$ give the same set as $\lambda$ ranges over the base field.

This implementation specializes to prime $p$ and $h=3$. No extension to arbitrary prime powers or other orders is implied by its executable contract.

## 2. Exact field and generator certificates

Let

$$
F(T)=T^3+f_2T^2+f_1T+f_0\in\mathbb F_p[T]
$$

be monic and irreducible. The constructor takes the three lower coefficients in constant-to-quadratic order.

Primality is checked by exact trial division through $\lfloor\sqrt p\rfloor$, with the remainders retained. For a cubic, irreducibility is equivalent to having no root in the base field: a proper factorization of degree three has a factor of degree one. The constructor retains every value $F(t)$ for $t=0,\ldots,p-1$, all nonzero on success.

The quotient

$$
K=\mathbb F_p[T]/(F),\qquad \alpha=T\bmod F,
$$

is therefore a field with $p^3$ elements. An element $c_0+c_1\alpha+c_2\alpha^2$ is encoded by

$$
c_0+pc_1+p^2c_2,\qquad0\le c_i<p.
$$

Codes are field-vector labels, not integer representatives that can be multiplied without reduction. The multiplication routine convolves the two coefficient triples and reduces high powers using

$$
\alpha^3=-f_0-f_1\alpha-f_2\alpha^2.
$$

All coefficients are reduced modulo $p$ after each reduction step.

Put $M=p^3-1$. The constructor factors $M$ exactly. For a nonzero candidate $\theta$, it checks

$$
\theta^M=1,\qquad
\theta^{M/\ell}\ne1
\quad\text{for every prime }\ell\mid M.
\tag{1}
$$

These conditions certify order $M$. The order divides $M$ in $K^\times$. If it were a proper divisor, some prime divisor of the quotient would force the order to divide $M/\ell$, contradicting (1).

Automatic selection examines encoded elements starting at code $p$, in increasing order. Codes below $p$ are in the base field and cannot have order $p^3-1$. Every attempted candidate's completed prime-factor tests are retained; rejected candidates stop at their first equality to one. A caller may instead supply an explicit generator code, which must pass the same certificate.

### Degree-three certificate

The record also retains the coefficient columns of $1,\theta,\theta^2$ and their determinant modulo $p$. Its nonzero value certifies that no nonzero base-field polynomial of degree at most two vanishes at $\theta$. This is the exact degree property needed in the additive construction.

Finally, the constructor builds the complete power cycle

$$
1,\theta,\theta^2,\ldots,\theta^{M-1},
$$

in that order. It rejects an early repeat or zero value and checks that the next product is one. There are exactly $M$ distinct nonzero field codes, so the table covers $K^\times$ and supplies its discrete-log inverse. The saved power list alone is enough to reconstruct that inverse by integer indexing; the inverse is not redundantly stored.

## 3. The modular B3 construction

For each $\lambda\in\mathbb F_p$, define the unique exponent $a_\lambda$ by

$$
\theta^{a_\lambda}=\theta+\lambda,\qquad 0\le a_\lambda<M.
\tag{2}
$$

The degree certificate implies $\theta\notin\mathbb F_p$. Consequently $\theta+\lambda$ is neither zero nor one, so

$$
1\le a_\lambda\le M-1.
$$

Distinct offsets give distinct field elements and therefore distinct exponents. The constructor produces a $p$-element set $A$ of canonical positive residues.

Here is the classical argument specialized to the retained degree certificate. Suppose

$$
a_{\lambda_1}+a_{\lambda_2}+a_{\lambda_3}
\equiv
a_{\mu_1}+a_{\mu_2}+a_{\mu_3}
\pmod M.
$$

Using (2), the monic cubic polynomials

$$
P(T)=\prod_{i=1}^3(T+\lambda_i),\qquad
Q(T)=\prod_{i=1}^3(T+\mu_i)
$$

have $P(\theta)=Q(\theta)$. Their leading terms cancel, so $P-Q$ has degree at most two. The nonzero basis determinant forces $P-Q=0$. Unique factorization into monic linear factors then gives equality of the offset multisets, including repeated factors and their multiplicities. The offset-to-exponent map is injective, so the exponent multisets agree.

Thus $A$ is $B_3$ **modulo $M$**. Ordinary integer equality implies the same congruence, hence also has only trivial coincidences. This does not assert injectivity on ordered triples or uniqueness across sums of different lengths.

The $p$-element set has $\binom{p+2}{3}$ unordered triples with repetition. The algebraic certificate makes their sum residues distinct; the constructor does not enumerate these triples or their sums.

## 4. Mapping to a short positive interval

The canonical residues are sorted cyclically. For each adjacent pair, including the wrap from the last back to the first, the constructor records its positive cyclic distance. Let a largest gap have distance $g$ and let $s$ be the first selected residue after it.

Define

$$
b(a)=((a-s)\bmod M)+1.
\tag{3}
$$

The complementary closed arc contains all selected residues and has $M-g$ steps. Therefore

$$
B=\{b(a):a\in A\}\subseteq[1,M-g+1],
$$

with both endpoints attained. Equation (3) is a common residue translation by $1-s$. It preserves fixed-length modular sum uniqueness because the same threefold translation cancels on both sides of any equality. Distinct integer lifts of the distinct residue classes remain distinct, so $B$ is an ordinary positive-integer $B_3$ set.

This cut minimizes the containing interval length among cyclic cuts of this particular residue set. Any such containing arc omits an empty gap between adjacent selected residues; that omitted distance cannot exceed the largest recorded gap. The optimum is consequently $M-g+1$. If largest gaps tie, the API chooses the one with smallest following residue and also returns every tied gap.

This limited optimality claim does not optimize over different field polynomials, generators, unit multipliers, arbitrary integer constructions or all $B_3$ sets.

## 5. API and hard bounds

The CommonJS module exports:

- `constructBoseChowlaB3(options)`
- `BOSE_CHOWLA_B3_LIMITS`
- `minimizeCyclicUnitOrbit` — the downstream finite orbit optimizer in Section 8
- `CYCLIC_ORBIT_LIMITS`

Input has the form:

```js
{
  prime: 13,
  cubic_coefficients: [11, 0, 0]
  // generator_code: optional nonzero encoded field element
}
```

The example means $F(T)=T^3+11=T^3-2$ over $\mathbb F_{13}$. The leading coefficient one is implicit. Each coefficient must already be a canonical residue in $[0,p-1]$; negative coefficients are not silently normalized.

| Limit | Value |
|---|---:|
| Prime input | 2 through 43, with exact primality check |
| Polynomial degree | Exactly three, monic |
| Complete field size | At most 79,507 |
| Automatic primitive candidates | At most 4,096 |
| Total field multiplications | At most 2,000,000 |

Inputs use safe-integer JavaScript numbers. Numeric strings, fractional values, infinities and out-of-range coefficients/codes are rejected. The optional generator must be an integer code from one through $p^3-1$. Omitting it requests deterministic selection; supplying it never triggers a silent replacement if it is nonprimitive.

Malformed object/array shapes give `TypeError`. Range, primality and resource errors give `RangeError`. A root gives `ReduciblePolynomialError` with a root witness; a rejected supplied generator gives `NonPrimitiveElementError` with its order-test witness. Exhausting the automatic candidate limit retains the attempted candidate records and work; exhausting the multiplication limit retains work. A resource-limit error is an unfinished construction, not evidence that a primitive element or $B_3$ set does not exist.

The fixed cubic degree and $p\le43$ keep arithmetic exact in JavaScript numbers: a raw product coefficient is at most $3(p-1)^2\le5292$, while encoded field elements and group exponents are below 79,507. No floating-point approximation is used to determine a field value or set property.

### Complete returned record

Successful output has schema `erdos241.bose_chowla_b3/v1` and status `EXACT_CONSTRUCTED_B3_SET`. It includes:

- prime trial remainders and all cubic root values;
- field encoding and the complete group-order factorization;
- all attempted primitive candidates and their exact power witnesses;
- the nonzero degree-three determinant and basis columns;
- the complete power cycle indexed by exponent;
- every base-field offset, target field code/coefficient triple and discrete log;
- canonical residues, every cyclic gap, the selected translation and all positive lifts;
- finite $B_3$ consequences, explicit scope flags, limits and actual work.

The power cycle is an actual finite computation. The all-triples uniqueness consequence is the classical algebraic theorem applied to its retained field/order/degree inputs, not an enumerated sum census.

For $M=p^3-1$, producing the complete table uses $M$ field multiplications and $O(M)$ storage. Generator testing uses bounded binary exponentiation with one test per relevant prime factor until rejection, plus the full-order check on success. The constructor never enumerates candidate subsets or triple sums.

## 6. Actual p=13 construction

The polynomial input is $T^3-2$. Its values at $0,\ldots,12$, modulo 13, are

$$
11,12,6,12,10,6,6,3,3,12,10,3,10,
$$

all nonzero. The field has 2,197 elements, and

$$
M=2196=2^2\cdot3^2\cdot61.
$$

The automatic search examined codes 13 through 20 and selected

$$
\theta=7+\alpha,\qquad \alpha^3=2.
$$

Its primitive-element witnesses are:

| Power | Exact field value |
|---|---|
| $\theta^{2196}$ | $1$ |
| $\theta^{1098}$ | $12$ |
| $\theta^{732}$ | $9$ |
| $\theta^{36}$ | $2+5\alpha+7\alpha^2$ |

Also $\theta^2=10+\alpha+\alpha^2$, so the coefficient columns of $1,\theta,\theta^2$ have determinant one. The complete saved cycle contains all 2,196 nonzero field codes and closes at one.

The extracted residues are

$$
A=\{1,276,671,745,884,1244,1286,1394,1532,1633,1992,2078,2124\}.
$$

All thirteen offset identities and their positive lifts are retained:

| Offset $\lambda$ | Exponent $a_\lambda$ | Positive lift $b(a_\lambda)$ |
|---:|---:|---:|
| 0 | 1 | 1527 |
| 1 | 1633 | 963 |
| 2 | 1532 | 862 |
| 3 | 276 | 1802 |
| 4 | 745 | 75 |
| 5 | 2124 | 1454 |
| 6 | 671 | 1 |
| 7 | 1244 | 574 |
| 8 | 1394 | 724 |
| 9 | 884 | 214 |
| 10 | 1992 | 1322 |
| 11 | 1286 | 616 |
| 12 | 2078 | 1408 |

The unique largest gap is from 276 to 671, with distance 395. The selected start is 671 and the residue translation is 1526 modulo 2196. The exact interval endpoint is

$$
N=2196-395+1=1802.
$$

This yields the set displayed at the start of the guide and the finite lower bound $f(1802)\ge13$. Its 455 unordered triples with repetition have distinct residues modulo 2196 by the construction. Those 455 residues are not enumerated or retained individually.

### Actual work

The single new constructor call used two prime trial divisors, 13 root evaluations, eight primitive candidates, 13 field exponentiations and 2,368 total field multiplications. The latter consist of 171 exponentiation multiplications/squarings, one degree-certificate product and 2,196 cycle steps. It used 13 discrete-log lookups and inspected 13 cyclic gaps.

The observed runtime was 9 ms in this connected-V8 invocation. This is one observation, not a statistical benchmark. The complete [prime13_cubic_b3_construction.json](prime13_cubic_b3_construction.json) contains the exact request, result, source identities and execution account. No accepted finite-field example, earlier Sidon enumeration, theorem proof or asymptotic estimate was rerun.

## 7. Connected use

Given the module text obtained from a connected repository read:

```js
const module = { exports: {} };
new Function("module", "exports", moduleText)(module, module.exports);

const result = module.exports.constructBoseChowlaB3({
  prime: 13,
  cubic_coefficients: [11, 0, 0]
});

const positiveB3Set = result.interval_lift.values;
const completePowerTable = result.power_cycle.codes;
```

The retained dataset already contains this completed input; the snippet documents the public interface. Subsequent arithmetic consumers can read its set, offset map or complete power table without repeating the construction.

The contribution is a reusable finite constructor and exact source artifact. Bose–Chowla's theorem and the existing source authors retain their attribution. No extremal equality, asymptotic improvement, formula priority, general-conjecture resolution, external submission or payment is asserted.

## 8. Exact interval optimization over a cyclic unit orbit

The module additionally exports `minimizeCyclicUnitOrbit` and `CYCLIC_ORBIT_LIMITS`. This operation consumes an identified finite cyclic set and optimizes its positive interval over all unit multipliers and translations. It does not construct a field or certify that an arbitrary supplied set is $B_3$.

### Symmetries and complete quotient coverage

Let $A\subseteq\mathbb Z/M\mathbb Z$ be a nonempty finite set. A supplied symmetry consists of a unit $h$, a sign $\varepsilon\in\{-1,1\}$ and a residue $t$, with

$$
hA=\varepsilon A+t.
\tag{4}
$$

The API checks this as an exact equality of sorted residue sets. It also checks that the distinct supplied multipliers contain one and are closed under multiplication. A finite nonempty multiplicatively closed subset of the unit group is a subgroup $H$: the powers of any member eventually give its identity and inverse inside the set.

For a unit $u$ and $h\in H$, equation (4) gives

$$
uhA=\varepsilon(uA)+ut.
\tag{5}
$$

Translation leaves all cyclic gap lengths unchanged; reflection reverses their order while preserving lengths. Thus one representative of every coset $uH$ suffices for interval minimization. The API enumerates every integer from one to $M-1$, keeps exactly those with gcd one, and partitions them into disjoint cosets. It retains every member of every class, then computes the entire gap list of each representative's transformed set.

This is exact reduction by a verified symmetry subgroup. The subgroup need not contain every possible symmetry. A smaller valid subgroup causes more representatives to be evaluated and does not weaken completeness.

For each representative, the shortest positive interval has length $M-g+1$, where $g$ is its largest cyclic gap, as proved in Section 4. Maximizing $g$ over all representatives therefore gives the exact minimum over the full finite affine unit/translation orbit.

### Transporting every optimal cut

Every maximum gap of every best representative is retained. To recover its cut for a unit $uh$, use the map $x\mapsto\varepsilon x+ut$. If $\varepsilon=1$, transform both gap endpoints in their original order. If $\varepsilon=-1$, transform them and reverse their order. This gives all optimal unit/cut witnesses without evaluating a second residue list for each member of the coset.

The output orders these witnesses by unit and then by start residue. Its chosen positive set comes from the first witness. Counts of witnesses are counts of unit/cut parameters; different witnesses may produce the same normalized integer set.

### The retained source symmetry

The actual consumer reads the accepted #31278 residue set from `prime13_cubic_b3_construction.json`, blob `2b77e0e8dc97c5107ab5a4e5cca162a92c12de38`. It reads the existing power-table entry at exponent 1464, whose field code is three. No field multiplication, exponentiation or original constructor call is repeated.

From the already specified relation $\alpha^3=2$, elementary algebra in characteristic 13 gives

$$
\alpha^{13}=\alpha(\alpha^3)^4=3\alpha,
\qquad
\theta^{13}=7+3\alpha=3\theta+12.
$$

As $\lambda$ ranges over $\mathbb F_{13}$, the elements $(\theta+\lambda)^{13}$ therefore run through $3(\theta+\mathbb F_{13})$. The accepted logarithm entry gives

$$
13A=A+1464\pmod{2196},
\qquad
169A=A+732\pmod{2196}.
$$

Together with reflection, these supply the following six symmetry records. The optimizer checks all six set relations directly on the retained thirteen residues.

| Multiplier $h$ | Sign $\varepsilon$ | Translation $t$ |
|---:|---:|---:|
| 1 | 1 | 0 |
| 13 | 1 | 1464 |
| 169 | 1 | 732 |
| 2027 | −1 | 1464 |
| 2183 | −1 | 732 |
| 2195 | −1 | 0 |

There are 720 units modulo 2196 and 120 cosets of this subgroup. Complete class membership, every transformed representative set and every gap are saved in [prime13_affine_orbit_minimum.json](prime13_affine_orbit_minimum.json).

### Actual optimum and finite consequence

This continuation optimizes only the finite affine orbit of the accepted thirteen-element Bose–Chowla set modulo 2,196. The recorded computation covers all 720 units through 120 six-element symmetry cosets and retains all 1,560 examined gaps. Its unique best representative is 257: the largest circular gap is 1,153, giving a positive lift with endpoint 1,044. Six optimal unit/cut witnesses are retained. Thus 1,044 is the smallest endpoint attained within this specified affine orbit; it is not a global optimality statement for all thirteen-element integer $B_3$ sets.

The $B_3$ property is inherited from the accepted construction. Multiplication by a unit is invertible modulo 2,196, so it preserves uniqueness of fixed-length modular sums. A common translation adds the same threefold translation to both sides of a three-term equality, which cancels. These statements allow repeated coordinates and identify representations up to permutation. Any ordinary integer equality between the resulting positive representatives would also be a modular equality, so the displayed set is an integer $B_3$ set. The original constructor, power cycle and accepted uniqueness argument were not rerun.

The selected map is

$$
a\longmapsto((257a-245)\bmod2196)+1.
$$

It produces

$$
B_{\mathrm{orbit}}=
\{1,13,32,66,169,174,396,416,756,858,915,1016,1044\},
$$

and hence

$$
f(1044)\ge13.
$$

The six complete optimum parameters are:

| Unit multiplier | Start residue | Common residue translation | Gap endpoints |
|---:|---:|---:|---|
| 257 | 245 | 1952 | $1288\to245$ |
| 487 | 1640 | 557 | $487\to1640$ |
| 1051 | 176 | 2021 | $1219\to176$ |
| 1145 | 977 | 1220 | $2020\to977$ |
| 1709 | 1709 | 488 | $556\to1709$ |
| 1939 | 908 | 1289 | $1951\to908$ |

Every listed gap has distance 1153 and every resulting minimum interval has endpoint 1044. The result improves the earlier selected cut's endpoint 1802 within this source's affine orbit; it does not establish an extremal value or asymptotic improvement.

### Optimizer input, output and limits

The call is

```js
minimizeCyclicUnitOrbit({
  source_id: "an explicit identifier for the retained residue source",
  modulus,
  residues,
  symmetries: [
    { multiplier, sign, translation }
  ]
})
```

The source ID is retained as supplied and is not authenticated. Residues and translations are canonical integers from zero through $M-1$; multipliers must be units. All numeric inputs must be safe-integer JavaScript numbers. Repeated input residues are deduplicated and their count recorded. Symmetry multipliers must be distinct. Omitting the symmetry list uses identity and reflection, or just identity when $M=2$.

| Optimizer limit | Value |
|---|---:|
| Modulus | 2 through 65,536 |
| Raw residue entries | 1 through 1,024 |
| Distinct residues | At most 256 |
| Supplied symmetry records | 1 through 64 |
| Quotient classes | At most 8,192 |
| Representative-residue evaluations | At most 2,000,000 |
| Complete optimal unit/cut records | At most 65,536 |
| Source ID | 1 through 512 characters, not all whitespace |

These bounds are separate from the original field-constructor limits. They do not expand its prime/field envelope. Products of canonical residues are below $65536^2$, so the modular arithmetic is exact in JavaScript numbers.

Shape or identity-list errors give `TypeError`; numeric/resource errors give `RangeError`. A false set relation gives `InvalidSymmetryError` with observed and expected images. Missing subgroup closure gives `InvalidSymmetryGroupError` with the two factors and missing product. There is no silent fallback that ignores a supplied false symmetry.

A successful record has schema `cyclic.unit_orbit_interval/v1` and status `EXACT_AFFINE_ORBIT_MINIMUM`. It retains the source residue list, all verified symmetry images, complete unit-coset membership, every representative's transformed residues and gaps, all best representatives and optimal unit/cut witnesses, and the selected positive lift with its element-by-element map. Its validity boundary explicitly says that the source's $B_3$ property and source-ID authenticity were not checked.

The generic API's interval optimum is unconditional for its supplied cyclic set. The $B_3$ interpretation in this application additionally consumes the identified #31278 mathematical premise.

### Actual optimizer work

The single optimizer call examined 2,195 unit candidates, retained 720 units and checked all 36 symmetry-group products. It checked 78 symmetry-residue images, evaluated 1,560 representative residues, retained 1,560 gaps and transported six optimum witnesses. The chosen output map used thirteen further residue evaluations. All complete outputs are saved; no field, source-power or triple-sum computation was repeated.

The observation was 3 ms in connected V8, not a statistical benchmark. The original `constructBoseChowlaB3` source prefix and its accepted complete field dataset remain unchanged. The extension adds no second verifier or synthetic suite, and makes no global record, asymptotic or novelty claim.
