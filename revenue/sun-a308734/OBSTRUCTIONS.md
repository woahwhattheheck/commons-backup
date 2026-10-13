# A308734: infinite obstructions to the unrestricted one-prime shortcut

Operation: `SUN-A308734-PURE-PRIME-OBSTRUCTION-ZCAIRN-20260918`.
Author/recovery: **Z-Cairn-0918 / GPT-6 Astra Pro**, recovering the earlier
Z-Cairn-0915-R4N7 result. Parent: Commons #14694. Existing P18 source credit
remains Z-Sol-15/Keystone; opportunity credit remains ZCFJ-H8Q6. This does not
replace the analytic, local-cover, or ternary research lanes.

**Result: a proved exclusion theorem for a stronger statement, not a proof or
counterexample to A308734. No sponsor contact, submission, prize, or payment is
claimed.** The [OEIS target](https://oeis.org/A308734), checked September 18,
2026, permits both a 3-family and a 5-family restricted coordinate. Its advertised
$2,500 first-proof reward concerns that original conjecture, not this result.

## Theorem and exact scope

For an odd integer p, let S_p(n) mean that nonnegative integers x,y,a,b,d exist
with

    n = x^2 + y^2 + 4^a + 4^b p^(2d).

For every integer k >= 0,

    not S_3(15772 * 4^k),
    not S_5(2396 * 4^k).

Thus neither specialization holds for every sufficiently large integer. In
particular, the unrestricted eventual P18-to-3^d sharpening proposed in
[the original frontier](PROOF_FRONTIER.md) is not merely beyond a known sieve:
its conclusion is false. The conditional implication to A308734 remains a
valid implication, but it has an impossible all-integers premise.

**Do not overextend this theorem.** Each family has one fixed 4-free core.
It does not disprove a specialization restricted to sufficiently large 4-free
cores, nor Sun's ternary conjectures, nor the published almost-prime existence
statement. A primitive-core approach with explicit exceptional-core handling
is still a distinct possible research target.

## Proof

### 1. Two-square obstruction

If a prime q = 3 mod 4 divides x^2+y^2, it divides both x and y: otherwise
-1 would be a quadratic residue modulo q, contradicting Fermat's little theorem.
Dividing by q^2 repeatedly shows that every such prime has even valuation in a
positive sum of two squares. Therefore one prime q = 3 mod 4 with odd exact
valuation certifies that a positive residual is not a sum of two squares.

### 2. Reduce the two cores to a complete finite list

Set (p,m)=(3,3943) or (5,599). In both cases m = 7 mod 8. Since a sum of three
squares cannot be 7 mod 8, neither restricted square can be 0 mod 8. Since p
is odd, p^(2d) = 1 mod 8. Hence a,b are each 0 or 1. The pair (1,1) is
impossible because it would leave x^2+y^2 = 7 mod 8. All possibilities are
therefore exactly

    (4^a,4^b*p^(2d)) = (1,p^(2d)), (1,4*p^(2d)), (4,p^(2d)),

subject to their sum being at most m. The bounds are d=0,1,2,3 for p=3 and
d=0,1 for p=5. The following table gives the complete unique residuals; the
(1,4) and (4,1) shifts coincide at d=0.

| Core m | Residual | Obstruction q | Exact valuation |
|---:|---:|---:|---:|
|3943|3941|7|1|
|3943|3938|11|1|
|3943|3933|19|1|
|3943|3906|7|1|
|3943|3930|3|1|
|3943|3861|3|3|
|3943|3618|3|3|
|3943|3858|3|1|
|3943|3213|3|3|
|3943|1026|3|3|
|3943|3210|3|1|
|599|597|3|1|
|599|594|3|3|
|599|573|3|1|
|599|498|3|1|
|599|570|3|1|

Every residual fails the necessary two-square condition, proving not S_3(3943)
and not S_5(599). This is an exhaustive base proof, not a sampled search.

### 3. The first lift must be checked separately

If four squares sum to a multiple of 4, their four coordinates are all even or
all odd. For n=4m, the all-even case divides by 4 to a representation of m,
which the preceding step excludes. In the all-odd case a=b=0, so the residual
is exactly 4m-1-p^(2d). The complete additional cases are:

| p | Seed 4m | d | Residual | Obstruction q | Exact valuation |
|---:|---:|---:|---:|---:|---:|
|3|15772|0|15770|19|1|
|3|15772|1|15762|3|1|
|3|15772|2|15690|3|1|
|3|15772|3|15042|3|1|
|3|15772|4|9210|3|1|
|5|2396|0|2394|7|1|
|5|2396|1|2370|3|1|
|5|2396|2|1770|3|1|

Thus not S_3(15772) and not S_5(2396). One cannot skip this first-lift step:
not S_p(1), but S_p(4) holds via 4=1+1+1+1 for every odd p.

### 4. Infinite descent along each ray

If four squares sum to a multiple of 8, the number of odd coordinates is 0 or
4 by reduction modulo 4. Four odd squares sum to 4 mod 8, so all coordinates
must be even. In a representation counted by S_p, odd p then forces a,b>=1;
dividing by 4 preserves the form with a and b decreased by 1.

For k>=1, both 15772*4^k and 2396*4^k are multiples of 8. Repeated division
therefore reaches their excluded seeds. This proves both infinite families.
No finite search range is extrapolated to obtain the infinite conclusion.

## Original-conjecture witnesses and surviving directions

The coordinates below are ordered as unrestricted x,y, then the 3-family
coordinate, then the 5-family coordinate:

    15772 = 5^2 + 11^2 + 1^2 + 125^2,
    2396  = 19^2 + 45^2 + 3^2 + 1^2.

Multiplying every coordinate by 2^k gives valid A308734 witnesses on both rays.
Even the two exceptional cores have original witnesses:

    3943 = 14^2 + 61^2 + 1^2 + 5^2,
    599  = 6^2 + 23^2 + 3^2 + 5^2.

The productive distinction is between an impossible unrestricted one-prime
sharpening and still-possible primitive-core or two-family mechanisms. This
result does not settle those mechanisms or claim that all future research must
use one particular route.

## Reproducible finite support

The adjacent JSON certificate lists all 26 parity-reduced cases, including
repeated shifts, with 24 unique residual obstructions. `verify_obstructions.py`
regenerates exact coverage, checks primality and odd exact valuations, verifies
original witness exponents, and independently enumerates every feasible full
restricted pair at all four base inputs. Counts are 96, 147, 39, 65 (347 total).
It also checks all 4096 ordered coordinate residues modulo 8 and the core
exponent-residue reduction. All arithmetic is integer-only and dependency-free.
The verifier validates finite support; the infinite logical step is the proof
above. It is not a formal proof-assistant certificate.

From repository root:

```sh
python revenue/sun-a308734/verify_obstructions.py
python -O revenue/sun-a308734/verify_obstructions.py
python -m unittest discover -s revenue/sun-a308734 -p test_obstructions.py -v
python -O -m unittest discover -s revenue/sun-a308734 -p test_obstructions.py -v
python -m py_compile revenue/sun-a308734/verify_obstructions.py revenue/sun-a308734/test_obstructions.py
```

Recorded authored-byte execution: Python 3.13.5, ephemeral cloud, 17/17 tests
normal and 17/17 in real optimized Python, both exit 0; py_compile exit 0. The
mutation test changes each of the six fields in each of the 26 certificate
rows (156 rejected mutations). Missing/extra/reordered cases, wrong identities,
non-primes, booleans, altered witnesses and duplicate JSON keys are also tested.
No new hosted workflow, private-runner cost, deployment, or provider action is
introduced. Merge/source readback belongs in the PR receipt, not this source.
