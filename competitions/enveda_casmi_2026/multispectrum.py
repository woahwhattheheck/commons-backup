"""Molecule-grouped multi-spectrum diagnostic baseline for Enveda CASMI 2026.

The executable fixture boundary is intentionally SYNTHETIC-only. Public/open,
competition-gated, private, or otherwise externally sourced spectra require a
separate code-owned source manifest with independently reviewed exact-byte
provenance and license/use authority before admission.

Preview rendering is stricter than result rendering: callers provide the exact
reviewed public contract plus a SYNTHETIC fixture. Preview code validates both,
re-runs the baseline itself, and verifies the generated result receipt. A
caller-authored RESULT_SCHEMA mapping is never a preview authority.

This module cannot sign in, accept Kaggle rules, download gated data, submit,
or claim eligibility, prizes, payment, or revenue.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

CONTRACT_SCHEMA = "commons.enveda-casmi-2026.public-contract/v1"
FIXTURE_SCHEMA = "commons.enveda-casmi-2026.multispectrum-fixture/v1"
RESULT_SCHEMA = "commons.enveda-casmi-2026.multispectrum-result/v1"
PUBLIC_CONTRACT_SHA256 = "cbd88d67e9c71353d83266a6e47c46a155c9cd440006a7ec86849ba63f0bad31"
MAX_JSON_BYTES = 2_000_000
MAX_ITEMS = 50_000
MAX_TEXT = 4_000


class MultiSpectrumError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise MultiSpectrumError(f"cannot canonicalize value: {exc}") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in items:
        if key in out:
            raise MultiSpectrumError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _bad_constant(value: str) -> None:
    raise MultiSpectrumError(f"non-finite JSON number: {value}")


def read_json(path: Path) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise MultiSpectrumError(f"cannot open JSON input: {path}: {exc}") from exc
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode):
            raise MultiSpectrumError(f"JSON input is not a regular file: {path}")
        if meta.st_size > MAX_JSON_BYTES:
            raise MultiSpectrumError(f"JSON input exceeds {MAX_JSON_BYTES} bytes: {path}")
        chunks: list[bytes] = []
        size = 0
        while size <= MAX_JSON_BYTES:
            chunk = os.read(fd, min(65536, MAX_JSON_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_JSON_BYTES:
            raise MultiSpectrumError(f"JSON input exceeds {MAX_JSON_BYTES} bytes: {path}")
    finally:
        os.close(fd)
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_bad_constant,
        )
    except MultiSpectrumError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise MultiSpectrumError(f"invalid JSON input: {path}: {exc}") from exc
    if type(value) is not dict:
        raise MultiSpectrumError(f"JSON root must be an object: {path}")
    return value


def _text(value: Any, where: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > MAX_TEXT:
        raise MultiSpectrumError(f"{where}: non-empty text <= {MAX_TEXT} chars required")
    out = value.strip()
    if any(ord(ch) < 32 for ch in out) or any(0xD800 <= ord(ch) <= 0xDFFF for ch in out):
        raise MultiSpectrumError(f"{where}: unsupported characters")
    return out


def _number(value: Any, where: str) -> float:
    if type(value) not in (int, float):
        raise MultiSpectrumError(f"{where}: numeric value required")
    out = float(value)
    if not math.isfinite(out) or out <= 0:
        raise MultiSpectrumError(f"{where}: finite positive value required")
    return out


def validate_public_contract(raw: Mapping[str, Any]) -> dict[str, Any]:
    if type(raw) is not dict or raw.get("schema") != CONTRACT_SCHEMA:
        raise MultiSpectrumError("public contract schema mismatch")
    if raw.get("competition_id") != "ENVEDA-CASMI-2026":
        raise MultiSpectrumError("public contract competition identity mismatch")
    if digest(raw) != PUBLIC_CONTRACT_SHA256:
        raise MultiSpectrumError("public contract does not match reviewed public generation")
    evaluation = raw.get("evaluation")
    submission = raw.get("submission")
    shape = raw.get("data_shape")
    timeline = raw.get("timeline")
    authority = raw.get("authority")
    if not isinstance(evaluation, dict) or evaluation.get("metric") != "MRR@25":
        raise MultiSpectrumError("MRR@25 contract missing")
    if evaluation.get("scoring_unit") != "MOLECULE" or evaluation.get("max_ranked_candidates") != 25:
        raise MultiSpectrumError("molecule/MRR@25 contract mismatch")
    if not isinstance(submission, dict):
        raise MultiSpectrumError("submission contract missing")
    if submission.get("required_columns") != ["molecule_id", "smiles"]:
        raise MultiSpectrumError("submission columns mismatch")
    if submission.get("max_candidates_per_molecule") != 25 or submission.get("filename") != "submission.csv":
        raise MultiSpectrumError("submission cardinality/filename mismatch")
    if submission.get("candidate_separator") != ";":
        raise MultiSpectrumError("candidate separator mismatch")
    if submission.get("notebook_only") is not True or submission.get("internet_enabled") is not False:
        raise MultiSpectrumError("notebook/internet contract mismatch")
    if submission.get("cpu_runtime_hours_max") != 9 or submission.get("gpu_runtime_hours_max") != 9:
        raise MultiSpectrumError("runtime contract mismatch")
    if (
        not isinstance(shape, dict)
        or shape.get("spectra_per_test_molecule_min") != 1
        or shape.get("spectra_per_test_molecule_max") != 16
    ):
        raise MultiSpectrumError("test multi-spectrum shape mismatch")
    if (
        not isinstance(timeline, dict)
        or timeline.get("final_submission_deadline_utc") != "2026-12-14T23:59:00Z"
    ):
        raise MultiSpectrumError("final deadline mismatch")
    if not isinstance(authority, dict) or not authority or any(value is not False for value in authority.values()):
        raise MultiSpectrumError("authority ceiling must remain all false")
    return dict(raw)


def _normalize_peaks(raw: Any, where: str) -> list[tuple[float, float]]:
    if type(raw) is not list or not raw or len(raw) > MAX_ITEMS:
        raise MultiSpectrumError(f"{where}: non-empty bounded peak list required")
    out: list[tuple[float, float]] = []
    last_mz = -math.inf
    for i, pair in enumerate(raw):
        if type(pair) is not list or len(pair) != 2:
            raise MultiSpectrumError(f"{where}[{i}]: [mz,intensity] required")
        mz = _number(pair[0], f"{where}[{i}].mz")
        intensity = _number(pair[1], f"{where}[{i}].intensity")
        if mz <= last_mz:
            raise MultiSpectrumError(f"{where}: peaks must have strictly increasing m/z")
        out.append((mz, intensity))
        last_mz = mz
    return out


def _normalize_spectrum(raw: Any, where: str) -> dict[str, Any]:
    if type(raw) is not dict or set(raw) != {"precursor_mz", "peaks"}:
        raise MultiSpectrumError(f"{where}: spectrum shape mismatch")
    return {
        "precursor_mz": _number(raw["precursor_mz"], f"{where}.precursor_mz"),
        "peaks": _normalize_peaks(raw["peaks"], f"{where}.peaks"),
    }


def normalize_fixture(raw: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema",
        "dataset_kind",
        "fragment_tolerance_da",
        "precursor_tolerance_da",
        "molecules",
        "candidates",
    }
    if type(raw) is not dict or set(raw) != expected or raw.get("schema") != FIXTURE_SCHEMA:
        raise MultiSpectrumError("multispectrum fixture shape/schema mismatch")
    if raw["dataset_kind"] != "SYNTHETIC":
        raise MultiSpectrumError(
            "only SYNTHETIC fixtures are admitted; external bytes require a code-owned exact-byte provenance/license manifest"
        )
    fragment_tol = _number(raw["fragment_tolerance_da"], "fragment_tolerance_da")
    precursor_tol = _number(raw["precursor_tolerance_da"], "precursor_tolerance_da")
    if fragment_tol > 2 or precursor_tol > 20:
        raise MultiSpectrumError("tolerances exceed diagnostic bounds")
    if type(raw["molecules"]) is not list or not raw["molecules"]:
        raise MultiSpectrumError("molecules must be a non-empty list")
    if type(raw["candidates"]) is not list or not raw["candidates"]:
        raise MultiSpectrumError("candidates must be a non-empty list")
    if len(raw["molecules"]) > MAX_ITEMS or len(raw["candidates"]) > MAX_ITEMS:
        raise MultiSpectrumError("fixture item count exceeds bound")

    molecules: list[dict[str, Any]] = []
    molecule_ids: set[str] = set()
    for i, row in enumerate(raw["molecules"]):
        if type(row) is not dict or set(row) != {"molecule_id", "expected_candidate_id", "spectra"}:
            raise MultiSpectrumError(f"molecules[{i}]: shape mismatch")
        mid = _text(row["molecule_id"], f"molecules[{i}].molecule_id")
        expected_candidate_id = _text(row["expected_candidate_id"], f"molecules[{i}].expected_candidate_id")
        if mid in molecule_ids:
            raise MultiSpectrumError(f"duplicate molecule_id: {mid}")
        molecule_ids.add(mid)
        spectra = row["spectra"]
        if type(spectra) is not list or not (1 <= len(spectra) <= 16):
            raise MultiSpectrumError(f"molecules[{i}].spectra: expected 1..16 spectra")
        molecules.append(
            {
                "molecule_id": mid,
                "expected_candidate_id": expected_candidate_id,
                "spectra": [
                    _normalize_spectrum(s, f"molecules[{i}].spectra[{j}]")
                    for j, s in enumerate(spectra)
                ],
            }
        )

    candidates: list[dict[str, Any]] = []
    candidate_ids: set[str] = set()
    for i, row in enumerate(raw["candidates"]):
        if type(row) is not dict or set(row) != {"candidate_id", "smiles", "reference_spectra"}:
            raise MultiSpectrumError(f"candidates[{i}]: shape mismatch")
        cid = _text(row["candidate_id"], f"candidates[{i}].candidate_id")
        smiles = _text(row["smiles"], f"candidates[{i}].smiles")
        if ";" in smiles or "\n" in smiles or "\r" in smiles:
            raise MultiSpectrumError(f"candidates[{i}].smiles: unsupported submission separator/newline")
        if cid in candidate_ids:
            raise MultiSpectrumError(f"duplicate candidate_id: {cid}")
        candidate_ids.add(cid)
        spectra = row["reference_spectra"]
        if type(spectra) is not list or not spectra or len(spectra) > 64:
            raise MultiSpectrumError(f"candidates[{i}].reference_spectra: non-empty <=64 required")
        candidates.append(
            {
                "candidate_id": cid,
                "smiles": smiles,
                "reference_spectra": [
                    _normalize_spectrum(s, f"candidates[{i}].reference_spectra[{j}]")
                    for j, s in enumerate(spectra)
                ],
            }
        )
    if any(row["expected_candidate_id"] not in candidate_ids for row in molecules):
        raise MultiSpectrumError("every expected_candidate_id must exist in candidate library")
    return {
        "schema": FIXTURE_SCHEMA,
        "dataset_kind": "SYNTHETIC",
        "fragment_tolerance_da": fragment_tol,
        "precursor_tolerance_da": precursor_tol,
        "molecules": molecules,
        "candidates": candidates,
    }


def _spectral_cosine(
    query: list[tuple[float, float]],
    ref: list[tuple[float, float]],
    tolerance: float,
) -> float:
    qnorm = math.sqrt(sum(intensity for _, intensity in query))
    rnorm = math.sqrt(sum(intensity for _, intensity in ref))
    if qnorm == 0.0 or rnorm == 0.0:
        return 0.0
    used: set[int] = set()
    dot = 0.0
    for qmz, qint in query:
        options = [
            (abs(qmz - rmz), idx, rint)
            for idx, (rmz, rint) in enumerate(ref)
            if idx not in used and abs(qmz - rmz) <= tolerance
        ]
        if not options:
            continue
        _, idx, rint = min(options, key=lambda item: (item[0], item[1]))
        used.add(idx)
        dot += math.sqrt(qint) * math.sqrt(rint)
    return max(0.0, min(1.0, dot / (qnorm * rnorm)))


def _spectrum_candidate_score(
    query: Mapping[str, Any],
    reference: Mapping[str, Any],
    fragment_tolerance_da: float,
    precursor_tolerance_da: float,
) -> float:
    spectral = _spectral_cosine(query["peaks"], reference["peaks"], fragment_tolerance_da)
    delta = abs(query["precursor_mz"] - reference["precursor_mz"])
    precursor = max(0.0, 1.0 - delta / precursor_tolerance_da)
    return 0.85 * spectral + 0.15 * precursor


def _candidate_for_molecule(
    spectra: list[Mapping[str, Any]],
    candidate: Mapping[str, Any],
    fragment_tolerance_da: float,
    precursor_tolerance_da: float,
) -> tuple[float, list[float]]:
    per_spectrum: list[float] = []
    for query in spectra:
        score = max(
            _spectrum_candidate_score(
                query,
                reference,
                fragment_tolerance_da,
                precursor_tolerance_da,
            )
            for reference in candidate["reference_spectra"]
        )
        per_spectrum.append(score)
    mean_score = sum(per_spectrum) / len(per_spectrum)
    aggregate = 0.70 * mean_score + 0.30 * max(per_spectrum)
    return aggregate, per_spectrum


def reciprocal_rank_at_25(rank: int) -> float:
    if type(rank) is not int or rank < 1:
        raise MultiSpectrumError("rank must be a positive integer")
    return 0.0 if rank > 25 else 1.0 / rank


def run_multispectrum_baseline(raw_fixture: Mapping[str, Any]) -> dict[str, Any]:
    fixture = normalize_fixture(raw_fixture)
    rows: list[dict[str, Any]] = []
    reciprocal_sum = 0.0
    spectrum_count = 0
    candidate_to_smiles = {
        row["candidate_id"]: row["smiles"] for row in fixture["candidates"]
    }
    for molecule in fixture["molecules"]:
        spectrum_count += len(molecule["spectra"])
        ranking: list[dict[str, Any]] = []
        for candidate in fixture["candidates"]:
            aggregate, per_spectrum = _candidate_for_molecule(
                molecule["spectra"],
                candidate,
                fixture["fragment_tolerance_da"],
                fixture["precursor_tolerance_da"],
            )
            ranking.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "smiles": candidate["smiles"],
                    "aggregate_score": round(aggregate, 12),
                    "per_spectrum_scores": [round(value, 12) for value in per_spectrum],
                }
            )
        ranking.sort(key=lambda row: (-row["aggregate_score"], row["candidate_id"]))
        rank = next(
            i + 1
            for i, row in enumerate(ranking)
            if row["candidate_id"] == molecule["expected_candidate_id"]
        )
        reciprocal = reciprocal_rank_at_25(rank)
        reciprocal_sum += reciprocal
        rows.append(
            {
                "molecule_id": molecule["molecule_id"],
                "spectrum_count": len(molecule["spectra"]),
                "expected_candidate_id": molecule["expected_candidate_id"],
                "expected_rank": rank,
                "reciprocal_rank_at_25": round(reciprocal, 12),
                "ranking": ranking,
            }
        )
    result_core = {
        "schema": RESULT_SCHEMA,
        "dataset_kind": "SYNTHETIC",
        "metric_kind": "LOCAL_MRR_AT_25_MATCHES_PUBLIC_METRIC_FORMULA_NOT_KAGGLE_SCORE",
        "scoring_unit": "MOLECULE",
        "molecule_count": len(rows),
        "spectrum_count": spectrum_count,
        "mrr_at_25": round(reciprocal_sum / len(rows), 12),
        "max_submission_candidates": 25,
        "rows": rows,
        "candidate_smiles": candidate_to_smiles,
        "fixture_sha256": digest(raw_fixture),
        "competition_score_claimed": False,
        "submission_used": False,
    }
    return {**result_core, "result_sha256": digest(result_core)}


def _verified_preview_result(
    raw_contract: Mapping[str, Any],
    raw_fixture: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile preview state from admitted inputs; caller-authored results are not accepted."""
    validate_public_contract(raw_contract)
    result = run_multispectrum_baseline(raw_fixture)
    if result.get("dataset_kind") != "SYNTHETIC":
        raise MultiSpectrumError("preview result is not synthetic")
    if result.get("fixture_sha256") != digest(raw_fixture):
        raise MultiSpectrumError("preview result fixture receipt mismatch")
    result_sha256 = result.get("result_sha256")
    if type(result_sha256) is not str or len(result_sha256) != 64:
        raise MultiSpectrumError("preview result receipt missing")
    core = dict(result)
    core.pop("result_sha256", None)
    if digest(core) != result_sha256:
        raise MultiSpectrumError("preview result receipt mismatch")
    return result


def submission_preview_rows(
    raw_contract: Mapping[str, Any],
    raw_fixture: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Render rows only from a freshly compiled, verified SYNTHETIC fixture."""
    result = _verified_preview_result(raw_contract, raw_fixture)
    rows = result["rows"]
    out: list[dict[str, str]] = []
    seen_molecules: set[str] = set()
    for i, row in enumerate(rows):
        if type(row) is not dict:
            raise MultiSpectrumError(f"rows[{i}]: object required")
        mid = _text(row.get("molecule_id"), f"rows[{i}].molecule_id")
        if mid in seen_molecules:
            raise MultiSpectrumError(f"duplicate result molecule_id: {mid}")
        seen_molecules.add(mid)
        ranking = row.get("ranking")
        if type(ranking) is not list or not ranking:
            raise MultiSpectrumError(f"rows[{i}].ranking: non-empty list required")
        smiles: list[str] = []
        seen_smiles: set[str] = set()
        for ranked in ranking:
            if type(ranked) is not dict:
                raise MultiSpectrumError(f"rows[{i}].ranking item: object required")
            value = _text(ranked.get("smiles"), f"rows[{i}].ranking.smiles")
            if ";" in value or "\n" in value or "\r" in value:
                raise MultiSpectrumError("SMILES contains unsupported separator/newline")
            if value in seen_smiles:
                continue
            seen_smiles.add(value)
            smiles.append(value)
            if len(smiles) == 25:
                break
        if not smiles:
            raise MultiSpectrumError(f"rows[{i}]: no submission candidates")
        out.append({"molecule_id": mid, "smiles": ";".join(smiles)})
    return out


def render_submission_preview_csv(
    raw_contract: Mapping[str, Any],
    raw_fixture: Mapping[str, Any],
) -> str:
    rows = submission_preview_rows(raw_contract, raw_fixture)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=["molecule_id", "smiles"],
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("baseline")
    b.add_argument("contract", type=Path)
    b.add_argument("fixture", type=Path)
    s = sub.add_parser("preview")
    s.add_argument("contract", type=Path)
    s.add_argument("fixture", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        contract = read_json(args.contract)
        fixture = read_json(args.fixture)
        validate_public_contract(contract)
        if args.command == "baseline":
            result = run_multispectrum_baseline(fixture)
            print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
        else:
            print(render_submission_preview_csv(contract, fixture), end="")
        return 0
    except MultiSpectrumError as exc:
        print(f"CASMI_MULTISPECTRUM_HOLD: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError, OverflowError) as exc:
        print(f"CASMI_MULTISPECTRUM_HOLD: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
