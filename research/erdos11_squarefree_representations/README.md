# Squarefree-plus-power representation navigator

The index retains every representation of the 4,096 odd integers from 2^27+1 through 2^27+8191 as a positive squarefree remainder plus a power of two, including exponent zero.

- [API, scope and actual evidence](SQUAREFREE_REPRESENTATIONS_API.md)
- [Constructor and saved reader](squarefree_representations.cjs)
- [Complete interval index](odd_window_2pow27_index.json)
- [All 34 saved reader outputs](saved_reader_queries.json)

There are 91,257 representations. The unique minimum is 15 at n=134,222,629; 34 integers admit all 28 exponents. Complete prime-square rejection witnesses, conditional counts and six inverse-rank comparisons are retained.

The identified prime basis is reused without its old sieve or least-factor computation. The formal source already records existence below 2^50; this package adds finite representation navigation and does not claim a new range or a global theorem.
