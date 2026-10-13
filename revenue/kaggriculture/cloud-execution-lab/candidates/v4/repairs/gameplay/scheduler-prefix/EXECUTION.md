# Canonical scheduler-prefix execution receipt

RIVET-MAINPORT, 2026-09-12 UTC. This extends the existing main-only package preserved by ASTRA/SOL in `3cb388d0c989edc4a088e504054feac030af3b37`. No sibling V4 carrier was created.

## Landed source

Materializer fix commit: `44d0056be2bb990b7c2c314ab9a313c4d7eb557a`.
Execution-test commit: `6f25e3abbd47b3ce3632471d2a0c2bc0f6b7e643`.

Exact bytes validated:

| Input or output | Git blob |
| --- | --- |
| Current lab `scheduler.py`, 21,035 bytes | `a483b24dd72b580d7d8811636b54d2d44f391575` |
| Official engine | `3c202c7ee921da239356789e266b694635103fc4` |
| Original canonical materializer | `f1028f7d8e32d8dfba3f302da410d2209551ca24` |
| Fixed canonical materializer | `f36e9120ea07c861a7eca5821a5306c6dbfa4613` |
| Existing six-test suite, unchanged | `f946996090f77346538870797ce78305b9da03cd` |
| New 40-test execution suite, 19,404 bytes | `31400e413bf07b0e7a226f9092c8960d13ec7445` |
| Generated scheduler postimage, 21,519 bytes | `1da9934ec45f485a16244bcbc78af26d9109b97e` |

The tests read the lab scheduler and enforce the pinned preimage; no duplicate scheduler authority is installed in this repair directory.

## Executed validation

From this directory:

```sh
python -m unittest -v test_scheduler_prefix_repair test_scheduler_prefix_execution
python -O -m unittest -v test_scheduler_prefix_repair test_scheduler_prefix_execution
```

**46/46 passed in each mode**: final normal run 2.705 seconds; optimized run 2.661 seconds. This includes the unchanged six engine-bound source/materialization checks and 40 new exact-source component/output-custody tests.

The engine bytes were recovered through GitHub Actions artifact `10288841962`, ZIP SHA256 `189b04ca31bc3125b6dff657d081d56ccf6c87c1ca4ab5968ab008926648aa40`, then independently matched to the engine Git blob above. Only the matching engine bytes were used from this older artifact, not its older scheduler or runtime as a replacement for current main.

A real positive CLI materialization also ran with the exact current scheduler and exact engine, without mocking the byte producer. It generated the postimage above and preserved both inputs. The six isolated output-custody unit tests separately mock the byte producer to isolate filesystem behavior; they are not presented as game-engine transitions.

## Recovery validated and blocker fixed

The existing canonical port recovers the V3 #12005/#12018 executable-prefix semantics: the two live current-main projection consumers are `cash_reserve` and `receipt_profile`. The old da1 scheduler's extra upfront SELL prepass is not restored. The newer uncapped `post_units(..., shed_capacity=10**6)` capacity proof remains intact.

Coverage includes 1,512 raw-slot/cap combinations, 144 below-cap predecessor-parity cases, eight explicit old/new cash or receipt counterexamples, before-market overflow, day boundaries, unchanged input objects and AST comparison of every other existing scheduler method/declaration. The #12643 bound-helper and collapsing dictionary-comprehension fixture hazards are avoided.

The additional fixed blocker was destructive CLI output handling. The old materializer could overwrite its pinned engine or an unrelated existing artifact, including an engine hard link or symlink. The repaired CLI rejects bound-input aliases, creates output exclusively, checks both inputs and verifies output readback. Running the six output-custody tests against the exact old materializer produced four expected failures and zero errors; all six pass after the fix.

## Integration boundary

Full-package imports, official-engine game replays, competitive economics and submission-archive validation are not claimed by these focused checks. Other `SellScheduler.act` full-market scans remain outside this two-probe repair. No production scheduler, shared router, feature/default, workflow, archive or Kaggle submission was changed; no legacy r04 materializer was executed.

Three non-force root-ref publication attempts were rejected because other writers advanced main. The final changes were published through sequential, path-scoped Contents API writes, preserving concurrent work. The abandoned detached candidates are not alternate integration authorities; this existing main package is the sole continuation point.
