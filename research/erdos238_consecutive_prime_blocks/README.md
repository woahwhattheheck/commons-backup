# Consecutive-prime blocks under raw-gap thresholds

This saved finite index covers the supplied 1,900-prime prefix from 2 through 16,381. It navigates nonempty consecutive blocks whose internal raw gaps are strictly greater than a threshold.

- [API, exact counting and source limits](CONSECUTIVE_PRIME_BLOCKS_API.md)
- [Constructor and saved reader](consecutive_prime_blocks.cjs)
- [Complete merge tree and threshold phases](prime_prefix1900_blocks.json)
- [All 37 saved reader outputs](saved_reader_queries.json)

The 22 phases and 3,799 tree nodes represent up to 1,805,950 contiguous blocks. At threshold 8, the unique longest block has ten primes, from 13,477 through 13,591; all 329 qualifying blocks of length at least three were exported.

The construction copies 1,897 old gap records and newly forms only the two omitted initial gaps. Reader arithmetic for 16 conditions is reported explicitly. These finite results do not establish the eventual logarithmic block-length claim in Erdős 238.
