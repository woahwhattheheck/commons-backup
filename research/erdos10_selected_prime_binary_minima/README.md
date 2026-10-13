# Erdős 10: selected-prime binary-summand minima

Exact finite navigation for every 70-bit integer with the supplied primes 2, 3, 5, 7, 11, 13 and 17.

- 2,080 saved bit-template blocks represent 590295810358705651712 integers.
- The minimum number of powers after a selected prime ranges from 1 to 67; 7 integers attain 1 and 73 attain 67.
- All minimum and maximum members are exported in 47 saved reader responses, with 16 exact inverse-rank matches.
- Nine complete conditional caches are stored in three shards; fresh query work is reported separately.
- Rank order is low residue, high-part trailing-zero count and lexicographic free bits, not increasing integer order.

Read [the API guide](SELECTED_PRIME_BINARY_MINIMA_API.md) for the reduction, source attribution, exact input lineage, methods and limitations. Load [the saved snapshot](bit70_minima_index.json) with [the module](selected_prime_binary_minima.cjs). [The input](input70.json), [reader responses](saved_reader_queries.json) and [cache manifest](conditional_cache_manifest.json) are complete.

The source permits repeated exponents, exponent zero and the empty sum. Canonical binary expansions attain the selected-prime minimum. A selected representation is valid globally, but a large selected-prime minimum is not a global lower bound or counterexample. No old construction, published numerical example, external proof or accepted query was replayed.
