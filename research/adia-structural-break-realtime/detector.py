"""Deterministic causal detector for the ADIA Structural Break Real-Time challenge.

Public-data-free source: the detector consumes only the historical reference segment
and the currently revealed online prefix. It keeps bounded state and never asks for
the future online horizon.
"""

from __future__ import annotations

from collections import deque
import math
import statistics
from typing import Deque, Iterable, Sequence

DETECTOR_VERSION = "zvk-r6m8-v1"
WINDOWS = (8, 16, 32, 64)
_CLIP_Z = 4.0
_CURRENT_CORROBORATION_Z = 0.50
_WINSOR_FRACTION = 0.05


def _as_finite_float(value: float) -> float:
    x = float(value)
    if not math.isfinite(x):
        raise ValueError("observations must be finite")
    return x


def _safe_sample_std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    return float(statistics.stdev(values))


def _winsorized_sample_std(values: Sequence[float]) -> float:
    """Return deterministic central dispersion with finite-tail resistance."""
    if len(values) < 2:
        return 0.0
    ordered = sorted(values)
    last = len(ordered) - 1
    low = ordered[int(_WINSOR_FRACTION * last)]
    high = ordered[int((1.0 - _WINSOR_FRACTION) * last)]
    winsorized = [min(high, max(low, value)) for value in values]
    return _safe_sample_std(winsorized)


def _moments(values: Sequence[float]) -> tuple[float, float]:
    mean = float(statistics.fmean(values))
    variance = max(
        1e-6,
        float(statistics.fmean(value * value for value in values)) - mean * mean,
    )
    return mean, variance


def _supported_evidence(values: Sequence[float]) -> float:
    """Require two genuinely distinct populated timescales."""
    if len(values) < 2:
        return 0.0
    ordered = sorted(values, reverse=True)
    return ordered[1]


class RollingStats:
    """Fixed-capacity rolling first/second moments."""

    __slots__ = ("size", "values", "sum", "sumsq")

    def __init__(self, size: int) -> None:
        if size < 2:
            raise ValueError("rolling size must be >= 2")
        self.size = int(size)
        self.values: Deque[float] = deque(maxlen=self.size)
        self.sum = 0.0
        self.sumsq = 0.0

    def push(self, value: float) -> None:
        x = _as_finite_float(value)
        if len(self.values) == self.size:
            oldest = self.values[0]
            self.sum -= oldest
            self.sumsq -= oldest * oldest
        self.values.append(x)
        self.sum += x
        self.sumsq += x * x

    @property
    def n(self) -> int:
        return len(self.values)

    def mean(self) -> float:
        return self.sum / self.n if self.n else 0.0


class ReferenceProfile:
    """Robust historical-only reference statistics."""

    __slots__ = (
        "center",
        "scale",
        "z_mean",
        "z_variance",
        "abs_z_mean",
        "abs_z_variance",
        "diff_mean",
        "diff_variance",
        "abs_diff_mean",
        "abs_diff_variance",
        "lag_product_mean",
        "lag_product_variance",
        "history_length",
    )

    def __init__(
        self,
        *,
        center: float,
        scale: float,
        z_mean: float,
        z_variance: float,
        abs_z_mean: float,
        abs_z_variance: float,
        diff_mean: float,
        diff_variance: float,
        abs_diff_mean: float,
        abs_diff_variance: float,
        lag_product_mean: float,
        lag_product_variance: float,
        history_length: int,
    ) -> None:
        self.center = center
        self.scale = scale
        self.z_mean = z_mean
        self.z_variance = z_variance
        self.abs_z_mean = abs_z_mean
        self.abs_z_variance = abs_z_variance
        self.diff_mean = diff_mean
        self.diff_variance = diff_variance
        self.abs_diff_mean = abs_diff_mean
        self.abs_diff_variance = abs_diff_variance
        self.lag_product_mean = lag_product_mean
        self.lag_product_variance = lag_product_variance
        self.history_length = history_length

    @classmethod
    def from_history(cls, history: Iterable[float]) -> "ReferenceProfile":
        values = [_as_finite_float(value) for value in history]
        if len(values) < 32:
            raise ValueError("historical segment must contain at least 32 observations")

        center = float(statistics.median(values))
        mad = float(statistics.median(abs(value - center) for value in values))
        robust_standard = _winsorized_sample_std(values)

        # MAD anchors the robust scale. A central winsorized dispersion floor keeps
        # discrete/nearly-constant references numerically useful without letting a
        # finite historical tail outlier erase a real later break.
        scale = max(1.4826 * mad, 0.35 * robust_standard, 1e-8)

        normalized = [
            max(-_CLIP_Z, min(_CLIP_Z, (value - center) / scale))
            for value in values
        ]
        differences = [
            normalized[index] - normalized[index - 1]
            for index in range(1, len(normalized))
        ]
        lag_products = [
            normalized[index] * normalized[index - 1]
            for index in range(1, len(normalized))
        ]

        z_mean, z_variance = _moments(normalized)
        abs_z_mean, abs_z_variance = _moments([abs(value) for value in normalized])
        diff_mean, diff_variance = _moments(differences)
        abs_diff_mean, abs_diff_variance = _moments(
            [abs(value) for value in differences]
        )
        lag_product_mean, lag_product_variance = _moments(lag_products)

        return cls(
            center=center,
            scale=scale,
            z_mean=z_mean,
            z_variance=z_variance,
            abs_z_mean=abs_z_mean,
            abs_z_variance=abs_z_variance,
            diff_mean=diff_mean,
            diff_variance=diff_variance,
            abs_diff_mean=abs_diff_mean,
            abs_diff_variance=abs_diff_variance,
            lag_product_mean=lag_product_mean,
            lag_product_variance=lag_product_variance,
            history_length=len(values),
        )


class OnlineBreakDetector:
    """Bounded-memory, strictly causal multi-channel structural-break detector.

    Five feature families are monitored across 8/16/32/64-point windows:
      * normalized level mean (location shifts);
      * normalized absolute level (scale/variance shifts);
      * first-difference mean (trend/slope shifts);
      * absolute first difference (volatility shifts);
      * lag-one normalized product (dependence/persistence shifts).

    Each family requires support across two fully populated timescales and current
    per-step corroboration. The persistence accumulator therefore cannot keep
    consuming stale rolling-window evidence from one isolated point. Scores depend
    only on the currently released prefix and may decline when later observations
    contradict a soft alarm; no future online horizon or suffix is inspected.
    """

    __slots__ = (
        "reference",
        "_levels",
        "_magnitudes",
        "_diffs",
        "_diff_magnitudes",
        "_lag_products",
        "_previous_z",
        "_evidence_state",
        "_step",
        "_last_raw_evidence",
    )

    def __init__(self, historical: Iterable[float]) -> None:
        self.reference = ReferenceProfile.from_history(historical)
        self._levels = [RollingStats(size) for size in WINDOWS]
        self._magnitudes = [RollingStats(size) for size in WINDOWS]
        self._diffs = [RollingStats(size) for size in WINDOWS]
        self._diff_magnitudes = [RollingStats(size) for size in WINDOWS]
        self._lag_products = [RollingStats(size) for size in WINDOWS]
        self._previous_z = None
        self._evidence_state = 0.0
        self._step = 0
        self._last_raw_evidence = 0.0

    @property
    def step(self) -> int:
        return self._step

    @property
    def evidence_state(self) -> float:
        return self._evidence_state

    @property
    def last_raw_evidence(self) -> float:
        return self._last_raw_evidence

    def retained_observation_cells(self) -> int:
        """Count online scalar observations retained in bounded deques."""
        families = (
            self._levels,
            self._magnitudes,
            self._diffs,
            self._diff_magnitudes,
            self._lag_products,
        )
        return sum(window.n for family in families for window in family)

    @staticmethod
    def maximum_retained_observation_cells() -> int:
        return 5 * sum(WINDOWS)

    @staticmethod
    def _family_evidence(
        windows: Sequence[RollingStats],
        reference_mean: float,
        reference_variance: float,
    ) -> list[float]:
        values = []
        for window in windows:
            # Partial windows can alias the same retained prefix and must not count
            # as independent timescale votes.
            if window.n < window.size:
                continue
            standardized = (
                abs(window.mean() - reference_mean)
                * math.sqrt(window.n)
                / math.sqrt(reference_variance)
            )
            values.append(standardized)
        return values

    @staticmethod
    def _current_corroborates(
        value: float | None,
        reference_mean: float,
        reference_variance: float,
    ) -> bool:
        if value is None:
            return False
        standardized = abs(value - reference_mean) / math.sqrt(reference_variance)
        return standardized >= _CURRENT_CORROBORATION_Z

    def update(self, observation: float) -> float:
        x = _as_finite_float(observation)
        z = max(
            -_CLIP_Z,
            min(_CLIP_Z, (x - self.reference.center) / self.reference.scale),
        )

        difference = None
        lag_product = None
        if self._previous_z is not None:
            difference = z - self._previous_z
            lag_product = z * self._previous_z
        self._previous_z = z

        for window in self._levels:
            window.push(z)
        for window in self._magnitudes:
            window.push(abs(z))
        if difference is not None:
            for window in self._diffs:
                window.push(difference)
            for window in self._diff_magnitudes:
                window.push(abs(difference))
            for window in self._lag_products:
                window.push(lag_product)

        family_specs = (
            (self._levels, z, self.reference.z_mean, self.reference.z_variance),
            (
                self._magnitudes,
                abs(z),
                self.reference.abs_z_mean,
                self.reference.abs_z_variance,
            ),
            (
                self._diffs,
                difference,
                self.reference.diff_mean,
                self.reference.diff_variance,
            ),
            (
                self._diff_magnitudes,
                abs(difference) if difference is not None else None,
                self.reference.abs_diff_mean,
                self.reference.abs_diff_variance,
            ),
            (
                self._lag_products,
                lag_product,
                self.reference.lag_product_mean,
                self.reference.lag_product_variance,
            ),
        )

        supported = []
        for windows, current_value, reference_mean, reference_variance in family_specs:
            evidence = _supported_evidence(
                self._family_evidence(windows, reference_mean, reference_variance)
            )
            if self._current_corroborates(
                current_value, reference_mean, reference_variance
            ):
                supported.append(evidence)
            else:
                supported.append(0.0)

        raw_evidence = max(supported, default=0.0)
        self._last_raw_evidence = raw_evidence

        # Bounded per-step contribution + decay: persistent corroborated evidence
        # crosses quickly, while stale evidence from one clipped point cannot keep
        # feeding the accumulator after the stream returns to its reference regime.
        increment = max(-0.60, min(1.50, raw_evidence - 3.50))
        self._evidence_state = max(
            0.0,
            0.85 * self._evidence_state + increment,
        )

        score = 1.0 / (1.0 + math.exp(-(self._evidence_state - 5.2) / 1.2))
        self._step += 1
        return float(max(0.0, min(1.0, score)))
