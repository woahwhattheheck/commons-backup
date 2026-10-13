# Real promotion run — 2026-09-10 — v3-p07-joint-actors

First live cycle of the promotion queue through the real
`titan-v3-paired-game-gate` scripts (no mocks).

## Candidate

`v3-p07-joint-actors`: additive joint pairwise assignment witness on the
frozen f8f1 producer. Submitted artifact `joint_actors.py` pins to
SHA-256 `4ab7678d12694d693ab3f189eb2e7646eec60f0af199044c32b7da1686905521`
— exactly the digest recorded in the candidate's `RESULTS.md`. Candidate
panel `matched_p07.GAMES.jsonl`: 192 cells (16 seeds × 6 opponents × both
seats), all `complete`.

## Predecessors

* frozen control: `matched_f8f1.GAMES.jsonl`, artifact identity pins
  archive `exports/titan-current.tar.gz`
  `f8f1750266b3cfaea0ebfe663f287aa9c5a2682f6fc47bc932957e1d48e63f1c`
* LAND: byte-identical to the frozen control (the landed archive *is*
  f8f1 for this run). The queue's auto strategy therefore selected
  `paired` — two real `gate.py` comparisons, one per slot — rather than
  fabricating a dual-predecessor distinction.

Engine: kaggle-environments 1.32.7 commit
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`; runner: v25 process-isolated
gauntlet evaluator (2 workers, 15 s action timeout), content-addressed
identity.

## Cycle 1 — standard policy (`promotion-policy/v1`, require_any_change=true)

Submission `pq-20260910-e7ad6210675d` → **REJECT** (status `failed`),
both slots, gate exit 3, failed check `any_score_change`. Aggregate
deltas: mean/median own delta 0.0, mean margin delta 0.0, zero
result regressions, zero new losses. The witness never accepted a live
swap, so the panel is score-identical to f8f1 — the policy's
`require_any_change` correctly rejects promoting a no-op. Duration 592 ms
for both gate runs (340 ms + 223 ms). Receipt
`receipts/r-pq-20260910-e7ad6210675d-a1.json` verifies OK.

## Cycle 2 — no-harm policy variant (require_any_change=false)

Submission `pq-20260910-1a9ae4ccf462` (same candidate bytes, different
policy → distinct pin, no dedupe collision) → **PROMOTE** (status
`passed`), both slots, gate exit 0, no failed checks. Duration 708 ms.
Receipt `receipts/r-pq-20260910-1a9ae4ccf462-a1.json` verifies OK.

## Rerun determinism

`rerun` on the failed cycle-1 submission requeued it with history kept;
the second attempt returned the identical verdicts and byte-identical
gate report hashes, sealed in chained receipt
`r-pq-20260910-e7ad6210675d-a2.json`
(`integrity.prev_receipt_digest` links attempt 1), which verifies OK.

## Reading

A REJECT here is the pipeline working, not a failure of the pipeline:
the gate's hard validity contract held on a real 192-cell panel, the
policy bit, and every byte is pinned in the receipts above.
