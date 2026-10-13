# Public-notebook binding

The Paper Track requires an attached public notebook and a real ARC-AGI-2 or ARC-AGI-3 Kaggle submission. This carrier deliberately does not fork or silently rewrite the existing ARC solver/notebook stack.

## Exact current-main notebook/runtime lineage

A fresh current-`main` reread after the initial GitHub core quota cleared established the following exact files and Git blob identities:

- `competitions/arc-agi-3-2026/kaggle/package.py` — Git blob `79a9d063571ffd62b970924e5d2616eab67e2108`. Its `notebook_object()` deterministically builds a notebook that inserts bundled `src/` on `sys.path` and runs `src/benchmark.py`; `build_bundle()` writes it as `offline_submission.ipynb` alongside an exact `source_manifest.json`.
- `competitions/arc-agi-3-2026/kaggle/readiness.py` — Git blob `e3741b1427e7125fd1faac03a321592b9f8a4a5b`. It fails closed on offline/secret-scan findings, smoke failure, runtime-margin failure, and unknown memory limit, and grants no Kaggle-submit or leaderboard authority.
- `competitions/arc-agi-3-2026/kaggle/hermetic.py` — Git blob `d468ed161adbeea255e60cf7853c63e4dd369cb1`. It consumes the packager manifest/bundle, rebinds exact source bytes, checks dependency closure, and executes in an isolated interpreter with a network/process escape audit fence. Its own contract states runtime measurements are evidence, not provider authority.

Lineage:

- issue #14099 — `ARC3 SAGE: ablation harness + offline Kaggle runtime packager`;
- PR #14109 — deterministic packager/runtime evidence gate;
- PR #14139 — hermetic offline execution/dependency closure;
- PR #14157 — dynamic-import/native escape hardening;
- PR #14181 — source-generation custody hardening.

The paper carrier therefore binds to this landed/hardened notebook-generation path rather than introducing a second solver copy.

## Current evidence state

The source-byte binding above is current-main evidence only. It is **not** evidence that a notebook has been published to Kaggle or submitted to ARC. Accordingly:

- `evidence.example.json` leaves `public_notebook_url` and `kaggle_submission_id` null;
- `paper_carrier.py` keeps the competition state on HOLD;
- no notebook publication, Kaggle execution, submission, score or rules acceptance is claimed.

## Required closure before external submission

1. Immediately before notebook generation, reread the three current-main blobs above; if any identity changes, refresh this binding and review the semantic delta rather than silently accepting drift.
2. Generate `offline_submission.ipynb` from the exact packager lineage and run its existing packaging/readiness/hermetic gates against the exact solver bundle.
3. Publish the notebook through the owner's authorized Kaggle account and record the concrete HTTPS notebook URL.
4. Perform a real ARC-AGI-2 or ARC-AGI-3 submission and record the provider submission ID + observed score.
5. Attach required cover/media and record its exact digest.
6. Feed those provider facts into the paper readiness compiler; a local repo receipt alone still cannot submit the paper.

Until all six are true, notebook/submission readiness is HOLD.
