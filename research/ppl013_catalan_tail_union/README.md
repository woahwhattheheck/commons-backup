# Restricted prime + Fibonacci + Catalan navigation

An exact union navigator for p+1+Cj with p in the retained seven-prime palette {3,5,7,11,13,17,19}, j>=0, and source-given F1=F2=1.

The complete prefix has 23 target integers from 28 value representations and 70 index-labelled representations. From Catalan index 5 onward, increasing gaps separate the translated blocks. The API supports arbitrary BigInt symbolic numeric-order rank/select, exact palette conditions and bounded decimal queries with an append-only Catalan cache.

Read [CATALAN_TAIL_API.md](CATALAN_TAIL_API.md) for the separation proof, schema, alias conventions, all 231 saved responses and fresh query-work accounting. [SOURCE_QUALIFICATION.md](SOURCE_QUALIFICATION.md) binds the actual Hou–Zeng statement in Sun's paper. Complete source/input/plan/certificate/reader and public checkpoints are included.

This is a deliberately restricted subfamily, not a full PPL013 verifier, an existence-range extension or a conjecture counterexample search. No Fibonacci recurrence, primality, old triangular collision work, source example or proof was replayed. Rank 10^100 selections remain exact symbolic expressions; their decimal expansions were not computed.
