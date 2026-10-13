# ARC Prize 2026 Paper Track — SAGE skill-induction carrier

Whole competition-paper carrier for Commons issue #14268. It builds a falsifiable paper and local mechanism evidence around already-landed ARC solver work while preventing local artifacts from impersonating Kaggle/provider facts.

## Local validation

```bash
cd competitions/arc-prize-2026-paper
python microdynamics.py
python -m unittest -v tests.test_paper_carrier
python -O -m unittest -v tests.test_paper_carrier
python -m py_compile paper_carrier.py microdynamics.py tests/test_paper_carrier.py
```

`microdynamics.py` regenerates `experiment_results.json` and two SVGs. These are intentionally labeled local synthetic evidence.

## Readiness gate

```bash
python paper_carrier.py evidence.example.json --now 2026-09-14T03:45:00Z
```

The example must remain `HOLD`. A positive `READY_FOR_OWNER_KAGGLE_SUBMISSION_REVIEW` state is only possible after exact provider evidence is supplied for the track, Kaggle submission ID, public notebook URL, real score, cover asset digest, upstream pins, and reconciled deadline.

The positive state is still **owner review only**. It never accepts rules, submits to Kaggle, or proves an award/payment.

## Owner actions before any external submission

1. Re-read both official deadline sources and resolve the Nov 8/Nov 9 discrepancy conservatively.
2. Reread the exact landed SAGE/ARC source bytes and confirm the notebook uses the pinned generation or update provenance truthfully.
3. Join the relevant Kaggle competition and Paper Track under the intended single Kaggle account; acceptance of Kaggle terms is a human/provider action, not a repository fact.
4. Create/run a public ARC-AGI-2 or ARC-AGI-3 notebook within competition limits and obtain a real submission ID + score.
5. Generate/inspect final figures and cover media, then replace the pending-results paragraph with provider-linked evidence without exceeding 1,500 words.
6. Run the readiness compiler against captured evidence. Treat any HOLD as blocking.
7. Submit the final Writeup/attachments in Kaggle before the conservative deadline. Record provider readback separately; do not infer submission from local files.

## No-spend / no-provider-mutation default

This carrier uses standard-library local tests only. It requires no paid compute and performs no external API/provider mutation.
