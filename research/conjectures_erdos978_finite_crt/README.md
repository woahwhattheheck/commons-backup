# Erdős 978(iii): finite CRT sieve continuation

Target: prove that `n^4 + 2` is squarefree for infinitely many natural numbers.  The original #16072 carrier records Conjectures.io task `fc-8432eac9-parts-iii-778ca9541c-formalized-v1`, commitment `sha256:b80bef9dde235afd4e086e4500d7be4747b878494fb94a14589c639decefc67a`, source-type SHA-256 `3e683925ba54f309a76278d99386826c87b151bb5cb1df828d0e3643f0e240fa`.

## What is new here

The already-published sponsor contribution `9a9241fd706f8b096cd34d40d7d6ba62d230f954361dd8d648e3fb21591f0d0b` (script Git blob `8c2962f14f9dfce9ee59b00479d891800f6a7666`) owns the local theory: odd-prime Hensel correspondence, at most four bad residue classes modulo `p²`, and the restriction that square obstructions can only come from primes `p ≡ 1 or 3 (mod 8)`.

This carrier does **not** repeat those lemmas.  It composes them over a finite set of distinct primes using the Chinese remainder theorem.  If `b_p` is the number of bad residue classes modulo `p²`, then for any finite set `P` of distinct primes the exact number of classes modulo

`M = ∏_{p∈P} p²`

that avoid every local obstruction `p² ∣ n⁴+2` is

`G(P) = ∏_{p∈P} (p² - b_p)`.

For odd primes the existing `b_p ≤ 4` bound therefore yields

`G(P) ≥ ∏_{p∈P} (p² - 4) > 0`.

So every *fixed finite* family of prime-square obstructions leaves a nonempty periodic set of admissible integers.  This is a useful bridge from local Hensel data to a finite sieve, but it does **not** control square divisors from arbitrarily large primes and therefore does not prove the target.

## Independent exact evidence

`finite_crt_sieve.py` is standard-library only.  It recomputes roots modulo `p` and `p²`, checks the local Hensel-cardinality contract for every prime through 251, checks the mod-8 filter, constructs CRT combinations, and performs a direct exhaustive enumeration over the full period for `P={3,11,19}`.  The direct count must exactly equal the product count; the generated `receipt.json` records both and binds the source/task identities above.

Run from this directory:

```bash
python -m py_compile finite_crt_sieve.py test_finite_crt_sieve.py
python -m unittest -v test_finite_crt_sieve.py
python -O -m unittest -v test_finite_crt_sieve.py
python finite_crt_sieve.py --receipt > receipt.json
```

## Formalization handoff

`LEAN_HANDOFF.md` gives a sponsor-shaped decomposition for the genuinely new CRT composition lemmas.  It is intentionally marked **UNEXECUTED** in this environment.  A sponsor submission should happen only after the file is turned into a self-contained `Contribution.*` Lean script, elaborated against the exact pinned task environment, and run through the current contribution checks.

## Connected CRT index and retained local data

[Exact CRT addressing](CONNECTED_CRT_INDEX.md) documents the dependency-free
`BigInt` interface in [finite_crt_index.cjs](finite_crt_index.cjs).
[The retained prime block](prime_block_252_1024.json) contains complete local
obstruction/lift records for `251 < p <= 1024` and actual rank/select use over
their 654-digit product modulus. This is a reusable API and data continuation;
the guide credits the prior report's overlapping calculations. The accepted
prime range through 251 and the original finite/global evidence boundary remain
as recorded above.

## Ordinary numerical interval navigation

[The numerical interval guide](NUMERIC_RESIDUE_INTERVAL_INDEX.md) documents
[residue_interval_index.cjs](residue_interval_index.cjs). It compiles forbidden
congruence hits in a finite interval and indexes the complementary gaps in
increasing integer order. Its work budget bounds emitted congruence hits, and
the saved exclusions can initialize a fresh runtime without recompilation.

[The complete interval dataset](residue_interval_45773612811_45775397187.json)
uses the retained 118 prime rules above on the inclusive interval
`[45,773,612,811, 45,775,397,187]`. Its 816 distinct exclusions have explicit
proper square-divisor witnesses; the remaining 1,783,561 candidates occupy
817 maximal gaps, all retained with numerical rank ranges. The endpoint values
come from [Commons #31166](https://github.com/woahwhattheheck/commons/pull/31166).
They determine this consumer's interval and confer no quartic squarefreeness
property. The result concerns exactly the selected primes `251 < p <= 1024`.
