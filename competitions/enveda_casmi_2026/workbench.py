"""Source-locked internal workbench for Enveda CASMI 2026.

This carrier permits internal research on synthetic/public-open spectra while the
competition-specific rules/data/license/submission contract is not retained.
It never joins Kaggle, accepts rules, downloads gated data, submits, or claims
eligibility/prize/revenue.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

SOURCE_SCHEMA = "commons.enveda-casmi-2026.sources/v1"
FIXTURE_SCHEMA = "commons.enveda-casmi-2026.spectral-fixture/v1"
REPORT_SCHEMA = "commons.enveda-casmi-2026.workbench-report/v1"
SOURCE_LEDGER_SHA256 = "52870451271e2513b037d8080a784d321909920c51c35f0b19f1b8b889a85728"
MAX_JSON_BYTES = 2_000_000
MAX_ITEMS = 20_000
MAX_TEXT = 4_000
RULE_FIELDS = (
    "competition_rules",
    "evaluation_metric",
    "eligibility",
    "team_rules",
    "data_license",
    "external_data_policy",
    "submission_format",
    "submission_frequency",
    "code_or_notebook_requirements",
)
CORE_FIELDS = ("competition_title", "problem", "prize_pool_usd", "entry_deadline_date")


class WorkbenchError(ValueError):
    pass


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in items:
        if key in out:
            raise WorkbenchError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _bad_constant(value: str) -> None:
    raise WorkbenchError(f"non-finite JSON number: {value}")


def read_json(path: Path) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise WorkbenchError(f"cannot open JSON input: {path}: {exc}") from exc
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode):
            raise WorkbenchError(f"JSON input is not a regular file: {path}")
        if meta.st_size > MAX_JSON_BYTES:
            raise WorkbenchError(f"JSON input exceeds {MAX_JSON_BYTES} bytes: {path}")
        raw = b""
        while len(raw) <= MAX_JSON_BYTES:
            chunk = os.read(fd, min(65536, MAX_JSON_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        if len(raw) > MAX_JSON_BYTES:
            raise WorkbenchError(f"JSON input exceeds {MAX_JSON_BYTES} bytes: {path}")
    finally:
        os.close(fd)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_bad_constant)
    except WorkbenchError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise WorkbenchError(f"invalid JSON input: {path}: {exc}") from exc
    if type(value) is not dict:
        raise WorkbenchError(f"JSON root must be an object: {path}")
    return value


def write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8", "strict") + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise WorkbenchError(f"refusing non-exclusive output publication: {path}: {exc}") from exc
    try:
        offset = 0
        while offset < len(payload):
            offset += os.write(fd, payload[offset:])
        os.fsync(fd)
    finally:
        os.close(fd)


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise WorkbenchError(f"cannot canonicalize value: {exc}") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _text(value: Any, where: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if type(value) is not str or not value.strip() or len(value) > MAX_TEXT:
        raise WorkbenchError(f"{where}: non-empty text <= {MAX_TEXT} chars required")
    text = value.strip()
    if any(ord(ch) < 32 for ch in text) or any(0xD800 <= ord(ch) <= 0xDFFF for ch in text):
        raise WorkbenchError(f"{where}: unsupported characters")
    return text


def _number(value: Any, where: str, *, positive: bool = True) -> float:
    if type(value) not in (int, float):
        raise WorkbenchError(f"{where}: numeric value required")
    out = float(value)
    if not math.isfinite(out) or (positive and out <= 0):
        raise WorkbenchError(f"{where}: finite {'positive' if positive else 'numeric'} value required")
    return out


def validate_sources(raw: Mapping[str, Any]) -> dict[str, Any]:
    if type(raw) is not dict or set(raw) != {"schema", "competition_id", "captured_date", "facts"}:
        raise WorkbenchError("source ledger shape mismatch")
    if raw["schema"] != SOURCE_SCHEMA or raw["competition_id"] != "ENVEDA-CASMI-2026":
        raise WorkbenchError("source ledger identity mismatch")
    _text(raw["captured_date"], "captured_date")
    facts = raw["facts"]
    if type(facts) is not dict:
        raise WorkbenchError("facts must be an object")
    required = set(CORE_FIELDS) | set(RULE_FIELDS) | {
        "competition_close_date",
        "candidate_competition_slug",
        "kaggle_general_participation_boundary",
    }
    if set(facts) != required:
        raise WorkbenchError("source fact set mismatch")
    for name, fact in facts.items():
        if type(fact) is not dict or set(fact) != {"value", "state", "source_class", "source_url", "note"}:
            raise WorkbenchError(f"{name}: source fact shape mismatch")
        _text(fact["state"], f"{name}.state")
        _text(fact["source_class"], f"{name}.source_class")
        _text(fact["source_url"], f"{name}.source_url", nullable=True)
        _text(fact["note"], f"{name}.note")
    if type(facts["prize_pool_usd"]["value"]) is not int or facts["prize_pool_usd"]["value"] != 50000:
        raise WorkbenchError("prize_pool_usd must remain the retained advertised integer $50,000")
    for name in CORE_FIELDS:
        if facts[name]["state"] not in {"VERIFIED_PUBLIC", "VERIFIED_PUBLIC_NOT_RULES"}:
            raise WorkbenchError(f"{name}: retained research fact lost verification")
    if digest(raw) != SOURCE_LEDGER_SHA256:
        raise WorkbenchError("source ledger does not match the reviewed retained generation")
    return dict(raw)


def _normalize_peaks(raw: Any, where: str) -> list[tuple[float, float]]:
    if type(raw) is not list or not raw or len(raw) > MAX_ITEMS:
        raise WorkbenchError(f"{where}: non-empty peak list required")
    peaks: list[tuple[float, float]] = []
    last_mz = -math.inf
    for idx, pair in enumerate(raw):
        if type(pair) is not list or len(pair) != 2:
            raise WorkbenchError(f"{where}[{idx}]: [mz,intensity] required")
        mz = _number(pair[0], f"{where}[{idx}].mz")
        intensity = _number(pair[1], f"{where}[{idx}].intensity")
        if mz <= last_mz:
            raise WorkbenchError(f"{where}: peaks must have strictly increasing m/z")
        last_mz = mz
        peaks.append((mz, intensity))
    return peaks


def normalize_fixture(raw: Mapping[str, Any]) -> dict[str, Any]:
    expected_keys = {"schema", "dataset_kind", "mass_tolerance_da", "precursor_tolerance_da", "queries", "candidates"}
    if type(raw) is not dict or set(raw) != expected_keys or raw["schema"] != FIXTURE_SCHEMA:
        raise WorkbenchError("spectral fixture shape/schema mismatch")
    if raw["dataset_kind"] not in {"SYNTHETIC", "PUBLIC_OPEN"}:
        raise WorkbenchError("dataset_kind must be SYNTHETIC or PUBLIC_OPEN; competition-gated data is not admitted")
    mass_tol = _number(raw["mass_tolerance_da"], "mass_tolerance_da")
    precursor_tol = _number(raw["precursor_tolerance_da"], "precursor_tolerance_da")
    if mass_tol > 2 or precursor_tol > 20:
        raise WorkbenchError("tolerances exceed local diagnostic safety bounds")
    if type(raw["queries"]) is not list or type(raw["candidates"]) is not list or not raw["queries"] or not raw["candidates"]:
        raise WorkbenchError("queries and candidates must be non-empty arrays")
    if len(raw["queries"]) > MAX_ITEMS or len(raw["candidates"]) > MAX_ITEMS:
        raise WorkbenchError("fixture item count exceeds bound")
    queries, candidates = [], []
    qids: set[str] = set(); cids: set[str] = set()
    for idx, item in enumerate(raw["queries"]):
        if type(item) is not dict or set(item) != {"query_id", "precursor_mz", "peaks", "expected_candidate_id"}:
            raise WorkbenchError(f"queries[{idx}]: shape mismatch")
        qid = _text(item["query_id"], f"queries[{idx}].query_id")
        expected = _text(item["expected_candidate_id"], f"queries[{idx}].expected_candidate_id")
        assert qid is not None and expected is not None
        if qid in qids: raise WorkbenchError(f"duplicate query_id: {qid}")
        qids.add(qid)
        queries.append({"query_id": qid, "precursor_mz": _number(item["precursor_mz"], f"queries[{idx}].precursor_mz"), "peaks": _normalize_peaks(item["peaks"], f"queries[{idx}].peaks"), "expected_candidate_id": expected})
    for idx, item in enumerate(raw["candidates"]):
        if type(item) is not dict or set(item) != {"candidate_id", "smiles", "precursor_mz", "reference_peaks"}:
            raise WorkbenchError(f"candidates[{idx}]: shape mismatch")
        cid = _text(item["candidate_id"], f"candidates[{idx}].candidate_id")
        smiles = _text(item["smiles"], f"candidates[{idx}].smiles")
        assert cid is not None and smiles is not None
        if cid in cids: raise WorkbenchError(f"duplicate candidate_id: {cid}")
        cids.add(cid)
        candidates.append({"candidate_id": cid, "smiles": smiles, "precursor_mz": _number(item["precursor_mz"], f"candidates[{idx}].precursor_mz"), "reference_peaks": _normalize_peaks(item["reference_peaks"], f"candidates[{idx}].reference_peaks")})
    if any(query["expected_candidate_id"] not in cids for query in queries):
        raise WorkbenchError("every expected_candidate_id must exist in the candidate library")
    return {"schema": FIXTURE_SCHEMA, "dataset_kind": raw["dataset_kind"], "mass_tolerance_da": mass_tol, "precursor_tolerance_da": precursor_tol, "queries": queries, "candidates": candidates}


def _spectral_cosine(query: list[tuple[float, float]], ref: list[tuple[float, float]], tolerance: float) -> float:
    qnorm = math.sqrt(sum(math.sqrt(intensity) ** 2 for _, intensity in query))
    rnorm = math.sqrt(sum(math.sqrt(intensity) ** 2 for _, intensity in ref))
    used: set[int] = set(); dot = 0.0
    for qmz, qint in query:
        options = [(abs(qmz-rmz), idx, rint) for idx, (rmz, rint) in enumerate(ref) if idx not in used and abs(qmz-rmz) <= tolerance]
        if not options: continue
        _, idx, rint = min(options, key=lambda x: (x[0], x[1]))
        used.add(idx); dot += math.sqrt(qint) * math.sqrt(rint)
    return 0.0 if not qnorm or not rnorm else max(0.0, min(1.0, dot / (qnorm * rnorm)))


def run_baseline(raw_fixture: Mapping[str, Any]) -> dict[str, Any]:
    fixture = normalize_fixture(raw_fixture)
    rows = []
    reciprocal_sum = 0.0; correct = 0
    for query in fixture["queries"]:
        ranking = []
        for candidate in fixture["candidates"]:
            spectral = _spectral_cosine(query["peaks"], candidate["reference_peaks"], fixture["mass_tolerance_da"])
            delta = abs(query["precursor_mz"] - candidate["precursor_mz"])
            precursor = max(0.0, 1.0 - delta / fixture["precursor_tolerance_da"])
            score = 0.8 * spectral + 0.2 * precursor
            ranking.append({"candidate_id": candidate["candidate_id"], "score": round(score, 12), "spectral_cosine": round(spectral, 12), "precursor_score": round(precursor, 12)})
        ranking.sort(key=lambda row: (-row["score"], row["candidate_id"]))
        rank = next(i + 1 for i, row in enumerate(ranking) if row["candidate_id"] == query["expected_candidate_id"])
        reciprocal_sum += 1.0 / rank; correct += int(rank == 1)
        rows.append({"query_id": query["query_id"], "expected_candidate_id": query["expected_candidate_id"], "expected_rank": rank, "top_candidate_id": ranking[0]["candidate_id"], "ranking": ranking})
    count = len(rows)
    core = {
        "baseline_kind": "PRECURSOR_PLUS_LIBRARY_SPECTRAL_COSINE_V1",
        "dataset_kind": fixture["dataset_kind"],
        "metric_kind": "LOCAL_DIAGNOSTIC_TOP1_AND_MRR_NOT_KAGGLE_METRIC",
        "query_count": count,
        "top1_accuracy": round(correct / count, 12),
        "mean_reciprocal_rank": round(reciprocal_sum / count, 12),
        "rows": rows,
        "fixture_sha256": digest(raw_fixture),
        "competition_score_claimed": False,
    }
    return {**core, "baseline_receipt_sha256": digest(core)}


def compile_report(raw_sources: Mapping[str, Any], raw_fixture: Mapping[str, Any]) -> dict[str, Any]:
    sources = validate_sources(raw_sources)
    baseline = run_baseline(raw_fixture)
    facts = sources["facts"]
    unresolved = sorted(name for name in RULE_FIELDS if facts[name]["state"] != "VERIFIED_COMPETITION_RULES")
    submission_state = "READY_FOR_OWNER_JOIN_REVIEW" if not unresolved else "HOLD_RULES_SOURCE"
    core = {
        "schema": REPORT_SCHEMA,
        "competition_id": "ENVEDA-CASMI-2026",
        "research_state": "GO_RESEARCH_INTERNAL",
        "submission_state": submission_state,
        "unresolved_rule_fields": unresolved,
        "advertised_prize_pool_usd": 50000,
        "expected_value_usd": None,
        "prize_or_revenue_claimed": False,
        "source_ledger_sha256": SOURCE_LEDGER_SHA256,
        "source_ledger": sources,
        "fixture": raw_fixture,
        "baseline": baseline,
        "authority": {
            "kaggle_account_access": False,
            "competition_join": False,
            "rules_acceptance": False,
            "team_mutation": False,
            "gated_data_download": False,
            "competition_submission": False,
            "organizer_contact": False,
            "eligibility_assertion": False,
            "prize_assertion": False,
            "revenue_recognition": False,
        },
        "notice": "Internal research may proceed. Local retrieval metrics are diagnostics only and are not the Kaggle evaluation metric. Competition participation remains held until competition-specific rules/evaluation/license/team/submission facts are owner-accessed and source-pinned.",
    }
    return {**core, "report_sha256": digest(core)}


def verify_report(raw: Mapping[str, Any]) -> bool:
    if type(raw) is not dict or raw.get("schema") != REPORT_SCHEMA:
        return False
    supplied = raw.get("report_sha256")
    if type(supplied) is not str or len(supplied) != 64:
        return False
    try:
        core = dict(raw); core.pop("report_sha256")
        if digest(core) != supplied:
            return False
        expected = compile_report(core["source_ledger"], core["fixture"])
        return canonical(expected) == canonical(raw)
    except Exception:
        return False


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile"); c.add_argument("sources", type=Path); c.add_argument("fixture", type=Path); c.add_argument("output", type=Path)
    v = sub.add_parser("verify"); v.add_argument("report", type=Path)
    b = sub.add_parser("baseline"); b.add_argument("fixture", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "compile":
            report = compile_report(read_json(args.sources), read_json(args.fixture)); write_json_exclusive(args.output, report)
            print(f"{report['research_state']} / {report['submission_state']} / {report['report_sha256']}")
            return 0 if report["research_state"] == "GO_RESEARCH_INTERNAL" else 1
        if args.command == "verify":
            ok = verify_report(read_json(args.report)); print("VERIFIED" if ok else "INVALID"); return 0 if ok else 1
        result = run_baseline(read_json(args.fixture)); print(json.dumps(result, sort_keys=True, indent=2)); return 0
    except WorkbenchError as exc:
        print(f"CASMI_WORKBENCH_HOLD: {exc}", file=sys.stderr); return 2
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError, OverflowError) as exc:
        print(f"CASMI_WORKBENCH_HOLD: {type(exc).__name__}: {exc}", file=sys.stderr); return 2
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
