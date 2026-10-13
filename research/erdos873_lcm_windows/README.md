# Contiguous LCM window navigation

A complete finite index for all 134,225,920 nonempty contiguous windows of the 16,384 accepted increasing smooth values from #31649. The 100,848 endpoint runs support strict rational-threshold counts, full length profiles and exact window rank/select. No prime products, factorizations, totients or primality results are recomputed.

See [the API and proof guide](LCM_WINDOWS_API.md), [the module](lcm_windows.cjs), [the construction manifest](smooth_lcm_windows.json), and [the saved 34-response reader](saved_reader_queries.json). All twenty-five run files and four condition-member files are complete and pinned.

For LCM < 10^9 the reader retains 15,614 windows, including 818 length-three windows and 67 length-fourteen windows; the longest admitted length is 68. These are finite-prefix results, not a resolution of Erdős 873's infinite-sequence question. The guide states the precise source, positive-integer and strict-threshold conventions and the limits of structural loading.
