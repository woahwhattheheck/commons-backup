"""Synthetic, matched, causal experiment runner; no participant data or network.

Run only trusted self-contained detector source. This is an evaluation harness,
not a sandbox for hostile Python. The detector API gets history then one point;
labels, scenario, seed, and online horizon are not passed to the detector.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import struct
import sys
import time
from types import ModuleType

from evaluation import Trace, canonical, digest, report, ts_auc, paired_bootstrap

SUITE = "adia-stress-v1"
SCENARIOS = (
    "null_iid", "null_ar", "null_heavy", "null_seasonal", "null_outliers", "null_garch",
    "mean_mild", "mean_large", "scale_up", "scale_down", "trend",
    "ar_mean", "ar_break", "heavy_mean", "seasonal_mean", "scale_mild",
    "early_mean", "late_mean",
)
HORIZONS = (10, 64, 256, 1000)
HISTORIES = (1000, 1500, 2500, 5000)


def f32(value: float) -> float:
    return struct.unpack("!f", struct.pack("!f", value))[0]


@dataclass(frozen=True)
class Case:
    case_id: str
    cluster: int
    scenario: str
    history: tuple[float, ...]
    online: tuple[float, ...]
    break_index: int | None

    def manifest(self) -> dict:
        data = {"case_id": self.case_id, "cluster": self.cluster, "scenario": self.scenario,
                "history": self.history, "online": self.online, "break_index": self.break_index}
        return {"case_id": self.case_id, "cluster": self.cluster, "scenario": self.scenario,
                "case_sha256": digest(data), "break_index": self.break_index,
                "online_length": len(self.online)}


def make_case(seed: int, scenario: str) -> Case:
    if type(seed) is not int or not 0 <= seed < 2**31 or scenario not in SCENARIOS:
        raise ValueError("invalid seed or scenario")
    # Stable keying: Python's salted hash() is deliberately not used.
    key = int.from_bytes(hashlib.sha256(f"{SUITE}/{seed}/{scenario}".encode()).digest()[:8], "big")
    rng = random.Random(key)
    h, n = HISTORIES[(seed // 4) % 4], HORIZONS[seed % 4]
    tau = None if scenario.startswith("null_") else max(0, n // 3)
    if scenario == "early_mean":
        tau = min(2, n - 1)
    elif scenario == "late_mean":
        tau = max(0, n - 16)
    values, prev, variance = [], rng.gauss(0, 1), 1.0
    phase = rng.random() * 2 * math.pi
    for t in range(h + n):
        online_t = t - h
        changed = tau is not None and online_t >= tau
        rho = 0.85 if scenario in ("null_ar", "ar_mean") else 0.0
        if scenario == "ar_break" and changed:
            rho = 0.8
        if scenario in ("null_heavy", "heavy_mean"):
            noise = rng.gauss(0, 1) / math.sqrt(rng.gammavariate(1.5, 2))  # unit-variance t3
        else:
            noise = rng.gauss(0, 1)
        if scenario == "null_garch":
            variance = 0.02 + 0.10 * prev * prev + 0.88 * variance
            value = noise * math.sqrt(variance)
        else:
            value = rho * prev + math.sqrt(1 - rho * rho) * noise
        prev = value
        if scenario in ("null_seasonal", "seasonal_mean"):
            value += 1.5 * math.sin(phase + 2 * math.pi * t / 24)
        if scenario == "null_outliers" and rng.random() < 0.02:
            value += rng.choice((-10, 10))
        if changed:
            if scenario == "mean_mild":
                value += 0.65
            elif scenario in ("mean_large", "early_mean", "late_mean"):
                value += 2.0
            elif scenario in ("ar_mean", "heavy_mean", "seasonal_mean"):
                value += 1.0
            elif scenario in ("scale_up", "scale_down", "scale_mild"):
                value *= {"scale_up": 1.75, "scale_down": 0.35, "scale_mild": 1.3}[scenario]
            elif scenario == "trend":
                value += 0.015 * (online_t - tau + 1)
        values.append(f32(value))
    return Case(f"{seed:010d}/{scenario}", seed, scenario, tuple(values[:h]), tuple(values[h:]), tau)


def corpus(seed_start: int = 20000, seeds: int = 32) -> tuple[Case, ...]:
    if type(seed_start) is not int or type(seeds) is not int or seeds < 1 or seeds > 512:
        raise ValueError("seeds must be an integer in [1,512]")
    if not 0 <= seed_start < 2**31 - seeds:
        raise ValueError("seed range out of bounds")
    return tuple(make_case(s, k) for s in range(seed_start, seed_start + seeds) for k in SCENARIOS)


def load_detector(path: Path, expected_sha256: str, class_name: str):
    source = path.read_bytes()
    actual = hashlib.sha256(source).hexdigest()
    if actual != expected_sha256:
        raise ValueError(f"detector source mismatch: actual {actual}")
    name = "_adia_detector_" + actual
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    # Execute the exact captured bytes, not a second filesystem read.
    exec(compile(source, str(path), "exec"), module.__dict__)
    factory = getattr(module, class_name)
    if not callable(factory):
        raise ValueError("detector class must be callable")
    return factory, actual


def run(factory, cases: tuple[Case, ...]) -> tuple[list[Trace], dict]:
    traces, updates = [], 0
    started = time.perf_counter()
    for case in cases:
        detector = factory(case.history)
        scores = []
        for observation in case.online:
            value = detector.update(observation)
            # Reject invalid raw output before the runner's float32 transport.
            if type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value):
                raise ValueError(f"invalid detector output at {case.case_id}:{len(scores)}")
            scores.append(f32(value))
            updates += 1
        m = case.manifest()
        traces.append(Trace(case.case_id, case.cluster, case.scenario, m["case_sha256"],
                            case.break_index, tuple(scores)))
    return traces, {"wall_seconds": time.perf_counter() - started, "updates": updates,
                    "history_and_case_hashing_included": True}


def summary(traces: list[Trace], cases: tuple[Case, ...], candidate_sha256: str) -> dict:
    result = {"report": report(traces, candidate_sha256=candidate_sha256, case_manifest=[c.manifest() for c in cases])}
    nulls = [t for t in traces if t.break_index is None]
    result["change_vs_all_null_ts_auc"] = {
        scenario: ts_auc(nulls + [t for t in traces if t.scenario == scenario])
        for scenario in SCENARIOS if not scenario.startswith("null_")
    }
    # Subgroup diagnostics are a separate deterministic extension of core report.
    result["summary_sha256"] = digest(result)
    return result


def _exclusive(path: Path, value: object) -> None:
    with path.open("xb") as handle:
        handle.write(canonical(value) + b"\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detector", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--class-name", default="OnlineBreakDetector")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--reference-sha256")
    parser.add_argument("--reference-class", default="OnlineBreakDetector")
    parser.add_argument("--seed-start", type=int, default=20000)
    parser.add_argument("--seeds", type=int, default=32)
    parser.add_argument("--bootstrap", type=int, default=500)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if bool(args.reference) != bool(args.reference_sha256):
            raise ValueError("reference path and SHA-256 must be supplied together")
        # An exclusive run directory prevents mixed-generation/partial overwrite.
        args.out.mkdir(parents=True, exist_ok=False)
        factory, sha = load_detector(args.detector, args.expected_sha256, args.class_name)
        cases = corpus(args.seed_start, args.seeds)
        traces, timing = run(factory, cases)
        result = {"suite": SUITE, "seed_start": args.seed_start, "seeds": args.seeds,
                  "python": platform.python_version(), "platform": platform.system(),
                  "transport": "float32_history_online_and_output",
                  "candidate": summary(traces, cases, sha), "candidate_runtime": timing,
                  "harness_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in (Path(__file__), Path(__file__).with_name("evaluation.py"))}}
        if args.reference:
            reference, ref_sha = load_detector(args.reference, args.reference_sha256, args.reference_class)
            reference_traces, ref_timing = run(reference, cases)
            result["reference"] = summary(reference_traces, cases, ref_sha)
            result["reference_runtime"] = ref_timing
            result["paired_comparison"] = paired_bootstrap(reference_traces, traces, replicates=args.bootstrap)
            _exclusive(args.out / "reference_traces.json", [t.record() for t in reference_traces])
        _exclusive(args.out / "case_manifest.json", [c.manifest() for c in cases])
        _exclusive(args.out / "candidate_traces.json", [t.record() for t in traces])
        _exclusive(args.out / "summary.json", result)
        _exclusive(args.out / "COMPLETE.json", {
            "status": "COMPLETE", "evidence_class": "LOCAL_SYNTHETIC_DIAGNOSTIC",
            "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.out.iterdir())},
        })
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, AttributeError, TypeError, OverflowError) as error:
        print(f"evaluation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
