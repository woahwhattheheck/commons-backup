# Publication receipt

The files in this directory were recovered from a pre-publication local build. Historical README/HANDOFF status text describes that pre-publication state and is intentionally preserved as provenance.

Publication completed through PR #14509, squash-merged to the sole canonical `main` integration line at `5551769c954c9df3fb480ae4694e80996c5b65a6` on 2026-09-14 EDT.

Scope remains evaluator/research instrumentation only. No gameplay controller, feature key, default/config, native runtime, archive, release, or Kaggle submission was changed.

The recovered execution evidence remains scoped to authenticated native archive `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`: 43/43 regression checks in normal and optimized parent-auditor modes, 8/8 deliberate behavioral mutants rejected per mode, 240 full-interpreter transparency pairs per mode, and 32 complete four-arm game runs. Native contestant workers were not optimized and internal native fallback was not instrumented.

Controlled known-policy result: fixed recorded-opponent tapes yielded replay-vs-live terminal cash-margin differences of +4962, +4972, +3536, and +3536 over two seeds/both seats. This is a method counterexample, not a universal replay correction factor and not a claim about the current top-30 corpus or every subsequently composed V4 repair.

Canonical review/publication carrier: https://github.com/woahwhattheheck/commons/pull/14509
