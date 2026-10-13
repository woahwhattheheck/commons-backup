# Arithmetic progressions of consecutive primes

This finite saved index separates AP and non-AP blocks in the supplied 1,900-prime prefix from 2 through 16,381. Blocks have length at least three and must be consecutive in the global prime list.

- [API, source conventions and finite result](CONSECUTIVE_PRIME_AP_API.md)
- [Constructor and saved reader](consecutive_prime_ap.cjs)
- [Complete equal-gap runs and start records](prime_prefix1900_ap_index.json)
- [All 43 reader outputs](saved_reader_queries.json)

There are 113 AP blocks: 101 triples and 12 quadruples. The other 1,802,038 blocks are non-AP. All 1,890 eleven-prime windows have retained first unequal-gap witnesses.

No prime or gap calculation was repeated. The 43 outputs include nine exact inverse ranks and an explicit four-query continuation after a neutral-condition input correction; the constructor and earlier queries were not rerun. These finite results establish no new prime-search range, eleven-prime resolution or global infinitude statement.
