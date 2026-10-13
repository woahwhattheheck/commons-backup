# Exact erasure navigation for a finite Type II circulant family

This package provides complete coordinate-erasure, shortening and puncturing data for a declared family of binary linear codes of length 16. It is a finite method-development consumer associated with PPL158. The sponsor's separate question asks for a Type II [72,36,16] code; this package does not search length 72, prove existence/nonexistence there, classify all Type II codes of length 16, or establish prize progress.

## Declared family and actual result

For each seed s from 0 through 255, define an 8 by 8 binary circulant matrix by A[i,j]=bit(s,(j-i) mod 8), for 0<=i,j<8. The generator is G=[I_8 | A]. Coordinates 0..7 are the identity half and 8..15 the circulant half. A message m in 0..255 selects generator rows by its bits, and their XOR is its codeword.

All 256 seeds were examined once. Exactly 32 are self-dual, and 16 are Type II:
```
21, 42, 69, 81, 84, 127, 138, 162, 168, 191, 223, 239, 247, 251, 253, 254
```

The systematic identity half makes different seeds different labelled codes. No equivalence under coordinate permutation is imposed. These counts concern only this circulant ansatz.

Every retained code has dimension 8 and minimum nonzero weight 4, with weight counts at weights 0,4,8,12,16 equal to 1,28,198,28,1. The complete family file retains all 256 candidate classifications, every failed Gram cell, all 16 generator matrices, their columns and all 4,096 message-labelled codewords. Equal weight enumerators are not treated as equality of codes or of their coordinate profiles.

There are 16 times 65,536 = 1,048,576 labelled (seed,erasure-mask) pairs. The saved reader found 360,848 patterns with zero ambiguity dimension and 687,728 with positive ambiguity dimension. It exported all 448 minimal ambiguous patterns of size four. The number counts labelled seed/mask pairs; a coordinate mask used in two codes contributes twice.

## Primary definitions and sponsor boundary

The sponsor page https://sites.google.com/site/professorstevendougherty/length72 was directly read and binds the Type II [72,36,16] question. It records historical existence/nonexistence offers subject to publication and sponsor adjudication. No present eligibility, payment or acceptance claim follows from that reading.

Definition support is E. M. Rains and N. J. A. Sloane, Self-Dual Codes, Handbook of Coding Theory (1998), pp. 177–294, author preprint https://arxiv.org/pdf/math/0208001 (2002). The inspected definition passages give binary linear codes, the standard binary inner product, orthogonal dual, self-duality, [n,k,d] notation and Type II as binary self-duality with all codeword weights divisible by four. Only those definitions were used. No published code example, table, Gleason formula, 72-code proof or existing computation was imported. See SOURCE_QUALIFICATION.md for retrieval scope.

Green40 covering-code work, RS097 list decoding and earlier MUB/SIC/Singer results were kept separate. This construction is new work on the explicitly declared circulant input. No source-specific access failure arose in this lane.

## Why the family filter is complete

The eight rows of G are independent because their first eight coordinates form an identity matrix. Thus every seed defines an 8-dimensional binary code.

The standard dot product is computed in F_2. All row inner products, including each row with itself, vanish exactly when their span is self-orthogonal. An 8-dimensional self-orthogonal subspace of F_2^16 equals its orthogonal dual, since both have dimension 8. This gives the self-duality test.

For binary vectors,
```
weight(x XOR y) = weight(x) + weight(y) - 2 * |support(x) intersect support(y)|.
```
When x and y are orthogonal, the intersection size is even. Therefore sums of mutually orthogonal generators whose weights are divisible by four retain weight divisible by four. Conversely each generator belongs to the code, so a Type II code must pass those generator-weight tests. The filter is necessary and sufficient for the declared systematic family.

All 256 message vectors are enumerated once for each admitted seed by removing the least nonzero message bit and XORing the corresponding generator row. This produces every codeword once, because the identity half preserves the message. For a linear code, minimum distance equals minimum nonzero codeword weight since a difference of codewords is again a codeword. These are direct finite arguments used by this implementation, not a review of the length-72 literature.

## Coordinate spans and dimension meanings

For a coordinate subset S, r(S) is the rank over F_2 of the generator columns indexed by S. The compiler builds every coordinate-mask span from the span of the mask with its least set bit removed and the one added column. Binary elimination keeps one reduced basis row at each pivot, and equal canonical bases share a span record. Each saved mask addresses a span and its rank.

Each code has its own span table and transition cache. The complete profiles retain 66,880 spans in total, including one empty span for each code, and 1,048,576 mask-to-span addresses. Some seeds have 2,704 spans and others 5,656; all retain the same full coordinate-mask domain.

For erased coordinates E, with complement taken only inside {0,...,15}, the meanings are:

| Quantity | Formula | Meaning |
|---|---|---|
| Punctured dimension | r(E complement) | Dimension after deleting E |
| Shortened-zero-on-E dimension | 8-r(E) | Impose zero on E, then delete E |
| Ambiguity dimension | 8-r(E complement) | Dimension of codewords supported entirely inside E |
| Unique erasure recovery | r(E complement)=8 | Every consistent known-coordinate pattern determines one codeword |

The shortening and ambiguity dimensions are different kernels. The complete profile histogram is indexed by erasure size and ambiguity dimension.

For a received word, the compatible codewords solve the coordinate-labelled equations on the known positions. If nonempty, the solutions form an affine translate of the ambiguity kernel, so their number is 2 raised to the ambiguity dimension. A received pattern can be inconsistent even when the ambiguity dimension is zero. In that case the API returns INCONSISTENT and no codeword, not successful recovery.

The span ranks alone describe homogeneous dimensions. To retain the labelled nonzero constraints, the reader filters the saved codewords using their original known-coordinate positions. It does not reconstruct a generator, codeword or span.

## Files and loading

complete_circulant_family.json is one complete acknowledged JSON blob, adc9ee7298ffbc2ebe08ed83d7923881f55639d8, 220,466 UTF-8 bytes.

profile_index.json lists all sixteen complete profile identities and loading instructions. Eight profiles fit as direct JSON files and their whole blob identities were natively acknowledged. The eight larger profiles are split into two literal text parts plus an assembly descriptor. Concatenate listed parts in order with no separators and parse JSON. Their whole identities are computed assembly comparisons; only their parts/descriptors were separately acknowledged. All sixteen assemblies matched their original complete bytes without rerunning rank calculations.

saved_reader_manifest.json similarly joins two literal text parts into the full 703,940-byte reader result with computed Git blob 325272e6dd99da0a7a07c1771a9c83a393cd7bd5. The whole reader blob was not separately acknowledged; its two parts and descriptor were.

```js
const { createReader } = require("./circulant_erasures.cjs");
const reader = createReader(family, completeProfiles);
const q = { min_size: 8, max_size: 8, max_loss: 0 };
reader.condition(q);
reader.select(q, "0");
reader.rank(q, selected.seed, selected.erased_mask);
reader.compatible(seed, erasedMask, receivedWord);
```

These show the contract, not an additional executed example. The actual requests and returned values are the saved reader records.

The exported constructors compileFamily(input) and compileProfile(family,seed) produced the public evidence once. Loading an existing family and profiles uses createReader and must not call those constructors again.

## Reader contract and ordering

Coordinates are integer labels 0..15; erasure and received masks are integers 0..65535. Seed identities are the original integers, not orbit representatives. The global order is ascending seed and then ascending numeric erasure mask. It is not coordinate-list lexicographic order, codeword order or a quotient by symmetry.

condition accepts optional seeds, require_erased, forbid_erased, inclusive min_size/max_size and inclusive min_loss/max_loss. Defaults admit the full family. An explicit empty seed list selects nothing. Unknown/repeated seeds, invalid/repeated coordinates and noninteger bounds throw. Bounds are clipped against the finite host. Conflicting masks, reversed bounds and wholly out-of-range size/loss requests yield zero.

Each complete condition scans the selected saved profiles once and retains counts in 256-mask blocks for every selected seed, plus a size/ambiguity histogram. It stores no newly constructed spans. Later rank/select/page calls reuse those block counts, scanning at most the relevant block after skipping complete blocks/seeds. The count represents labelled (seed,E) pairs.

select uses a canonical nonnegative decimal rank string, length at most 64, and returns OUT_OF_RANGE for rank>=count. rank takes a seed and integer erased mask; a tuple outside the condition returns NOT_IN_CONDITION. Pages accept decimal offsets and a limit from 1 through 128. Offset=count is a successful empty page; larger offsets are OUT_OF_RANGE.

pattern returns dimensions and the code-level erasure property for a single retained seed and mask. Its compatible_words_when_consistent field is explicitly conditional on consistency.

compatible(seed,erased,received) examines all 256 saved message-codewords and returns the complete matching fiber in ascending message order. Erased received bits are ignored. The status is INCONSISTENT, UNIQUE or AMBIGUOUS, with count and all codeword/message/weight rows. It also returns the pattern metadata; code-level unique_erasure_recovery can be true when the received fiber is empty.

marginals counts how many selected labelled (seed,E) pairs erase each coordinate. snapshot retains every complete condition and the accumulated reader work. Counts fit exactly in safe JavaScript integers for this fixed domain; public rank/count strings avoid conflating numbers with masks.

This implementation trusts its own saved family/profile custody. It checks declared shape and labels, but is not an adversarial mathematical-certificate verifier. It has no filesystem, network, clock, randomness or external dependency. Treat inputs and returned data as immutable.

## Actual new reader use

The first reader driver and plan were natively checkpointed before use. One run retained 151 responses, 39 selections with matching inverse ranks, 18 complete conditions, four coordinate-marginal vectors and all 448 size-four ambiguous patterns. It also returned sixteen complete generator-support fibers and the empty/full/systematic-half boundary fibers.

| Condition | Count |
|---|---:|
| all | 1048576 |
| unique | 360848 |
| ambiguous | 687728 |
| loss-one | 325056 |
| loss-four | 35088 |
| minimal-ambiguity | 448 |
| eight-erased-unique | 54784 |
| eight-erased-loss-one | 117504 |
| eight-erased-loss-at-least-two | 33632 |
| twelve-erased | 29120 |
| paired-constraints-unique | 20369 |
| paired-constraints-ambiguous | 19583 |
| conflicting | 0 |
| past-host | 0 |
| negative-size | 0 |
| reversed-loss | 0 |
| no-seeds | 0 |
| first-code | 65536 |

Every generator-support fiber in the actual declared requests has two compatible codewords. With no erasures, the selected saved codeword gives a singleton, while the received unit vector gives an empty fiber even though the kernel dimension is zero. With all coordinates erased, all 256 codewords are compatible. Erasing either systematic half in the retained first-code requests still yields one compatible word. These are saved actual reader outputs, not a new candidate-family construction.

There are no ambiguous patterns of size below four because every nonzero codeword has weight at least four. A four-coordinate ambiguous set must support a nonzero codeword and is therefore minimal under deletion of coordinates. The complete four-coordinate export is consequently the whole minimal-size ambiguous family for these codes, not a claim that every inclusion-minimal ambiguous pattern has size four.

Every request was retained before invocation, every response after return, and the latest complete caches/work after each response. No reader error, retry or reconstruction occurred.

## Work and custody

Family construction:
```json
{
  "maskSizeCells": 65536,
  "circulantCandidates": 256,
  "generatorRows": 2048,
  "gramCells": 9216,
  "codewords": 4096,
  "codewordXors": 4080,
  "columnBits": 2048,
  "externalCodeExamples": 0
}
```

All sixteen coordinate profiles:
```json
{
  "coordinateMasks": 1048576,
  "transitionRequests": 1048560,
  "transitionHits": 869616,
  "newTransitions": 178944,
  "newSpans": 66864,
  "basisXors": 310367,
  "pivotInsertions": 160848,
  "histogramCells": 1048576,
  "codewordReconstructions": 0,
  "gramReconstructions": 0
}
```

Saved-data reader:
```json
{
  "conditionsBuilt": 18,
  "conditionHits": 541,
  "profileRowsScanned": 12648448,
  "spanRankReads": 11041654,
  "selectBlockRows": 33883,
  "rankBlockRows": 4836,
  "marginalRows": 4194304,
  "marginalBitChecks": 22871280,
  "compatibleWordReads": 5376,
  "newProfiles": 0,
  "newCodewords": 0,
  "newGramCells": 0
}
```

A span is shared only inside its own code profile. Transition requests/hits count the actual new construction; they are not provider-call counts. The reader's millions of rank reads and row scans are fresh saved-data queries, not recomputation of those spans.

The full source/input/plan was acknowledged before construction. The family was banked before profiles, and every profile before moving to the next code. Reader driver/plan and complete reader results form the next links in public_checkpoints.json. No private raw provider or Slack envelopes are included in those public manifests.

A complete frozen publication spec is additionally checkpointed before publication. Its recovery locator belongs to the release receipt, avoiding a recursive self-inclusion. Native blob acknowledgement establishes a returned content identity, not branch inclusion, mathematical correctness or indefinite retention. Guarded publication separately verifies paths, pins, PR/head/merge and all immutable file bodies. The release records any current-main observation precisely.

No old accepted computation, published example, test fixture or proof was rerun. This is a complete finite circulant erasure capability, with no extension to the unresolved length-72 problem.
