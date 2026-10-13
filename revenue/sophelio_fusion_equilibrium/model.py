"""Memory-bounded shot-balanced PCA + ridge modeling and grouped validation."""
from __future__ import annotations

from hashlib import sha256
import heapq
from typing import Iterable, Sequence

import numpy as np
from sklearn.decomposition import IncrementalPCA
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score
from sklearn.preprocessing import RobustScaler

try:
    from .contract import ContractError, D3D_COMPOSITE_GATE, GRID_SHAPE, Prediction, ProxyScore
    from .resampling import balanced_frame_indices, shot_group_folds
except ImportError:
    from contract import ContractError, D3D_COMPOSITE_GATE, GRID_SHAPE, Prediction, ProxyScore
    from resampling import balanced_frame_indices, shot_group_folds


def _stable_priority(shot_id: str, frame_index: int, seed: int) -> int:
    raw = f"{seed}\0{shot_id}\0{frame_index}".encode("utf-8")
    return int.from_bytes(sha256(raw).digest()[:8], "big", signed=False)


def _bounded_training_indices(
    shot_ids: Sequence[str],
    max_per_shot: int,
    max_total: int,
    seed: int,
) -> np.ndarray:
    """Select before target materialization, with one retained frame per shot."""
    ids = np.asarray([str(s) for s in shot_ids], dtype=object)
    if max_total < 2:
        raise ValueError("max_total must be at least two")
    candidates = balanced_frame_indices(ids, max_per_shot, seed)
    shots = sorted(set(ids.tolist()))
    if len(shots) > max_total:
        raise ContractError("global retained-frame ceiling below distinct shot count")
    groups = [candidates[ids[candidates] == shot] for shot in shots]
    if any(g.size == 0 for g in groups):
        raise AssertionError("balanced selector dropped a shot")
    chosen = [int(g[0]) for g in groups]
    round_index = 1
    target = min(max_total, int(candidates.size))
    while len(chosen) < target:
        progressed = False
        for group in groups:
            if round_index < group.size:
                chosen.append(int(group[round_index]))
                progressed = True
                if len(chosen) >= target:
                    break
        if not progressed:
            break
        round_index += 1
    return np.asarray(sorted(chosen), dtype=np.int64)


def target_storage_bytes(n_frames: int, *, itemsize: int = 4) -> int:
    """Exact dense psirz storage for budget receipts; no allocation is performed."""
    if n_frames < 0 or itemsize < 1:
        raise ValueError("invalid target storage request")
    return int(n_frames) * int(GRID_SHAPE[0]) * int(GRID_SHAPE[1]) * int(itemsize)


class ShotGroupedPCARidge:
    """Transparent baseline with bounded retained targets and incremental PCA.

    The batch ``fit`` path requires indexable arrays/memmaps and chooses the
    retained frame indices *before* reading/casting ``psirz``. The
    ``fit_shot_stream`` path is the real-fold path: it consumes one shot at a
    time and never retains more than ``max_retained_frames`` target frames.
    """

    def __init__(
        self,
        n_components: int = 24,
        alphas: Sequence[float] = (0.03, 0.3, 3.0),
        max_frames_per_shot: int = 48,
        max_retained_frames: int = 8192,
        pca_batch_size: int = 256,
        seed: int = 42,
    ) -> None:
        if n_components < 1:
            raise ValueError("n_components must be positive")
        if not alphas or any(a <= 0 for a in alphas):
            raise ValueError("alphas must be positive")
        if max_frames_per_shot < 1:
            raise ValueError("max_frames_per_shot must be positive")
        if max_retained_frames < 2:
            raise ValueError("max_retained_frames must be at least two")
        if pca_batch_size < 2:
            raise ValueError("pca_batch_size must be at least two")
        self.n_components = int(n_components)
        self.alphas = tuple(float(a) for a in alphas)
        self.max_frames_per_shot = int(max_frames_per_shot)
        self.max_retained_frames = int(max_retained_frames)
        self.pca_batch_size = int(pca_batch_size)
        self.seed = int(seed)
        self.scaler: RobustScaler | None = None
        self.pca: IncrementalPCA | None = None
        self.coef_models: list[Ridge] = []
        self.scalar_models: list[Ridge] = []
        self.retained_frame_count = 0
        self.retained_target_bytes = 0

    def _fit_retained(
        self,
        x: np.ndarray,
        psirz: np.ndarray,
        q95: np.ndarray,
        beta_n: np.ndarray,
    ) -> "ShotGroupedPCARidge":
        xs = np.asarray(x, dtype=np.float64)
        ys = np.asarray(psirz, dtype=np.float32)
        q = np.asarray(q95, dtype=np.float64).reshape(-1)
        b = np.asarray(beta_n, dtype=np.float64).reshape(-1)
        n = xs.shape[0]
        if xs.ndim != 2 or ys.shape != (n, *GRID_SHAPE) or q.size != n or b.size != n:
            raise ContractError("retained training arrays disagree")
        if n < 2 or n > self.max_retained_frames:
            raise ContractError("retained frame count outside configured budget")
        if not (np.isfinite(xs).all() and np.isfinite(ys).all() and np.isfinite(q).all() and np.isfinite(b).all()):
            raise ContractError("retained training arrays must be finite")

        flat = ys.reshape(n, -1)
        ncomp = min(self.n_components, n - 1, flat.shape[1])
        batch = max(ncomp, min(self.pca_batch_size, n))
        self.scaler = RobustScaler(quantile_range=(10.0, 90.0)).fit(xs)
        xz = self.scaler.transform(xs)
        self.pca = IncrementalPCA(n_components=ncomp, batch_size=batch).fit(flat)
        z = self.pca.transform(flat)
        scalars = np.column_stack([q, b])
        self.coef_models = [Ridge(alpha=alpha).fit(xz, z) for alpha in self.alphas]
        self.scalar_models = [Ridge(alpha=alpha).fit(xz, scalars) for alpha in self.alphas]
        self.retained_frame_count = int(n)
        self.retained_target_bytes = int(flat.nbytes)
        return self

    def fit(
        self,
        x: np.ndarray,
        psirz: np.ndarray,
        q95: np.ndarray,
        beta_n: np.ndarray,
        shot_ids: Sequence[str],
    ) -> "ShotGroupedPCARidge":
        """Fit from an indexable frame store without full-fold target casting."""
        ids = np.asarray([str(s) for s in shot_ids], dtype=object)
        n = int(ids.size)
        if len(set(ids.tolist())) < 2:
            raise ContractError("training requires at least two shots")
        x_shape = getattr(x, "shape", None)
        y_shape = getattr(psirz, "shape", None)
        if x_shape is None or len(x_shape) != 2 or int(x_shape[0]) != n:
            raise ContractError("training feature shape disagrees")
        if tuple(y_shape or ()) != (n, *GRID_SHAPE):
            raise ContractError("training target shape disagrees")
        if len(q95) != n or len(beta_n) != n:
            raise ContractError("training scalar lengths disagree")

        take = _bounded_training_indices(
            ids,
            self.max_frames_per_shot,
            self.max_retained_frames,
            self.seed,
        )
        try:
            xs = np.asarray(x[take], dtype=np.float64)
            ys = np.asarray(psirz[take], dtype=np.float32)
            q = np.asarray(q95[take], dtype=np.float64)
            b = np.asarray(beta_n[take], dtype=np.float64)
        except Exception as exc:
            raise ContractError("training inputs must support bounded indexed reads") from exc
        return self._fit_retained(xs, ys, q, b)

    def fit_shot_stream(
        self,
        shots: Iterable[tuple[str, np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
        *,
        expected_shots: int,
    ) -> "ShotGroupedPCARidge":
        """Fit from one-shot-at-a-time records with a hard global target budget.

        Each item is ``(shot_id, x, psirz, q95, betaN)``. One deterministic
        frame per shot is mandatory. Remaining budget is a deterministic
        priority reservoir over the other per-shot candidates. Thus peak
        retained target storage is bounded by ``max_retained_frames`` rather
        than the full training-fold frame count.
        """
        if expected_shots < 2:
            raise ContractError("stream requires at least two shots")
        if expected_shots > self.max_retained_frames:
            raise ContractError("global retained-frame ceiling below expected shot count")

        mandatory: list[tuple[int, tuple]] = []
        extras: list[tuple[int, int, tuple]] = []
        extra_budget = self.max_retained_frames - int(expected_shots)
        seen: set[str] = set()
        serial = 0

        for shot_id_raw, x_raw, y_raw, q_raw, b_raw in shots:
            shot_id = str(shot_id_raw)
            if shot_id in seen:
                raise ContractError(f"duplicate streamed shot {shot_id}")
            seen.add(shot_id)
            x = np.asarray(x_raw, dtype=np.float64)
            y = np.asarray(y_raw, dtype=np.float32)
            q = np.asarray(q_raw, dtype=np.float64).reshape(-1)
            b = np.asarray(b_raw, dtype=np.float64).reshape(-1)
            n = q.size
            if x.ndim != 2 or y.shape != (n, *GRID_SHAPE) or b.size != n or x.shape[0] != n or n < 1:
                raise ContractError(f"streamed shot arrays disagree for {shot_id}")
            if not (np.isfinite(x).all() and np.isfinite(y).all() and np.isfinite(q).all() and np.isfinite(b).all()):
                raise ContractError(f"streamed shot contains non-finite data: {shot_id}")

            local_ids = [shot_id] * n
            candidates = balanced_frame_indices(local_ids, self.max_frames_per_shot, self.seed)
            if candidates.size < 1:
                raise AssertionError("stream selector dropped a shot")

            def payload(i: int) -> tuple:
                return (
                    shot_id,
                    int(i),
                    np.array(x[i], dtype=np.float64, copy=True),
                    np.array(y[i], dtype=np.float32, copy=True),
                    float(q[i]),
                    float(b[i]),
                )

            first = int(candidates[0])
            mandatory.append((_stable_priority(shot_id, first, self.seed), payload(first)))
            for raw_i in candidates[1:]:
                if extra_budget <= 0:
                    break
                i = int(raw_i)
                priority = _stable_priority(shot_id, i, self.seed)
                item = (-priority, serial, payload(i))
                serial += 1
                if len(extras) < extra_budget:
                    heapq.heappush(extras, item)
                elif priority < -extras[0][0]:
                    heapq.heapreplace(extras, item)

        if len(seen) != expected_shots:
            raise ContractError(f"streamed {len(seen)} shots, expected {expected_shots}")

        selected = mandatory + [(-neg_priority, payload) for neg_priority, _, payload in extras]
        selected.sort(key=lambda item: (item[0], item[1][0], item[1][1]))
        x_keep = np.stack([item[1][2] for item in selected], axis=0)
        y_keep = np.stack([item[1][3] for item in selected], axis=0)
        q_keep = np.asarray([item[1][4] for item in selected], dtype=np.float64)
        b_keep = np.asarray([item[1][5] for item in selected], dtype=np.float64)
        return self._fit_retained(x_keep, y_keep, q_keep, b_keep)

    def predict(self, x: np.ndarray) -> Prediction:
        if self.scaler is None or self.pca is None or not self.coef_models:
            raise RuntimeError("model not fitted")
        x = np.asarray(x, dtype=np.float64)
        if x.ndim != 2 or not np.isfinite(x).all():
            raise ContractError("prediction features invalid")
        xz = self.scaler.transform(x)
        z = np.mean([m.predict(xz) for m in self.coef_models], axis=0)
        scal = np.mean([m.predict(xz) for m in self.scalar_models], axis=0)
        psi = self.pca.inverse_transform(z).reshape((-1, *GRID_SHAPE)).astype(np.float32)
        return Prediction(psi, scal[:, 0].astype(np.float32), scal[:, 1].astype(np.float32))


def _proxy_score(y_true: np.ndarray, q_true: np.ndarray, b_true: np.ndarray, pred: Prediction, shot_ids: Sequence[str]) -> ProxyScore:
    yt = np.asarray(y_true, dtype=np.float64).reshape(len(pred.q95), -1)
    yp = np.asarray(pred.psirz, dtype=np.float64).reshape(len(pred.q95), -1)
    rpsi = float(r2_score(yt.reshape(-1), yp.reshape(-1)))
    rs = 0.5 * (
        float(r2_score(np.asarray(q_true), np.asarray(pred.q95)))
        + float(r2_score(np.asarray(b_true), np.asarray(pred.betaN)))
    )
    partial = 0.55 * rpsi + 0.15 * rs
    return ProxyScore(rpsi, rs, partial, len(pred.q95), len(set(map(str, shot_ids))))


def grouped_cross_validate(
    x: np.ndarray,
    psirz: np.ndarray,
    q95: np.ndarray,
    beta_n: np.ndarray,
    shot_ids: Sequence[str],
    *,
    n_splits: int = 3,
    n_components: int = 12,
    max_frames_per_shot: int = 32,
    max_retained_frames: int = 8192,
    seed: int = 42,
) -> list[ProxyScore]:
    """Development helper; real full-fold scoring should use the organizer scorer."""
    ids = np.asarray([str(s) for s in shot_ids], dtype=object)
    folds = shot_group_folds(ids.tolist(), n_splits=n_splits, seed=seed)
    scores: list[ProxyScore] = []
    for fold in folds:
        train_mask = np.isin(ids, fold.train_shots)
        valid_mask = np.isin(ids, fold.valid_shots)
        if np.any(train_mask & valid_mask):
            raise AssertionError("shot leakage")
        model = ShotGroupedPCARidge(
            n_components=n_components,
            max_frames_per_shot=max_frames_per_shot,
            max_retained_frames=max_retained_frames,
            seed=seed,
        ).fit(x[train_mask], psirz[train_mask], q95[train_mask], beta_n[train_mask], ids[train_mask])
        pred = model.predict(x[valid_mask])
        scores.append(_proxy_score(psirz[valid_mask], q95[valid_mask], beta_n[valid_mask], pred, ids[valid_mask]))
    return scores


def transfer_retention(d3d_score: float, mast_score: float, gate: float = D3D_COMPOSITE_GATE) -> float:
    """Challenge-2 ratio semantics, with the organizer's DIII-D gate."""
    if not (np.isfinite(d3d_score) and np.isfinite(mast_score)):
        raise ValueError("scores must be finite")
    if d3d_score < gate or d3d_score <= 0:
        return 0.0
    return float(mast_score / d3d_score)
