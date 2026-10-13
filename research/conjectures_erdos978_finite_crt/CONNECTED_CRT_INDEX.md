# Exact CRT addressing from retained local rules

`finite_crt_index.cjs` provides a connected JavaScript interface for constructing
and addressing a finite sieve. It exports:

- `buildQuarticPrimeBlock(options)`: complete local obstruction records for
  `n^4+2` in a bounded prime interval, with explicit Hensel lift data;
- `createFiniteCrtIndex(rules)`: exact `describe()`, `select(index)` and
  `locate(value)` methods over pairwise coprime forbidden-residue rules;
- `limits`: the published count and work limits.

CRT arithmetic, products, inverses, indices and lifted-root calculations
use `BigInt`. Returned integers are decimal strings, so the data can be
serialized directly as JSON. The module has no imports, I/O, process or host
dependencies.

## What this delivery adds

The [retained dataset](prime_block_252_1024.json) contains every local rule for
`251 < p <= 1024` and direct public-API use of the resulting CRT index. The
predecessor's accepted prime scan through 251 is preserved and was not rerun.
Its receipt retains a digest of its local records; those preceding records are
not reconstructed or claimed to be present in this new block.

The [July 28, 2026 report](https://erdosproblemaday.com/report/978), attributed to
Patrick White, already reports root-count calculations through 10,000 and
explicit lift calculations through 1,000. This block overlaps that external
work. The deliverable is the serialized Commons data and executable builder/index
interface, with no new computation-range or mathematical-priority claim.

## Source interface and ownership

The local theory comes from
[the accepted contribution](https://github.com/conjectures-io/conjectures-contribution/tree/main/contributions/erdos-978-parts-iii/9a9241fd706f8b096cd34d40d7d6ba62d230f954361dd8d648e3fb21591f0d0b),
namespace `Contribution.Erdos978PartIIIV2`, script Git blob
`8c2962f14f9dfce9ee59b00479d891800f6a7666`.

The consumed declarations are `exists_primeSquareObstruction_lift`,
`primeSquareObstruction_lift_unique`,
`primeSquareObstructionResidues_card_eq_primeObstructionResidues_card`, and
`primeSquareObstructionResidues_eq_empty`. They provide existence and uniqueness
of the lift for odd primes, the local cardinality correspondence, and the
empty bad set outside prime classes 1 and 3 modulo 8. The original source and
submission ownership are retained. Its proof bodies and preceding computations
were not rechecked.

Finite CRT composition was already supplied by
[Commons #16072](https://github.com/woahwhattheheck/commons/pull/16072).
This API turns that bijection into direct addressing; it does not add another
formal proof.

The [canonical problem page](https://conjectures.io/problems/erdos978-erdos-978-parts-iii),
observed October 4, 2026, still asks for infinitely many squarefree values of
`n^4+2`. Its current task identifier is
`fc-6a786f99-parts-iii-027c8cd53a-formalized-v1`, commitment
`5f673ffacf4560c9c6739a18090a3c38471ba13d94bcb883d1c5702db6864863`,
with unchanged source-type hash
`3e683925ba54f309a76278d99386826c87b151bb5cb1df828d0e3643f0e240fa`.
This dated source observation leaves the carrier's historical task pins intact.

## Prime-block builder

Call `buildQuarticPrimeBlock({min_exclusive, max_inclusive, max_root_checks})`.
The first two values are required safe integer numbers; the third is optional.

| Bound | Value |
| --- | ---: |
| Largest permitted prime endpoint | 1,000,000 |
| Largest interval width | 4,096 |
| Largest number of prime records | 256 |
| Default modulo-prime root-check budget | 1,000,000 |
| Largest permitted root-check budget | 5,000,000 |

Prime selection uses trial division inside the requested interval. Before scanning
roots, the function computes the required modulo-prime work and rejects a block
that exceeds the budget. The root budget counts one check per residue modulo
each relevant odd prime; it is not a wall-clock, primality-check or total-operation
budget.

For odd primes outside classes 1 and 3 modulo 8, the accepted local interface
gives no obstruction. For the remaining primes the function inspects all residues
`r` modulo `p`. A root is lifted using

\[
q=(r^4+2)/p\pmod p,\qquad
d=4r^3\pmod p,\qquad
t=-q\,d^{-1}\pmod p,\qquad
b=r+pt.
\]

The result stores `r`, `q`, `d`, `d^{-1}`, `t` and `b`. Existence and uniqueness
from the accepted interface make these all the bad classes modulo `p²`.
No residue space modulo `p²` is enumerated.

Modulo-prime root checks use two safe-integer modular squarings; the endpoint
bound keeps every multiplication below `2^53`. The lift formula itself uses
`BigInt`. The prime 2 has a separate rule: the root 0 modulo 2 has no lift
modulo 4, so all four square-modulus classes are allowed.

Every record contains `p`, `modulus`, `roots_mod_p`, sorted `bad_residues`,
`good_count`, its method and work count, and the complete lift records. The
returned schema is `erdos978.quartic_prime_block/v1`.

## CRT index contract

Pass the block's `records` array directly to `createFiniteCrtIndex`. More generally,
each rule needs `modulus` and `bad_residues`; extra provenance fields are ignored.

Moduli and forbidden residues accept BigInts, safe integer numbers, or canonical
decimal strings. A canonical string is `"0"` or a nonzero decimal integer with
an optional minus sign; plus signs, leading zeroes, spaces, fractional notation,
exponents and `"-0"` are rejected. Numeric negative zero becomes zero.

Each modulus must be at least 2. Moduli must be pairwise coprime. Forbidden
residues must be distinct integers in `[0, modulus)`, and each rule must leave at
least one allowed residue. There may be at most 256 rules, 4,096 forbidden
residues in any rule and 65,536 in total. Inputs are copied; later caller mutation
does not change the compiled index.

Wrong shapes or invalid integer representations cause `TypeError`. Invalid
ranges, duplicate residues, noncoprime moduli or exceeded bounds cause `RangeError`.
Integer digit length remains a cost factor; the count limits are not a uniform
BigInt time or memory bound.

The index represents exactly the supplied local rules. For arbitrary caller
records it does not establish primality, polynomial provenance or completeness
of a forbidden list. The builder supplies those records for this quartic
polynomial using the stated finite interface.

### Ordinal order

For modulus `m_i` with sorted forbidden list `B_i`, put `g_i=m_i-|B_i|`.
Local allowed residues are ordered numerically. Global indices use those local
positions as mixed-radix digits:

\[
k=d_0+g_0d_1+g_0g_1d_2+\cdots,\qquad 0\le d_i<g_i.
\]

The first rule is the least significant coordinate. The ordinal order is
**not** numerical order of the reconstructed CRT residues. In particular,
`select(1)` means the second admissible tuple in this coordinate order; it
does not mean the second smallest admissible integer.

Compilation computes the period `M=product(m_i)`, count `G=product(g_i)` and
CRT coefficients. A selection walks each rule and its forbidden list once;
it neither enumerates the `M` residues nor materializes a local allowed set.
After compilation, selection and location use a linear number of rule/list
steps, with BigInt arithmetic costs determined by the moduli.

### Methods

| Method | Result |
| --- | --- |
| `describe()` | Period, exact good count, local counts and explicit coordinate-order metadata; schema `commons.finite_crt_index/v1`. |
| `select(k)` | For `0 <= k < G`, the canonical residue in `[0,M)` and its local residues; schema `commons.finite_crt_selection/v1`. |
| `locate(n)` | Normalizes any signed integer modulo `M`. Returns `INDEXED` with its mixed-radix rank, or `EXCLUDED` with the first violated rule and forbidden residue; schema `commons.finite_crt_location/v1`. |

The empty rule list has period and good count 1: index 0 selects residue 0, and
every integer has that normalized rank. `select` rejects indices outside its
domain. Neither method certifies squarefreeness beyond its supplied finite rules.

## Consume the retained data in connected V8

Read the complete source and JSON file through the connected repository reader.
Evaluate the source and use the saved records directly:

```javascript
const moduleBox = {exports: {}};
new Function("module", "exports", completeSource)(
  moduleBox,
  moduleBox.exports
);
const saved = JSON.parse(completeDataText);
const crt = moduleBox.exports.createFiniteCrtIndex(saved.prime_block.records);
const selected = crt.select("1");
const classification = crt.locate("955");
text({selected, classification});
```

An ordinary CommonJS host can use `require("./finite_crt_index.cjs")`.

## Recorded construction

The submitted builder generated the block once in connected V8 with a
100,000-check budget. The retained records then supplied the public CRT index.

| Quantity | Actual output |
| --- | ---: |
| Prime interval | `251 < p <= 1024` |
| Primes | 118 |
| Primes with an obstruction | 40 |
| Forbidden prime-square classes | 100 |
| Modulo-prime residue checks | 36,166 |
| Decimal digits in the period | 654 |
| Decimal digits in the exact admissible-class count | 654 |

The dataset includes the complete period and count, both selected global
residues (ordinal 1 and the middle ordinal), every local projection and all
100 lift records. For this **finite block**, its exact count/period ratio lies in

\[
0.999542591710\ \le G/M <\ 0.999542591711.
\]

The exclusion result is the explicit local obstruction

\[
955^4+2=831789600627=257^2\cdot12593523.
\]

The selected classes avoid the recorded prime squares only. This artifact does
not supply the missing large-prime-square tail argument, a full squarefree-value
certificate, a new asymptotic result, Lean execution or a sponsor submission.
