"""Historical-window calibrated causal change detector (research candidate).

Z-Meridian. Shares the multiscale feature idea with ZVK-R6M8/ZHA-V6Q3;
empirical window dispersion replaces independent-observation scaling.
Only historical data and the currently released online prefix are used.
"""
from __future__ import annotations

from collections import deque
import math
import numpy as np

DETECTOR_VERSION = "z-meridian-empirical-window-v1"


class OnlineBreakDetector:
    WINDOWS = (8, 16, 32, 64, 128, 256)

    def __init__(self, historical):
        values = np.asarray(tuple(historical), dtype=float)
        if values.ndim != 1 or len(values) < 32 or not np.isfinite(values).all():
            raise ValueError('historical values must be finite, one-dimensional, and length >= 32')
        center = float(np.median(values))
        mad = float(np.median(np.abs(values - center)))
        central = np.clip(values, *np.quantile(values, [0.05, 0.95]))
        scale = max(1.4826 * mad, 0.35 * float(np.std(central, ddof=1)), 1e-8)
        if not math.isfinite(center) or not math.isfinite(scale):
            raise ValueError('historical location and dispersion exceed numerical range')
        self.center, self.scale = center, scale
        z = np.clip((values - center) / scale, -4.0, 4.0)
        features = np.column_stack((z[1:], np.abs(z[1:]), np.abs(np.diff(z)), z[1:] * z[:-1]))
        self.feature_mean = np.mean(features, axis=0)
        self.feature_var = np.maximum(np.var(features, axis=0), 1e-6)
        prefixes = np.vstack((np.zeros(4), np.cumsum(features, axis=0)))
        self.windows = tuple(w for w in self.WINDOWS if w + 8 <= len(features) + 1)
        self.standard_errors = []
        for w in self.windows:
            means = (prefixes[w:] - prefixes[:-w]) / w
            # Empirical rolling-mean dispersion includes serial dependence.
            variance = np.mean((means - self.feature_mean) ** 2, axis=0)
            self.standard_errors.append(np.sqrt(np.maximum(variance, 0.25 * self.feature_var / w)))
        self.standard_errors = np.array(self.standard_errors)
        self.buffers = [deque() for _ in self.windows]
        self.sums = np.zeros((len(self.windows), 4))
        self.previous_z = float(z[-1])
        self.state = 0.0
        self.steps = 0

    def update(self, observation):
        x = float(observation)
        if not math.isfinite(x):
            raise ValueError('observations must be finite')
        z = max(-4.0, min(4.0, (x - self.center) / self.scale))
        feature = np.array((z, abs(z), abs(z - self.previous_z), z * self.previous_z))
        self.previous_z = z
        available = []
        for i, w in enumerate(self.windows):
            if len(self.buffers[i]) == w:
                self.sums[i] -= self.buffers[i].popleft()
            self.buffers[i].append(feature)
            self.sums[i] += feature
            if len(self.buffers[i]) == w:
                available.append(np.abs(self.sums[i] / w - self.feature_mean) / self.standard_errors[i])
        self.steps += 1
        raw = 0.0
        if len(available) >= 2:
            # Two full, distinct horizons and live corroboration, not aliases.
            votes = np.sort(np.array(available), axis=0)[-2]
            corroborates = np.abs(feature - self.feature_mean) >= 0.5 * np.sqrt(self.feature_var)
            raw = float(np.max(np.where(corroborates, votes, 0.0)))
        self.state = max(0.0, 0.85 * self.state + max(-0.6, min(1.5, raw - 3.5)))
        # A small bounded current-evidence term removes otherwise uninformative
        # floor ties without letting a single impulse create a strong alarm.
        logit = (self.state - 5.2) / 1.2 + 0.2 * (min(raw, 8.0) - 1.0)
        return float(1.0 / (1.0 + math.exp(-logit)))
