# SPDX-License-Identifier: Apache-2.0
"""Verify and rank the immutable AMBER-CASH 32,768-path saved bank.

The command executes no pricing, simulator, actor, game, or path generator. It
reads the already-produced shard records, verifies every manifested payload and
feeds their complete two-route cash matrix through DATE's existing paired-cash
ranker. Independent-uniform weights are an explicit caller assumption over this
saved identity-path bank, not measured probabilities or a hidden-seed model.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction
import gzip
from hashlib import sha1, sha256
import importlib.util
import json
import math
from pathlib import Path, PurePosixPath
import sys
from time import perf_counter
from types import ModuleType
from typing import Any
import zipfile

ARCHIVE_SHA256 = "82573a9463a9c6d5d725610d39ce032551928e0fd0c0fedfc65d1f098b106ca6"
ROOT = "TITAN-AMBER-cash-scope-20260908/"
MAIN = "7015cc00acfa4922"
SHEEP = "dc76e4003029ac51"
ROUTES = (MAIN, SHEEP)
DRAWS_VISIBLE = (288, 360, 432, 504, 576)


def _git_blob(body: bytes) -> str:
    return sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest()


def _identity(body: bytes) -> dict[str, Any]:
    return {"bytes": len(body), "sha256": sha256(body).hexdigest(),
            "git_blob": _git_blob(body)}


def _load_ranker(path: Path) -> tuple[ModuleType, dict[str, Any]]:
    body = path.read_bytes()
    name = "titan_full_bank_dated_scenarios"
    spec = importlib.util.spec_from_loader(name, loader=None, origin=str(path))
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        exec(compile(body, str(path), "exec"), module.__dict__)
    except BaseException:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
        raise
    return module, _identity(body)


def _member_name(name: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not name.startswith(ROOT):
        raise ValueError("archive member escapes the package root")
    return name


def _verify_archive(path: Path, expected_sha256: str) -> tuple[zipfile.ZipFile, dict, dict]:
    body_hash = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            body_hash.update(block)
    archive_sha = body_hash.hexdigest()
    if archive_sha != expected_sha256:
        raise ValueError("AMBER-CASH archive SHA256 differs")
    archive = zipfile.ZipFile(path)
    names = archive.namelist()
    if len(names) != len(set(names)):
        archive.close()
        raise ValueError("duplicate archive member")
    for name in names:
        _member_name(name)
    manifest = json.loads(archive.read(ROOT + "MANIFEST.json"))
    files = manifest.get("files")
    if not isinstance(files, dict) or len(files) != 147:
        archive.close()
        raise ValueError("expected the original 147-file manifest")
    checked = 0
    for relative, expected in files.items():
        name = _member_name(ROOT + relative)
        body = archive.read(name)
        if len(body) != expected.get("bytes") or sha256(body).hexdigest() != expected.get("sha256"):
            archive.close()
            raise ValueError("manifest payload differs: " + relative)
        checked += 1
    return archive, manifest, {
        "file_name": "TITAN-AMBER-cash-scope-20260908.zip",
        "source_file_id": "file_00000000426481f5abbc7dd2b7a6278f",
        "sha256": archive_sha,
        "manifest_payloads": checked,
        "all_manifest_payloads_match": True,
    }


def _base_report(scenarios: list[dict], ids: tuple[str, str]) -> dict:
    return {
        "selected": ids[0], "incumbent": ids[0], "changed": False,
        "reason": "no_covered_improvement", "minimum_gain": 0.0,
        "scope": "saved_nominal_fixed_quantity_own_cash_over_complete_AMBER_identity_paths",
        "scenarios": scenarios, "candidates": {},
        "minimum_cash_scope": "saved_ordered_nominal_cash_not_physical_fill_or_per_slot_causality",
        "rival_utility": None,
    }


def _compact(report: dict, objective: str) -> dict:
    result = {
        "objective": objective,
        "selected": report["selected"],
        "incumbent": report["incumbent"],
        "changed": report["changed"],
        "reason": report["reason"],
        "candidate": deepcopy(report.get("candidates", {}).get(SHEEP)),
    }
    values = report.get("objective_values")
    if values:
        result["objective_values"] = {
            route: {key: value for key, value in route_values.items()
                    if key != "scenario_regret"}
            for route, route_values in values.items()
        }
    for key in ("decision_objective", "objective_arithmetic", "weight_scope",
                "regret_comparator", "eligible_routes"):
        if key in report:
            result[key] = deepcopy(report[key])
    return result


def consume(archive_path: Path, ranker_path: Path, *, expected_archive_sha256: str = ARCHIVE_SHA256) -> dict:
    started = perf_counter()
    ranker, ranker_identity = _load_ranker(ranker_path)
    archive, manifest, archive_identity = _verify_archive(archive_path, expected_archive_sha256)
    try:
        summary = json.loads(archive.read(ROOT + "evidence/full-scan/SUMMARY.json"))
        run = json.loads(archive.read(ROOT + "evidence/full-scan/RUN.json"))
        if summary.get("complete") is not True or run.get("complete") is not True:
            raise ValueError("saved AMBER scan is incomplete")
        if summary.get("identity_paths") != 32768 or summary.get("route_scenario_pairs") != 65536:
            raise ValueError("saved-bank dimensions differ")
        shard_names = sorted(
            ROOT + relative for relative in manifest["files"]
            if relative.startswith("evidence/full-scan/shards/") and relative.endswith(".jsonl.gz"))
        if len(shard_names) != 128:
            raise ValueError("expected 128 immutable scan shards")

        scenarios: list[dict] = []
        names: list[str] = []
        gains: list[Fraction] = []
        paths: list[tuple[str, ...]] = []
        next_index = 0
        route_records = 0
        for shard_name in shard_names:
            payload = gzip.decompress(archive.read(shard_name)).decode("utf-8")
            for line in payload.splitlines():
                row = json.loads(line)
                index = row.get("index")
                if type(index) is not int or index != next_index:
                    raise ValueError("missing, duplicate, or reordered identity path")
                path = row.get("path")
                if not isinstance(path, list) or len(path) != 5 or not all(isinstance(x, str) for x in path):
                    raise ValueError("identity path shape differs")
                records = row.get("rows")
                if not isinstance(records, list) or len(records) != 2:
                    raise ValueError("each identity path must contain two routes")
                indexed = {}
                for record in records:
                    route = record.get("route_id")
                    if route not in ROUTES or route in indexed:
                        raise ValueError("route identity differs or repeats")
                    final = record.get("final_marked_cash")
                    minimum = record.get("minimum_marked_cash")
                    if (isinstance(final, bool) or isinstance(minimum, bool)
                            or not isinstance(final, (int, float))
                            or not isinstance(minimum, (int, float))
                            or not math.isfinite(final) or not math.isfinite(minimum)):
                        raise ValueError("saved cash value is not finite")
                    indexed[route] = {
                        "complete": True,
                        "final_nominal_cash": float(final),
                        "minimum_nominal_cash": float(minimum),
                    }
                    route_records += 1
                if set(indexed) != set(ROUTES):
                    raise ValueError("route bank differs")
                gain = Fraction(str(indexed[SHEEP]["final_nominal_cash"])) - Fraction(
                    str(indexed[MAIN]["final_nominal_cash"]))
                if gain != Fraction(str(row.get("paired_own_cash_change"))):
                    raise ValueError("saved paired gain differs")
                name = f"identity-{index:05d}"
                scenarios.append({"name": name, "routes": indexed})
                names.append(name)
                gains.append(gain)
                paths.append(tuple(path))
                next_index += 1
        if next_index != 32768 or route_records != 65536:
            raise ValueError("saved-bank record count differs")

        robust = ranker._rank_paired(_base_report(deepcopy(scenarios), ROUTES), ROUTES, 0.0)
        regret = ranker._rank_paired(
            _base_report(deepcopy(scenarios), ROUTES), ROUTES, 0.0,
            objective="minimax_regret")
        uniform = Fraction(1, len(names))
        expected = ranker._rank_paired(
            _base_report(deepcopy(scenarios), ROUTES), ROUTES, 0.0,
            objective="expected_cash", scenario_weights={name: uniform for name in names})

        sign_counts = {
            "positive": sum(gain > 0 for gain in gains),
            "zero": sum(gain == 0 for gain in gains),
            "negative": sum(gain < 0 for gain in gains),
        }
        first_yarn = {}
        for position, visible in enumerate(DRAWS_VISIBLE):
            selected = [gain for path, gain in zip(paths, gains)
                        if "YARN_STORE" not in path[:position] and path[position] == "YARN_STORE"]
            first_yarn[str(visible)] = {
                "paths": len(selected),
                "positive": sum(gain > 0 for gain in selected),
                "zero": sum(gain == 0 for gain in selected),
                "negative": sum(gain < 0 for gain in selected),
                "minimum_paired_gain": str(min(selected)) if selected else None,
                "maximum_paired_gain": str(max(selected)) if selected else None,
            }
        expected_gain = sum(gains, Fraction(0)) / len(gains)
        if expected_gain != Fraction(-107769299, 32768):
            raise ValueError("independent-uniform expected gain differs from the completed receipt")
        if sign_counts != {"positive": 7956, "zero": 1, "negative": 24811}:
            raise ValueError("saved support sign counts differ")
        if first_yarn["360"]["positive"] != 3576 or first_yarn["360"]["negative"] != 8:
            raise ValueError("first-YARN360 counts differ")
        if (first_yarn["432"]["positive"], first_yarn["432"]["zero"],
                first_yarn["432"]["negative"]) != (284, 1, 2851):
            raise ValueError("first-YARN432 counts differ")

        return {
            "schema": "titan.amber-cash-full-bank-objectives.v1",
            "complete": True,
            "archive": archive_identity,
            "ranker": ranker_identity,
            "bank": {
                "identity_paths": len(gains),
                "route_cash_records": route_records,
                "route_ids": list(ROUTES),
                "cash_scope": run.get("scope"),
                "probabilities": None,
                "rival_utility": None,
                "physical_feasibility_established": False,
            },
            "objectives": {
                "robust": _compact(robust, "robust"),
                "minimax_regret": _compact(regret, "minimax_regret"),
                "assumed_independent_uniform_expected_cash": {
                    **_compact(expected, "expected_cash"),
                    "assumption": "independent uniform over the 32,768 explicit identity paths; not inferred or calibrated",
                    "expected_sheep_minus_main": str(expected_gain),
                    "expected_sheep_minus_main_decimal": float(expected_gain),
                },
            },
            "paired_gain": {
                "minimum": str(min(gains)),
                "maximum": str(max(gains)),
                "sign_counts": sign_counts,
                "first_yarn_visible": first_yarn,
            },
            "execution": {
                "pricing_calls": 0, "simulation_calls": 0, "actor_calls": 0,
                "game_calls": 0, "path_generation_calls": 0,
                "manifest_payloads_verified": archive_identity["manifest_payloads"],
                "original_author_ingest_and_rank_wall_seconds": 6.49,
                "publication_readback_wall_seconds": perf_counter() - started,
            },
            "limits": [
                "These are saved nominal fixed-quantity own-cash records, not physical fills or rival margin.",
                "Support signs are not game wins, and independent-uniform weights are not measured probabilities.",
                "Earlier no-buyer and first-YARN288 physical payoffs are separate and are not copied into this bank.",
                "No route is promoted and no runtime default is changed by this offline reader."
            ],
        }
    finally:
        archive.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--ranker", type=Path, default=Path(__file__).with_name("dated_scenarios.py"))
    parser.add_argument("--expected-archive-sha256", default=ARCHIVE_SHA256)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a fresh output file")
    try:
        result = consume(args.archive, args.ranker,
                         expected_archive_sha256=args.expected_archive_sha256)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "complete": result["complete"],
        "identity_paths": result["bank"]["identity_paths"],
        "objectives": {key: value["selected"] for key, value in result["objectives"].items()},
        "expected_sheep_minus_main": result["objectives"]["assumed_independent_uniform_expected_cash"]["expected_sheep_minus_main"],
        "publication_readback_wall_seconds": result["execution"]["publication_readback_wall_seconds"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
