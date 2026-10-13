# Shifted finite-prime totient-product correlations

This package consumes the seven-prime version of the saved atom table in [Commons #31398](https://github.com/woahwhattheheck/commons/pull/31398). It constructs the **joint periodic distribution** of R_P(n) and R_P(n+h), where R_P(n) is the product of (1-1/p) over supplied primes p dividing n. The declared basis is P={2,3,5,7,11,13,17}; its saved period is Q=510510.

The complete result has **128 lag-divisibility profiles and 62,500 support-pair rows**. Of those rows, 62,372 are new joint masses and 128 are copied diagonal masses. Every profile has total mass Q. Exact joint moments, covariance, rectangle/support conditioning and ordinary or weighted support-pair navigation are retained.

This finite periodic product is not the full totient ratio for arbitrary integers. No omitted-prime error, positive-derivative conclusion, improved classical density enclosure or prize claim is supplied.

## Input and source identity

The predecessor is #31398 at merge 44380533ac7cf3f8425b8033d5714ec8b1f2ec81. Complete data blob e056035b46910fc37911418ed12ca622329ccecd (338,223 bytes) and guide blob 7b4922f7691f0f7c7c4111a30fbdb9e68d44ceb4 (27,161 bytes) were acquired and independently matched. The exact new input copies /index/versions/7 and the first seven stored primes. No predecessor source was executed.

Its source row schema is [mask, ratio numerator, ratio denominator, integer weight, cumulative weight]. input.json retains mask, reduced ratio and weight with the source-row index. The old cumulative weights are unused. Primality, completeness, saved ratios, marginal weights and strict rational row order remain identified premises. This package does not recompute or authenticate those mathematical premises.

The full current FormalConjectures/ErdosProblems/50.lean, requested at main, returned blob bc1ea50a170839b20f3c8b69ea4dc94180c22d3e. It uses the strict distribution of phi(n)<c*n on c in [0,1] and a derivative within that interval. Its solved existence/singularity annotations and open derivative annotation accompany local placeholders. They are observed metadata, not audited formal proofs or a new status survey.

The [PPL003 intake](https://prizeproblems.org/problems/003/) was read. The canonical Erdős50 access denial remains held and was not retried. The predecessor guide's Banerjee–Chahal–Chaubey–Khurana existence/continuity attribution is preserved without re-reading that external paper or the predecessor enclosure proof. SOURCE_QUALIFICATION.md gives the full boundary.

## Exact two-point construction

Write L and R for the support masks of primes dividing n and n+h. For one supplied prime p:

| Lag condition | Left divides | Right divides | Residues modulo p |
| --- | --- | --- | ---: |
| p divides h | Yes | Yes | 1 |
| p divides h | No | No | p-1 |
| p does not divide h | Yes | No | 1 |
| p does not divide h | No | Yes | 1 |
| p does not divide h | No | No | p-2 |

The two exceptional residues in the last case are distinct because h is nonzero modulo p. At p=2 the neither case has zero mass and is omitted. CRT makes prime-residue choices independent, so multiplying the local masses gives the exact number of n residues modulo Q for each joint support pair.

Only the divisibility mask of h matters for these multiplicities. Each of the 128 masks has a representative given by the product of its selected primes. Arbitrary signed integer lags are mapped to that mask by seven exact remainders.

For the all-dividing lag pattern, L=R and the profile directly copies every saved atom's marginal mass. That profile does not rebuild the old marginal distribution. Its product moment is a new quantity.

Joint rows are [left_source_row,right_source_row,integer_mass], sorted first by the left saved row and then by the right saved row. Source support masks remain identities; equal numerical values would not justify silently merging support pairs. The supplied table already has strict ratio order.

R_P is defined on all residue classes, including the zero residue. That is a finite product convention, not phi(0)/0. For positive-integer interpretation take n>0 and n+h>0. For fixed h only finitely many positive n can fail the second inequality, so each periodic event has natural density equal to its residue mass divided by Q. This elementary periodic density concerns R_P, not the untruncated totient distribution.

## Moments and covariance

Let u_i=Q*r_i for a saved ratio r_i. Its denominator divides Q, so the new conversion produces an exact integer. Let a_i be the inherited marginal weight and w_ij the new joint mass.

The package retains:

- A=sum a_i*u_i, giving E[R_P(n)]=A/Q^2.
- B_h=sum w_ij*u_i*u_j, giving E[R_P(n)R_P(n+h)]=B_h/Q^3.
- Covariance numerator B_h*Q-A^2, with denominator Q^4.

The third Q in the product-moment denominator includes the probability mass normalization. Both marginals are the same periodic product distribution; shifting a complete residue system permutes it. Covariance here is not a normalized Pearson correlation coefficient.

All fractions are exact and deliberately unreduced. The common first-moment record is:

```json
{"numerator":"160526499840","denominator":"260620460100"}
```

Selected complete-profile product moments have common denominator 133049351085651000:

| Lag | Mask | Support pairs | Product-moment numerator | Covariance numerator over Q^4 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0 | 1458 | 44065967771165340 | -3272639944023902302200 |
| 2 | 1 | 1458 | 55082459713956675 | 2351389357690502128650 |
| 6 | 3 | 972 | 57705433986049850 | 3690443953336788897900 |
| 30 | 7 | 648 | 58207220368537240 | 3946610919460426366800 |
| 210 | 15 | 432 | 58384142010994800 | 4036931187151435322400 |
| 510510 | 127 | 128 | 58467638465280000 | 4079556962028572774400 |

These are exact results for the supplied seven-prime truncation. Their signs or magnitudes are not extrapolated to the full totient ratio.

## Reader contract

```javascript
const {createReader} = require("./shifted_correlations.cjs");
const certificate = require("./certificate.json");
const reader = createReader(certificate);

// Illustrative new consumer calls. The publication's completed calls
// are already in saved_reader.json and do not need to be replayed.
reader.profile({lag:"1"});
reader.condition({
  lag:"1",
  left:{upper:["1","2"]},
  right:{lower:["3","4"],lower_closed:false}
});
reader.select({lag:"1",weighted:true,rank:0});
reader.page({lag:"1",start:0,limit:10000});
reader.marginals({lag:"2",require_left:1,require_right:1});
```

Lags are canonical signed decimal strings, at most 2048 characters. Zero is accepted; negative zero is rejected. Rational endpoints are two canonical nonnegative decimal strings [numerator,denominator], each at most 2048 characters, with positive denominator and value in [0,1]. Fractions need not be reduced. Cache keys retain the exact endpoint tokens, so equivalent rational spellings need not share a cache.

Both coordinate intervals default to the closed interval [0,1]. lower_closed:false or upper_closed:false makes that endpoint strict. Exact integer cross multiplication implements all comparisons. Reversed bounds define an empty condition. Endpoint equality is handled according to both closure flags, with no floating-point tolerance.

require_left, exclude_left, require_right and exclude_right are masks in [0,127], defaulting to zero. Overlapping required/excluded masks yield an empty condition. Feasible source rows must satisfy both support masks and both coordinate bounds. A support pair prohibited by the lag profile also yields no mass.

condition returns the exact matching row indices, cumulative joint masses, atom count, mass, probability mass/Q and conditional product moment. For surviving mass M, that conditional moment is sum(w*u_L*u_R)/(M*Q^2). An empty condition returns null for this moment, rather than dividing by zero. The numerator is stored as weighted_product_sum. Full unrestricted profiles reuse their saved moment; genuinely filtered conditions compute new moment terms from saved ratio units.

profile returns a saved global profile's moment and covariance. marginals sums saved joint masses by each source row and returns the surviving mass as conditional denominator, or null when empty. It is a new joint projection, not a re-run of the predecessor's atom weights.

## Ranking: support pairs and mass offsets

All ranks are zero-based nonnegative safe integers. Ordinary select/rank navigates the matching support-pair rows in the inherited left-row/right-row lexicographic order.

With weighted:true, each support pair occupies a contiguous block of length equal to its exact mass. A selected unit is identified by profile_row and mass_offset, with 0<=mass_offset<mass. Weighted rank reconstructs the block start plus that offset.

**A mass offset is not an integer residue, a representative n or a numeric CRT rank.** No ordering of actual residue solutions inside a support fiber is constructed. The weighted navigation is a precise finite measure representation, not a residue-selection algorithm.

select returns FOUND or OUT_OF_RANGE. rank returns FOUND or NOT_IN_CONDITION, with a range check for weighted offsets. page exports ordinary support rows, with limit at most 10,000. Rows include exact ratios, masks, source row IDs, mass and weighted start. snapshot retains every computed condition; work supplies named operation counts.

The reader checks the schema tag and valid argument shapes; it trusts the identified certificate's mathematical provenance. It is not an adversarial verifier of arbitrary supplied joint data.

## Complete actual reader

The new reader retained **308 complete responses**, including all 128 profile summaries, sixteen named conditions, **72 matching rank/select inverse pairs**, two matching lag-pattern aliases, all **1,458 lag-one support pairs**, and three complete marginal vectors. No failed call or lost response occurred.

The lags -1 and Q*10^100+1 matched the lag-one condition key. This reuses a saved profile by divisibility; it does not enumerate huge intervals.

| Condition | Matching support pairs | Exact mass |
| --- | ---: | ---: |
| lag1 | 1458 | 510510 |
| lag2 | 1458 | 510510 |
| lag6 | 972 | 510510 |
| lag30 | 648 | 510510 |
| lag210 | 432 | 510510 |
| diagonal | 128 | 510510 |
| negativeLag | 1458 | 510510 |
| hugeEquivalentLag | 1458 | 510510 |
| asymmetricRectangle | 344 | 160304 |
| bothEvenImpossible | 0 | 0 |
| bothEvenLag2 | 729 | 255255 |
| quarterHalf | 98 | 52539 |
| exactHalf | 64 | 92160 |
| emptyHalf | 0 | 0 |
| supportOverlap | 0 | 0 |
| reversedBounds | 0 | 0 |

The asymmetric rectangle is R_P(n)<=1/2 and R_P(n+h)>3/4 for h=1. The quarterHalf condition is 1/4<=R_P(n)<1/2 and 1/2<=R_P(n+6)<=1. exactHalf uses the closed singleton left interval {1/2}; emptyHalf makes its upper endpoint strict. The even/even condition for h=1 is impossible, while it has mass 255255 for h=2. These are finite periodic results, not full-totient counts.

The constructor performed 127 new joint profiles, copied one diagonal profile, retained 62,372 new and 128 copied rows, made 103,742 local branch/weight products, 128 saved-ratio unit conversions, 128 new marginal-moment terms and 62,500 joint-moment terms. It performed zero sieve runs, old atom reconstructions, prime-tail calculations or primorial-residue enumeration.

Actual reader work is:

```json
{
  "lagRemainders": 2156,
  "conditionsBuilt": 14,
  "conditionHits": 166,
  "jointRowsScanned": 14816,
  "ratioComparisons": 22076,
  "conditionalMomentTerms": 1235,
  "savedFullMoments": 6,
  "selectionRows": 14556,
  "rankRows": 28450,
  "marginalRows": 3260,
  "rowMaterializations": 1602,
  "newJointRows": 0,
  "oldAtomReconstructions": 0,
  "sieveRuns": 0,
  "primeTailCalculations": 0
}
```

There are 14 distinct cached conditions because two named lag aliases share the lag-one cache. The driver used 448 multiplications to form the 128 lag representatives. Counters describe the named implementation operations, not all JavaScript work or an elapsed-time benchmark. The reader adds no joint rows. Its 1,235 filtered moment terms and conditional cumulative masses are explicitly new query work.

## Artifact and checkpoint layout

The eleven files include the source, exact copied input and lineage, predeclared plans, source qualification, complete certificate, actual reader source and outputs, this guide, README and public checkpoint chain.

certificate.json contains every profile and all 62,500 rows, not a sample. It is 790310 bytes, blob 289948fcee309f6dc99a3a0b2a7fb47b6c60873e. saved_reader.json contains every response and final cache; it is 1011776 bytes, blob 7d45bf87e099ce279869ef483dc1d0385d1c3a93.

Source/input/plan were native-blob checkpointed before the once-only constructor, the complete result before the reader, reader source/plan before the first call, and complete reader before publication. public_checkpoints.json records actual native acknowledgements with independently matched hashes. The later full frozen-spec checkpoint is reported in the release, avoiding a self-referential file. Public checkpoints exclude private provider envelopes and private journal locators.

No accepted sieve, marginal atom, predecessor bound, prior example, source proof or known verification range was replayed. No sponsor contact, acceptance or novelty assertion accompanies this finite joint-distribution API.
