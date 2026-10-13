# Erdős #64 — 24-vertex certificate/search spine

Status: **BOUNDED COMPUTATIONAL EVIDENCE / NO COUNTEREXAMPLE / NO PRIZE CLAIM**.

This carrier advances the 24-vertex frontier for the Erdős–Gyárfás conjecture without replaying the now-dominated `n <= 23` search. The conjecture asks whether every finite simple graph of minimum degree at least 3 contains a simple cycle whose length is a power of two. Garcia's September 2026 `arXiv:2609.04686v1` reports DRAT-certified exhaustive search through 23 vertices and notes that Markström's four 24-vertex cubic examples avoid 4- and 8-cycles but contain 16-cycles.

Prize metadata has conflicting historical/current public figures, so the exact sponsor award/acceptance terms must be re-read before any payout claim. Nothing here is a sponsor submission or evidence of earned revenue.

## Source pins

- Garcia: `arXiv:2609.04686v1` (2026-09-04).
- SageMath source commit `671dfa344f4cc4a6d54f343cbfd1272ee81698c9`, `smallgraphs.py` blob `f747bce25536d6eb8a59b7d2e06aad83239d112a`. Its published `MarkstroemGraph` construction was independently normalized into the 36-edge `MARKSTROEM_EDGES` instance.
- Existing Commons Garcia construction audit verifier blob `79f749138e8186f8cfd27abb2f741fdf3c6c2098`. This carrier composes with that work and does not change its DRAT-archive evidence boundary.

## What is established

`n24_cert.py` is stdlib-only. It validates simple labeled graph input, produces a deterministic fixed-label SHA-256 encoding, exactly enumerates simple cycles of power-of-two lengths, checks minimum degree, implements Garcia's adjacent-row lexicographic symmetry predicate, and enumerates every simple degree-preserving 2-switch neighbor of a graph.

For the pinned 24-vertex Markström instance, the verifier reproduces a cubic graph with 36 edges, fixed-label SHA-256 `b3e692f3c6265f978ce31add6c1956cd3b4dcfe1f3c4f8c00edbc5a806a87c1f`, **0 C4**, **0 C8**, and **228 C16**. The first canonical 16-cycle is `[0, 1, 2, 3, 4, 5, 6, 7, 8, 17, 16, 20, 23, 21, 18, 9]`.

The local search exhaustively enumerates every distinct *labeled simple cubic graph* one 2-switch away from that pinned labeling: **993** neighbors. **30** still avoid both C4 and C8, but **0** of those avoid C16. The first short-clean neighbor has fixed-label SHA-256 `0da825dcd428654baf0d547958bba280f3f2aeafb0bd73cd6938391422eadc1d` and the deterministic scan receipt hash is `6d8eab5c5e36de293897ae417fa8ea76f8f20c836578b75912ea7ba55f5ddcf4`.

This is exact bounded negative evidence around one known order-24 frontier object. It is **not** an exhaustive search of all 24-vertex graphs or all four Markström examples, so the zero local counterexamples cannot be promoted to a theorem.

## SAT/certificate bridge

`receipt.json` records the source pins, exact verifier result, local-search receipt, and the stronger order-24 obligations:

- `C(24,2)=276` edge variables;
- `3*C(24,4)=31,878` direct C4 blockers;
- minimum-degree-at-least-3 constraints;
- lazy exact C8 blockers for concrete solver models;
- Garcia's adjacent-row lexicographic symmetry condition;
- C16 as the decisive remaining power-of-two cycle length at order 24.

The historical Markström labeling used here does not itself satisfy the adjacent-row lex predicate; that is only a labeling fact, not a graph defect. `labeled_sha256` is canonical for the supplied vertex labels (stable under edge-row order and endpoint direction), **not** an isomorphism-canonical graph hash.

## Reproduce

```bash
python research/erdos64_n24_cert/n24_cert.py verify-markstroem
python research/erdos64_n24_cert/n24_cert.py scan
python research/erdos64_n24_cert/n24_cert.py receipt

python -m unittest discover -s research/erdos64_n24_cert -p 'test_*.py' -v
python -O -m unittest discover -s research/erdos64_n24_cert -p 'test_*.py' -v
```

The committed receipt is tested against exact regeneration. The tests also fail closed on duplicate edges, loops, out-of-range endpoints, and degree violations, and confirm that every generated 2-switch neighbor remains cubic.

## Next exact work

Do not rerun `n <= 23`. The stronger continuation is to bind all four published 24-vertex no-C4/no-C8 examples, explore structurally reduced order-24 candidates, and/or generate an independently checkable SAT/DRAT decision instance for `{4,8,16}`. Any 24-vertex graph that the exact verifier confirms has minimum degree at least 3 and zero 4-, 8-, and 16-cycles would be a full finite counterexample and should be independently checked before sponsor contact.
