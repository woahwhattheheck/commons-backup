# Smooth-window frequency index

This package classifies every length-16 word over {1,2} under the stated finite derivative, builds its overlap graph, and retains an exact frequency certificate for that graph. The graph has 126 nodes and 142 edges. Its maximum long-run frequency of 1 is 8/15 and its minimum is 7/15. A 15-edge cycle attains the upper endpoint, while an integer potential proves that no cycle exceeds it.

Every Kolakoski factor satisfies the derivative condition, so the graph also gives a coarse necessary enclosure for Kolakoski prefixes. This is not a claim that the limiting frequency exists, equals one half, or has newly improved bounds. The periodic graph extremizer is not identified with Kolakoski.

## Sources and scope

Shallit's official [bc4 presentation](https://cs.uwaterloo.ca/~shallit/Talks/bc4.pdf), printed slide 38, asks whether the letter frequencies in the Oldenburger–Kolakoski word exist and equal one half. The presentation's open framing is dated; this package does not assert an exhaustive current literature or award-status assessment.

Vašek Chvátal's [Notes on the Kolakoski Sequence](https://users.encs.concordia.ca/~chvatal/93-84.pdf), DIMACS Technical Report 93-84, December 1993, already uses finite directed graphs and cycle ratios to bound letter densities. His edge labels may emit multiple digits, so the relevant ratio counts 1s divided by emitted length. This package's edges each emit exactly one digit. Its graph uses fixed smooth windows rather than reconstructing Chvátal's depth graphs. His report proves an upper density below 0.50084 for each symbol, much stronger than this small graph's 8/15 bound. Neither that computation nor its tables were rerun.

The 2021 primary article [Kolakoski sequence: links between recurrence, symmetry and limit density](https://pisrt.org/psr-press/journals/odam/04-vol-4-2021-issue-1/kolakoski-sequence-links-between-recurrence-symmetry-and-limit-density/) explains the finite derivative's incomplete-boundary convention and states in Lemma 10 that Kolakoski factors are infinitely differentiable. Boundary runs of length one are discarded; boundary runs of length two remain. This is a necessary factor condition, with no converse presumed. The article credits Dekking for the convention; that original source was not separately inspected here. An apparent typo in the HTML piecewise display is not copied into the contract.

No Kolakoski prefix was generated. The earlier A025142/A025143 run-length pair, Thue–Morse outputs, and accepted finite examples were not replayed.

## Finite derivative and exhaustive input

The alphabet is exactly the two characters "1" and "2". A run is a maximal nonempty consecutive block of one character. At each derivative level:

1. If any run has length greater than two, reject, retaining the first such run.
2. Remove the first run if its length is one.
3. Remove the last remaining run if its length is one. A sole singleton is removed once.
4. Replace each remaining run by its length, producing another word over {1,2}.
5. Repeat until the empty word, which accepts.

A sole run of length two produces the one-letter word "2", then the empty word. Words "1", "2", "12" and "21" have empty first derivative. The constructor accepts window lengths 4 through 16; only length 16 was executed in this artifact. Smaller branches and contract checks were source-inspected, not separately run.

For a factor of Kolakoski, a boundary singleton might be incomplete, so discarding it is safe. A run of length two is complete because the ambient sequence has no longer run. The retained complete run lengths form a contiguous factor of the run-length sequence, which is Kolakoski again. The derivative length strictly decreases for nonempty admissible words. Iteration therefore shows why Kolakoski factors pass this test. This does not make arbitrary smooth windows actual Kolakoski factors, or make an infinite path infinitely differentiable at every larger window length.

Each word has a fixed-width binary mask: replace 1 by 0 and 2 by 1, read most significant bit first, keeping all leading zero bits. Thus masks 0 through 65,535 enumerate every length-16 word exactly once in lexicographic order. Exactly 142 accept and 65,394 reject. Every accepting word retains its full derivative chain down to empty. Every rejection retains a packed first-failure certificate.

The actual input, source references and exact caps are included in window16_frequency_certificate.json. Its input identity is a6f7155a6ba422b490a36bea016c5b548cb85cc1, 1,236 UTF-8 bytes.

## Graph, sharp frequency certificate and prefix bound

For every accepted length-n window, create an edge from its first n−1 symbols to its last n−1 symbols. Duplicate node words are identified; node masks and edge/window masks are sorted. The edge emits the last symbol and has weight w=1 when that symbol is 1, otherwise w=0. The initial node contributes n−1 symbols before the edge emissions.

For the actual graph, p=8 and q=15. The snapshot records an integer potential H for every node and the residual

    H(v) - H(u) - (q*w(e) - p)

for every edge e:u→v. All 142 residuals are nonnegative, ranging from 0 through 8. Potentials range from 0 through 26. Summing along a walk telescopes. For a closed walk, the potential difference is zero, so its mean weight cannot exceed p/q.

The retained critical cycle has edge IDs

    [29,79,9,42,104,53,121,75,4,34,85,17,60,129,96]

and emits

    121121221121122

It has length 15 and eight 1s. Each edge is tight, the cycle closes, and q times its 1-count equals p times its length. This proves attainment and exact optimality within this finite graph. Interchanging symbols complements every accepted window, swaps weights w and 1−w, and gives a saved node/edge permutation. Therefore the graph's minimum mean is exactly 1−8/15=7/15.

The constructor obtains a candidate ratio from an integer walk-length dynamic program. The published optimality certificate is the explicit cycle and edgewise potential, so the conclusion does not depend on treating an optimizer's answer as a proof. It retains one candidate row per reachable terminal node, including a minimizing walk length, but does not claim to retain the whole intermediate dynamic-programming matrix. All acceptance chains, classification records, graph rows, dual residuals, complement maps and the attaining cycle are complete.

Let a graph word have T≥15 symbols, start node s, end node t, and c(s) 1s in its initial 15-symbol node. Its L=T−15 emissions satisfy

    15 * (number of 1s) - 8*T
      <= 15*c(s) - 8*15 - H(s) + H(t).

The maximum of the right-hand side over node endpoints is bounded by the saved slack B=26. Applying the same inequality to the complemented path gives the lower bound. Therefore every such word has

    max(0, ceil((7*T - 26)/15))
      <= number of 1s
      <= min(T, floor((8*T + 26)/15)).

For T<15 the API intentionally returns only [0,T]. Every Kolakoski prefix of length at least 15 has the required graph path or initial node by the necessary factor condition. The finite endpoint inequality and its asymptotic liminf/limsup enclosure therefore apply, without assuming convergence. The enclosure is coarse relative to published bounds.

A periodic graph extremizer may satisfy all retained length-16 constraints while failing a longer smoothness condition. Its exact graph extremality is not a Kolakoski frequency construction.

## Saved result and work accounting

One source-frozen constructor invocation classified all 65,536 words. It recorded:

| Quantity | Count |
|---|---:|
| Derivative levels inspected | 69,506 |
| Accepted windows / graph edges | 142 |
| Rejected windows | 65,394 |
| Graph nodes | 126 |
| Walk DP cells | 16,002 |
| Walk DP arc relaxations | 17,892 |
| Potential passes | 21 |
| Potential arc relaxations | 2,982 |
| Saved dual residuals | 142 |
| Complement edge bindings | 142 |
| Attaining cycle edges | 15 |

The observed 174 ms is one connected-runtime observation, not a benchmark. No source example, older graph or prior sequence calculation was rerun.

The executed and published source is smooth_window_frequency.cjs, Git blob 5c87401cedd1d7bb888b7dc4fbc83a28ce51ae52, 12,189 bytes. The complete original constructor output was banked in its producing call: 71aba083a8a2c406df2e9ad85aec130bd6356d65, 1,421,027 bytes. The published package retains all of that result except that the 65,536 classification tokens are moved, without recalculation, into four complete compact shards. The package records their exact ranges and blob identities. There is no unavailable result or failed reader continuation for this input.

## Module contract

The plain CommonJS module has no I/O or dependencies:

    const { compileSmoothWindows, openSmoothWindows } =
      require("./smooth_window_frequency.cjs");

### compileSmoothWindows(input)

input.window_length must be a safe integer from 4 through 16. The constructor caps the graph at 2,400 nodes. It returns {snapshot, summary}. It enumerates all 2^n words, so its public cap is deliberately small. The length-n mask, packed certificates and all graph arithmetic fit exact safe integers within these caps. Query lengths use BigInt.

The length-16 constructor has already run for the shipped data. Consumers should open its saved snapshot rather than reconstruct it.

### openSmoothWindows(snapshot)

This consumes a restored complete snapshot. It checks schema, version, array lengths, IDs, integer bounds and sorted allowed masks. It does not independently prove the derivative classification, overlap graph, candidate optimization, potential inequalities or source semantics. Those are the identified producing certificate and its documented derivation. It creates only a lookup map for saved allowed windows.

Returned objects and arrays are copies where exposed, so ordinary result edits do not mutate the saved certificate. The supplied snapshot itself should be treated as immutable by its owner.

| Method | Meaning |
|---|---|
| summary() | Saved dimensions, exact mean bounds and critical cycle |
| classifyWindow(word) | Exact-length saved acceptance chain or decoded first rejection |
| selectWindow(rank) | Zero-based lexicographic accepted-window selection, with saved rank |
| windowsPage(offset,limit) | Accepted masks and their fixed-width words |
| nodesPage(offset,limit) | Node masks, words, 1-counts and complement IDs |
| edgesPage(offset,limit) | Full overlap edges and weights |
| potentialPage(offset,limit) | Node potential values |
| frequencyBounds(length) | Integer prefix-count enclosure from the saved mean/slack |
| periodicWord(length,offset,complement) | Requested symbols of the saved extremizing periodic graph word |
| traceWord(word) | New saved-graph lookup trace, or first rejected window |
| statistics() | Current reader work counters |

Pages take safe-integer offsets and limits 0 through 256. Offset may equal the collection length. selectWindow accepts a rank from 0 through 141 for this input. Words use the literal alphabet {1,2}; classification requires exactly 16 symbols here. traceWord accepts 16 through 4,096 symbols and returns all looked-up edge IDs on success.

frequencyBounds accepts a nonnegative safe integer or a canonical nonnegative decimal string of at most 1,200 digits. periodicWord emits 0 through 4,096 symbols, accepts the same decimal offset form, and reduces it modulo the saved period. The complement argument uses Boolean truth semantics; pass true or false. Frequencies and large counts are exact rational data or decimal integer strings, with no floating approximation required.

The graph coefficient is the count of symbol 1. No path count, partition enumeration, claimed rank of Kolakoski prefixes, or test of eventual periodicity is exposed. A rejected arbitrary finite word is not automatically a statement about a claimed prefix until its identity as that prefix is separately justified.

## Restoring the four classification shards

The complete publication consists of the module, this guide, a certificate package, the saved-reader output file, this directory's README, and four classification shards. Restore the snapshot by literal concatenation:

    const packet = require("./window16_frequency_certificate.json");
    const snapshot = structuredClone(packet.construction.result.snapshot);
    const records = [];
    for (const spec of snapshot.failure_shards) {
      const shard = require("./" + spec.path);
      if (shard.start !== records.length ||
          shard.end_exclusive - shard.start !== shard.records.length) {
        throw new Error("classification shard gap");
      }
      records.push(...shard.records);
    }
    snapshot.failures = records;
    delete snapshot.failure_shards;
    const reader = openSmoothWindows(snapshot);

Bind files to the saved manifest identities when validating external transport. The example only illustrates range assembly and does not recompute classification or verify cryptographic hashes itself.

A zero token means accepted. A positive token is one plus

    mask + 65536 * (length + 32 * (depth + 32 * (start + 32*run))).

Here mask and length describe the first failing derivative word, depth is zero for the original word, start is a zero-based run offset, and run is its length greater than two. Unpacking uses integer division/remainders. The token is a compact retained witness; decoding it does not run the derivative again.

| Shard | Mask interval, inclusive | Git blob |
|---|---|---|
| failures_00000_16383.json | 0–16,383 | 55cdde25c68c9295df7c4a56fb189602d26a10aa |
| failures_16384_32767.json | 16,384–32,767 | b29099e2ced4d1455c7615eb9908588e797daa3f |
| failures_32768_49151.json | 32,768–49,151 | 9ee77f20abaf95d5e8d76b4c0d9020bdfaf79748 |
| failures_49152_65535.json | 49,152–65,535 | 0a43e6e18dad2414ac244784e681386b952b0cf2 |

The complete certificate package has blob 8c8460318ae8aeb7268eaa30829206e0000586fc, 109,211 bytes. The original full bank remains identified for provenance; it is not an additional executed consumer.

## Banked reader evidence

A fresh connected context parsed the complete saved construction, opened the reader, and banked all 23 queries in the same producing call. Each individual result was also retained before the next query. Complete output file saved_reader_queries.json has blob bf3918d9df090f2e4b4eb412f978b8ffffe2a3a0, 49,822 bytes.

The reader exported all 142 accepted windows in two pages, selected ranks 0, 71 and 141, decoded two failures, exposed node/edge/potential pages, evaluated six length bounds, generated two requested periodic blocks, and traced those two new blocks through the saved graph.

Examples include:

- First accepted window: 1121121221121122; last: 2212212112212211.
- At T=1,000, the saved necessary enclosure is 465 through 535 occurrences of 1.
- The exact bound for T=10^1000+183 is retained in full decimal form; there was no generation of its preceding symbols.
- A 90-symbol upper-period block contains 48 occurrences of 1. Its complemented-period block contains 42. Both pass the saved length-16 graph, as expected from the retained cycles, without being asserted to occur in Kolakoski.

Reader counters: 5 saved classification lookups, 150 graph-edge lookups, 180 emitted symbols and 6 bound queries. New derivative computations, graph construction, cycle optimization and dual-residual checks were all zero. The emitted blocks and path lookups are explicit new query arithmetic, not reconstruction of the compiler certificate.

These files provide a complete, small finite-language frequency certificate and navigation interface. They do not improve the known Kolakoski frequency enclosure, establish limiting frequencies, settle Shallit's question, or claim priority for the classical graph method.

## Publication custody

The first Git Trees publication attempt stopped before any mutation, during the research-directory preimage read, after three fetches. It retained an UNKNOWN native error with no HTTP status. The caller did not bank the thrown response body, so that body and the research-tree SHA are unavailable; no transport, rate-limit or access diagnosis is inferred. The failed request is held and was not retried. Source, complete construction and reader output were already banked, and the entire prepared nine-file package was preserved as blob ca25132ecdd5fabc5f176b12f917406d14107985 before choosing another publication method.

The deliberate Contents publisher checks actual path absence at an immutable base, serial writes and sole-parent commit lineage, full file contents, aggregate changed paths, current-base preimages and an expected-head merge. It makes no independent Git-mode or whole-tree verification claim. The second invocation records every native request and response before parsing, and retains any outer exception. This publication-method change does not rerun the mathematics or replace unknown preimages with assumed absence.
