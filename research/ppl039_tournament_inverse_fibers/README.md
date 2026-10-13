# PPL039 / Erdős564: tournament inverse fibers

A complete finite inverse index for the credited Erdős–Hajnal tournament construction: an unordered triple is red when cyclic and blue when transitive.

The delivered six-label constructor enumerates all **32,768 orientations** once and finds **8,563 distinct cyclic-triple signatures**. Every forward word and inverse orientation witness is retained. A fresh saved reader then makes 15 recorded queries, including exact fiber count/rank/select, reversal, transitive-subset orders, and a saved partial-coloring view.

## Files

| File | Purpose |
|---|---|
| [tournament_fibers.cjs](tournament_fibers.cjs) | Dependency-free CommonJS compiler and saved reader, with exact bounded integer masks and explicit resource guards. |
| [TOURNAMENT_FIBERS_API.md](TOURNAMENT_FIBERS_API.md) | Encodings, proofs, complete API, work counts, limits, trust boundary, and actual consumer results. |
| [six_vertex_fibers.json](six_vertex_fibers.json) | Complete index, all 15 query arguments/results/work records, source custody and timing observations. |

The source used unchanged throughout the actual computation is Git blob `0a07891cdc03dc0dbce7058658385b2cad446c42`, 38,780 bytes. The complete data file is 676,846 bytes. Packed integer arrays retain every entry in its original order.

## Actual finite results

| Quantity | Result |
|---|---:|
| Labeled vertices | 6 |
| Directed-pair bit positions | 15 |
| Triple bit positions | 20 |
| Orientations | 32,768 |
| Distinct signatures | 8,563 |
| Largest inverse fiber | 720 orientations, signature zero |
| Maximum cyclic triples | 8 |
| First orientation attaining that maximum | Code 280, signature 53,732 |
| Saved reader queries | 15 |
| Reader orientation/triple reclassification | 0 |

The fiber-size distribution is:

| Fiber size | Number of signatures |
|---:|---:|
| 2 | 5,160 |
| 4 | 2,772 |
| 8 | 280 |
| 16 | 105 |
| 24 | 210 |
| 48 | 35 |
| 720 | 1 |

The all-transitive fiber's rank 359 is code 16,383 with order `[0,1,2,3,5,4]`. Reversal gives code 16,384 at rank 360. Reversal preserves a signature and reverses rank within its fiber; labels and reversed orientations are counted distinctly.

The partial triple pattern cyclic `012,123` and transitive `013,023` has **2,048 orientations across 623 signatures**. Its grouped rank 777 selects code 31,521 with signature 66,569. The complete view and its 624 cumulative endpoints are saved for later rank/select/page operations.

Signature 19, whose only red triples are `012,013,023`, has no representing tournament. It is red-`K4^(3)`-free but already violates the tournament restriction of at most two cyclic triples on four vertices. The guide proves this distinction.

## Consume the saved index

~~~js
const { openTournamentFibers } = require("./tournament_fibers.cjs");
const evidence = require("./six_vertex_fibers.json");

const reader = openTournamentFibers(evidence.saved, {
  source_id: "my-distinct-consumer"
});
const fiber = reader.findFiber({ signature: 0 });
const selected = reader.selectPatternOrientation({
  view: { session_id: 0, query_id: 10 },
  rank: 777
});
~~~

The compiler supports three through six vertices for new bounded inputs. The delivered six-label space is complete; ordinary consumption uses its saved record. Pattern order is increasing signature, then increasing orientation code within a signature, and differs from globally increasing orientation code.

Saved opening checks bounded encodings, array coverage and forward/inverse references. It does not rerun cyclic classification or independently authenticate the mathematical semantics of edited records. Ordinary queries copy arguments, results and their new receipts; explicit opening/export handles the full index. The guide states the complete costs and trust boundary.

## Source and scope

[Conlon–Fox–Sudakov, *Hypergraph Ramsey numbers*, arXiv:0808.3760v1](https://arxiv.org/pdf/0808.3760), printed page 3, supplies the construction and credits Erdős–Hajnal. The guide separates that source from the formal Erdős564 target and its unpinned observed annotation.

This contribution is an exact finite data structure and consumer for a restricted construction family. It does not improve the asymptotic Ramsey bound, identify isomorphism classes, assume all red-`K4^(3)`-free colorings are representable, or establish prize eligibility. No author or sponsor contact occurred.

Operation: `ERDOS564-TOURNAMENT-INVERSE-FIBERS-20261004-7CA6`.
