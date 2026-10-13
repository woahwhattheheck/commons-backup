# Erdős 153: ten-element finite premises

## Exact finite result

The exact minimum gap energy among Sidon ten-element subsets of
`[0,71]` is **`376/55`**.

The new [translation-weighted API](translated_sidon_gap_search.cjs)
completed this finite window once. It evaluated 86,638 normalized
Sidon sets, representing 203,840 original Sidon sets, and retained all
24 minimizers without truncation. The
[complete JSON output](n10_finite_premises.json) contains every
minimizer, both translation families, all 352 energy-histogram rows,
both coverage accounts and all per-depth counters.

| Quantity | Exact result |
|---|---:|
| Set size `n` | 10 |
| Inclusive cutoff `D` | 71 |
| Sumset cardinality | 55 |
| All original ten-element subsets | 536,211,932,256 |
| All minimum-zero ten-element subsets | 74,473,879,480 |
| Original non-Sidon subsets charged to rejected prefixes | 536,211,728,416 |
| Normalized non-Sidon subsets charged to rejected prefixes | 74,473,792,842 |
| Original Sidon subsets | 203,840 |
| Evaluated normalized Sidon subsets | 86,638 |
| Normalized prefix extension attempts | 311,297,245 |
| First-invalid normalized prefixes | 260,848,198 |
| Minimum sum of squared gaps | 376 |
| Minimum energy | 376/55 |
| Original minimizers | 24 |
| Normalized minimizer families | 2 |

These are finite computational premises for the accepted
`Contribution.Erdos153Gaps.f_eq_of_search` interface. The cutoff
calculation below is sufficient for its `n=10` conclusion.
No new Lean elaboration, kernel receipt, mathematical priority,
sponsor acceptance or asymptotic solution is claimed.

## Objective and actual attaining set

The elements are natural integers, including zero. All unordered pair
sums with repetition are included: `a_i+a_j` for `i<=j`, including
diagonals. Sidon membership means that these unordered pair sums are
distinct.

For ten Sidon elements, the sumset has 55 values and 54 consecutive
gaps. The energy is the sum of those squared gaps divided by 55.

The following normalized set attains the minimum:

```text
A = {0, 1, 9, 14, 24, 35, 41, 53, 57, 60}
```

Its full sorted sumset is:

```text
0, 1, 2, 9, 10, 14, 15, 18, 23, 24, 25, 28, 33, 35, 36, 38, 41, 42, 44, 48, 49, 50, 53, 54, 55, 57, 58, 59, 60, 61, 62, 65, 66, 67, 69, 70, 71, 74, 76, 77, 81, 82, 84, 88, 92, 94, 95, 98, 101, 106, 110, 113, 114, 117, 120
```

Its consecutive gaps are:

```text
1, 1, 7, 1, 4, 1, 3, 5, 1, 1, 3, 5, 2, 1, 2, 3, 1, 2, 4, 1, 1, 3, 1, 1, 2, 1, 1, 1, 1, 1, 3, 1, 1, 2, 1, 1, 3, 2, 1, 4, 1, 2, 4, 4, 2, 1, 3, 3, 5, 4, 3, 1, 3, 3
```

The unchanged public BigInt objective evaluated this new attaining
input once and returned `SIDON`, a gap-square sum of 376, and reduced
energy `376/55`. The complete result is retained under
`attaining_witness` in the JSON.

## All minimizers

The 24 explicit minimizers are exactly these two normalized sets,
each translated by every integer from 0 through 11:

| Normalized set | Translation range | Original sets |
|---|---|---:|
| `{0,1,9,14,24,35,41,53,57,60}` | `0 <= t <= 11` | 12 |
| `{0,3,7,19,25,36,46,51,59,60}` | `0 <= t <= 11` | 12 |

The two representatives are reflections in 60. The search did not
quotient reflections. It discovered both representatives and expanded
all of their fitting translations. The JSON retains all 24 arrays, the
two family records, `minimizer_count="24"`,
`normalized_minimizer_count="2"`, and both truncation flags as false.

## Candidate selection and retained collision witnesses

Before the full run, the unchanged public objective evaluated the
chosen ten-element input

```text
{0,1,6,10,23,26,34,41,53,55}
```

as Sidon, with 55 sums, gap-square sum 378 and energy `378/55`.
This gives the sufficient initial cutoff

```text
55 * 54 * (378/55) = 20412 <= 20736 = 4 * 72^2.
```

A bounded construction attempt also consumed the two normalized
nine-element minimizer families retained by
[Commons PR #31140](https://github.com/woahwhattheheck/commons/pull/31140).
For each family, it adjoined every integer in `[0,71]` not already
present. These were 126 new ten-element inputs. Each had an explicit
unordered-pair sum collision; none improved the chosen starting input.

The JSON retains a compact witness for every attempted extension:
the source-family index, added element, common sum, and the two
distinct unordered value-pairs with that sum. For example, adjoining
2 to the first family gives `0+2 = 1+1`.
The source families and full input rule are retained alongside those
witnesses, so the exact finite attempt can be consumed without replay.

This statement concerns only the stated finite inputs and carries no
general nonextendability or new-construction priority claim. The
nine-element search itself was not rerun.

## Complete accounting by translation

The [API guide](TRANSLATED_SEARCH_API.md) derives the exact prefix
weights. Each set has a unique minimum-zero representative. A
representative of diameter `d` corresponds to `72-d` translated
sets in this window. A first-invalid normalized prefix of length
`k` ending at `x` represents

```text
C(71-x, 10-k) normalized completions,
C(72-x, 11-k) original completions.
```

First-invalid prefix subtrees are disjoint. Every surviving normalized
Sidon leaf is evaluated, and its translation weight contributes to the
original-set counts and histogram. The exact final identities are:

```text
74,473,792,842 normalized non-Sidon subsets
+      86,638 normalized Sidon subsets
= 74,473,879,480
= C(71,9)

536,211,728,416 original non-Sidon subsets
+      203,840 original Sidon subsets
= 536,211,932,256
= C(72,10).
```

The run used `createTranslatedSidonGapSearch({n:10, cutoff:71,
max_saved_minimizers:4096, max_saved_minimizer_families:4096})`.
Each advance was bounded by 1,000,000 new prefix extension attempts.
The operation allowed at most 2,048 advances and completed during
advance 312. All normalized and translated coverage counts are exact
BigInt quantities; the bounded gap-square totals are exact integers.

The weighted histogram records every visited Sidon energy, with both
its normalized representative count and its original translated count.
The final result is `COMPLETE`. No smaller window or earlier
`n<=9` input was rerun.

## Finite premises for the accepted interface

Use `n=10`, `D=71`, `t=C(11,2)=55`, and `v=376/55`.
The accepted interface's numerical cutoff is

```text
t * (t - 1) * v <= 4 * (D + 1)^2.

55 * 54 * (376/55) = 20304
4 * 72^2           = 20736
20304 <= 20736.
```

After clearing the denominator 55, this is
`1116720 <= 1140480`.

The retained attaining set has ten elements, lies in
`Finset.range 72`, is Sidon and has energy `376/55`.
The completed enumeration supplies the computational lower bound for
every Sidon ten-set in that finite range. These are the concrete
premises for the accepted declaration's conclusion
`Erdos153.f 10 = 376/55`.

The already-published reduction and proof are accepted dependencies.
This publication supplies the new finite evidence and a reusable exact
enumerator. It does not represent a new admissible formal bridge as
already elaborated.

## Consume the output

No search replay is needed to use the retained result:

```javascript
const record = JSON.parse(completeJsonText);
const result = record.search;

const minimum = result.minimum_energy;          // "376" / "55"
const allSets = result.minimizers;               // all 24 arrays
const families = result.minimizer_families;      // both families
const histogram = result.energy_histogram;      // all 352 rows
const witness = record.attaining_witness;       // full sums and gaps
const collisions =
  record.seed_extension_attempt.collision_witnesses; // all 126
```

The enclosing schema is `erdos153.n10_finite_premises/v1`.
The search schema is `erdos153.translated_sidon_gap_search/v1`.
See the [API guide](TRANSLATED_SEARCH_API.md) for exact types, numerical
ceilings, bounded advances, retention semantics and the partial/complete
distinction.

## Sources and ownership

- [Commons PR #16049](https://github.com/woahwhattheheck/commons/pull/16049)
  is the original finite-value carrier, merged at
  `d1e76d7d0a7511ec8f66d8ca336cc44f1896a97e`.
  Its earlier work and submission ownership remain intact.
- [Commons PR #31130](https://github.com/woahwhattheheck/commons/pull/31130)
  introduced the original public API and the eight-element input.
  The unchanged objective/traversal module has blob
  `82f165edd18b7d71f5746f96ff606ad14fe0aadf`.
- [Commons PR #31140](https://github.com/woahwhattheheck/commons/pull/31140)
  retained the nine-element input, merged at
  `9d70946d233232926bda4d55be4331d509a47ea5`.
  Its complete data blob is
  `0c4240de31cb91bb605e95f7c1145e71138555d2`.
- [The accepted contribution](https://github.com/conjectures-io/conjectures-contribution/blob/main/contributions/erdos-153/d283fe047b326ca9bb9de8919c667b521df46d9500cc839b50916321fee0192b/script.lean)
  contains `Contribution.Erdos153Gaps.f_eq_of_search`.
  The retained script blob is
  `546fb3a40683a5e33956262b2a46ca55bace0218`, with contribution
  identifier
  `d283fe047b326ca9bb9de8919c667b521df46d9500cc839b50916321fee0192b`.
- [The Erdős 153 target page](https://conjectures.io/problems/erdos153-erdos-153)
  and [Formal Conjectures target](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/153.lean)
  provide the surrounding objective and conjecture.
  The retained target type hash is
  `b35a9b51e1956e50dac187c15f5e0fd861c1ae3dcaaceb7941a1ce9bfd770316`.

Operation: `ERDOS153-TRANSLATION-SEARCH-N10-20261004-7CA6`.
Original mathematics thread: `1789745818.950459`, channel
`C0C3MEWHTR6`; narrow claim: `1791100045.862959`.
No sponsor submission, payment, new Lean receipt or asymptotic
conclusion is represented.
