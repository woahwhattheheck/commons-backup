# Run-length prefixes: finite factor index

Exact comparison of two literal published words associated with Kimberling's segment-containment question:

- A025142 source indices 1–1004, the complete initial block retained from its b-file;
- A025143 target indices 1–111, the complete retrieved synthesized b-file.

The target has 5,124 distinct nonempty factors: 2,787 occur in the retained source and 2,337 do not. Every target factor through length 26 is present. Two length-27 factors are the shortest absent ones. The unique longest shared factor has length 66 and occurs at target index 31 and source index 325.

These absences concern only the source prefix. The remainder of the advertised 10,000-row A025142 b-file was not fully retained, and nothing is inferred about the infinite sequence.

## Files

- [finite_factor_index.cjs](finite_factor_index.cjs): generalized suffix/LCP constructor and saved count/rank/select/occurrence queries.
- [FACTOR_INDEX_API.md](FACTOR_INDEX_API.md): source conventions, correctness argument, complete contract and custody limits.
- [published_prefix_factors.json](published_prefix_factors.json): literal inputs, complete suffix/LCP tables, count intervals, occurrence-minimum trees and all 28 saved-reader outputs.

## Use saved data

    const { open } = require("./finite_factor_index.cjs");
    const packet = JSON.parse(savedText);
    const reader = open(packet.construction.snapshot);
    const missing = reader.openSlice(reader.shortestAbsent()).page(0,64);
    const occurrence = reader.occurrences("target", missing.items[0].word, 0, 8);

Opening saved data performs structural checks without rebuilding suffix order, LCPs or the source sequences. Query comparisons, interval scans and output extraction are explicitly counted. Structural validity does not independently authenticate a saved construction.

All ranks and offsets are zero-based; companion index fields are one-based. Occurrence pages use lexicographic suffix order, while first_index separately gives the earliest numerical position. Factors are contiguous, nonempty and counted as distinct words, including overlapping occurrences.

The author asks containment from t=r(s) into s. Neither truncated run lengths nor the reversed direction of a following illustration are substituted for that statement. No global containment, counterexample, novelty or prize claim is made.
