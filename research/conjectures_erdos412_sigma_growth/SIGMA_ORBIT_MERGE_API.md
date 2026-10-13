# Exact finite sigma-orbit merge

The public module [sigma_orbit_merge.cjs](sigma_orbit_merge.cjs) compares two increasing orbits of the sum-of-positive-divisors function. It records an exact factorization witness for every completed transition and stops at a meeting or an explicit finite limit. It runs as plain CommonJS in connected V8, without imports, native programs, network access or I/O.

The actual consumer uses the first two retained values from [the #31166 digit-survivor dataset](../conjectures_erdos376_digit_exact_20260918/interval_1000001_1000000000000.json): **59,548,377** and **59,548,401**. Their digit property supplies concrete existing inputs; it implies no relationship between their sigma orbits.

That new run computed **18 transitions, nine per seed**, and reached two distinct heads above the direct factor-input cap. Its complete records establish **no common orbit value at most 3,643,474,348,799**. The next possible common value is not excluded. The API, full paths and factorized records are published together in [sigma_orbits_59548377_59548401.json](sigma_orbits_59548377_59548401.json).

## Sources and mathematical conventions

Erdős attributes the underlying question to a conjecture that van Wijngaarden described to him in the early 1950s; see §1, printed page 71 of [Erdős's 1979 paper](https://www.renyi.hu/~p_erdos/1979-23.pdf). Erdős also records that numerical experiments by Selfridge and others led them to suspect a negative answer. This package preserves that attribution.

Here, sigma is the sum of **all positive divisors**, including one and the input itself. The [current Formal Conjectures statement](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/412.lean), read at blob 1c4dcea6de61664cc8ece2068d9cf8f6151763fc, asks whether every pair of seeds m,n at least two has independent natural indices i,j satisfying sigma^i(m) = sigma^j(n). The indices may differ and may be zero; sigma^0(n) = n. Seed one is outside the question.

Allowing zero does not change the unbounded existence question, because any equality can be advanced once on both sides. It can change a question restricted to a numerical cutoff, so the API reports the actual zero-based indices. Equal inputs produce a meeting at indices zero without a factorization.

[Cohen and te Riele, *Iterating the Sum-of-Divisors Function*, Experimental Mathematics 5 (1996), 91–100](https://ir.cwi.nl/pub/10355/10355D.pdf), §4, report 21 orbit trees for starting values 2 through 200 that remained distinct at the 10^200 boundary, and 64 trees for starts through 1000 with a 10^100 boundary. They compare the first terms beyond the specified cutoffs. These are historical finite computations; their statement that separation continues is a conjecture.

The [July 28, 2026 working report](https://www.erdosproblemaday.com/report/412), credited to Patrick White with model assistance disclosed there, reports no common value at most 10^342 for the seed-two and seed-five orbits. The report is labelled PARTIAL and expressly not independently verified. That computation is cited as prior work and was not replayed or certified here. This new Commons input makes no external frontier or priority claim.

The original [#16060 carrier](https://github.com/woahwhattheheck/commons/pull/16060) supplies the accepted strict-growth reduction for seeds at least two. This API consumes that result. Its 9,999 one-step checks and 2,040 transitions from seeds 2 through 256 were not rerun. The original arithmetic, receipt, Lean, source and test files remain unchanged.

## Why advancing the smaller head is sufficient

Write A_i = sigma^i(m) and B_j = sigma^j(n). The accepted reduction makes both sequences strictly increasing. Keep one current head from each sequence.

If the heads agree, return that value and the two current indices. Otherwise, discard and advance the smaller head. Suppose A_i < B_j. Every future term of the second orbit is at least B_j and therefore exceeds A_i. Every earlier term of that second orbit was already discarded at an earlier merge decision, when it was below the then-current first-orbit head, and cannot equal any later first-orbit term. Thus A_i cannot be a common value.

Inductively, **every discarded head is absent from the other entire orbit**. An undiscovered common value must therefore lie in both remaining tails, and hence be at least

\[
\max(A_i,B_j).
\]

This gives the closed excluded interval from zero through max(A_i,B_j) − 1. If the heads agree, their common value is the least common value; earlier values have already been excluded.

The conclusion is useful even when the smaller remaining head exceeds the factor-input cap. In the actual run, the current heads are

\[
A_9=2{,}839{,}668{,}249{,}600,\qquad
B_9=3{,}643{,}474{,}348{,}800.
\]

Both are above 10^12. The invariant excludes all values below the **larger** head, so it excludes every common value through 3,643,474,348,799. It does **not** exclude B_9 itself: a later term of the first orbit could equal it. No factorization of either remaining head was performed.

## Exact divisor sums and work bounds

For an input factored as n = product of p^e, the API uses

\[
\sigma(n)=\prod_{p^e\parallel n}(1+p+\cdots+p^e).
\]

Unique prime factorization identifies each divisor by an independent exponent choice, giving the product of the geometric sums. Each record contains the prime, exponent, prime power and geometric sum, along with the reconstructed input product and resulting sigma product.

The direct factorizer tries two and then increasing odd divisors. A divisor that extracts a factor must be prime: otherwise its smaller prime factor would already have been removed. Once the next trial divisor squared exceeds the residual, any residual greater than one is prime. The loop uses a non-strict square comparison, so a remaining square is still tested.

The direct input cap is 10^12. Residuals, successful integer quotients, trial divisors and their squares stay within Number's exact integer range. Successful divisions have integral, exactly representable quotients. Prime powers, geometric sums, factor products and sigma products use BigInt. Heads and input parsing likewise use BigInt, including a resulting head above the direct factor cap.

At most 500,000 distinct trial candidates can occur below the cap. There are at most floor(log2(10^12)) = 39 successful quotient divisions. The declared bound of **500,040 remainder tests and 39 quotient divisions per transition** is conservative. A batch contains at most 16 transitions, so it performs at most 8,000,640 remainder tests. The chosen 256-transition run had a declared total bound of 128,010,240 remainder tests; it actually used 1,677.

Work counters record remainder tests, successful exact quotient divisions, trial candidates, factorizations, retained prime-power factors and logical head-order decisions. One head-order decision occurs initially and after each completed transition; this counts three-way ordering decisions, not individual JavaScript comparison operators.

The factor records retain trial counts, the last tested divisor and the terminal square/residual bound. They do not retain every unsuccessful trial remainder or separate formal primality certificates. Their prime designations come from the documented deterministic trial algorithm.

## Public API

The module exports sigmaFactorization, createSigmaOrbitMerge and limits. All returned values are JSON serializable. Mathematical integers are decimal strings; bounded indices, exponents and work counters are ordinary safe integers.

### sigmaFactorization(value)

The point operation accepts a positive input through 10^12 and returns the complete sigma factorization record. It accepts BigInt, a safe integer Number, or a canonical decimal string. Negative inputs, zero, noncanonical strings and values above the cap are rejected.

For input one, it returns the empty prime-factor list and sigma equal to one. This point-operation endpoint does not add seed one to the orbit factory's domain.

Its output schema is erdos412.sigma_factorization/v1. The actual consumer called it only through the merge; no extra point inputs or synthetic suite were run.

### createSigmaOrbitMerge(options)

Options are:

| Field | Contract |
| --- | --- |
| left, right | Natural seeds at least two, supplied as BigInt, safe integer Number or canonical decimal string; at most 256 decimal digits |
| factor_limit | Optional integer from two through 10^12; default 10^12 |
| max_transitions | Optional integer Number from one through 1024; default 256; counts completed transitions across both orbits |

Seeds may exceed the factor limit. Equality is checked first; otherwise the factory can immediately report a finite factor boundary. The factor limit bounds inputs to the direct factorizer, not the magnitude of returned sigma values.

The returned handle has three methods:

| Method | Result |
| --- | --- |
| describe() | Current heads and indices, status, finite excluded interval, meeting or next required transition, continuation fields and work counts |
| advance(transitionBudget) | Complete up to the requested number of new transitions, from one through 16; default 16; return the new description |
| records({start_index, limit}) | Copy a page of complete transition records; default start zero, default and maximum page length 256 |

Record indices are zero based. A page start may equal the processed record count, producing an empty final page. The next_start_index field is null only at the end of the records currently processed by that handle. The page also reports the handle's status and processed_record_count.

The handle preserves state across bounded calls while it remains alive. Returned descriptions and record copies do not expose mutable internal arrays. An invalid request throws an Error with a code field. Invalid bounds or inputs do not commit a transition. There are no partial factorization records: each committed event contains one complete factorization.

### Status and continuation semantics

| Status | Meaning |
| --- | --- |
| IN_PROGRESS | The smaller current head can be factored, and transition capacity remains |
| MEETING | The current heads agree; meeting contains the value and both independent local indices |
| FACTOR_LIMIT | The smaller current head exceeds factor_limit, so both current heads are beyond that input limit |
| TRANSITION_LIMIT | The configured number of complete transitions has been reached |

The priority is equality, factor-input limit, then transition limit. Calling advance on a terminal handle returns its current description without further arithmetic.

Every description reports the sound closed interval in bounded_nonintersection. The field no_common_value_at_most_factor_limit is true if that interval covers the cap, false if a meeting at or below the cap was found, and null if the completed prefix decides neither conclusion.

An unfinished description exposes the two current heads in continuation.tail_options and their separate index_offsets. Starting a fresh factory from those heads starts the two remaining tails with local indices zero; later indices must be added to the saved offsets and accompanied by the already-retained prefix records. This is a composable tail restart, not serialization of a hidden live handle.

For this actual result, both continuation capability flags are false: the next required input, 2,839,668,249,600, exceeds even the hard direct factor cap. Re-instantiating this module with its returned tail options immediately reports FACTOR_LIMIT. Further progress requires an implementation able to evaluate sigma at the retained heads. The full 18-transition prefix remains reusable.

### Connected V8 invocation

The recorded consumer used the complete module text as sourceText and the two values extracted from the retained JSON:

~~~javascript
const box = { exports: {} };
new Function("module", "exports", sourceText)(box, box.exports);

const run = box.exports.createSigmaOrbitMerge({
  left: retained.combined_result.values[0].value,
  right: retained.combined_result.values[1].value,
  factor_limit: "1000000000000",
  max_transitions: 256
});
let state = run.describe();
while (state.status === "IN_PROGRESS") {
  state = run.advance(16);
}
const page = run.records({ start_index: 0, limit: 256 });
~~~

The actual execution used one factory, one initial description, two advance calls and one record page. The second advance supplied the final two transitions and stopped at the factor boundary.

## Complete new finite result

The array index in each retained path is the iterate count:

| Index | Seed 59,548,377 orbit | Seed 59,548,401 orbit |
| ---: | ---: | ---: |
| 0 | 59,548,377 | 59,548,401 |
| 1 | 92,360,976 | 94,682,016 |
| 2 | 251,159,520 | 335,724,480 |
| 3 | 816,721,920 | 1,508,028,480 |
| 4 | 3,334,064,640 | 6,491,996,160 |
| 5 | 10,861,019,136 | 22,548,535,296 |
| 6 | 36,641,299,968 | 68,702,699,520 |
| 7 | 146,192,674,320 | 293,131,509,216 |
| 8 | 688,733,061,120 | 979,760,259,072 |
| 9 | 2,839,668,249,600 | 3,643,474,348,800 |

The final in-cap terms occur at index eight. Their exact outgoing sigma values establish the first above-cap terms at index nine.

The run retained all 18 input/output transitions, all 96 prime-power factors, each geometric-sum witness and both complete ten-term paths. It used 1,677 remainder tests, 252 successful quotient divisions, 1,425 trial candidates and 19 head-order decisions. Every record identifies the advanced side, its input/output indices and the opposite head at the decision.

For example, the first left input factors as

\[
59{,}548{,}377=3\cdot 7^2\cdot 405{,}091,
\]

so its recorded sigma product is

\[
4\cdot57\cdot405{,}092=92{,}360{,}976.
\]

The final left transition uses geometric factors 65,535, 13, 6, 14, 20, 32 and 62, whose product is 2,839,668,249,600. The final right transition uses 16,383, 13, 400, 18, 44 and 54, whose product is 3,643,474,348,800. These factors and the complete prime-power decompositions of the inputs are present in the JSON.

This finite nonintersection result leaves the two unprocessed tails unresolved. It does not settle the universal question, establish infinite separation, supply a new Lean elaboration or alter the original submission ownership.
