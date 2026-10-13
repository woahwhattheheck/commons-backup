# Exact finite Reed–Solomon lists

Count and navigate the full codewords around one fixed received word, with closed Hamming radii, optional coordinate puncturing and prescribed matches. Every polynomial is evaluated once; saved queries decode packed codewords without polynomial reevaluation.

For the length-13, dimension-four code over F13 and the declared received word, the complete 28,561-codeword index has 791 agreement fibers. Minimum distance is seven with seven nearest codewords; closed radius-eight and radius-nine lists have 58 and 413 codewords.

- [API, derivation and exact scope](REED_SOLOMON_LISTS_API.md)
- [CommonJS module](reed_solomon_lists.cjs)
- [Complete fibers and all packed codewords](prime13_received_word_certificate.json)
- [38 saved responses and nine condition records](saved_reader_queries.json)

The conventions follow [McEliece’s author-primary account](https://tmo.jpl.nasa.gov/progress_report/42-153/153F.pdf). This is a fixed-center bounded enumeration, not a worst-case list-size threshold or prize claim. The linked 2026/680 PDF was unavailable and remains outside the source evidence.
