# Erdős 1142 primitive-root tail sieve

This carrier is a nonduplicate continuation of the published Conjectures.io contribution
“Erdős 1142: covering-congruence sieve pinning solutions to 15 mod 30 and 2145|n, with
decidability” (`8b087102…`). That piece already proves the general covering theorem and its
instances at `p = 3,5,11,13,19`, culminating in `40755 ∣ n` once
`n > 262163`.

## New mathematical content

For an odd prime `p`, the published covering theorem applies with `K = p-1` whenever `2`
is a primitive root modulo `p`: the powers `2^1,…,2^(p-1)` then hit every nonzero residue.
Consequently

`Erdos1142Prop n ∧ (2^(p-1)+p < n)  ⇒  p ∣ n`.

The exact classification of primes relevant to the Mientka–Weitzenkamp range `n ≤ 2^44`
is:

| p | ord_p(2) | threshold `2^(p-1)+p` | cumulative divisor |
|---:|---:|---:|---:|
| 3 | 2 | 7 | 3 |
| 5 | 4 | 21 | 15 |
| 11 | 10 | 1,035 | 165 |
| 13 | 12 | 4,109 | 2,145 |
| 19 | 18 | 262,163 | 40,755 |
| **29** | **28** | **268,435,485** | **1,181,895** |
| **37** | **36** | **68,719,476,773** | **43,730,115** |

The first five rows are already owned by the published contribution. **The new rows are
`p=29` and `p=37`.** They are also the last possible direct primitive-root instances that
can affect `n≤2^44`: every prime `p≥47` has threshold `2^(p-1)+p > 2^44`, while the exact
scan of primes through 45 shows that all the other odd primes fail the required covering
condition.

Thus the published `p=19` residual can be refined piecewise:

* `4109 < n ≤ 262163`: `2145 ∣ n` — 121 candidates (published continuity row).
* `262163 < n ≤ 268435485`: `40755 ∣ n` — 6,580 candidates.
* `268435485 < n ≤ 68719476773`: `1181895 ∣ n` — 57,916 candidates.
* `68719476773 < n ≤ 2^44`: `43730115 ∣ n` — 400,718 candidates.

That leaves **465,335** arithmetic candidates in `(4109,2^44]`, versus **431,657,237**
under the published `p=19` tail alone: an exact reduction by more than 900×. This still
does **not** prove the Mientka–Weitzenkamp finite classification, because each survivor must
still be checked against every required primality condition.

## Downstream residue refinement

The [nonprimitive refinement](NONPRIMITIVE_REFINEMENT.md) consumes the accepted
four intervals and recorded orders, then applies parity and p = 7, 17, 23, 31,
41, 43. Its exact proper-divisor API reduces the 465,335 arithmetic candidates
to **10,618** and publishes the complete
[surviving candidate dataset](residual_candidates.json) for further work.
The predecessor certificate below remains the original primitive-root result.
The new guide also records the October 4 canonical task-pin change; the
September pins below remain historical.

### Completed residual tail

The [explicit residual completion](RESIDUAL_COMPLETION.md) now supplies a
proper factorization for every one of those 10,618 saved candidates. Combined
with the preceding reductions, this leaves **zero possible solutions in
`4109 < n <= 2^44`**. The complete
[indexed witness dataset](residual_exclusion_witnesses.json) is available for
downstream formalization; the two earlier sieves were not rerun. The lower
range through 4,109 and the global conjecture remain outside this continuation.

## Exact executable evidence

`verify_tail.py` uses only the Python standard library. It:

1. enumerates all primes `≤45`;
2. computes the exact multiplicative order of `2 mod p`;
3. checks the complete nonzero-residue covering for every primitive-root prime;
4. records explicit least-exponent covering witnesses and SHA-256 digests;
5. checks both new thresholds and cumulative products; and
6. recomputes every piecewise residual count through `2^44`.

`receipt.json` is generated canonically from that computation. Its payload SHA-256 is:

`24f36e4f7dcb1bf81366a0fc825f81cced7a10c41b81e9bc4ba0366c81c9c4aa`

Run from this directory:

```bash
python verify_tail.py
python -m unittest -v test_verify_tail.py
python -O -m unittest -v test_verify_tail.py
python -m py_compile verify_tail.py test_verify_tail.py
```

## Sponsor/source pins

* Task: `fc-8432eac9-erdos1142-erdos-1142-a29719d6af-formalized-v1`
* Task commitment: `60a1381809a9c064c907712012dcc037343ee3d39486f392c00e34a42dda7b4d`
* Source type SHA-256: `140c4194bf440ed9095b2b1a1f8cb6b534b1f4738ee1c9d78a89ec890ed38632`
* Existing published contribution: `8b08710200d75e84c26054cc34ad7f155d26ca3c649f5e06290878af8770409b`

See `LEAN_HANDOFF.md` for the exact intended formal statements and the self-containment caveat.

## Evidence ceiling

This is a rigorous finite-premise certificate and mathematical reduction, not a proof that
there are infinitely many Erdős-1142 numbers, not a proof of the finite classification through
`2^44`, and not a sponsor-accepted Lean contribution.
