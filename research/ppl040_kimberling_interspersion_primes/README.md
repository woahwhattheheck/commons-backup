# Kimberling 15: exact row-prime intervals

This directory supplies a bounded exact sieve and saved navigation API for the specific triangular-number array
\[
T(r,c)=r+(r+c-2)(r+c-1)/2,\qquad r,c\ge1.
\]
The formula is in Kimberling's [A185787 comments](https://oeis.org/A185787); his [section 15 question](https://faculty.evansville.edu/ck6/integer/unsolved.html) concerns infinitely many primes in each row.

The new finite consumer uses **row 493, columns 10,001–22,000**. It retains **1,124 primes and 10,876 composites**, with every composite's least prime divisor, quotient and local rule reference. The initial 10,000-column interval contains 953 primes; a saved-rule append adds 171 primes in 2,000 new columns.

| File | Purpose |
| --- | --- |
| [interspersion_row_prime_index.cjs](interspersion_row_prime_index.cjs) | Exact compiler, saved append and finite count/rank/select API |
| [ROW_PRIME_INTERVAL_API.md](ROW_PRIME_INTERVAL_API.md) | Source conventions, complete local/sieve proof, API and execution bounds |
| [row493_columns10001_20000.json](row493_columns10001_20000.json) | Complete initial basis, rules, 10,000 classifications and work record |
| [row493_columns10001_22000.json](row493_columns10001_22000.json) | Complete final 12,000-column index, append provenance and saved-query results |

```js
const { openRetainedInterspersionRowPrimeIndex } =
  require("./interspersion_row_prime_index.cjs");
const saved = require("./row493_columns10001_22000.json");
const index = openRetainedInterspersionRowPrimeIndex(saved.snapshot);

index.selectPrime("562");          // column 15872, value 133882559
index.countPrimesThrough("21000"); // 1045 within the retained interval
index.recordAtColumn("22000");    // 252934279 = 13 * 19456483
```

The complete basis has 1,900 primes through 16,384. Odd-prime hit rules use the discriminant \(1-8r\); prime 2 uses a separate period-four rule. A hit equal to its basis prime remains prime. All values left unmarked above one are prime because the basis covers every possible least divisor of a composite in the interval.

The append reused the complete basis and all local rules and processed only its new columns. The final reader returned six query results without rebuilding a basis, finding modular roots or resieving a column. Loading checks structure and consumes the saved mathematical premise; it does not authenticate arbitrary supplied data.

Ranks and counts concern only the recorded interval, beginning at column 10,001. Row 493 reuses only the accepted #31400 point-count scalar. These finite data and methods make no infinitude, asymptotic, global-frontier or novelty claim; the source's conditional prime-polynomial discussion retains its attribution.
