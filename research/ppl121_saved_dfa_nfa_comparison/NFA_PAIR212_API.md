# Saved DFA/NFA comparison for one word pair

This package constructs and navigates all labelled three-state, epsilon-free binary NFAs with initial state 0 that accept w = 0^212 1^2 and reject x = 0^2 1^212. Both words have length 214. It consumes authenticated saved relation matrices from Commons #31503 and the completed DFA minimum 4 for this pair from #31368. It does not execute either older constructor, proof or query suite.

The new catalogue contains 7,810 separating transition tables and **25,294 separating full machines**, where a full machine also chooses its final-state subset. All 16 embedded two-state relations have identical full matrices at exponents 2 and 212. Together with a new three-state witness this gives NFA minimum 3 for this pair, and the inherited DFA convention gives the finite ratio 4/3. This is a result for one declared pair, not a worst-case separation-ratio bound, priority claim or prize submission.

## Source and custody

The current [PPL121 card](https://prizeproblems.org/problems/121/) identifies Shallit's problem. His [official slides](https://cs.uwaterloo.ca/~shallit/Talks/bc4.pdf), printed slide 24, ask for bounds on sep(w,x)/nsep(w,x), next to the equal-length NFA question. The short passage does not explicitly settle epsilon transitions, single versus multiple initial states, or directional separation. Our catalogue conventions below are explicit. The current sponsor talks page reports partial 2026 progress by John Nicol; that paper and proof were not opened or reviewed. No reward availability or claim eligibility is inferred.

The complete immutable inputs were independently hash-matched:
- [#31368](https://github.com/woahwhattheheck/commons/pull/31368), merge 668abf68f02c4aadc03c9fb93a1a85cf33a7067a: RLE_DFA_SEPARATOR_API.md, blob a2c7e636e97f51f3db3b3d62c7a15db6e48925d3, 21,196 bytes. Its pair and completed DFA minimum 4 are inherited premises.
- [#31503](https://github.com/woahwhattheheck/commons/pull/31503), merge 7438e3f84903c148728eb90e0bcc2449c7b28ca6: n4_pair_identity.json, blob 79f4d21be382497df830a2b93334f6b64ff6aecc, 2,530,359 bytes; UNARY_IDENTITY_API.md, blob f66a2efd7ec12ddde374051f44581801e13d66b8, 16,558 bytes. The exact copied rows come from /lower_bound/snapshot/records.

The unary atlas stores seven binary powers at exponents 1, 2, 4, 8, 16, 32, 64 and accumulators for 5 and 65. It does **not** store every exponent through 64; in particular R20 is absent. The old literal-main empty-body acquisition remains held. We acquired the immutable input for a different consumer, without retrying that route.

## Machine model and encoding

States are 0, 1, 2. A relation is represented by three row bitmasks: bit j in row i means an i-to-j edge. Its code is row0 + 8 row1 + 64 row2, from 0 to 511. Symbol 0 uses relation A, symbol 1 uses relation B. Both may be empty or partial. There are no epsilon transitions in the counted catalogue.

Every final mask F from 0 to 7 is admitted as a candidate. Acceptance means at least one reachable state belongs to F. Unreachable states, unused labels, and isomorphic but differently labelled machines remain distinct. No accessibility, completeness, minimality of a particular transition table, or graph-isomorphism quotient is imposed.

Table code is A + 512 B, so order is B-major and A-minor. Full-machine order is ascending table code, then ascending numeric final mask. This differs from ordering by edge count or by textual matrix entries.

The complete candidate universe has 262,144 transition tables and 2,097,152 final-mask assignments. Each saved endpoint byte is wMask + 8*xMask, encoded as two lowercase hexadecimal characters. Concatenation in table-code order has 524,288 characters. No symbols of the 214-letter words are expanded.

## New construction

Only base rows and R2, R4, R16, R64 are copied into input.json. Composition AB means following A, then B. Four new Boolean products per relation are computed:
1. R128 = R64 R64.
2. R20 = R4 R16.
3. R84 = R20 R64.
4. R212 = R84 R128.

For a symbol pair, the first reachable mask is row0(A212) followed through B2; the second is row0(A2) followed through B212. A final mask separates exactly when F intersects the first mask and is disjoint from the second. If the endpoint masks are W and X, the number of such final masks is 2^(3-|X|) - 2^(3-|X union W|).

The constructor performs 2,048 new Boolean products, 11,418 product row unions, 262,144 endpoint evaluations, 954,368 endpoint row unions, and 2,097,152 final-mask inspections. It records zero old-power products, zero old DFA evaluations, and zero expanded symbols.

Counts by final mask 0 through 7 are [0, 3060, 3215, 3732, 3215, 3732, 3716, 4624]. In particular, final mask 7 can separate when the second reachable subset is empty; it must not be discarded as automatically accepting every nonempty word in a partial NFA.

The edge-count histogram for 0 through 18 symbol-labelled edges is [0,0,0,8,120,808,2984,6218,7294,5048,2154,568,86,6,0,0,0,0,0]. Edges belonging to different symbols are counted separately. The saved exact-three-edge page contains all eight machines in that restricted slice.

## Finite minimum argument

The lower certificate includes every relation on two states, embedded with row 2 empty and no bit 2 in rows 0 or 1. For each of these 16 relations it retains base rows, copied R2, new R212, and all three difference rows. Every difference row is zero. This compares whole relations, not just the initial row.

Thus for arbitrary two-state symbol relations A and B, A212 B2 = A2 B2 = A2 B212. The two words reach the same set from every initial subset and cannot be separated by any choice of final states. One-state machines embed into this family; a zero-state machine cannot accept the first word.

This lower argument also permits epsilon transitions. If E* is epsilon closure, use effective symbol relations E* A E* and E* B E* and an epsilon-closed initial subset. The full-matrix identity holds for every such effective two-state relation. The words are nonempty, so this standard absorption preserves their acceptance. No enumeration of epsilon matrices is claimed.

The first catalogue witness has A code 114, rows [2,6,1], B code 1, rows [1,0,0], final mask 1. Its saved endpoints are 1 and 0. A retained run-boundary trace agrees with the saved bytes. This proves the forward NFA minimum is 3; since no two-state machine separates in either direction, the minimum when either direction is permitted is also 3. No separate reverse-direction three-state witness or minimum is asserted here.

The DFA minimum 4 is the authenticated prior result under that catalogue's convention. This package does not reproduce its accepted enumeration or proof.

## Files and assembly

Load nfa_catalogue_manifest.json, concatenate its ordered part files without adding separators, check the byte count and Git blob identity, then JSON.parse. The complete catalogue is 667,497 UTF-8 bytes with computed identity 462b3a488a05897542ed744c7610630765c203e4. Only its two parts and assembly descriptor were natively acknowledged; the whole identity is not a whole-blob acknowledgement.

The first-reader record is assembled identically from saved_reader_manifest.json and four ordered parts. It is 1,442,238 bytes with computed identity 9d065ef183b60bb48ed1d26fa01c64425c650124. Concatenation checks are byte identity checks, not mathematical re-execution.

The certificate retains every new power matrix, every table endpoint, complete histograms, all two-state comparison matrices, and work counters. The reader record retains every request/response, all inverse and trace results, and complete final condition caches. public_checkpoints.json links native manifests for source/input/plan, complete constructor, reader plan, and complete reader output. Native blobs do not imply indefinite retention or publication until a commit includes the files.

## API

Require nfa_pair212.cjs and call open(certificate,input). Opening uses saved material. It does not call compile, authenticate all provenance, or reconstruct old powers. Callers should validate the declared file identities before opening.

- summary(): complete candidate and separating counts, inherited DFA minimum, NFA minimum and finite ratio.
- lowerBound(): all 16 full-matrix comparison records and their equality flag.
- relationPower(code): the four newly constructed matrices for one relation. This is not the old atlas query API.
- condition(raw): normalize a condition and retain its block counts and prefix counts.
- select(raw,rank): select a full machine with zero-based rank.
- rank(raw,tableCode,finalMask): inverse rank, or null for a nonmember.
- trace(tableCode,finalMask): base rows, saved endpoint masks, first/second run-boundary masks, and exact agreement with the saved endpoints.
- page(raw,start,limit): at most 128 machines. Default limit 32; start equal to count gives an empty page; limit 0 is permitted.
- snapshot(): all condition caches and work counters.
- work(): current counters.

A raw condition can contain zero_code or one_code in 0..511; final_mask in 0..7; require_final and forbid_final bitmasks in 0..7; min_edges and max_edges integer inclusive bounds. Omitted code/final restrictions are unrestricted. Pass the original raw object back to queries, not the normalized object containing null sentinels.

All restrictions intersect. Required and forbidden final bits that overlap give an empty family. Reversed or wholly negative edge bounds also give an empty family. Empty symbol relations yield no separating machines for these two nonempty-block words. Invalid code, mask, rank, start, page limit, or noninteger bound throws. A nonmember rank returns null instead of throwing. A rank on an empty family is out of range.

At most 64 distinct conditions are cached per open reader. Each fresh condition scans the 262,144 saved endpoint bytes and counts candidates into 1,024 blocks of 256 table codes. A select binary-searches block prefix counts and scans at most one block. Rank sums within one block. Conditions do not recompute endpoints or matrix powers; traces use the copied/new saved matrices for a selected machine.

## First actual reader

The frozen reader_consumer.cjs ran once, after its native plan checkpoint. It produced 127 saved responses, 45 rank/select inverses (all matched), three exact successful traces, and 23 complete condition caches. It queried every final mask; edge slices; empty symbol relations; contradictory final restrictions; reversed and negative bounds; and fixed symbol codes derived from the first witness. It retained the first and last 32 machines and all eight exact-three-edge machines, plus empty end and zero-limit pages and a nonmember rank.

Work: 6,029,312 endpoint rows scanned for conditions; 26,741,264 final-mask checks; 17,488 selection rows; 6,219 inverse-rank rows; 14 trace row unions; 168 cache hits. Reader new-power products, old DFA evaluations, and expanded symbols are all zero. These are actual operation counts, not performance benchmarks or independent proof audits.

No general separation bound, asymptotic improvement, new automata theorem, current prize resolution, or external proof verification is claimed.
