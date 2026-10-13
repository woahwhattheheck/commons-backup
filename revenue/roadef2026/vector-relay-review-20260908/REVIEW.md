# ROADEF finite-rank traversal — raw-artifact review

## Result

**The retained `d85ee618` traversal candidate beats the retained `e8014d78` baseline on both tested cases under the declared full-vector ordering.** Both candidates preserve the same maximum saturation on each case. The gains occur later in the sorted objective vector, not at its maximum and not in a contest leaderboard position.

This reviewer consumes the already-completed experiment without running a solver or the official checker, rebuilding a candidate, or changing a competition package. Root and the local evaluator retain solver selection and submission ownership. This directory publishes the runnable evidence reader, its tests, and the findings; publication is separate from competition promotion.

| Case | Vector length | First differing rank | Baseline, six-decimal output | Traversal, six-decimal output | Result |
|---|---:|---:|---:|---:|---|
| A04 | 500 | 72 | 0.193101 | 0.193070 | Traversal wins |
| A14 | 2,216 | 8 | 0.328086 | 0.265828 | Traversal wins |

Every preceding coordinate ties. The six-decimal maximum remains 0.587276 on A04 and 0.517621 on A14. The independently parsed twelve-decimal outputs agree on the winners and first differing ranks: A04 changes 0.193101375515 → 0.193070635994; A14 changes 0.328086259196 → 0.265828803072.

This is **lexicographic improvement, not uniform improvement**. In the six-decimal sorted vectors, A04 has 187 improved and 115 worsened lower coordinates; A14 has 228 improved and 238 worsened coordinates. A worse later coordinate does not undo an earlier improvement under the declared ordering. No re-rounding, rescaling, cost tiebreak, or binary floating-point parsing was used. Reported costs tie at 44 for A04 and 13 for A14.

## Identity and integrity

Run: [34215340899](https://github.com/woahwhattheheck/commons/actions/runs/34215340899), attempt 1. Operation: `roadef-rank-traversal-cold-a04-a14-20260908-01`. Source commit: `6cfc5d6ca1c3201014c30aee7ef31bd1883f578c`.

Artifact: `10051660766`, 3,973,104 bytes; SHA256:

```text
c6b754563dcafb6a33a1c7ffc312efdb0053f784ca783f897e54bf927b91a62f
```

All **739 outer-manifest file entries** matched their recorded sizes and hashes. There were no missing, unlisted, duplicate, path-traversal, or symbolic-link members among the 740 ZIP members. The nested prior manifest independently verified **529 files**; these are included in the outer count, not additional execution evidence.

| Component | SHA256 |
|---|---|
| Baseline source | `e8014d78f40df5546d80f0ff6f1c6bc3a97944a526d7c347eb0dcdbe77728e46` |
| Baseline executable | `13694deaa08e933c65a1460c2963208b020cbb17b12db92e6b8bdea27f7279df` |
| Traversal source | `d85ee6187607b1e04c9d77073d42e3eba699fe42309ee3f3324f25528a8f945e` |
| Traversal executable | `e2d77efc895e3849e70102c2ea8d26e5bdbb2523bb320c760b8ea46a246e2009` |

The baseline really used the retained `e801` executable, not the older candidate inside the supporting context. Both newly executed baseline solution files byte-match the corresponding earlier cold-trial `e801` outputs. The new solutions are A04 `04e80a84f5a443b334c297cb3a4c1d647c49c545b29277e4b8aee74bfaa1b731` and A14 `d9be08ed8d532b9dad3dc1472a88c844e5d74c6559713187e254c6692a4695a4`.

## Execution and check readback

Recorded order was A04 baseline → traversal, then A14 traversal → baseline. Timestamp comparisons confirm that all four portfolio invocations and their eight independent 6/12-precision checks were sequential, without overlap. The first portfolio started September 8, 2026 at 10:25:32.552410 UTC; the last checker finished at 10:29:25.712499 UTC.

All four outer invocations returned 0. All twelve portfolio lane exits returned 0. All eight retained checker outputs report `valid: true` and their processes returned 0. Every selected output matches its validated portfolio receipt and came from the candidate lane, not the zero-change fallback. Coordinate sets, vector lengths, and reported costs agree across precisions. The recorded outer processes and checks reported no unexpected or surviving descendants; portfolio receipts recorded no received signal.

| Case | Baseline portfolio wall | Traversal portfolio wall | Baseline polish time / accepts | Traversal polish time / accepts |
|---|---:|---:|---:|---:|
| A04 | 43.0887 s | 45.1937 s | 0.017182 s / 0 | 0.243597 s / 2 |
| A14 | 68.1749 s | 71.1859 s | 0.0517787 s / 3 | 0.550647 s / 4 |

Both arms used the declared 585-second portfolio / 565-second internal allowance, 16 passes, 32 demands, 24 pair nodes, and one-thread environment controls. Only the traversal arm enabled `FLEET_POLISH_RANK_TRAVERSAL=1`. The external guard was TERM after 590 seconds with KILL after another 10 seconds. Cold-start configuration contains no initial incumbent override.

Recorded hardware exposed four logical CPUs with affinity 0–3 and about 16 GB host memory. CPU and memory quota fields were unavailable. RSS observations are sampled, not hard bounds; neither host RAM nor shared resource counters establishes a dedicated allocation. The timing difference is not an equal-work speed benchmark.

## Actionable mechanism finding

Both traversal runs entered polishing after natural search exhaustion and then stopped for **`pass_budget`**, not time or signal. Their single shared 16-pass budget included restarts after accepted moves. A04 reached selected rank 7 at most and retained 519.991 seconds of its internal allowance. A14 reached selected rank 8 at most, reset after the extra acceptance, and stopped at selected rank 5 with 494.037 seconds remaining.

The configured rank limit of 16 therefore did **not** mean that sixteen different ranks were visited. The cap/restart interaction is a concrete next diagnostic for the existing owner; these data do not establish that increasing the cap will improve unseen cases. On A04, accepted moves at selected ranks 4 and 5 first change the final sorted objective at rank 72. Selected search rank and first improved objective rank are different quantities.

Within these two declared pairs, the raw evidence supports choosing `d85` over `e801`. It does not establish hidden-instance performance, whole-set superiority, qualification standing, runtime worst-case safety, or default-off parity. No new experiment or promotion was performed by this review.

## Reproduce this review without running the optimization

```sh
python3 -B review_artifact.py roadef-rank-traversal-34215340899.zip --output fresh-review.json
python3 -B test_review.py
```

The helper uses the standard library, verifies the exact retained artifact identity, reads ZIP members without extraction, validates source/output records and manifests, and parses the complete numeric vectors with `decimal.Decimal`. The generated JSON contains all eight sorted vector strings plus process, phase, and hash records. `summary.json` retains the compact findings and exact input/reviewer identities; original binaries and raw experiment records remain in the existing artifact rather than being duplicated here. Eight reviewer-only tests cover scientific submicro differences, lexicographic versus uniform improvement, ties, length mismatch, duplicate/nonfinite JSON, and manifest hash/coverage failures. No archived code or binary is executed.

The input artifact remains unchanged. Download artifact `10051660766` using the connected GitHub `download_workflow_artifact` action or the existing run page, then run the commands above from this directory. The review command writes a new output file and performs no network or publication operation. Publication receipts are tracked separately in [the Commons record](../../../p/vector-relay-roadef-review-publication-20260908-01.md) and the ROADEF coordination thread.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
