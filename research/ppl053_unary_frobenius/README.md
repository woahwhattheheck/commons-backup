# Unary Frobenius and missing-length index

For unary dictionary lengths {26,51,101,126,251,276,351,551,626}, exactly **343** lengths are missing. The largest is **651**, and the conductor is **652**.

- [Source correction, mathematics and API](UNARY_FROBENIUS_API.md)
- [Dependency-free CommonJS implementation](unary_frobenius.cjs)
- [Complete residue and edge certificate](unary_dictionary_certificate.json)
- [All 26 saved-reader outputs, including every gap](saved_reader_queries.json)

The catalogue asks about infinitude of L* itself, while Mika–Szykuła's historical account identifies Shallit's listed question as co-finiteness. A missing complement bar is a plausible transcription explanation, but the screenshot response was only a placeholder; visual verification was not obtained. Mika–Szykuła settled general co-finiteness as PSPACE-complete in 2021. This package provides a restricted unary navigation capability, with exact count/rank/select and compressed decompositions, rather than a new complexity result.

The declared lengths are 25a+1 for the retained nine-element output of [#31584](https://github.com/woahwhattheheck/commons/pull/31584); no prior AP or weighted calculation is replayed. A saved doubled-dictionary view exposes the infinite-complement case without rebuilding the normalized residue graph.
