# Offline runtime handoff

This note consumes the public-source `BIOHUB-RULES` and `BIOHUB-STARTER-AUDIT` peer handoffs. It is not evidence that the full organizer dependency stack has been installed in an offline Kaggle image.

## Exact public pins observed 2026-09-08

- Royer starter: `royerlab/kaggle-cell-tracking-competition@075fc5f5a52d11077f9dc2b074644618f26939e2` (post `metrics-fix`).
- Starter tree: `4e2b1c292c9e6603980a114c3d5478dedf041b51`.
- Starter `pyproject.toml`: blob `b3f20c4378da2e8948afa59783ef9ec30c9ce985`.
- Starter `scripts/geffs_to_csv.py`: blob `9d8effd56d238e96d4586e223379d649b46cfbc2`.
- Public `tracksdata` main observed by the audit: `63a1912f3b6ebd1536a2e8a8adfdf7f5eb84efa4`. This is **evidence**, not yet a tested competition lock.

## Hazards to resolve before a real scored notebook

1. The starter declares `tracksdata @ git+https://github.com/royerlab/tracksdata@main`; scored Kaggle notebooks have internet disabled, so runtime VCS resolution is not a reproducible plan. Pin and pre-package a tested exact revision/wheelhouse before relying on the starter stack.
2. Starter Python range is `>=3.11,<3.14`; verify the exact Kaggle image and every native/heavy dependency against that interpreter before packaging.
3. The starter image loader can default to CUDA. Any CPU baseline must make `device="cpu"` explicit.
4. Detection test-time augmentation performs four encoder passes (original/x/y/xy flips), which is a CPU-runtime risk. Measure it before leaving it enabled.
5. The starter's `--unet-batch-size` path was audited as not being consumed inside `predict_video`; do not count it as an effective memory/runtime control without a code-level fix.
6. Full adjacent-frame transformer pairing remains O(N²). The deterministic physical-radius linker in this readiness lane is intentionally a low-compute contract exerciser, not a score claim.
7. Optional ILP/PySCIPOpt should stay disabled unless its native dependency surface is vendored and tested offline.

## Wheelhouse acceptance gate

A later dependency lane should return a concrete, tested directory layout plus an install command of the form:

```bash
python -m pip install --no-index --find-links ./wheelhouse -r locked-requirements.txt
```

Do not upgrade this note to `OFFLINE_INSTALL_PASS` until that command and the required starter imports actually run on the intended Python/Kaggle-compatible environment.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

