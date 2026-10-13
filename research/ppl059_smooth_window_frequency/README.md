# PPL059: smooth-window frequency certificate

Exact finite navigation for all smooth length-16 words over {1,2}: 142 accepted windows among 65,536, a 126-node / 142-edge overlap graph, and a complete cycle/potential certificate for graph frequencies 7/15 through 8/15.

[Read the API and proof guide](SMOOTH_WINDOW_FREQUENCY_API.md). The necessary Kolakoski factor condition gives a coarse enclosure, without proving frequency convergence or identifying every graph word with a Kolakoski factor. Chvátal's 1993 published frequency bounds are much tighter; no numerical or methodological priority is claimed.

Files:

- [CommonJS constructor and saved reader](smooth_window_frequency.cjs)
- [Complete graph, chains, potential, cycle and provenance](window16_frequency_certificate.json)
- [All 23 banked reader outputs](saved_reader_queries.json)
- [Classification masks 0–16383](failures_00000_16383.json)
- [Classification masks 16384–32767](failures_16384_32767.json)
- [Classification masks 32768–49151](failures_32768_49151.json)
- [Classification masks 49152–65535](failures_49152_65535.json)

The four shards together classify every window and are assembled as documented. The one constructor result and fresh reader are complete; no Kolakoski sequence, old run-length example, accepted graph or published table was regenerated. The saved reader makes its 150 new graph lookups and 180 emitted query symbols explicit.
