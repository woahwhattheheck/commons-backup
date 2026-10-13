# Threat model

This companion gate decides only whether an already-valid parent `PROMOTE` also satisfies declared intersection and paired-margin robustness checks. It is monotone: it may preserve `PROMOTE` or downgrade it to `REJECT`/`INVALID`; it cannot create a promotion from a parent rejection.

## In scope

- **Marginal masking.** Positive global, per-opponent, and per-seat summaries can coexist with a negative opponent × candidate-seat stratum.
- **Pair masking.** Positive global mean margin can coexist with a negative two-seat `(opponent, seed)` mean margin.
- **Report substitution.** The contract binds the exact parent report by SHA-256.
- **Cell tampering.** Own, rival, margin, and result fields are independently recomputed from the two score vectors and candidate seat.
- **Partial grids.** The complete declared opponents × seeds × seats `[0, 1]` product is mandatory, with no extra or duplicate cells.
- **Parser/numeric attacks.** Duplicate keys, booleans used as numbers, NaN/Infinity, finite-endpoint arithmetic overflow, malformed vectors, and derived-mean overflow fail closed.
- **Input races and filesystem substitution.** Inputs are single-open regular files, `O_NOFOLLOW` is used when available, bytes are size-bounded, metadata is checked across acquisition, and the consumed bytes are hashed.
- **Evidence destruction.** The output may not alias either immutable input by path, symlink, or hard link.
- **Verdict escalation.** Parent `REJECT` remains `REJECT`; parent `INVALID`, malformed `PROMOTE`, or failed parent checks become `INVALID`.

## Out of scope

- proving that parent game rows came from the official engine;
- binding each row to candidate archive/runtime/action bytes;
- proving action-trace causality for a score change;
- choosing development versus holdout seeds;
- statistical confidence or leaderboard generalization;
- comparing against private/unavailable top-ten policies;
- changing TITAN runtime behavior or authorizing a Kaggle upload.

Those remain upstream/downstream responsibilities. In particular, row-level candidate-byte custody and both-seat ledger completeness should be composed before this gate, while action-bound causality and disjoint hosted calibration remain required after it.

## Trust boundary

The immutable intersection contract is trusted to name the intended parent report, grid, and policy. The parent report is not trusted for arithmetic: every consumed cell is rederived. The parent report is trusted only for upstream evidence dimensions this adapter cannot reconstruct, and only when its exact bytes match the contract and its own promotion checks are coherent.
