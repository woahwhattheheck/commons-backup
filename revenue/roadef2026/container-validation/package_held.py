#!/usr/bin/env python3
"""Package the tested frozen context and method PDF with submission still held.

The ZIP contains the unchanged build context at its root, method.pdf, the frozen
candidate declaration and an inventory. Runtime inputs and communication drafts
are not package payloads. PDF visual review remains pending in this receipt.
"""
import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

from pypdf import PdfReader


FROZEN_COMMIT = "6feb9c0566b8f203c5d1a2ffdfbf1cb6d11be055"
FROZEN_NAME = "FROZEN-CANDIDATE-20260908.json"
FROZEN_SHA256 = "6a5127cbf56305cfa46e5f26b52b4105c6c8b8aaa4ce12ed7643a076f82c9c51"
CANDIDATE_SHA256 = "758977095f8f34263bbcd9ed043ac4ab7943f04f65fae530c78ee64787c34f8f"
EXPECTED_CASES = {(instance, case) for instance in ("B01", "B11", "B12")
                  for case in ("normal-30s", "term-after-checkpoint")}
MANIFEST_NAME = "HELD-MANIFEST.json"


def sha256(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def identity(path):
    return {"bytes": path.stat().st_size, "sha256": sha256(path)}


def checked_path(name):
    if not isinstance(name, str):
        raise ValueError(f"Invalid manifest member path: {name!r}")
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or
            ".." in path.parts or "\\" in name or path.as_posix() != name):
        raise ValueError(f"Invalid manifest member path: {name!r}")
    return path.as_posix()


def verify_file(path, expected):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular retained file: {path}")
    actual = identity(path)
    if any(actual[key] != expected[key] for key in ("bytes", "sha256") if key in expected):
        raise ValueError(f"Retained file identity differs: {path}")
    return actual


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def verify_context(work, preparation, frozen):
    context = work / "context"
    context_manifest = context / "source-manifest.json"
    verify_file(context_manifest, {"sha256": preparation["context_manifest_sha256"]})
    manifest = read_json(context_manifest)
    payload, records = {}, {}
    for row in manifest["files"]:
        name = checked_path(row["path"])
        if name in records or name == "source-manifest.json":
            raise ValueError(f"Duplicate/self-listed source manifest member: {name}")
        records[name] = verify_file(context / name, row)
        payload[name] = context / name
    if any(path.is_symlink() for path in context.rglob("*")):
        raise ValueError("Build context contains a symbolic link")
    actual = {path.relative_to(context).as_posix() for path in context.rglob("*") if path.is_file()}
    if actual != set(records) | {"source-manifest.json"}:
        raise ValueError("Context inventory contains missing or unmanifested files")
    candidate_path = "sources/candidate/main.cpp"
    candidate = frozen["candidate_source"]
    verify_file(context / candidate_path, {"bytes": candidate["result_bytes"],
                                           "sha256": CANDIDATE_SHA256})
    if (candidate["result_sha256"] != CANDIDATE_SHA256 or
            preparation["candidate"]["used_sha256"] != CANDIDATE_SHA256 or
            records[candidate_path]["sha256"] != CANDIDATE_SHA256):
        raise ValueError("Candidate source differs from the frozen composition")
    prepared_runtime = {row["path"]: row for row in preparation["runtime_files"]}
    for row in frozen["runtime_files"]:
        prepared = prepared_runtime[row["path"]]
        name = checked_path(prepared["context_path"])
        if (prepared["commit"] != row["commit"] or prepared["used_sha256"] != row["sha256"] or
                records[name]["sha256"] != row["sha256"]):
            raise ValueError(f"Context runtime differs from frozen publication: {name}")
        verify_file(context / name, row)
    payload["source-manifest.json"] = context_manifest
    return payload


def verify_documents(work, frozen):
    documentation = frozen["documentation"]
    source = work / checked_path(documentation["method_source"])
    generator = work / checked_path(documentation["generator"])
    source_identity = verify_file(source, {"bytes": documentation["method_bytes"],
                                            "sha256": documentation["method_sha256"]})
    generator_identity = verify_file(generator, {"bytes": documentation["generator_bytes"],
                                                   "sha256": documentation["generator_sha256"]})
    pdf = work / "method.pdf"
    verify_file(pdf, {})
    reader = PdfReader(pdf)
    if reader.is_encrypted or len(reader.pages) != 2:
        raise ValueError("Method PDF must be unencrypted and contain exactly two pages")
    return {"source": {"path": source.name, "commit": FROZEN_COMMIT, **source_identity},
            "generator": {"path": generator.name, "commit": FROZEN_COMMIT, **generator_identity},
            "pdf": {"payload_path": "method.pdf", "pages": 2},
            "visual_review": {"status": "pending", "scope": "Final Actions PDF must be rendered and both pages inspected before delivery"},
            "packaging_pypdf_version": importlib.metadata.version("pypdf")}


def require_comparison(report, winners):
    rows = report["instances"]
    if (len(rows) != 1 or rows[0]["winner"] not in winners or
            rows[0].get("left_valid") is not True or rows[0].get("right_valid") is not True):
        raise ValueError("Retained official-vector comparison does not support the required result")


def verify_execution(work, results, preparation):
    runtime_path = results / "RESULTS.json"
    build_path = work / "build-evidence" / "RESULTS.json"
    runtime, build = read_json(runtime_path), read_json(build_path)
    if runtime.get("passed") is not True or build.get("passed") is not True:
        raise ValueError("Both actual runtime validation and capped image build must have passed")
    image = runtime["image_id"]
    if build["built_image_id"] != image:
        raise ValueError("Runtime image differs from the capped build result")
    if (runtime["preparation_sha256"] != sha256(work / "PREPARATION.json") or
            build["source_manifest_sha256"] != preparation["context_manifest_sha256"]):
        raise ValueError("Execution receipts differ from the staged preparation")
    if (build.get("requested_memory_bytes") != 4 * 1024 ** 3 or
            build.get("requested_memory_swap_bytes") != 4 * 1024 ** 3 or
            build["before"].get("cap_confirmed") is not True or
            build["after"].get("cap_confirmed") is not True or
            build.get("compiler_cgroup_inheritance_confirmed") is not True or
            build.get("context_identity_unchanged") is not True):
        raise ValueError("Build receipt has inconsistent compiler resource or context checks")
    if (runtime.get("runtime_source_identity_verified") is not True or
            runtime.get("input_hashes_unchanged") is not True or
            runtime.get("planned_cases") != 6 or len(runtime["cases"]) != 6 or
            {(row["instance"], row["case"]) for row in runtime["cases"]} != EXPECTED_CASES):
        raise ValueError("Runtime evidence must contain exactly the six planned instance/case pairs")
    if (runtime["cleanup"].get("complete") is not True or runtime["cleanup"].get("forced_running") or
            runtime["cleanup"].get("owned_containers_remaining") or build["cleanup"].get("complete") is not True):
        raise ValueError("Build/runtime cleanup did not complete")
    probe_path = results / "image-runtime.json"
    probe = read_json(probe_path)
    if probe["files"]["source-manifest.json"] != preparation["context_manifest_sha256"]:
        raise ValueError("Actual image source manifest differs from the packaged context")
    for row in preparation["runtime_files"]:
        if row["path"] in ("run.sh", "supervisor.py", "compare_checker.py"):
            if probe["files"][row["path"]] != row["used_sha256"]:
                raise ValueError("Actual image runtime differs from the frozen staged files")
    cases = []
    for row in runtime["cases"]:
        directory = results / checked_path(row["output_directory"])
        case_result = directory / "RESULT.json"
        if read_json(case_result) != row or row.get("passed") is not True or row["image_id"] != image:
            raise ValueError("Per-case evidence differs from the complete passing runtime receipt")
        if row.get("forced_stops_before_next_case") or row.get("case_cleanup_errors"):
            raise ValueError("A runtime case required forced cleanup")
        if row["portfolio_budget_seconds"] != (90 if row["case"].startswith("term") else 30):
            raise ValueError("Runtime smoke budget differs from the planned case")
        require_comparison(row["selected_recheck"], {"tie"})
        if row["case"].startswith("term"):
            seconds = row["signal_to_observed_exit_seconds"]
            if (row["signal_observation_window_seconds"] != 10 or
                    not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 <= seconds <= 10):
                raise ValueError("Accepted-checkpoint SIGTERM did not exit within the requested ten seconds")
            require_comparison(row["checkpoint_preservation"], {"right", "tie"})
        solution = directory / "solution.json"
        checker = directory / "solution-checker-6.json"
        verify_file(solution, {"sha256": row["final_solution_sha256"]})
        verify_file(checker, {"sha256": row["final_checker_sha256"]})
        cases.append({"instance": row["instance"], "case": row["case"], "passed": True,
                      "result_path": f"{directory.name}/RESULT.json", "result_identity": identity(case_result),
                      "solution_identity": identity(solution), "official_checker_identity": identity(checker),
                      "observed_wall_seconds": row["observed_wall_seconds"],
                      "signal_to_observed_exit_seconds": row.get("signal_to_observed_exit_seconds")})
    return {"image_id": image, "runtime_results": {"path": "RESULTS.json", **identity(runtime_path)},
            "build_results": {"path": "build-evidence/RESULTS.json", **identity(build_path)},
            "image_probe": {"path": "image-runtime.json", **identity(probe_path)},
            "cases": cases, "runtime_cleanup_complete": True, "build_cleanup_complete": True,
            "build_memory_limit_bytes": 4 * 1024 ** 3,
            "build_memory_peak_bytes": build["after"]["cgroup"].get("memory_peak_bytes")}


def workflow_identity():
    run_id, attempt, event_sha = (os.environ.get(name, "") for name in
                                 ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA"))
    if not run_id.isdigit() or not attempt.isdigit() or not re.fullmatch(r"[0-9a-f]{40}", event_sha):
        raise ValueError("Workflow run, attempt or commit metadata is missing or malformed")
    checkout = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                       cwd=Path(__file__).resolve().parent, text=True, timeout=10).strip()
    if checkout != event_sha:
        raise ValueError("Validation checkout differs from the workflow commit")
    return {"run_id": run_id, "run_attempt": attempt, "workflow_sha": event_sha,
            "validation_checkout": checkout,
            "run_url": f"https://github.com/woahwhattheheck/commons/actions/runs/{run_id}",
            "package_script_sha256": sha256(Path(__file__).resolve())}


def package(work, results, output):
    frozen_path = work / FROZEN_NAME
    verify_file(frozen_path, {"sha256": FROZEN_SHA256})
    frozen = read_json(frozen_path)
    if frozen.get("submission_hold") is not True:
        raise ValueError("Frozen declaration must retain the submission hold")
    preparation_path = work / "PREPARATION.json"
    preparation = read_json(preparation_path)
    if (preparation["frozen"]["sha256"] != FROZEN_SHA256 or
            preparation["frozen"]["commit"] != FROZEN_COMMIT or preparation["frozen"]["manifest"] != frozen):
        raise ValueError("Staged preparation differs from the exact frozen declaration")
    if (preparation["configuration"] != frozen["configuration"] or
            preparation["preparer"]["commit"] != frozen["preparer"]["commit"] or
            preparation["preparer"]["used_sha256"] != frozen["preparer"]["sha256"]):
        raise ValueError("Staged configuration or preparer differs from the frozen declaration")
    payload = verify_context(work, preparation, frozen)
    documents = verify_documents(work, frozen)
    execution = verify_execution(work, results, preparation)
    workflow = workflow_identity()
    additions = {"method.pdf": work / "method.pdf", FROZEN_NAME: frozen_path}
    if set(payload) & (set(additions) | {MANIFEST_NAME}):
        raise ValueError("Context files collide with held-package documentation or inventory")
    payload.update(additions)
    inventory = [{"path": name, **identity(path)} for name, path in sorted(payload.items())]
    # Recheck after reading execution evidence; the inventory must still describe
    # the exact context originally checked, not a changed source tree.
    verify_context(work, preparation, frozen)
    verify_documents(work, frozen)
    manifest = {"schema_version": 1, "candidate_id": frozen["candidate_id"], "team_id": frozen["team_id"],
                "submission_hold": True, "submitted": False, "status": "HELD_PENDING_PDF_VISUAL_REVIEW",
                "workflow": workflow, "frozen_manifest": {"payload_path": FROZEN_NAME, "commit": FROZEN_COMMIT},
                "source": {"candidate_path": "sources/candidate/main.cpp", "candidate_sha256": CANDIDATE_SHA256,
                           "context_manifest_path": "source-manifest.json", "preparation_identity": identity(preparation_path),
                           "runtime_files": preparation["runtime_files"], "preparer": preparation["preparer"],
                           "archives": preparation["archives"], "configuration": preparation["configuration"]},
                "documentation": documents, "validation": execution,
                "inventory_scope": "Every ZIP payload file exactly once; HELD-MANIFEST.json excludes itself",
                "files": inventory}
    manifest_path = output / MANIFEST_NAME
    write_json(manifest_path, manifest)
    archive = output / f"HELD-{frozen['candidate_id']}.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as stream:
        for name, path in sorted(payload.items()):
            stream.write(path, arcname=name)
        stream.write(manifest_path, arcname=MANIFEST_NAME)
    # Verify the packaged bytes, including hidden source files, before publishing
    # a successful package receipt. No source file is rewritten by this operation.
    with zipfile.ZipFile(archive) as stream:
        names = stream.namelist()
        if len(names) != len(set(names)) or set(names) != set(payload) | {MANIFEST_NAME}:
            raise ValueError("ZIP member inventory differs from the held manifest")
        for row in inventory:
            raw = stream.read(row["path"])
            if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
                raise ValueError(f"Packaged bytes differ from tested payload: {row['path']}")
        if stream.read(MANIFEST_NAME) != manifest_path.read_bytes():
            raise ValueError("Packaged manifest differs from retained manifest")
    pdf_copy = output / "method.pdf"
    with pdf_copy.open("xb") as stream:
        stream.write((work / "method.pdf").read_bytes())
    verify_file(pdf_copy, next(row for row in inventory if row["path"] == "method.pdf"))
    return {"passed": True, "candidate_id": frozen["candidate_id"], "submission_hold": True,
            "submitted": False, "visual_review": "pending", "workflow": workflow,
            "archive": {"path": archive.name, **identity(archive)},
            "manifest": {"path": MANIFEST_NAME, **identity(manifest_path)},
            "method_pdf": {"path": "method.pdf", "pages": 2, **identity(pdf_copy)},
            "payload_files": len(inventory), "archive_files": len(inventory) + 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(args.work.resolve() / "context"):
        parser.error("Package output must be separate from the tested source context.")
    output.mkdir(parents=True, exist_ok=False)
    report = {"passed": False, "submission_hold": True, "submitted": False, "visual_review": "pending"}
    try:
        report = package(args.work.resolve(strict=True), args.results.resolve(strict=True), output)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    write_json(output / "RESULTS.json", report)
    print(json.dumps({"passed": report["passed"], "result": str(output / "RESULTS.json"),
                      "archive": report.get("archive")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
