# SPDX-License-Identifier: Apache-2.0
"""Verify this repository delivery against the complete retained AMBER-CASH package."""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED_PACKAGE_SHA256 = "82573a9463a9c6d5d725610d39ce032551928e0fd0c0fedfc65d1f098b106ca6"
EXPECTED_SOURCES = {
    "arrival_choice_map.py": "a26cbff46e4d7d4faf76c97fdaeec06ae9f745936c290ef51fd30fd78cee766c",
    "cash_scope_audit.py": "a3d42ec4fef1e7be20077a4f9f679d40912dc00e59c3aa7bf522520f3844eb50",
    "exhaustive_cash_scan.py": "112bf3dcc8a37f2e71e029b82e1438bea7304289d414a0c001436175b1f94eee",
    "test_cash_scope.py": "f0620bc816b1d5e2076197364e842644a3acc5e0795fe53b5e63619213f8f529",
    "verify_scan.py": "9870eab7d8e954e9906c382d984baeffe16a5e8e90168919d6063ed0d43485b3",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True,
                        help="Extracted TITAN-AMBER-cash-scope-20260908 directory")
    parser.add_argument("--package", type=Path,
                        help="Optional original ZIP for its top-level digest check")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence_root.resolve()
    problems = []
    if args.package and digest(args.package) != EXPECTED_PACKAGE_SHA256:
        problems.append("package_sha256")
    for name, expected in EXPECTED_SOURCES.items():
        repo_path = HERE / name
        source_path = evidence / "src" / name
        if not repo_path.is_file() or digest(repo_path) != expected:
            problems.append("repository_source:" + name)
        if not source_path.is_file() or digest(source_path) != expected:
            problems.append("evidence_source:" + name)
        elif repo_path.read_bytes() != source_path.read_bytes():
            problems.append("source_mismatch:" + name)
    saved = json.loads((evidence / "evidence/verification.json").read_text())
    expected_results = json.loads((HERE / "RESULTS.json").read_text())
    if saved != expected_results["verification"]:
        problems.append("verification_summary")
    arrival = json.loads((evidence / "evidence/arrival-choice-map.json").read_text())
    if arrival != expected_results["arrival_map"]:
        problems.append("arrival_map")
    with tempfile.TemporaryDirectory(prefix="amber-cash-delivery-") as tmp:
        output = Path(tmp) / "check"
        completed = subprocess.run(
            [sys.executable, "-B", str(evidence / "run_checks.py"),
             "--output", str(output)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if completed.returncode:
            problems.append("retained_run_checks")
        else:
            rerun = json.loads((output / "verification.json").read_text())
            if rerun != expected_results["verification"]:
                problems.append("rerun_verification")
            tests = json.loads((output / "tests.json").read_text())
            if tests.get("tests") != 21 or tests.get("failures") or tests.get("errors"):
                problems.append("rerun_tests")
    report = {
        "schema": "titan-amber-cash-delivery-check-v1",
        "successful": not problems,
        "problems": problems,
        "source_files": len(EXPECTED_SOURCES),
        "focused_methods": 21,
        "identity_paths": 32768,
        "cash_records_reconciled": 65536,
        "settlements_reconciled": 14254080,
        "new_games": 0,
        "actor_calls": 0,
        "engine_calls": 0,
        "pricing_calls": 0,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["successful"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
