"""Offline smoke receipt for the Sophelio carrier.

This does NOT claim challenge performance. It proves the grouped training and
exact submission packaging path execute without network/data credentials.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import numpy as np

from toolkit import ShotGroupedPCARidge, compile_bundle, grouped_cross_validate, verify_bundle


def main() -> int:
    rng = np.random.default_rng(20260913)
    shots, frames = 8, 6
    ids = np.repeat([f"shot-{i}" for i in range(shots)], frames)
    x = rng.normal(size=(shots * frames, 10))
    basis = rng.normal(scale=0.05, size=(4, 65 * 65))
    latent = np.column_stack([x[:, 0], x[:, 1] - x[:, 2], x[:, 3] + x[:, 4], x[:, 5]])
    psi = (latent @ basis).reshape((-1, 65, 65))
    q = 2.2 + x[:, 0] - 0.1*x[:, 3]
    beta = 1.1 - 0.3*x[:, 1] + 0.2*x[:, 4]
    scores = grouped_cross_validate(x, psi, q, beta, ids, n_splits=4, n_components=4)
    model = ShotGroupedPCARidge(n_components=4, max_frames_per_shot=12).fit(x, psi, q, beta, ids)
    p1 = model.predict(x[:3])
    p2 = model.predict(x[3:7])
    with tempfile.TemporaryDirectory() as td:
        receipt = compile_bundle(Path(td), [p1], [3], [p2], [4])
        verify_bundle(Path(td))
        print("synthetic_grouped_cv_partial=", [round(s.partial_composite, 6) for s in scores])
        print("bundle_sha256=", receipt.bundle_sha256)
    print("TRUTH: synthetic-only; no organizer data score, Codabench submission, award or payment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
