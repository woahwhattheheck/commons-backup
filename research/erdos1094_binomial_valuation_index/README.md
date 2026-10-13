# Erdős 1094: finite binomial valuation index

The complete lower-half triangle 2 ≤ n ≤ 256, 1 ≤ k ≤ floor(n/2) contains 16,384 binomial rows. Every row retains its full sparse prime-exponent factorization, least prime factor and the strict threshold condition from Formal1094.

Exactly 13 pairs have least prime factor greater than max(floor(n/k),k). All are exported with complete factors. The saved reader has 62 responses and 22 matching rank/select inverses, plus explicit fresh exact and modular products. These are finite-instance results, with no global finiteness or numerical-frontier claim.

Read [the API guide](BINOMIAL_VALUATION_API.md) for source attribution, the Legendre reduction, exact input lineage, assembly and limitations. [The manifest](triangle256_manifest.json) and eight row shards reconstruct the complete snapshot by byte identity. [The reader packet](saved_reader_queries.json) and [condition caches](saved_condition_caches.json) retain the actual navigation evidence.

Only literal prime values were reused from the identified earlier input; no old sieve, least-factor table, gap calculation or accepted binomial work was replayed. The complete-prime-prefix property is an inherited premise.
