"""Synthetic-only neutral-loss consensus experiment for Enveda CASMI 2026.

This is an additive research harness. It cannot join Kaggle, accept rules, download
competition data, submit, change teams, claim prizes, move money, or recognize revenue.
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

FIXTURE_SCHEMA = "commons.enveda-casmi-2026.neutral-loss-fixture/v1"
RESULT_SCHEMA = "commons.enveda-casmi-2026.neutral-loss-consensus-result/v1"
MAX_JSON_BYTES = 2_000_000
MAX_ITEMS = 50_000
MAX_TEXT = 4_000
MAX_SPECTRA = 16
MAX_REFERENCES = 64
SCORE_SCALE = 1_000_000
WEIGHT_SCALE = 10_000
AUTHORITY_KEYS = (
    "kaggle_account_authorized",
    "competition_join_authorized",
    "rules_acceptance_authorized",
    "gated_download_authorized",
    "submission_authorized",
    "team_mutation_authorized",
    "prize_or_payment_claim_authorized",
    "revenue_recognition_authorized",
)


class NeutralLossError(ValueError):
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
        raise NeutralLossError(f"cannot canonicalize value: {exc}") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in items:
        if key in out:
            raise NeutralLossError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _bad_constant(value: str) -> None:
    raise NeutralLossError(f"non-finite JSON number: {value}")


def read_json(path: Path) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise NeutralLossError(f"cannot open JSON input: {path}: {exc}") from exc
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode):
            raise NeutralLossError(f"JSON input is not a regular file: {path}")
        if meta.st_size > MAX_JSON_BYTES:
            raise NeutralLossError(f"JSON input exceeds {MAX_JSON_BYTES} bytes: {path}")
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
            raise NeutralLossError(f"JSON input exceeds {MAX_JSON_BYTES} bytes: {path}")
    finally:
        os.close(fd)
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_bad_constant,
        )
    except NeutralLossError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise NeutralLossError(f"invalid JSON input: {path}: {exc}") from exc
    if type(value) is not dict:
        raise NeutralLossError(f"JSON root must be an object: {path}")
    return value


def _text(value: Any, where: str) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > MAX_TEXT:
        raise NeutralLossError(f"{where}: exact non-empty text <= {MAX_TEXT} chars required")
    if any(ord(ch) < 32 or 0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise NeutralLossError(f"{where}: unsupported characters")
    return value


def _number(value: Any, where: str) -> float:
    if type(value) not in (int, float):
        raise NeutralLossError(f"{where}: numeric value required")
    out = float(value)
    if not math.isfinite(out) or out <= 0:
        raise NeutralLossError(f"{where}: finite positive value required")
    return out


def _weight(value: Any, where: str) -> int:
    if type(value) is not int or not (0 <= value <= WEIGHT_SCALE):
        raise NeutralLossError(
            f"{where}: integer basis points in [0,{WEIGHT_SCALE}] required"
        )
    return value


def _authority(raw: Any) -> dict[str, bool]:
    if type(raw) is not dict or tuple(sorted(raw)) != tuple(sorted(AUTHORITY_KEYS)):
        raise NeutralLossError("authority shape mismatch")
    if any(raw[key] is not False for key in AUTHORITY_KEYS):
        raise NeutralLossError("authority ceiling must remain all false")
    return {key: False for key in AUTHORITY_KEYS}


def _peaks(raw: Any, precursor: float, where: str) -> list[tuple[float, float]]:
    if type(raw) is not list or not raw or len(raw) > MAX_ITEMS:
        raise NeutralLossError(f"{where}: non-empty bounded peak list required")
    out: list[tuple[float, float]] = []
    last = -math.inf
    for i, pair in enumerate(raw):
        if type(pair) is not list or len(pair) != 2:
            raise NeutralLossError(f"{where}[{i}]: [mz,intensity] required")
        mz = _number(pair[0], f"{where}[{i}].mz")
        intensity = _number(pair[1], f"{where}[{i}].intensity")
        if mz <= last:
            raise NeutralLossError(f"{where}: peaks must have strictly increasing m/z")
        if mz >= precursor:
            raise NeutralLossError(f"{where}[{i}]: fragment m/z must be below precursor")
        out.append((mz, intensity))
        last = mz
    return out


def _spectrum(raw: Any, where: str) -> dict[str, Any]:
    if type(raw) is not dict or set(raw) != {"precursor_mz", "peaks"}:
        raise NeutralLossError(f"{where}: spectrum shape mismatch")
    precursor = _number(raw["precursor_mz"], f"{where}.precursor_mz")
    return {
        "precursor_mz": precursor,
        "peaks": _peaks(raw["peaks"], precursor, f"{where}.peaks"),
    }


def normalize_fixture(raw: Mapping[str, Any]) -> dict[str, Any]:
    keys = {
        "schema",
        "dataset_kind",
        "fragment_tolerance_da",
        "neutral_loss_tolerance_da",
        "precursor_tolerance_da",
        "fragment_weight_bp",
        "neutral_loss_weight_bp",
        "authority",
        "molecules",
        "candidates",
    }
    if type(raw) is not dict or set(raw) != keys or raw.get("schema") != FIXTURE_SCHEMA:
        raise NeutralLossError("neutral-loss fixture shape/schema mismatch")
    if raw["dataset_kind"] != "SYNTHETIC":
        raise NeutralLossError("only SYNTHETIC fixtures are executable")
    frag_tol = _number(raw["fragment_tolerance_da"], "fragment_tolerance_da")
    loss_tol = _number(raw["neutral_loss_tolerance_da"], "neutral_loss_tolerance_da")
    precursor_tol = _number(raw["precursor_tolerance_da"], "precursor_tolerance_da")
    if frag_tol > 2 or loss_tol > 2 or precursor_tol > 50:
        raise NeutralLossError("tolerances exceed synthetic diagnostic bounds")
    fw = _weight(raw["fragment_weight_bp"], "fragment_weight_bp")
    lw = _weight(raw["neutral_loss_weight_bp"], "neutral_loss_weight_bp")
    if fw + lw != WEIGHT_SCALE or fw == 0 or lw == 0:
        raise NeutralLossError(
            "fragment/neutral-loss weights must both be positive and sum to 10000"
        )
    authority = _authority(raw["authority"])

    molecules_raw = raw["molecules"]
    candidates_raw = raw["candidates"]
    if type(molecules_raw) is not list or not molecules_raw or len(molecules_raw) > MAX_ITEMS:
        raise NeutralLossError("molecules must be a non-empty bounded list")
    if type(candidates_raw) is not list or not candidates_raw or len(candidates_raw) > MAX_ITEMS:
        raise NeutralLossError("candidates must be a non-empty bounded list")

    molecules: list[dict[str, Any]] = []
    mids: set[str] = set()
    for i, row in enumerate(molecules_raw):
        if type(row) is not dict or set(row) != {
            "molecule_id",
            "expected_candidate_id",
            "spectra",
        }:
            raise NeutralLossError(f"molecules[{i}]: shape mismatch")
        mid = _text(row["molecule_id"], f"molecules[{i}].molecule_id")
        expected = _text(
            row["expected_candidate_id"],
            f"molecules[{i}].expected_candidate_id",
        )
        if mid in mids:
            raise NeutralLossError(f"duplicate molecule_id: {mid}")
        mids.add(mid)
        spectra = row["spectra"]
        if type(spectra) is not list or not (1 <= len(spectra) <= MAX_SPECTRA):
            raise NeutralLossError(
                f"molecules[{i}].spectra: expected 1..{MAX_SPECTRA}"
            )
        molecules.append(
            {
                "molecule_id": mid,
                "expected_candidate_id": expected,
                "spectra": [
                    _spectrum(s, f"molecules[{i}].spectra[{j}]")
                    for j, s in enumerate(spectra)
                ],
            }
        )

    candidates: list[dict[str, Any]] = []
    cids: set[str] = set()
    for i, row in enumerate(candidates_raw):
        if type(row) is not dict or set(row) != {
            "candidate_id",
            "smiles",
            "reference_spectra",
        }:
            raise NeutralLossError(f"candidates[{i}]: shape mismatch")
        cid = _text(row["candidate_id"], f"candidates[{i}].candidate_id")
        smiles = _text(row["smiles"], f"candidates[{i}].smiles")
        if ";" in smiles or "\n" in smiles or "\r" in smiles:
            raise NeutralLossError(
                f"candidates[{i}].smiles: unsupported separator/newline"
            )
        if cid in cids:
            raise NeutralLossError(f"duplicate candidate_id: {cid}")
        cids.add(cid)
        refs = row["reference_spectra"]
        if type(refs) is not list or not (1 <= len(refs) <= MAX_REFERENCES):
            raise NeutralLossError(
                f"candidates[{i}].reference_spectra: expected 1..{MAX_REFERENCES}"
            )
        candidates.append(
            {
                "candidate_id": cid,
                "smiles": smiles,
                "reference_spectra": [
                    _spectrum(s, f"candidates[{i}].reference_spectra[{j}]")
                    for j, s in enumerate(refs)
                ],
            }
        )
    if any(row["expected_candidate_id"] not in cids for row in molecules):
        raise NeutralLossError(
            "every expected_candidate_id must exist in candidate library"
        )

    molecules.sort(key=lambda x: x["molecule_id"])
    candidates.sort(key=lambda x: x["candidate_id"])
    return {
        "schema": FIXTURE_SCHEMA,
        "dataset_kind": "SYNTHETIC",
        "fragment_tolerance_da": frag_tol,
        "neutral_loss_tolerance_da": loss_tol,
        "precursor_tolerance_da": precursor_tol,
        "fragment_weight_bp": fw,
        "neutral_loss_weight_bp": lw,
        "authority": authority,
        "molecules": molecules,
        "candidates": candidates,
    }


def _neutral_losses(spectrum: Mapping[str, Any]) -> list[tuple[float, float]]:
    precursor = spectrum["precursor_mz"]
    rows = [(precursor - mz, intensity) for mz, intensity in spectrum["peaks"]]
    rows.sort(key=lambda x: x[0])
    if any(loss <= 0 for loss, _ in rows):
        raise NeutralLossError("derived neutral loss must be positive")
    return rows


def _cosine(
    query: list[tuple[float, float]],
    ref: list[tuple[float, float]],
    tolerance: float,
) -> float:
    qnorm = math.sqrt(sum(i for _, i in query))
    rnorm = math.sqrt(sum(i for _, i in ref))
    if qnorm <= 0 or rnorm <= 0:
        return 0.0
    used: set[int] = set()
    dot = 0.0
    for qmz, qint in query:
        options = [
            (abs(qmz - rmz), idx, rint)
            for idx, (rmz, rint) in enumerate(ref)
            if idx not in used and abs(qmz - rmz) <= tolerance
        ]
        if options:
            _, idx, rint = min(options, key=lambda x: (x[0], x[1]))
            used.add(idx)
            dot += math.sqrt(qint) * math.sqrt(rint)
    return max(0.0, min(1.0, dot / (qnorm * rnorm)))


def _baseline_pair(
    query: Mapping[str, Any],
    ref: Mapping[str, Any],
    frag_tol: float,
    precursor_tol: float,
) -> float:
    spectral = _cosine(query["peaks"], ref["peaks"], frag_tol)
    delta = abs(query["precursor_mz"] - ref["precursor_mz"])
    precursor = max(0.0, 1.0 - delta / precursor_tol)
    return 0.85 * spectral + 0.15 * precursor


def _to_ppm(value: float) -> int:
    if not math.isfinite(value):
        raise NeutralLossError("non-finite score")
    return max(
        0,
        min(SCORE_SCALE, int(math.floor(value * SCORE_SCALE + 0.5))),
    )


def _median_ppm(values: list[int]) -> int:
    if not values:
        raise NeutralLossError("empty consensus score")
    rows = sorted(values)
    n = len(rows)
    if n % 2:
        return rows[n // 2]
    return (rows[n // 2 - 1] + rows[n // 2] + 1) // 2


def _candidate_scores(
    molecule: Mapping[str, Any],
    candidate: Mapping[str, Any],
    fixture: Mapping[str, Any],
) -> tuple[float, int, int, int, int]:
    baseline_each: list[float] = []
    loss_each: list[int] = []
    for query in molecule["spectra"]:
        frag_best = max(
            _baseline_pair(
                query,
                ref,
                fixture["fragment_tolerance_da"],
                fixture["precursor_tolerance_da"],
            )
            for ref in candidate["reference_spectra"]
        )
        qloss = _neutral_losses(query)
        loss_best = max(
            _cosine(
                qloss,
                _neutral_losses(ref),
                fixture["neutral_loss_tolerance_da"],
            )
            for ref in candidate["reference_spectra"]
        )
        baseline_each.append(frag_best)
        loss_each.append(_to_ppm(loss_best))

    # Frozen multispectrum.py ranks the aggregate after round(..., 12).
    # Keep that 12-decimal float as the ranking key; ppm is projection only.
    baseline_mean = sum(baseline_each) / len(baseline_each)
    predecessor_rank_score = round(
        0.70 * baseline_mean + 0.30 * max(baseline_each),
        12,
    )
    predecessor_ppm = _to_ppm(predecessor_rank_score)

    # The successor deliberately removes the max-spectrum bonus and uses a robust
    # median across spectra for both evidence spaces before blending.
    fragment_consensus = _median_ppm([_to_ppm(x) for x in baseline_each])
    loss_consensus = _median_ppm(loss_each)
    combined = (
        fragment_consensus * fixture["fragment_weight_bp"]
        + loss_consensus * fixture["neutral_loss_weight_bp"]
        + WEIGHT_SCALE // 2
    ) // WEIGHT_SCALE
    return (
        predecessor_rank_score,
        predecessor_ppm,
        fragment_consensus,
        loss_consensus,
        combined,
    )


def reciprocal_rank_ppm(rank: int) -> int:
    if type(rank) is not int or rank < 1:
        raise NeutralLossError("rank must be a positive integer")
    return 0 if rank > 25 else (SCORE_SCALE + rank // 2) // rank


def compile_fixture(raw_fixture: Mapping[str, Any]) -> dict[str, Any]:
    fixture = normalize_fixture(raw_fixture)
    rows: list[dict[str, Any]] = []
    predecessor_rr = 0
    successor_rr = 0
    spectrum_count = 0
    for molecule in fixture["molecules"]:
        spectrum_count += len(molecule["spectra"])
        ranking: list[dict[str, Any]] = []
        for candidate in fixture["candidates"]:
            (
                predecessor_rank_score,
                predecessor_score,
                fragment_consensus,
                loss_consensus,
                combined,
            ) = _candidate_scores(molecule, candidate, fixture)
            ranking.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "smiles": candidate["smiles"],
                    "absolute_fragment_predecessor_ppm": predecessor_score,
                    "fragment_median_consensus_ppm": fragment_consensus,
                    "neutral_loss_consensus_ppm": loss_consensus,
                    "combined_consensus_ppm": combined,
                    "_predecessor_rank_score": predecessor_rank_score,
                }
            )
        predecessor = sorted(
            ranking,
            key=lambda x: (-x["_predecessor_rank_score"], x["candidate_id"]),
        )
        successor = sorted(
            ranking,
            key=lambda x: (-x["combined_consensus_ppm"], x["candidate_id"]),
        )
        expected = molecule["expected_candidate_id"]
        pred_rank = next(
            i + 1 for i, x in enumerate(predecessor) if x["candidate_id"] == expected
        )
        succ_rank = next(
            i + 1 for i, x in enumerate(successor) if x["candidate_id"] == expected
        )
        prr = reciprocal_rank_ppm(pred_rank)
        srr = reciprocal_rank_ppm(succ_rank)
        predecessor_rr += prr
        successor_rr += srr
        rows.append(
            {
                "molecule_id": molecule["molecule_id"],
                "spectrum_count": len(molecule["spectra"]),
                "expected_candidate_id": expected,
                "predecessor_expected_rank": pred_rank,
                "successor_expected_rank": succ_rank,
                "predecessor_reciprocal_rank_at_25_ppm": prr,
                "successor_reciprocal_rank_at_25_ppm": srr,
                "predecessor_top25": [
                    {
                        k: x[k]
                        for k in (
                            "candidate_id",
                            "smiles",
                            "absolute_fragment_predecessor_ppm",
                        )
                    }
                    for x in predecessor[:25]
                ],
                "successor_top25": [
                    {
                        k: x[k]
                        for k in (
                            "candidate_id",
                            "smiles",
                            "absolute_fragment_predecessor_ppm",
                            "fragment_median_consensus_ppm",
                            "neutral_loss_consensus_ppm",
                            "combined_consensus_ppm",
                        )
                    }
                    for x in successor[:25]
                ],
            }
        )
    count = len(rows)
    core = {
        "schema": RESULT_SCHEMA,
        "dataset_kind": "SYNTHETIC",
        "method": "MEDIAN_MULTI_SPECTRUM_FRAGMENT_PLUS_NEUTRAL_LOSS_CONSENSUS",
        "scoring_unit": "MOLECULE",
        "metric_kind": "LOCAL_MRR_AT_25_FORMULA_DIAGNOSTIC_NOT_KAGGLE_SCORE",
        "fragment_weight_bp": fixture["fragment_weight_bp"],
        "neutral_loss_weight_bp": fixture["neutral_loss_weight_bp"],
        "molecule_count": count,
        "spectrum_count": spectrum_count,
        "predecessor_mrr_at_25_ppm": (
            predecessor_rr + count // 2
        ) // count,
        "successor_mrr_at_25_ppm": (
            successor_rr + count // 2
        ) // count,
        "rows": rows,
        "fixture_sha256": digest(raw_fixture),
        "authority": fixture["authority"],
        "competition_score_claimed": False,
        "submission_used": False,
        "prize_or_revenue_claimed": False,
    }
    return {**core, "result_sha256": digest(core)}


def verify_result(packet: Any, raw_fixture: Mapping[str, Any]) -> bool:
    if type(packet) is not dict or packet.get("schema") != RESULT_SCHEMA:
        raise NeutralLossError("result schema mismatch")
    receipt = packet.get("result_sha256")
    if (
        type(receipt) is not str
        or len(receipt) != 64
        or any(ch not in "0123456789abcdef" for ch in receipt)
    ):
        raise NeutralLossError("result receipt malformed")
    body = dict(packet)
    del body["result_sha256"]
    if digest(body) != receipt:
        raise NeutralLossError("result receipt mismatch")
    expected = compile_fixture(raw_fixture)
    if canonical(expected) != canonical(packet):
        raise NeutralLossError("semantic exact-recompile mismatch")
    return True


def write_create_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    parent = path.parent
    if parent.exists() and parent.is_symlink():
        raise NeutralLossError("symlink output parent forbidden")
    if not parent.exists():
        raise NeutralLossError("output parent must already exist")
    data = (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise NeutralLossError(
            f"create-exclusive output failed: {path}: {exc}"
        ) from exc
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compile")
    c.add_argument("fixture", type=Path)
    c.add_argument("output", type=Path)
    v = sub.add_parser("verify")
    v.add_argument("fixture", type=Path)
    v.add_argument("packet", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        fixture = read_json(args.fixture)
        if args.command == "compile":
            packet = compile_fixture(fixture)
            write_create_exclusive(args.output, packet)
            print(packet["result_sha256"])
        else:
            packet = read_json(args.packet)
            verify_result(packet, fixture)
            print(packet["result_sha256"])
        return 0
    except NeutralLossError as exc:
        print(f"CASMI_NEUTRAL_LOSS_HOLD: {exc}", file=sys.stderr)
        return 2
    except (
        OSError,
        TypeError,
        ValueError,
        UnicodeError,
        RecursionError,
        OverflowError,
    ) as exc:
        print(
            f"CASMI_NEUTRAL_LOSS_HOLD: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
