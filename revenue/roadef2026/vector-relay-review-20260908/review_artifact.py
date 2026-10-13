#!/usr/bin/env python3
"""Read-only verification of the retained ROADEF rank-traversal experiment.

Uses only the Python standard library. Does not extract or execute archive code,
run a solver/checker, access a network, or modify the supplied artifact.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import stat
import zipfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath

EXPECTED_SHA = "c6b754563dcafb6a33a1c7ffc312efdb0053f784ca783f897e54bf927b91a62f"
EXPECTED_SIZE = 3973104
ROOT = "/home/runner/work/_temp/roadef-rank-traversal/"
ORDER = [("setA-04", "base_e801"), ("setA-04", "new_d85"),
         ("setA-14", "new_d85"), ("setA-14", "base_e801")]

def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result

def reject_constant(value: str):
    raise ValueError(f"Nonfinite JSON number: {value}")

def read_json(z: zipfile.ZipFile, name: str):
    return json.loads(z.read(name), parse_float=Decimal,
                      parse_constant=reject_constant, object_pairs_hook=unique_object)

def compare_vectors(old: list, new: list) -> dict:
    require(len(old) == len(new), "Vector lengths differ")
    differences = [(i + 1, o, n) for i, (o, n) in enumerate(zip(old, new)) if o != n]
    return {"count": len(old), "winner": "new" if new < old else "base" if old < new else "tie",
            "first_difference": None if not differences else {
                "rank": differences[0][0], "base": differences[0][1], "new": differences[0][2]},
            "changed_ranks": len(differences),
            "improved_ranks": sum(n < o for _, o, n in differences),
            "worsened_ranks": sum(n > o for _, o, n in differences),
            "base_maximum": old[0], "new_maximum": new[0]}

def verify_manifest(z: zipfile.ZipFile, prefix: str = "") -> dict:
    name = prefix + "ARTIFACT-MANIFEST.json"
    m = read_json(z, name)
    seen = {name}
    for row in m["files"]:
        p = PurePosixPath(row["path"])
        require(not p.is_absolute() and ".." not in p.parts, "Unsafe manifest path")
        member = prefix + row["path"]
        require(member not in seen, f"Duplicate manifest row: {member}")
        seen.add(member)
        b = z.read(member)
        require(len(b) == row["bytes"] and digest(b) == row["sha256"],
                f"Manifest size/hash mismatch: {member}")
    actual = {i.filename for i in z.infolist() if not i.is_dir() and i.filename.startswith(prefix)}
    require(seen == actual, f"Manifest coverage mismatch under {prefix!r}")
    return {"verified_files": len(m["files"]), "sha256": digest(z.read(name)),
            "missing": [], "unlisted": [], "mismatches": []}

def record_match(z: zipfile.ZipFile, record: dict, expected: str | None = None) -> None:
    absolute = record["path"]
    require(absolute.startswith(ROOT), f"Unexpected recorded root: {absolute}")
    member = absolute[len(ROOT):]
    require(expected is None or member == expected, f"Unexpected recorded member: {member}")
    b = z.read(member)
    require(record["bytes"] == len(b) and record["sha256"] == digest(b), f"Record mismatch: {member}")

def clean_process(z: zipfile.ZipFile, process: dict) -> dict:
    require(process["returncode"] == 0, "Nonzero process exit")
    require(not process["unexpected_descendants_after_exit"], "Unexpected descendants")
    require(not process["descendants_remaining_after_cleanup"], "Surviving descendants")
    for label in ("stdout", "stderr"):
        record_match(z, process[label])
    return {k: process[k] for k in ["returncode", "started_utc", "finished_utc", "wall_seconds",
            "guard", "sampled_peak_tree_rss_kib", "rss_scope", "unresolved_root_samples",
            "unexpected_descendants_after_exit", "descendants_remaining_after_cleanup"]}

def review(path: Path) -> dict:
    raw = path.read_bytes()
    require(len(raw) == EXPECTED_SIZE and digest(raw) == EXPECTED_SHA, "Wrong retained artifact bytes")
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        require(len(infos) == len(set(z.namelist())), "Duplicate ZIP member")
        require(sum(i.file_size for i in infos) < 1024**3, "Unexpectedly large uncompressed input")
        for i in infos:
            p = PurePosixPath(i.filename)
            require(not p.is_absolute() and ".." not in p.parts and "\\" not in i.filename,
                    "Unsafe ZIP path")
            require(not stat.S_ISLNK(i.external_attr >> 16), "ZIP symlink")
        manifests = {"outer": verify_manifest(z), "prior": verify_manifest(z, "prior/")}
        run = read_json(z, "RUN.json")
        require(run["GITHUB_RUN_ID"] == "34215340899", "Run mismatch")
        require(run["GITHUB_RUN_ATTEMPT"] == "1", "Run attempt mismatch")
        require(run["ordered_arms"] == [f"{c.removeprefix('set').replace('-', '')} {a}" for c, a in ORDER], "Declared arm order mismatch")
        integration = read_json(z, "integration-receipt.json")
        for field, member in [("base", "prior/new.cpp"), ("output", "new.cpp"), ("patch", "generated.patch")]:
            require(integration[field]["sha256"] == digest(z.read(member)), f"Integration {field} mismatch")
        arms, vectors, raw_checks = {}, {}, {}
        last_finish = None
        for case, arm in ORDER:
            prefix = f"results/{case}/{arm}/"
            r = read_json(z, prefix + "result.json")
            p = read_json(z, prefix + "portfolio.json")
            require(r["case"] == case and r["arm"] == arm and r["cold_start"] is True, "Arm identity mismatch")
            require(r["complete"] and r["receipt_matches_solution"] and r["precisions_agree_on_keys_and_cost"], "Incomplete arm")
            new = arm == "new_d85"
            for field, member in [("candidate_binary", "new-candidate" if new else "prior/new-candidate"),
                                  ("candidate_source", "new.cpp" if new else "prior/new.cpp"),
                                  ("solution", prefix + "solution.json"),
                                  ("rank_report_file", prefix + "rank-report.json")]:
                record_match(z, r[field], member)
            for inp in r["input_files"]:
                record_match(z, inp)
            c = r["controls"]
            for key, value in {"PORTFOLIO_SECONDS": "585", "FLEET_POLISH_AFTER_EXHAUSTION": "1",
                               "FLEET_RANK1_PASSES": "16", "FLEET_RANK1_DEMANDS": "32",
                               "FLEET_RANK1_PAIR_NODES": "24", "OMP_NUM_THREADS": "1"}.items():
                require(c[key] == value, f"Control changed: {key}")
            require(c.get("FLEET_POLISH_RANK_TRAVERSAL") == ("1" if new else None), "Traversal control mismatch")
            require("CLOUD_INITIAL_SOLUTION" not in c, "Resumed rather than cold arm")
            require(p["status"] == "complete" and p["validated"] and p["selected_lane"] == "candidate", "Unexpected selection")
            require(p["signal_received"] is None and all(x["returncode"] == 0 for x in p["lanes"]), "Signal/lane failure")
            require(p["solution_sha256"] == digest(z.read(prefix + "solution.json")), "Receipt output mismatch")
            require(p["deadline_seconds"] == 585 and p["search_allowance_seconds"] == 565, "Allowance changed")
            require(p["wall_seconds"] < p["deadline_seconds"], "Deadline exceeded")
            proc = clean_process(z, r["process"])
            require(proc["guard"] == {"term_after_seconds": 590, "kill_after_term_seconds": 10}, "Outer guard mismatch")
            start = datetime.fromisoformat(proc["started_utc"])
            require(last_finish is None or start >= last_finish, "Overlapping arm/checker invocations")
            last_finish = datetime.fromisoformat(proc["finished_utc"])
            check_rows, coordinate_sets, costs = {}, [], []
            for prec in (6, 12):
                obj = read_json(z, prefix + f"checker-{prec}.stdout")
                cp = clean_process(z, read_json(z, prefix + f"checker-{prec}.process.json"))
                require(datetime.fromisoformat(cp["started_utc"]) >= last_finish, "Checker overlap")
                last_finish = datetime.fromisoformat(cp["finished_utc"])
                require(obj["valid"] is True, "Invalid checked solution")
                rows = obj["saturations"]
                coords = [(x["t"], x["from"], x["to"]) for x in rows]
                require(len(coords) == len(set(coords)), "Duplicate saturation coordinate")
                values = [Decimal(x["sat"]) for x in rows]
                require(all(v.is_finite() and v >= 0 for v in values), "Invalid saturation value")
                values.sort(reverse=True)
                require(len(values) == (500 if case == "setA-04" else 2216), "Wrong full-vector size")
                vectors[(case, arm, prec)] = values
                raw_checks[(case, arm, prec)] = obj
                coordinate_sets.append(set(coords)); costs.append(obj["total_cost"])
                check_rows[str(prec)] = {"valid": obj["valid"], "vector_length": len(values),
                    "total_cost_diagnostic": obj["total_cost"], "process": cp,
                    "raw_stdout_sha256": digest(z.read(prefix + f"checker-{prec}.stdout"))}
            require(coordinate_sets[0] == coordinate_sets[1] and costs[0] == costs[1], "Cross-precision mismatch")
            events = [x["event"] for x in r["phase_readout"]["events"]]
            require(not r["phase_readout"]["malformed_events"], "Malformed phase events")
            beginning = [e for e in events if e["event"] == "begin"]
            ending = [e for e in events if e["event"] == "end"]
            require(len(beginning) == len(ending) == 1 and beginning[0]["reason"] == "natural_exhaustion", "Phase boundary mismatch")
            passes = r["rank_report"]["passes"]
            require(sum(x["attempts"] for x in passes) == ending[0]["attempted"], "Attempt accounting mismatch")
            require(sum(x["accepted"] for x in passes) == ending[0]["accepted"], "Accept accounting mismatch")
            arms[f"{case}/{arm}"] = {"solution_sha256": p["solution_sha256"], "selected_lane": p["selected_lane"],
                "process": proc, "portfolio_wall_seconds": p["wall_seconds"], "checks": check_rows,
                "source_sha256": r["candidate_source"]["sha256"], "binary_sha256": r["candidate_binary"]["sha256"],
                "lane_exit_codes": {x["name"]: x["returncode"] for x in p["lanes"]},
                "phase_begin": beginning[0], "phase_end": ending[0], "pass_count": len(passes),
                "maximum_selected_rank": max(x.get("selected_rank", 1) for x in passes),
                "rank_stop": [e for e in events if e["event"] == "rank_stop"],
                "sampled_portfolio_rss_kib": p["peak_sampled_process_rss_kib"],
                "resource_scope": p["memory_measurement"],
                "runner_observation": {k: r["process"]["limits_before"][k] for k in ["logical_cpus", "affinity", "cpu_max", "memory_max", "scope"]}}
        comparisons, prior_parity = {}, {}
        for case in ("setA-04", "setA-14"):
            comparisons[case] = {}
            for prec in (6, 12):
                old, new = (raw_checks[(case, arm, prec)] for arm in ("base_e801", "new_d85"))
                require({(x['t'],x['from'],x['to']) for x in old['saturations']} ==
                        {(x['t'],x['from'],x['to']) for x in new['saturations']}, "Arm coordinate sets differ")
                comparisons[case][str(prec)] = compare_vectors(vectors[(case,"base_e801",prec)], vectors[(case,"new_d85",prec)])
            old_bytes = z.read(f"prior/results/{case}/new/solution.json")
            current_base = z.read(f"results/{case}/base_e801/solution.json")
            prior_parity[case] = {"solution_byte_identical": old_bytes == current_base,
                                 "prior_sha256": digest(old_bytes), "current_base_sha256": digest(current_base)}
        return {"schema": "read-only-roadef-rank-review-v1", "review_type": "retained raw evidence; zero solver/checker executions",
            "artifact": {"id": 10051660766, "bytes": len(raw), "sha256": digest(raw), "zip_members": len(infos)},
            "run": run, "manifests": manifests, "arms": arms, "comparisons": comparisons,
            "base_parity_with_prior_cold_outputs": prior_parity,
            "recorded_vector_strings": {f"{c}/{a}/{p}": [str(v) for v in values] for (c,a,p),values in vectors.items()},
            "scope_limits": ["Two existing cold pairs; not hidden-instance or fleet-wide performance.",
                             "6- and 12-decimal outputs compared independently without rounding.",
                             "Resource figures are sampled/observed; unavailable quota fields remain unknown.",
                             "No new experiment, publication, promotion, submission, or Slack message performed."]}

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), "Refusing to overwrite an existing review")
    report = review(args.artifact)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, allow_nan=False)
        f.write("\n")
    print(json.dumps({"status": "verified", "manifest_files": report["manifests"]["outer"]["verified_files"],
                      "comparisons": report["comparisons"]}, default=str))

if __name__ == "__main__":
    main()
