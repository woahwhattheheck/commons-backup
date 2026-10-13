# Erdős 153: nine-element finite premises

## Result

The exact minimum gap energy among Sidon nine-element subsets of
`[0,52]` is **`254/45`**. This is a completed new input to the public
[search and objective API](sidon_gap_search.cjs) introduced in
[Commons PR #31130](https://github.com/woahwhattheheck/commons/pull/31130).

The computation accounts for every one of the `C(53,9) = 4,431,613,550`
subsets in the window. It retains all 18 minimizers without truncation,
the full 129-row energy histogram, all per-depth counters, and the exact
attaining witness in [the complete JSON output](n9_finite_premises.json).

| Quantity | Exact result |
|---|---:|
| Set size `n` | 9 |
| Inclusive cutoff `D` | 52 |
| Sumset cardinality for a Sidon set | 45 |
| All nine-element subsets of the window | 4,431,613,550 |
| Non-Sidon subsets accounted by rejected prefixes | 4,431,608,000 |
| Evaluated Sidon subsets | 5,550 |
| Prefix extension attempts | 51,676,095 |
| Rejected prefixes | 41,535,599 |
| Minimum sum of squared gaps | 254 |
| Minimum gap energy | 254/45 |
| Attaining sets in the window | 18 |

These numbers are a finite computational result. The cutoff arithmetic below
supplies the numerical premises for the already-published
`Contribution.Erdos153Gaps.f_eq_of_search` declaration at `n=9`.
This artifact does not contain a new Lean elaboration or kernel receipt.
A formal contribution still needs an admissible checked bridge to that
accepted interface. No mathematical priority or asymptotic result is claimed.

## Objective and conventions

The ambient elements are natural integers, including zero. For a finite set
`A`, form all unordered pair sums `a_i + a_j` with `i <= j`, including
diagonal pairs. The set is Sidon exactly when these pair sums are distinct.

For a Sidon nine-set there are `t = 9*10/2 = 45` ordered sumset values
`s_0 < ... < s_44`. The objective is

```text
gapEnergy(A) = ((s_1-s_0)^2 + ... + (s_44-s_43)^2) / 45.
```

Thus there are 44 gaps, and the denominator is 45. Coordinates and the
bounded gap-square totals in the search are exact integers. The public
objective used for the witness uses BigInt arithmetic and returns reduced
rational energy.

The conventions come from the accepted Erdős 153 target and interface
identified under Sources. The prior `n=5,6,7` carrier, the accepted
`n=8` output and the public API source remain unchanged.

## Concrete attaining witness

Before this enumeration, the public objective evaluated the following
concrete input:

```text
A0 = {0, 1, 5, 12, 25, 27, 35, 41, 44}
```

Its complete sorted sumset is:

```text
0, 1, 2, 5, 6, 10, 12, 13, 17, 24, 25, 26, 27, 28, 30, 32, 35, 36, 37, 39, 40, 41, 42, 44, 45, 46, 47, 49, 50, 52, 53, 54, 56, 60, 62, 66, 68, 69, 70, 71, 76, 79, 82, 85, 88
```

The consecutive gaps are:

```text
1, 1, 3, 1, 4, 2, 1, 4, 7, 1, 1, 1, 1, 2, 2, 3, 1, 1, 2, 1, 1, 1, 2, 1, 1, 1, 2, 1, 2, 1, 1, 2, 4, 2, 4, 2, 1, 1, 1, 5, 3, 3, 3, 3
```

The 45 pair sums are distinct and the gap-square total is 254, giving
energy `254/45`. The exact objective output from that initial evaluation
is retained under `candidate` in the JSON. The completed search attains
the same value. This witness was a chosen input; its inclusion is not a
claim to a new Sidon construction.

## All minimizers in the window

The 18 sets in the output are exactly the following two normalized sets,
each translated by every integer `u` from 0 through 8:

| Normalized set | Allowed translations |
|---|---|
| `{0,1,5,12,25,27,35,41,44}` | `u = 0,1,2,3,4,5,6,7,8` |
| `{0,3,9,17,19,32,39,43,44}` | `u = 0,1,2,3,4,5,6,7,8` |

The second normalized set is the reflection of the first in 44. This
family description was extracted from the actual retained list, not used
to restrict the search. The search traversed the entire window without
translation or reflection quotienting. The JSON contains all 18 explicit
nine-element arrays as returned by the API, together with the extracted
translation families.

## Exact combinatorial coverage

The unchanged API maintains a strictly increasing prefix and the positive
differences already present. When a newly added largest element repeats
a positive difference, that prefix and every extension are non-Sidon.
For a rejected prefix of length `k` ending at `x`, the exact number
of remaining full subsets is

```text
C(52-x, 9-k).
```

The traversal charges a full subset only to its first rejected prefix;
prefixes already rejected are not extended. Every surviving complete
prefix is evaluated with the objective above. The completed API output
therefore has the exact accounting identity

```text
4,431,608,000 non-Sidon subsets
+       5,550 evaluated Sidon subsets
= 4,431,613,550 total subsets
= C(53,9).
```

The rejected-prefix count is a count of pruned branches, not a count of
individual non-Sidon subsets. Both quantities are retained separately.
The API's completion status includes its exact final accounting check.
The JSON also retains every energy-histogram row; each energy is the
integer `gap_square_sum` divided by 45.

The actual call used `createSidonGapSearch({n:9, cutoff:52,
max_saved_minimizers:4096})`, then advances of at most 1,000,000 prefix
extension attempts each. It completed during advance 52, below the
operation's limit of 512 advances. The output reports
`minimizer_count = "18"` and `minimizers_truncated = false`.

No previous finite window was replayed, and the search/objective source
was not modified for this input. This was one new bounded mathematical
computation through the connected V8 runtime.

## Premises for the accepted reduction

Use `n=9`, `D=52`, `t = C(10,2) = 45`, and `v=254/45` in the
accepted `f_eq_of_search` declaration. Its cutoff condition is

```text
t * (t - 1) * v <= 4 * (D + 1)^2.

45 * 44 * (254/45) = 11176
4 * 53^2           = 11236
11176 <= 11236.
```

Equivalently, after clearing the denominator 45, the inequality is
`502920 <= 505620`. The candidate has nine elements, is Sidon, lies in
the chosen window and has the displayed energy. The exhaustive output
supplies the computational lower bound for every Sidon nine-set in
`Finset.range 53`.

Those are the concrete finite premises for the accepted interface's
conclusion `Erdos153.f 9 = 254/45`. The existing translation/diameter
reduction and its proof are accepted dependencies; they were not
reproved or rerun here. This publication retains the finite evidence
needed by a future admissible formal bridge and does not claim that such
a bridge has already been elaborated.

## Consume the retained result

The JSON is directly usable without running the search again:

```javascript
const record = JSON.parse(completeJsonText);
const result = record.search;

const minimum = result.minimum_energy;        // "254" / "45"
const allMinimizers = result.minimizers;       // all 18 explicit arrays
const energies = result.energy_histogram;     // all 129 exact count rows
const witness = record.candidate;             // complete sums and gaps
const cutoff = record.cutoff;                 // exact reduction arithmetic
```

The result schema is `erdos153.sidon_gap_search/v1`; the enclosing
certificate schema is `erdos153.n9_finite_premises/v1`.
Exact counts, gap-square sums and rational numerators/denominators are
decimal strings. Bounded search coordinates are JSON numbers.
The public API contracts and limits are documented in
[the eight-element API guide](N8_FINITE_PREMISES.md).
The saved JSON is a complete result, not a resumable traversal state.

## Sources and retained ownership

- [The original finite-value carrier, Commons PR #16049](https://github.com/woahwhattheheck/commons/pull/16049),
  merged at `d1e76d7d0a7511ec8f66d8ca336cc44f1896a97e`, owns the earlier
  `n=5,6,7` computation and handoff. Its files and submission ownership
  are preserved.
- [The connected API and eight-element input, Commons PR #31130](https://github.com/woahwhattheheck/commons/pull/31130),
  merged at `2b794162c6ad3d571c376a5c7cbe3f7f69362f89`.
  This run consumed the complete literal-main module with blob
  `82f165edd18b7d71f5746f96ff606ad14fe0aadf`.
- [The accepted contribution source](https://github.com/conjectures-io/conjectures-contribution/blob/main/contributions/erdos-153/d283fe047b326ca9bb9de8919c667b521df46d9500cc839b50916321fee0192b/script.lean)
  contains `Contribution.Erdos153Gaps.f_eq_of_search`.
  The retained source blob is
  `546fb3a40683a5e33956262b2a46ca55bace0218`; the accepted contribution
  identifier is
  `d283fe047b326ca9bb9de8919c667b521df46d9500cc839b50916321fee0192b`.
- [The Erdős 153 target page](https://conjectures.io/problems/erdos153-erdos-153)
  and [the Formal Conjectures target](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/153.lean)
  provide the objective and overall conjecture context.
  The retained target type hash is
  `b35a9b51e1956e50dac187c15f5e0fd861c1ae3dcaaceb7941a1ce9bfd770316`.

Operation: `ERDOS153-N9-GAP-SEARCH-20261004-7CA6`. The narrow claim is
message `1791099437.051339` in the original mathematics thread
`1789745818.950459`, channel `C0C3MEWHTR6`.
No sponsor submission, new Lean receipt, bounty, revenue or asymptotic
conclusion is represented by this carrier.
