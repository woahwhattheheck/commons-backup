# Totient shift queries

An exact finite divisor-family index for phi(n) dividing n+a, with arbitrary signed shift queries and parameter-window pair navigation.

The retained prime-exponent box has 16,384 positive n and 16,375 congruence classes. Eight complete row shards and eight complete kernel shards support the reader. The saved consumer includes all matches at shifts 0, -1 and 1, a congruent parameter with over a thousand digits, and exact rank/select over a window containing 84554615105186672910327581 pairs.

Read [TOTIENT_SHIFTS_API.md](TOTIENT_SHIFTS_API.md) for the prime-input premise, finite proof, exact conventions, full identities, API and work accounting. The source is [totient_shifts.cjs](totient_shifts.cjs), the manifest is [primes17_cap3_index.json](primes17_cap3_index.json), and complete queries/caches are in [saved_reader_queries.json](saved_reader_queries.json).

The set of n is fixed and finite. Varying a without bound does not prove the Erdős828 requirement of infinitely many n for every fixed a. Pair counts do not deduplicate shift values, and n=1 with phi(1)=1 remains explicit.
