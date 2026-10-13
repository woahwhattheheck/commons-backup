# Erdős #64 — four published order-24 examples

Status: **BOUND FOUR / EXACTLY REPRODUCED / NO COUNTEREXAMPLE / NO PRIZE CLAIM**.

This extension closes the provenance gap called out by the existing 24-vertex certificate spine: all four published 24-vertex cubic examples are now bound to exact source blobs and checked by the same stdlib verifier used by `n24_cert.py`.

## Pinned source

The independent reproduction is the `special-graphs` branch of `rbsandeep/Erdos-Gyarfas` at commit `f7bea75afecb07dab552047ece2d551722f32272`, tree `06c2d84a617ce9852be9bcaa4025235ab81af6c1`, README blob `a3be3d50b5aa5377f9ba20f7c187c039cc7d4a0f`. That README states that the branch reproduced four graphs from the paper containing the Markström Graph and stores the adjacency matrices under `special/`.

The four pinned source blobs and normalized verifier results are:

| source file | Git blob | normalized labeled SHA-256 | C4 | C8 | C16 |
| --- | --- | --- | ---: | ---: | ---: |
| `markstroem.txt` | `e661c40ad9560d74a543f956ce47e07dbb5fd6db` | `ba701ecae49e80975541fa3274c2fa84eb77c3cb4a65614385555e0b984a7575` | 0 | 0 | 228 |
| `24-node-cubic-no-4-8-cycles-p18-free.1.txt` | `851b3aa030e2233839f61095f13d6889829db69f` | `30cd406b48e4ae6480a5f138d41c8fc4d5f809e2b180e28b5cc718ced44f1c7b` | 0 | 0 | 315 |
| `24-node-cubic-no-4-8-cycles-p18-free.2.txt` | `79fff11f0cea351f468fe89131320666b9495732` | `c843c454fe972accf74c312d36b7e8a55b3827b9f4ac90ddc579c5ff0aeb4db5` | 0 | 0 | 330 |
| `24-node-cubic-no-4-8-cycles-p18-free.3.txt` | `2c8c4664964097da3e39efe3efc272834d85ebc6` | `63c307c75d96e0b1b05ecdba4629034122c512959f6315e4ccf719fda13beb11` | 0 | 0 | 207 |

Every fixture has 24 vertices, 36 edges, and degree histogram `{3: 24}`. Each therefore reproduces the published no-C4/no-C8 property, and each has many C16s, so none is a counterexample to Erdős #64. The four exact C16 counts are all different; because cycle counts are isomorphism invariants, this also gives a simple machine-checkable witness that the four fixtures are pairwise non-isomorphic.

## Cross-source binding

The previously pinned SageMath-derived `MARKSTROEM_EDGES` fixture has a different labeling from `special/markstroem.txt`. `published_examples.py` records an explicit 24-vertex permutation and verifies that relabeling the Sage fixture produces the exact normalized upstream edge set. Thus the existing 228-C16 result and the independent reproduction are tied to the same graph rather than merely sharing summary statistics.

## Reproduce

```bash
python research/erdos64_n24_cert/published_examples.py audit
python -m unittest research/erdos64_n24_cert/test_published_examples.py -v
python -O -m unittest research/erdos64_n24_cert/test_published_examples.py -v
```

`published_examples_receipt.json` is compared to exact regeneration by the test suite.

## Evidence ceiling

This is a provenance and exact-verification extension over four already published order-24 graphs. It does **not** search all order-24 graphs, prove or disprove the conjecture, submit anything to a sponsor, or establish a prize/payment/revenue claim. The remaining materially stronger route is an independently checkable full order-24 `{4,8,16}` decision certificate or a genuinely new finite counterexample.
