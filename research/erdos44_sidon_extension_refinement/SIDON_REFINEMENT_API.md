# Saved Sidon refinement and append-only extension API

This package incrementally refines the complete saved B₂[2] family on [1,19] from [Commons #31744](https://github.com/woahwhattheheck/commons/pull/31744) into a Sidon family. It imports saved pair fibers and a decision diagram as identified premises, constructs only additional two-representation obstructions and changed diagram nodes, and supports exact finite extension queries.

The full refined family has **5,035 subsets**. Its size polynomial is
`1 + 19z + 171z² + 888z³ + 2310z⁴ + 1622z⁵ + 24z⁶`.
The maximum cardinality is six, attained by 24 subsets. These are labelled subsets of the declared integer host, not isomorphism or translation classes.

## Actual append-only input

The seed is `N=4, A={1,2,4}, M=19`. A queried extension is a set `B⊆{5,…,19}`; the reported selected set is `A∪B`. The missing old value 3 stays forbidden. No greedy seed generation is performed.

There are **41 extensions**, including the empty append. Their total-cardinality coefficients at sizes 3, 4, 5 and 6 are respectively **1, 12, 26 and 2**. The two largest extended sets are:
- {1,2,4,9,15,19}
- {1,2,4,9,13,19}

These are in the API's zero-before-one bitvector order, not lexicographic order on ascending element lists. Both append exactly three new values.

Single-value append queries allow 8 through 19. The complete rejected list is:
| New value | Saved collision |
|---|---|
| 5 | 1+5 = 2+4 |
| 6 | 2+6 = 4+4 |
| 7 | 1+7 = 4+4 |

The two occurrences of 4 in a diagonal sum are allowed. Repeating an element within a representation is different from storing it more than once in the set.

## Source and scope

Gang Yu, *An upper bound for B₂[g] sets*, Journal of Number Theory 122 (2007), 211–220, DOI 10.1016/j.jnt.2006.04.008, defines B₂[g] using unordered representations `a≤b`, including diagonals, and identifies B₂[1] as Sidon. The author-primary locator is https://www.math.kent.edu/~yu/research/sidon.pdf . Its direct extraction renders the inequality glyph poorly; the same primary's indexed excerpt supplies the legible relation, consistent with the independently read formal statement. No visual inspection is claimed.

The complete [FormalConjectures Erdős 44 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/44.lean) was obtained through the contents API without an explicit ref; its observed independent Git blob identity is `31daa29ec0c50f3717f382b63c3babff2fa71a6f` (6,057 UTF-8 bytes). That observed file requires `A⊆[1,N]`, `M>N`, and `B⊆[N+1,M]`; it asks for an extension approaching the square-root scale for every positive tolerance. The main statement is annotated research open and retains a local placeholder. Its separately annotated empty-start Singer variant is not the seeded assertion. Reading the source did not audit or execute its embedded proof text or examples.

Yu supplies representation conventions; Formal44 supplies the append-only intervals. Neither source is credited with this saved-data refinement implementation. The finite host result establishes no asymptotic seeded extension, density theorem, unrestricted extremal value, Singer construction, current prize entitlement or mathematical priority.

## Exact input lineage

The accepted input is the complete B₂[2] snapshot from #31744 at immutable merge `9112c0a9d8fd664a61791c750d5992912f4a4b4b`. Its full serialized identity is `f9b551bf2f8d67f29fc5e764866b1e6797cbf3e1` (1,437,975 bytes). The input's pair-sum validity, completeness of its B₂[2] family, old constraints and old coefficient arrays are explicit inherited premises. This package does not reprove those claims.

Base directory: `research/erdos158_b2_two_families/`.

| Base file | Git blob |
|---|---|
| snapshot_manifest.json | d35a641c600104ad6b73cfc955eaca8ff72c6ead |
| nodes_00.json | a4978bf920b089eb5ada24245d97d97034da1bb4 |
| nodes_01.json | 598733b6d72cce46ce3df9c583e454406a196f8d |
| nodes_02.json | cd782fee0722ac9b446b515ed4fc58e0b4eb1ab3 |
| nodes_03.json | e8066688a31519ebf4f45fbf76689c92b903c2f0 |

The four shards contain node IDs 0–2047, 2048–4095, 4096–6143 and 6144–6422. Replacing the manifest snapshot's null `nodes` field with their concatenation reconstructs the identified snapshot. This is byte/data assembly, not computation of a family or coefficients.

The new request was frozen as 1263 bytes, blob `e966b0a820208f7eed6bf6d9603c5f02791631a8`, before production. Its complete content is:
```json
{
  "base": {
    "pr": 31744,
    "merge": "9112c0a9d8fd664a61791c750d5992912f4a4b4b",
    "full_snapshot_blob": "f9b551bf2f8d67f29fc5e764866b1e6797cbf3e1",
    "manifest_path": "research/erdos158_b2_two_families/snapshot_manifest.json",
    "manifest_blob": "d35a641c600104ad6b73cfc955eaca8ff72c6ead",
    "node_shards": [
      {
        "path": "nodes_00.json",
        "blob": "a4978bf920b089eb5ada24245d97d97034da1bb4"
      },
      {
        "path": "nodes_01.json",
        "blob": "598733b6d72cce46ce3df9c583e454406a196f8d"
      },
      {
        "path": "nodes_02.json",
        "blob": "cd782fee0722ac9b446b515ed4fc58e0b4eb1ab3"
      },
      {
        "path": "nodes_03.json",
        "blob": "e8066688a31519ebf4f45fbf76689c92b903c2f0"
      }
    ]
  },
  "seed": {
    "N": 4,
    "seed": [
      1,
      2,
      4
    ],
    "M": 19
  },
  "limits": {
    "max_N": 24,
    "max_new_states": 200000,
    "max_new_coefficient_cells": 1000000
  },
  "provenance": {
    "formal_blob": "31daa29ec0c50f3717f382b63c3babff2fa71a6f",
    "primary": "https://www.math.kent.edu/~yu/research/sidon.pdf",
    "scope": "New finite Sidon refinement from saved B2[2] fibers and DAG; no old pair sums, three-pair obstructions or coefficients rebuilt."
  }
}
```

Only the saved pair records and nodes are consumed by the new construction. It does not execute the old module's constructor, compute any a+b values, regenerate old three-pair obstructions, rerun a field cycle, or reconstruct old base coefficients.

## New obstruction and diagram argument

A subset is Sidon exactly when no saved sum fiber has two active unordered pair representations. For each two distinct pairs in one inherited fiber, the new constructor forms the union of their endpoint masks. A subset activates both representations exactly when it contains that union. This handles diagonals because their endpoint mask has one bit. Pair order is already canonical in the input.

Every Sidon set is a B₂[2] set. Consequently intersecting the complete inherited B₂[2] family with all these new avoidance constraints gives the complete Sidon family on the same host. This proof uses the accepted base family; it does not reverify it.

The base is a zero-suppressed ordered decision diagram. Node 0 rejects, node 1 accepts, and a skipped variable is absent. At a source node, an exclusion drops every residual constraint containing that variable; an inclusion clears its bit and rejects if a constraint becomes empty. If a source edge skips variables, any constraint containing a skipped bit is impossible and is dropped. With no remaining constraints, the entire old subgraph is returned unchanged.

Memoization keys use the old node ID and the normalized residual mask list after skipped-bit removal. Output nodes are shared by the triple (variable, low child, high child). The unique-node table is initialized with all old nodes. An existing node returns its already stored coefficient array. Only genuinely new nodes calculate `P_low + z·P_high`; a zero high child reduces to the low child, and equal children are not collapsed. Thus the old graph IDs and all old coefficients remain literal inputs.

## Bounded constructor contract

Exports are `refine(base,input)` and `openIndex(base,delta)`. Actual production called `refine` once.

Before refinement, the module requires a host size from 3 through 24, increasing labels 1 through N, the expected base schema and g=2, at most 300,000 inherited nodes, ordered child IDs and variables, decimal nonnegative coefficients, and at most N pair records per fiber. It checks pair endpoint masks without recomputing their sums. The explicit request limits are 200,000 new states and 1,000,000 new coefficient cells. Exceeding a cap throws; no partial success is represented. These structural checks do not certify an arbitrary hostile base's mathematical completeness.

Actual new construction work:
| Item | Count |
|---|---:|
| Saved pair records consumed | 190 |
| New two-pair witnesses / distinct supports | 525 / 525 |
| Saved nodes / coefficient entries | 6,423 / 28,316 |
| New refinement states / memo hits | 2,966 / 1,158 |
| Unchanged-subgraph returns | 10 |
| Old-node reuses / new unique-node hits | 449 / 23 |
| Zero-high reductions | 1,799 |
| Appended nodes / new coefficient cells | 695 / 2,581 |
| New pair sums | 0 |
| Rebuilt old triple obstructions | 0 |
| Rebuilt base coefficients | 0 |

The saved coefficient-entry count includes the accepting terminal's one, explaining its one-entry difference from the old constructor's nonterminal work counter. The actual skipped-constraint-drop count is zero; the general source handles this case, but this run does not supply a nonzero example.

## Saved delta and opening

`host19_sidon_delta.json` contains the complete 525 witness records and constraint masks, all 695 new nodes, the new root and its coefficients, seed, input references, bounds and actual work. It stores no duplicate base node table. The full composed table has 7,118 nodes; base IDs 0 through 6422 are unchanged and new IDs start at 6423.

Example use after acquiring the exact base files from the immutable commit:
```js
const fs = require("node:fs");
const { openIndex } = require("./sidon_refinement.cjs");
const baseDir = "../erdos158_b2_two_families";
const read = p => JSON.parse(fs.readFileSync(p, "utf8"));
const manifest = read(baseDir + "/snapshot_manifest.json");
const nodes = ["nodes_00.json","nodes_01.json","nodes_02.json","nodes_03.json"]
  .flatMap(name => read(baseDir + "/" + name).nodes);
const base = { ...manifest.snapshot, nodes };
const delta = read("./host19_sidon_delta.json");
const reader = openIndex(base, delta);
const extension = { N: 4, seed: [1,2,4], M: 19 };
reader.query({ op: "family", extension });
reader.query({ op: "page", extension, size: 6, offset: "0", limit: 256 });
```

Opening validates structure and copies/parses stored arrays. It performs no refinement recursion or polynomial recurrence. Callers must bind the exact input identities themselves; shape checks are not cryptographic or mathematical premise verification.

## Reader interface

All ranks and counts use nonnegative decimal strings and BigInt arithmetic. Labels and node IDs are bounded safe integers. A set is represented by a sorted distinct label list; duplicates are rejected.

| Operation | Inputs and result |
|---|---|
| summary | Construction totals and work. |
| family | Optional condition or extension, optional total `size`; returns all cardinality coefficients, selected mass and maximum. |
| select | Same restrictions plus decimal `rank`; returns one complete selected set. |
| rank | Same restrictions plus `values`; returns member status and rank, or null for a nonmember. |
| page | Same restrictions plus `offset`, `limit≤256`; returns bounded consecutive ranks and next cursor. |
| extensions | Explicit `extension`; classifies the seed and every single-value append in (N,M], with collision explanations. |
| classify | `values`; scans saved pair membership and returns all active fibers and first two-pair violation. |
| fiber | A saved integer sum in [2,2·host]. |
| obstruction | A saved new witness ID. |
| node | A composed old or new node ID. |
| conditions | Complete coefficient summaries for cached conditions. |

An `extension` is `{N,seed,M}` with 1≤N<M≤host and seed⊆[1,N]. It translates into required seed values and forbidden old holes plus all values above M. The API does not silently add holes. An empty seed is permitted; a non-Sidon seed simply has an empty completion family.

Alternatively `condition:{required,forbidden}` directly conditions the fixed host. A query cannot provide both an extension and a direct condition. There are at most 32 cached conditions and at most 1,000,000 fresh conditional coefficient cells per reader. Conditional coefficients count total selected cardinality, including seed vertices.

Ordering reads the indicator bits of labels 1,2,…,19 with exclusion before inclusion. It is not increasing integer-mask order and is not lexicographic ordering of element lists. Rank and selection use saved branch masses with the appropriate skipped-variable semantics.

## Actual fresh reader

All **36 query responses** were banked individually and are present in `saved_reader_queries.json`. They include:
- all 24 global maximum sets and both maximum seed extensions;
- eight select/rank inverse matches across unrestricted, seeded and seeded-size-six families;
- all fifteen single-value seed append decisions;
- a known two-representation rejection and a full saved-fiber description of a selected seed maximum;
- eight complete condition coefficient vectors.

Additional seed-window results, still with old hole 3 forbidden:
| M | All completions | Maximum total size | Number of maxima |
|---:|---:|---:|---:|
| 5 | 1 | 3 | 1 |
| 8 | 2 | 4 | 1 |
| 12 | 6 | 4 | 5 |
| 16 | 19 | 5 | 9 |
| 19 | 41 | 6 | 2 |

The empty seed in [1,4], permitting only [5,19], has 1,359 completions and maximum size five attained 156 times. The non-Sidon seed {1,2,3} has none.

Fresh reader work is explicit: 8 conditions, 88 conditional nodes, 184 conditional coefficient cells, 20 cache hits, 348 saved-polynomial shortcuts, one skipped-required rejection, 384 selection steps, 88 rank steps, 3,420 saved pair-membership checks, one saved fiber read and 15 extension candidates. New original-constructor states, pair sums, constraints, base coefficients, refinement states and two-pair obstructions are all zero.

These queries do not enumerate the represented 5,035 subsets; they export the requested maxima and selected records. The retained inverse matches and complete source/data form finite evidence, not a new general theorem or a replayed test suite. There was no constructor cap failure, failed query or missing response in this delivery.

## Files and provenance boundary

`sidon_refinement.cjs`: complete constructor and reader; production source blob `3f86202f4795402eb702f605a30702332f8df499`.
`host19_sidon_delta.json`: complete new delta, blob `04c37939e513719e2e8863fc1624847887e9780a`.
`saved_reader_queries.json`: all actual new query responses, blob `835346f2102dbe940b732e1877a1df9ea304bbd5`.

The accepted base remains a required external immutable input. Publishing the delta does not claim to revalidate or duplicate that source package. All new input, source, construction output and reader responses were banked before the guarded publication.
