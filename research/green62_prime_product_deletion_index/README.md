# Green 62: prime product deletion index

For all 54 primes below 257, this package retains all 1,485 unordered two-prime products, including diagonal pairs, and every nonzero residue's complete family of coverage-destroying prime deletions.

Read [the API and source guide](PRIME_PRODUCT_DELETION_API.md). The core interface supports exact cardinality counts, ranks, selections, pages and complete surviving-coverage queries from saved data.

- [Compiler and reader](prime_product_deletion_index.cjs)
- [Literal input and inherited premises](input257.json)
- [Entire finite index](prime257_deletion_index.json)
- [All 47 fresh reader requests and outputs](saved_reader_queries.json)

All 256 targets are covered before deletions. Minimum target-destroying deletion sizes range from 1 to 11. Target 69 has 50,020,977,505,120 size-27 blocking deletion sets; saved rank/select navigates them without enumeration. A retained minimum 11-prime deletion loses only target 69.

The compiler reuses accepted prime and binomial-row premises. A first input-shape failure occurred before arithmetic; the corrected adapter and exact chronology are documented. Reader work does not rebuild modular products or coefficient tables. Counts across targets are target/deletion incidences, not distinct globally damaging palettes.

This fixed-modulus result does not settle Green's eventual-prime conjecture, establish a new threshold or claim a prize. The source attribution and repeated-factor convention are explicit in the guide.
