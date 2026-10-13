# Erdős 153 exact-value extension: finite certificates for `f(5)`, `f(6)`, `f(7)`

This carrier advances the live Conjectures.io Erdős #153 target without duplicating the existing published contribution. The sponsor's current contribution index already contains a 59-declaration piece proving an infimum-free interface, attainment, a finite-search theorem `Contribution.Erdos153Gaps.f_eq_of_search`, exact values `f(2)=2/3`, `f(3)=4/3`, `f(4)=9/5`, and an asymptotic lower bound with ceiling 16. This carrier starts exactly where that piece stops.

Pinned source state used here:

- `conjectures-io/conjectures-tasks` main: `d9a67b509c5a8b220ba262c1c7ce26f61f52763a`.
- task-pinned Formal Conjectures repository commit: `8432eac998110a563e03df65a28c117e97c8c142`.
- formal target type hash: `sha256:b35a9b51e1956e50dac187c15f5e0fd861c1ae3dcaaceb7941a1ce9bfd770316`.
- `conjectures-io/conjectures-contribution` main: `f22e02d120e9b9e12a41848f74087934a922790e`.
- prior Erdős 153 contribution: `d283fe047b326ca9bb9de8919c667b521df46d9500cc839b50916321fee0192b`.

## Exact finite result

The dependency-free checker exhausts **every** `n`-subset of `range(D+1)`, checks the exact Formal-Conjectures Sidon condition via uniqueness of unordered pair sums, computes `A+A`, and evaluates the gap energy with `fractions.Fraction`. The cutoffs are the smallest integer `D` satisfying the published `f_eq_of_search` cutoff inequality for the displayed candidate value.

| n | D | all subsets | Sidon subsets | exact window minimum | minimizers | witness |
|---:|---:|---:|---:|---:|---:|---|
| 5 | 12 | 1,287 | 22 | `14/5` | 8 | `{0,1,4,9,11}` |
| 6 | 19 | 38,760 | 80 | `74/21` | 6 | `{0,1,4,10,15,17}` |
| 7 | 29 | 2,035,800 | 760 | `9/2` | 30 | `{0,1,4,10,18,23,25}` |

Together with the already-published and Lean-checked theorem `f_eq_of_search`, these finite premises identify the next three exact values **provided they are replayed inside that Lean interface**:

- `Erdos153.f 5 = 14/5`
- `Erdos153.f 6 = 74/21`
- `Erdos153.f 7 = 9/2`

The committed `receipt.json` hashes the complete ordered stream of Sidon candidates and exact energies for each cutoff, so a later Lean executor can detect any enumeration drift.

## Reproduce

From this directory:

```bash
python3 exact_values.py --write-receipt receipt.json
python3 -m unittest -v test_exact_values.py
python3 -O -m unittest -v test_exact_values.py
python3 -m py_compile exact_values.py test_exact_values.py
```

No network, floating point, randomization, third-party packages, or native code are used.

## Sponsor handoff / evidence ceiling

This is intentionally **not** represented as a sponsor-accepted contribution yet. The sponsor requires every contribution `.lean` file to elaborate by itself against the pinned Mathlib/Formal Conjectures environment; sibling contribution scripts cannot be imported. The useful finite-search theorem we compose with currently lives inside the prior immutable contribution rather than the task source. Therefore a sponsor-ready second piece must either (a) factor an admissible nonduplicative reusable interface into the sponsor's accepted source path, or (b) restate enough of the bridge in a self-contained way and pass exact `contrib check` plus Lean elaboration. This runtime has not produced that kernel receipt.

The finite enumeration itself is exact and independently reproducible. It does **not** prove the asymptotic conjecture `Filter.Tendsto Erdos153.f Filter.atTop Filter.atTop`, does not close the $4,296 solve bounty, and is not a payment/revenue claim.

## Eight-element continuation and connected API

[The eight-element finite premise](N8_FINITE_PREMISES.md) records a new exact
minimum of `11/2` for Sidon eight-sets in `[0,42]`, with the numerical cutoff
needed by the accepted `f_eq_of_search` reduction.
[The complete output](n8_finite_premises.json) accounts for all 145,008,513
subsets and retains all 32 minimizers.
[The connected search/objective API](sidon_gap_search.cjs) supplies bounded
prefix traversal and exact witness data without native execution.
The preceding `n=5,6,7` computations remain as recorded above.

## Nine-element continuation

[The nine-element finite premise](N9_FINITE_PREMISES.md) records the exact
minimum `254/45` for Sidon nine-sets in `[0,52]`, with the sufficient
cutoff `11176 <= 11236` for the accepted finite-search reduction.
[The complete retained output](n9_finite_premises.json) accounts for all
4,431,613,550 subsets, including 5,550 Sidon sets, and keeps all 18
minimizers plus the full energy histogram.
This new input used the unchanged connected API; the earlier finite
computations were not rerun.

## Translation-weighted API and ten-element continuation

[The translation-weighted API](TRANSLATED_SEARCH_API.md) traverses
minimum-zero representatives and uses exact binomial weights to retain
complete coverage of the original finite window.
[Its ten-element input](N10_FINITE_PREMISES.md) has exact minimum
`376/55` in `[0,71]`, with sufficient cutoff `20304 <= 20736`.
[The complete output](n10_finite_premises.json) accounts for all
536,211,932,256 original subsets through 74,473,879,480 normalized
subsets and retains all 24 minimizers, both families, the full weighted
energy histogram and 126 explicit seed-extension collision witnesses.
The original API and earlier finite outputs are unchanged.
