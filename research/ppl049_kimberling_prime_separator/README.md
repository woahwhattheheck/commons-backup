# Kimberling prime separator array: saved finite continuation

The public CommonJS API continues Kimberling's array from an identified boundary prefix, retaining exact product frontiers, both new mex certificates and all newly covered values. It uses the old product square for both choices before adding either boundary.

The actual source seed is the complete published 60-pair prefix from [A129259](https://oeis.org/A129259/b129259.txt) and [A129260](https://oeis.org/A129260/b129260.txt). The construction follows [A129258](https://oeis.org/A129258); the motivating first-row-gap question is [Kimberling's section 12](https://faculty.evansville.edu/ck6/integer/unsolved.html).

## Result

One continuation added indices 61–256, and one saved-state append added 257–320. The final boundaries are R_320=1,237 and C_320=1,238. Every value from 204 through 1,238 is classified: 157 primes, 515 old-product composites and 363 selected composites. The new primes split 72 into the first row and 85 into the first column.

The largest gap among the 260 new first-row steps is 11, uniquely at index 96: 332 to 343. This is a finite interval result, not a uniform bound for all gaps.

## Use

- [PRIME_SEPARATOR_API.md](PRIME_SEPARATOR_API.md) gives the mathematical derivation, conventions, caps and API.
- [prime_separator_frontier.cjs](prime_separator_frontier.cjs) exports `continuePrimeSeparator`, `openRetainedPrimeSeparator` and `PRIME_SEPARATOR_LIMITS`.
- [seed60_through256.json](seed60_through256.json) retains the complete first-stage state.
- [seed60_through320.json](seed60_through320.json) retains the complete final state, append and saved-reader receipts.

Both data files are directly loadable through their `.snapshot` field. The final state supports prime count/rank/select, product/absence queries, boundary lookup, gap pages and later bounded append. Ranks are zero-based within the new value interval above 203; boundary indices are one-based.

All 520 selected-value certificates, 2,975 divisor-membership rows, 1,259 least-factor division steps, 515 proper-product witnesses and 1,035 classified values are retained. The final fresh reader exported all 260 gap rows and recovered rank 78 at prime 691 with zero product or factorization work.

The accepted 60-pair prefix and PR31426 prime/least-factor basis were consumed as premises. The old square, prior construction steps and prime sieve were not rebuilt. Saved loading is structural only. Other inputs and unexercised branches are source-inspected; no synthetic suite or exhaustive behavior claim is made.

Original attribution and the infinite question remain separate from this bounded API and computation.
