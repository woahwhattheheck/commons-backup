# Factorial-shift prefixes and exact tail enclosures

The positive-index model fixes b1=1, permits b2..24 in {1,2}, fixes b25..48=2, and allows every later shift in {1,2}, in the additive-denominator series Σ 1/(n!+b_n). The index represents 8,388,608 finite prefixes without enumerating them. All their rational tail enclosures are disjoint.

- [API, derivation, source conventions and actual results](FACTORIAL_SHIFT_PREFIXES_API.md)
- [Compiler and saved reader](factorial_shift_prefixes.cjs)
- [Complete input-specific index](cutoff48_variable24_index.json)
- [All 44 actual reader responses](saved_reader_queries.json)

The reader provides exact numeric-prefix rank/select, carry gaps, threshold and window counts, enclosure location and certified-or-undecided radix prefixes. Six rank inverses and three strict/non-strict threshold pairs match. Forty-place decimal queries certify for the three selected ranks; 80-place requests remain undecided.

Only identified factorial rows from #31740 are reused, with no recurrence replay. Kovač–Tao's Type3 additive-shift convention is kept separate from the formal Nat-index sum. An enclosure hit does not prove an infinite value is attained, and this package does not establish irrationality or the general bounded-shift assertion.
