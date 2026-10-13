# Projected quotient DFA with prime exceptions

This index projects the accepted q=7 and q=13 relation graphs from Commons #31552 onto their output integers and forms a new complete product DFA. It counts distinct y values, including overlaps, and supplies exact prime-exception or proper-factor certificates for accepted values.

At binary length 24, the 730-state DFA accepts 455,789 distinct values: 287,447 through only q=7, 156,390 through only q=13 and 11,952 through both. Its only accepted primes are 7 and 13 under the identified source and prime-constant premises. Every other accepted value has a proper factor 7 or 13.

- [API, proof, ordering and source scope](PROJECTED_PRIME_DFA_API.md)
- [CommonJS module](projected_prime_dfa.cjs)
- [Complete product graph and coefficient manifest](quotients7_13_projected_dfa.json)
- [All 25 saved-reader outputs](saved_reader_queries.json)

Five consecutive coefficient shards retain every state and all 54,750 cells for lengths 0–24. The fresh reader counted 914,156 accepted values at most 2^24−1, of which 914,154 are composite, and returned exact factor 7 for 7*2^1000. It reconstructed no relation, projection, product or count table.

The general Shallit question concerns arbitrary DFAs. This fixed-factor language does not settle that question, and rejected integers receive no primality conclusion. The graph is complete but is not claimed minimal. Source lineage and the inherited all-length arithmetic semantics are explicit in the guide.
