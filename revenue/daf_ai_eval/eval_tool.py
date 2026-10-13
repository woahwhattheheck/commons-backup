#!/usr/bin/env python3
"""Deterministic, provider-neutral AI evaluation evidence compiler.

Synthetic/research-owned evidence only. It does not make operational, deployment,
mission, safety, procurement, or award decisions.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

MAX_BYTES = 2_000_000
MAX_CASES = 10_000
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
CONDITIONS = {"NOMINAL", "PERTURBATION", "DRIFT", "TIMEOUT", "FAILURE"}
OUTCOMES = {"SUCCESS", "TIMEOUT", "ERROR"}
PROVIDER_CLASSES = {"SYNTHETIC", "RESEARCH_OWNED"}

class EvalError(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise EvalError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_loads(raw: bytes) -> Any:
    if len(raw) > MAX_BYTES:
        raise EvalError("input too large")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise EvalError("input must be UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(EvalError(f"non-finite number: {token}")),
        )
    except EvalError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise EvalError(f"invalid JSON: {exc}") from exc


def canonical(obj: Any) -> bytes:
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise EvalError(f"cannot canonicalize: {exc}") from exc


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def _obj(value: Any, name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise EvalError(f"{name} must be object")
    return value


def _arr(value: Any, name: str, limit: int = 256) -> list[Any]:
    if type(value) is not list or len(value) > limit:
        raise EvalError(f"{name} must be bounded array")
    return value


def _str(value: Any, name: str, limit: int = 1024) -> str:
    if type(value) is not str or not value or len(value) > limit:
        raise EvalError(f"{name} must be non-empty bounded string")
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise EvalError(f"{name} contains non-scalar Unicode")
    return value


def _int(value: Any, name: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise EvalError(f"{name} must be integer in [{lo},{hi}]")
    return value


def _bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise EvalError(f"{name} must be boolean")
    return value


def _keys(value: dict[str, Any], required: set[str], allowed: set[str], name: str) -> None:
    missing = required - set(value)
    extra = set(value) - allowed
    if missing:
        raise EvalError(f"{name} missing fields: {sorted(missing)}")
    if extra:
        raise EvalError(f"{name} unknown fields: {sorted(extra)}")


def _id(value: Any, name: str) -> str:
    text = _str(value, name, 128)
    if not ID_RE.fullmatch(text):
        raise EvalError(f"{name} invalid identifier")
    return text


def _sha(value: Any, name: str) -> str:
    text = _str(value, name, 64)
    if not SHA_RE.fullmatch(text):
        raise EvalError(f"{name} invalid sha256")
    return text


def _time(value: Any, name: str) -> dt.datetime:
    text = _str(value, name, 20)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", text):
        raise EvalError(f"{name} must be canonical UTC seconds")
    try:
        return dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError as exc:
        raise EvalError(f"{name} invalid timestamp") from exc


def _ts(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rate(num: int, den: int) -> dict[str, int | None]:
    return {"numerator": num, "denominator": den, "basis_points": None if den == 0 else (num * 10000) // den}


def validate_policy(value: Any) -> dict[str, int]:
    p = _obj(value, "policy")
    keys = {"schema", "min_nominal_accuracy_bps", "min_reliability_bps", "min_robust_accuracy_bps", "max_drift_drop_bps", "max_success_latency_ms", "min_explainability_coverage_bps"}
    _keys(p, keys, keys, "policy")
    if p["schema"] != "ai-eval-policy/v1":
        raise EvalError("unsupported policy schema")
    return {
        "min_nominal_accuracy_bps": _int(p["min_nominal_accuracy_bps"], "policy.min_nominal_accuracy_bps", 0, 10000),
        "min_reliability_bps": _int(p["min_reliability_bps"], "policy.min_reliability_bps", 0, 10000),
        "min_robust_accuracy_bps": _int(p["min_robust_accuracy_bps"], "policy.min_robust_accuracy_bps", 0, 10000),
        "max_drift_drop_bps": _int(p["max_drift_drop_bps"], "policy.max_drift_drop_bps", 0, 10000),
        "max_success_latency_ms": _int(p["max_success_latency_ms"], "policy.max_success_latency_ms", 1, 3_600_000),
        "min_explainability_coverage_bps": _int(p["min_explainability_coverage_bps"], "policy.min_explainability_coverage_bps", 0, 10000),
    }


def validate_suite(value: Any, as_of: dt.datetime) -> list[dict[str, Any]]:
    root = _obj(value, "suite")
    keys = {"schema", "suite_id", "model_id", "generated_at", "provider", "cases"}
    _keys(root, keys, keys, "suite")
    if root["schema"] != "ai-eval-scenario-set/v1":
        raise EvalError("unsupported suite schema")
    _id(root["suite_id"], "suite.suite_id")
    _id(root["model_id"], "suite.model_id")
    generated = _time(root["generated_at"], "suite.generated_at")
    if generated > as_of:
        raise EvalError("suite generated_at is in the future")
    provider = _obj(root["provider"], "suite.provider")
    _keys(provider, {"class", "name", "version", "source_sha256"}, {"class", "name", "version", "source_sha256"}, "suite.provider")
    provider_class = _str(provider["class"], "suite.provider.class", 32)
    if provider_class not in PROVIDER_CLASSES:
        raise EvalError("provider class must be synthetic or research-owned")
    _str(provider["name"], "suite.provider.name", 128)
    _str(provider["version"], "suite.provider.version", 128)
    _sha(provider["source_sha256"], "suite.provider.source_sha256")

    cases = _arr(root["cases"], "suite.cases", MAX_CASES)
    if not cases:
        raise EvalError("suite must contain cases")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for idx, raw in enumerate(cases):
        case = _obj(raw, f"case[{idx}]")
        ckeys = {"id", "condition", "expected_class", "observed_class", "outcome", "latency_ms", "explanation"}
        _keys(case, ckeys, ckeys, f"case[{idx}]")
        cid = _id(case["id"], f"case[{idx}].id")
        if cid in seen:
            raise EvalError("duplicate case id")
        seen.add(cid)
        condition = _str(case["condition"], f"case[{idx}].condition", 32)
        if condition not in CONDITIONS:
            raise EvalError("unsupported condition")
        expected = _str(case["expected_class"], f"case[{idx}].expected_class", 128)
        observed = case["observed_class"]
        if observed is not None:
            observed = _str(observed, f"case[{idx}].observed_class", 128)
        outcome = _str(case["outcome"], f"case[{idx}].outcome", 16)
        if outcome not in OUTCOMES:
            raise EvalError("unsupported outcome")
        latency = _int(case["latency_ms"], f"case[{idx}].latency_ms", 0, 3_600_000)
        if outcome == "SUCCESS" and observed is None:
            raise EvalError("successful case requires observed_class")
        if outcome != "SUCCESS" and observed is not None:
            raise EvalError("failed/timeout case must not claim observed_class")
        explanation = _obj(case["explanation"], f"case[{idx}].explanation")
        _keys(explanation, {"provided", "evidence_ids"}, {"provided", "evidence_ids"}, f"case[{idx}].explanation")
        provided = _bool(explanation["provided"], f"case[{idx}].explanation.provided")
        evidence_ids = _arr(explanation["evidence_ids"], f"case[{idx}].explanation.evidence_ids", 64)
        evidence = [_id(x, f"case[{idx}].explanation.evidence_ids") for x in evidence_ids]
        if provided != bool(evidence):
            raise EvalError("explanation.provided must match evidence presence")
        normalized.append({"id": cid, "condition": condition, "expected": expected, "observed": observed, "outcome": outcome, "latency": latency, "explained": provided})
    return normalized


def compile_report(suite: Any, policy: Any, as_of: dt.datetime) -> dict[str, Any]:
    if as_of.tzinfo is None:
        raise EvalError("as_of must be timezone-aware")
    as_of = as_of.astimezone(dt.timezone.utc).replace(microsecond=0)
    p = validate_policy(policy)
    rows = validate_suite(suite, as_of)

    nominal = [r for r in rows if r["condition"] == "NOMINAL" and r["outcome"] == "SUCCESS"]
    perturb = [r for r in rows if r["condition"] == "PERTURBATION" and r["outcome"] == "SUCCESS"]
    drift = [r for r in rows if r["condition"] == "DRIFT" and r["outcome"] == "SUCCESS"]
    successes = [r for r in rows if r["outcome"] == "SUCCESS"]

    nominal_rate = _rate(sum(r["observed"] == r["expected"] for r in nominal), len(nominal))
    robust_rate = _rate(sum(r["observed"] == r["expected"] for r in perturb), len(perturb))
    drift_rate = _rate(sum(r["observed"] == r["expected"] for r in drift), len(drift))
    reliability = _rate(len(successes), len(rows))
    explained = _rate(sum(r["explained"] for r in successes), len(successes))
    latency_max = max((r["latency"] for r in successes), default=None)

    nominal_bps = nominal_rate["basis_points"]
    drift_bps = drift_rate["basis_points"]
    drift_drop = None if nominal_bps is None or drift_bps is None else max(0, nominal_bps - drift_bps)
    reasons: list[str] = []
    checks = [
        (nominal_bps is not None and nominal_bps >= p["min_nominal_accuracy_bps"], "NOMINAL_ACCURACY"),
        (reliability["basis_points"] is not None and reliability["basis_points"] >= p["min_reliability_bps"], "RELIABILITY"),
        (robust_rate["basis_points"] is not None and robust_rate["basis_points"] >= p["min_robust_accuracy_bps"], "ROBUST_ACCURACY"),
        (drift_drop is not None and drift_drop <= p["max_drift_drop_bps"], "DRIFT_DROP"),
        (latency_max is not None and latency_max <= p["max_success_latency_ms"], "SUCCESS_LATENCY"),
        (explained["basis_points"] is not None and explained["basis_points"] >= p["min_explainability_coverage_bps"], "EXPLAINABILITY_COVERAGE"),
    ]
    for passed, name in checks:
        if not passed:
            reasons.append(f"HOLD_{name}")
    state = "PASS" if not reasons else "HOLD"
    base = {
        "schema": "ai-eval-report/v1",
        "evaluated_at": _ts(as_of),
        "state": state,
        "reason_codes": reasons,
        "metrics": {
            "nominal_accuracy": nominal_rate,
            "reliability": reliability,
            "robust_accuracy": robust_rate,
            "drift_accuracy": drift_rate,
            "drift_drop_basis_points": drift_drop,
            "max_success_latency_ms": latency_max,
            "explainability_coverage": explained,
        },
        "source_bindings": {"suite_sha256": digest(suite), "policy_sha256": digest(policy)},
        "authority": {
            "operational_recommendation": False,
            "deployment": False,
            "military_system_access": False,
            "proposal_submission": False,
            "award_or_payment": False,
        },
    }
    base["report_sha256"] = digest(base)
    return base


def verify_report(suite: Any, policy: Any, report: Any) -> None:
    report_obj = _obj(report, "report")
    evaluated_at = _time(report_obj.get("evaluated_at"), "report.evaluated_at")
    expected = compile_report(suite, policy, evaluated_at)
    if canonical(expected) != canonical(report_obj):
        raise EvalError("report verification failed")


def read_regular(path: Path) -> bytes:
    flags = os.O_RDONLY | (getattr(os, "O_NOFOLLOW", 0))
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise EvalError(f"safe input open failed: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            raise EvalError("input must be bounded regular file")
        data = bytearray()
        while True:
            chunk = os.read(fd, min(65536, MAX_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise EvalError("input too large")
        after = os.fstat(fd)
        a = (before.st_dev, before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        b = (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if a != b or len(data) != after.st_size:
            raise EvalError("input changed during read")
        return bytes(data)
    finally:
        os.close(fd)


def write_exclusive(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise EvalError(f"refusing output target: {exc}") from exc
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                raise EvalError("short write")
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _load(path: Path) -> Any:
    return strict_loads(read_regular(path))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile-current")
    c.add_argument("--suite", required=True, type=Path); c.add_argument("--policy", required=True, type=Path); c.add_argument("--out", required=True, type=Path)
    v = sub.add_parser("verify-integrity")
    v.add_argument("--suite", required=True, type=Path); v.add_argument("--policy", required=True, type=Path); v.add_argument("--report", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        suite, policy = _load(args.suite), _load(args.policy)
        if args.cmd == "compile-current":
            report = compile_report(suite, policy, dt.datetime.now(dt.timezone.utc).replace(microsecond=0))
            write_exclusive(args.out, canonical(report) + b"\n")
            print(report["state"])
        else:
            verify_report(suite, policy, _load(args.report)); print("VERIFIED")
        return 0
    except EvalError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
