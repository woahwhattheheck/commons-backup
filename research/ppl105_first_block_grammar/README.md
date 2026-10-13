# First-block-bounded grammar

A finite automaton, terminal-first right-linear grammar, and exact saved word navigation for a restriction of Okhotin's Example 4 language. The first a-block length is at most seven; later block lengths and the total word length remain unbounded.

The complete certificate retains 53 minimal DFA states, all 1,378 shortest distinguishing-suffix records, 150 grammar rules, and 6,837 coefficient cells through length 128. There are 3261580183297445286869369238003347558 accepted words at that length. All 38 fresh reader responses are saved, including a 502-symbol membership/derivation query and exact prefix/rank/select traces.

Read [the API guide](FIRST_BLOCK_GRAMMAR_API.md) for source coverage, proof, limits and usage. The [constructor/reader](first_block_grammar.cjs), [complete certificate](bound7_language_certificate.json), and [reader outputs](saved_reader_queries.json) require no third-party package.

The grammar applies to the declared regular restriction. It does not resolve the general Greibach-normal-form question for Boolean grammars or claim a current prize result.
