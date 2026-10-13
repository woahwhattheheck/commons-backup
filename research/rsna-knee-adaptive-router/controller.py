from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping, Sequence

SCHEMA = "rsna-knee-adaptive-router/v1"
LABELS = (
    "ACL", "MCL", "Medial Meniscus", "Lateral Meniscus", "Medial OA",
    "Lateral OA", "PF OA", "Effusion", "Synovitis", "Baker's",
    "Contusion", "Fracture",
)
PLANES = ("Sagittal", "Coronal", "Axial")

# Routing priors are compute hints, not diagnoses or label-generation rules.
PLANE_PRIORS = {
    "ACL": (1.00, .52, .34), "MCL": (.48, 1.00, .44),
    "Medial Meniscus": (1.00, .82, .28), "Lateral Meniscus": (1.00, .82, .28),
    "Medial OA": (.55, 1.00, .36), "Lateral OA": (.55, 1.00, .36),
    "PF OA": (.48, .38, 1.00), "Effusion": (.82, .48, 1.00),
    "Synovitis": (.58, .50, 1.00), "Baker's": (1.00, .52, .82),
    "Contusion": (.88, .88, .64), "Fracture": (.78, .78, .72),
}


def _num(x: Any, name: str, lo: float = -math.inf, hi: float = math.inf) -> float:
    if type(x) not in (int, float) or type(x) is bool or not math.isfinite(float(x)):
        raise ValueError(f"{name} must be finite numeric")
    y = float(x)
    if not lo <= y <= hi:
        raise ValueError(f"{name} outside [{lo}, {hi}]")
    return y


def _integer(x: Any, name: str, lo: int, hi: int) -> int:
    if type(x) is not int or not lo <= x <= hi:
        raise ValueError(f"{name} must be integer in [{lo}, {hi}]")
    return x


def _prob(x: Any, name: str) -> float:
    return _num(x, name, 0.0, 1.0)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _receipt_kind(kind: Any) -> str:
    if type(kind) is not str or not kind or not kind.replace("_", "").replace("-", "").isalnum():
        raise ValueError("invalid receipt kind")
    return kind


def _detached_payload(payload: Any) -> dict[str, Any]:
    detached = json.loads(canonical_bytes(payload))
    if type(detached) is not dict:
        raise ValueError("receipt payload must be a JSON object")
    return detached


def receipt(kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    # The receipt owns a canonical detached payload snapshot. Mutating the caller's
    # object after issuance cannot silently mutate the receipt in memory.
    core = {"schema": SCHEMA, "kind": _receipt_kind(kind), "payload": _detached_payload(payload)}
    return {**core, "sha256": hashlib.sha256(canonical_bytes(core)).hexdigest()}


def verify_receipt(value: Mapping[str, Any]) -> None:
    """Verify internal receipt integrity only; this does not establish authority."""
    if set(value) != {"schema", "kind", "payload", "sha256"} or value["schema"] != SCHEMA:
        raise ValueError("receipt shape/schema mismatch")
    kind = _receipt_kind(value["kind"])
    digest = value["sha256"]
    if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("receipt digest must be lowercase SHA-256")
    core = {"schema": value["schema"], "kind": kind, "payload": _detached_payload(value["payload"])}
    if hashlib.sha256(canonical_bytes(core)).hexdigest() != digest:
        raise ValueError("receipt digest mismatch")


def verify_receipt_authoritative(
    value: Mapping[str, Any], *, expected_sha256: str, expected_kind: str
) -> None:
    """Verify integrity plus an out-of-band retained digest and receipt context."""
    if type(expected_sha256) is not str or len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise ValueError("expected receipt digest must be lowercase SHA-256")
    expected_kind = _receipt_kind(expected_kind)
    verify_receipt(value)
    if value["kind"] != expected_kind:
        raise ValueError("receipt kind does not match retained context")
    if value["sha256"] != expected_sha256:
        raise ValueError("receipt digest does not match retained authority")


@dataclass(frozen=True)
class Series:
    study_id: str
    series_id: str
    plane: str
    fluid_sensitive: int
    fat_suppression: int
    slice_count: int

    def validate(self) -> "Series":
        if not self.study_id or not self.series_id or len(self.study_id) > 160 or len(self.series_id) > 160:
            raise ValueError("invalid study/series id")
        if self.plane not in PLANES:
            raise ValueError("invalid plane")
        _integer(self.fluid_sensitive, "fluid_sensitive", 0, 1)
        _integer(self.fat_suppression, "fat_suppression", 0, 1)
        _integer(self.slice_count, "slice_count", 1, 10000)
        return self


@dataclass(frozen=True)
class Policy:
    initial_series: int = 3
    max_extra_series: int = 2
    slices_per_series: int = 16
    extra_slices_per_series: int = 24
    uncertainty_width: float = .16
    max_notebook_seconds: float = 32400.0
    target_fraction: float = .70
    runtime_safety: float = 1.20

    def validate(self) -> "Policy":
        _integer(self.initial_series, "initial_series", 1, 8)
        _integer(self.max_extra_series, "max_extra_series", 0, 8)
        _integer(self.slices_per_series, "slices_per_series", 1, 512)
        _integer(self.extra_slices_per_series, "extra_slices_per_series", 1, 512)
        _num(self.uncertainty_width, "uncertainty_width", 0, .49)
        _num(self.max_notebook_seconds, "max_notebook_seconds", 1)
        _num(self.target_fraction, "target_fraction", .05, 1)
        _num(self.runtime_safety, "runtime_safety", 1, 4)
        return self


@dataclass(frozen=True)
class Calibration:
    slope: float = 1.0
    intercept: float = 0.0
    fitted: bool = False


def _validate_study(series: Sequence[Series]) -> None:
    if not series:
        raise ValueError("study has no series")
    ids = set()
    study = series[0].study_id
    for s in series:
        s.validate()
        if s.study_id != study:
            raise ValueError("cross-study series mix")
        if s.series_id in ids:
            raise ValueError("duplicate series")
        ids.add(s.series_id)


def route_weight(label: str, series: Series) -> float:
    if label not in PLANE_PRIORS:
        raise ValueError("unknown label")
    w = PLANE_PRIORS[label][PLANES.index(series.plane)]
    if series.fluid_sensitive:
        w += .18
    if series.fat_suppression:
        w += .08
    if 16 <= series.slice_count <= 96:
        w += .03
    return max(.05, w)


def select_initial(series: Sequence[Series], policy: Policy) -> tuple[str, ...]:
    policy.validate(); _validate_study(series)
    remaining, chosen = list(series), []
    while remaining and len(chosen) < min(policy.initial_series, len(series)):
        def key(s: Series) -> tuple[float, float, str]:
            coverage = sum(route_weight(label, s) for label in LABELS)
            diversity = .35 if all(c.plane != s.plane for c in chosen) else 0.0
            cost = max(1.0, s.slice_count / policy.slices_per_series)
            return ((coverage + diversity) / cost, coverage, s.series_id)
        best = max(remaining, key=key)
        chosen.append(best); remaining.remove(best)
    return tuple(s.series_id for s in chosen)


def uncertain_labels(probabilities: Mapping[str, Any], width: float) -> tuple[str, ...]:
    width = _num(width, "width", 0, .49)
    if set(probabilities) != set(LABELS):
        raise ValueError("probability labels mismatch")
    return tuple(label for label in LABELS if abs(_prob(probabilities[label], label) - .5) <= width + 1e-12)


def select_upgrade(series: Sequence[Series], chosen: Sequence[str], uncertain: Sequence[str], policy: Policy) -> tuple[str, ...]:
    policy.validate(); _validate_study(series)
    if not set(uncertain).issubset(LABELS):
        raise ValueError("unknown uncertain label")
    ids = {s.series_id for s in series}
    if len(set(chosen)) != len(chosen) or not set(chosen).issubset(ids):
        raise ValueError("invalid chosen series")
    if not uncertain or not policy.max_extra_series:
        return ()
    remaining = [s for s in series if s.series_id not in chosen]
    ranked = sorted(
        remaining,
        key=lambda s: (sum(route_weight(label, s) for label in uncertain) / max(1.0, s.slice_count / policy.extra_slices_per_series), s.series_id),
        reverse=True,
    )
    return tuple(s.series_id for s in ranked[:policy.max_extra_series])


def _logit(p: float) -> float:
    p = min(1 - 1e-6, max(1e-6, p)); return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x); return 1 / (1 + z)
    z = math.exp(x); return z / (1 + z)


def aggregate(series: Sequence[Series], predictions: Mapping[str, Mapping[str, Any]], calibrations: Mapping[str, Calibration] | None = None) -> dict[str, float]:
    _validate_study(series)
    by_id = {s.series_id: s for s in series}
    if not predictions or not set(predictions).issubset(by_id):
        raise ValueError("missing/unknown prediction series")
    cals = calibrations or {label: Calibration() for label in LABELS}
    if set(cals) != set(LABELS):
        raise ValueError("calibration labels mismatch")
    out = {}
    for label in LABELS:
        numerator = denominator = 0.0
        for sid in sorted(predictions):
            row = predictions[sid]
            if set(row) != set(LABELS):
                raise ValueError("prediction labels mismatch")
            w = route_weight(label, by_id[sid])
            numerator += w * _logit(_prob(row[label], f"{sid}/{label}")); denominator += w
        raw = _sigmoid(numerator / denominator)
        cal = cals[label]
        out[label] = _sigmoid(_num(cal.slope, "slope", .1, 5) * _logit(raw) + _num(cal.intercept, "intercept", -5, 5))
    return out


def fit_calibration(rows: Sequence[Mapping[str, Any]], min_class_count: int = 8) -> dict[str, Calibration]:
    _integer(min_class_count, "min_class_count", 2, 100000)
    if not rows:
        return {label: Calibration() for label in LABELS}
    seen = set()
    for row in rows:
        if set(row) != {"study_id", "fold", "truth", "prediction", "is_oof"} or row["is_oof"] is not True:
            raise ValueError("calibration accepts explicit OOF rows only")
        key = (row["study_id"], _integer(row["fold"], "fold", 0, 1000))
        if key in seen:
            raise ValueError("duplicate study/fold")
        seen.add(key)
        if set(row["truth"]) != set(LABELS) or set(row["prediction"]) != set(LABELS):
            raise ValueError("calibration label mismatch")
    result = {}
    for label in LABELS:
        pairs = []
        for row in rows:
            y = row["truth"][label]
            if type(y) is not int or y not in (0, 1):
                raise ValueError("truth must be 0/1 int")
            pairs.append((y, _prob(row["prediction"][label], label)))
        pos = sum(y for y, _ in pairs); neg = len(pairs) - pos
        if min(pos, neg) < min_class_count:
            result[label] = Calibration(); continue
        def loss(slope: float, intercept: float) -> float:
            total = 0.0
            for y, p in pairs:
                q = min(1 - 1e-12, max(1e-12, _sigmoid(slope * _logit(p) + intercept)))
                total -= y * math.log(q) + (1 - y) * math.log(1 - q)
            return total / len(pairs)
        base = loss(1, 0); best = (base, 0.0, 1.0, 0.0)
        for slope in (.6, .8, 1.0, 1.2, 1.5):
            for intercept in (-.5, -.25, 0, .25, .5):
                cand = (loss(slope, intercept), abs(slope - 1) + abs(intercept), slope, intercept)
                if cand < best: best = cand
        if best[0] + 1e-12 >= base:
            result[label] = Calibration(); continue
        shrink = min(.8, len(pairs) / (len(pairs) + 64.0))
        result[label] = Calibration(1 + shrink * (best[2] - 1), shrink * best[3], True)
    return result


def local_efficiency_surrogate(
    auc: float, runtime_seconds: float, benchmark_auc: float, reference_max_auc: float
) -> float:
    """Local planning heuristic only; lower is better and this is not an organizer score."""
    auc = _num(auc, "auc", 0, 1); runtime = _num(runtime_seconds, "runtime", 0)
    benchmark = _num(benchmark_auc, "benchmark_auc", 0, 1)
    reference_max = _num(reference_max_auc, "reference_max_auc", 0, 1)
    if reference_max <= benchmark:
        raise ValueError("reference_max_auc must exceed benchmark_auc")
    if auc > reference_max:
        raise ValueError("auc must not exceed reference_max_auc")
    quality_gap = (reference_max - auc) / (reference_max - benchmark)
    runtime_fraction = runtime / 32400.0
    return quality_gap + runtime_fraction


def project_runtime(study_count: int, policy: Policy, fixed_seconds: float, seconds_per_slice: float, upgrade_rate: float) -> float:
    policy.validate(); n = _integer(study_count, "study_count", 1, 1000000)
    fixed = _num(fixed_seconds, "fixed_seconds", 0); per = _num(seconds_per_slice, "seconds_per_slice", 0); rate = _num(upgrade_rate, "upgrade_rate", 0, 1)
    slices = n * policy.initial_series * policy.slices_per_series + n * rate * policy.max_extra_series * policy.extra_slices_per_series
    return (fixed + per * slices) * policy.runtime_safety


def assert_runtime_budget(projected: float, policy: Policy) -> None:
    if _num(projected, "projected", 0) > policy.max_notebook_seconds * policy.target_fraction:
        raise ValueError("projected runtime exceeds target")


def assert_vram_budget(estimated_peak_mb: float, available_mb: float, safety: float = 1.15) -> None:
    estimate = _num(estimated_peak_mb, "estimated_peak_mb", 0); available = _num(available_mb, "available_mb", 0); safety = _num(safety, "vram_safety", 1, 4)
    if (estimate == 0) != (available == 0):
        raise ValueError("VRAM estimate and availability must both be zero or both positive")
    if available and estimate * safety > available:
        raise ValueError("safety-adjusted peak VRAM exceeds available VRAM")


Predictor = Callable[[str, Sequence[str], str], tuple[Mapping[str, Mapping[str, float]], float]]


def run_study(series: Sequence[Series], predictor: Predictor, policy: Policy, calibrations: Mapping[str, Calibration] | None = None) -> dict[str, Any]:
    _validate_study(series); initial = select_initial(series, policy); study_id = series[0].study_id
    rows1, t1 = predictor(study_id, initial, "stage1")
    if set(rows1) != set(initial): raise ValueError("stage1 returned missing/extra series")
    stage1 = aggregate(series, rows1, calibrations); uncertain = uncertain_labels(stage1, policy.uncertainty_width)
    upgrade = select_upgrade(series, initial, uncertain, policy); rows = dict(rows1); elapsed = _num(t1, "stage1_seconds", 0)
    if upgrade:
        rows2, t2 = predictor(study_id, upgrade, "upgrade")
        if set(rows2) != set(upgrade): raise ValueError("upgrade returned missing/extra series")
        rows.update(rows2); elapsed += _num(t2, "upgrade_seconds", 0)
    return {"study_id": study_id, "initial_series": initial, "upgrade_series": upgrade, "uncertain_after_stage1": uncertain, "prediction": aggregate(series, rows, calibrations), "predictor_seconds": elapsed}


def run_dataset(studies: Sequence[Sequence[Series]], predictor: Predictor, policy: Policy, *, fixed_seconds: float, seconds_per_slice: float, expected_upgrade_rate: float, expected_test_studies: int = 1300, estimated_peak_vram_mb: float = 0, available_vram_mb: float = 0, vram_safety: float = 1.15, calibrations: Mapping[str, Calibration] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not studies: raise ValueError("no studies")
    projected = project_runtime(expected_test_studies, policy, fixed_seconds, seconds_per_slice, expected_upgrade_rate)
    assert_runtime_budget(projected, policy); assert_vram_budget(estimated_peak_vram_mb, available_vram_mb, vram_safety)
    runs = [run_study(s, predictor, policy, calibrations) for s in studies]
    payload = {"projected_full_test_seconds": projected, "actual_sample_predictor_seconds": sum(r["predictor_seconds"] for r in runs), "actual_sample_upgrade_rate": sum(bool(r["upgrade_series"]) for r in runs) / len(runs), "estimated_peak_vram_mb": estimated_peak_vram_mb, "available_vram_mb": available_vram_mb, "vram_safety": vram_safety, "policy": asdict(policy)}
    return runs, receipt("dataset_run", payload)


def submission_csv_bytes(runs: Sequence[Mapping[str, Any]], expected_study_ids: Sequence[str]) -> bytes:
    if [r["study_id"] for r in runs] != list(expected_study_ids) or len(set(expected_study_ids)) != len(expected_study_ids):
        raise ValueError("run order must exactly match unique test study order")
    buf = io.StringIO(newline=""); writer = csv.writer(buf, lineterminator="\n"); writer.writerow(["StudyInstanceUID", *LABELS])
    for run in runs:
        pred = run["prediction"]
        if set(pred) != set(LABELS): raise ValueError("prediction labels mismatch")
        writer.writerow([run["study_id"], *[f"{_prob(pred[label], label):.10f}" for label in LABELS]])
    return buf.getvalue().encode()


def assert_inference_record_has_no_report(record: Mapping[str, Any]) -> None:
    forbidden = {k for k in record if k.lower() in {"report", "radiologyreport", "report_text", "text"}}
    if forbidden: raise ValueError(f"test-time report fields forbidden: {sorted(forbidden)}")
