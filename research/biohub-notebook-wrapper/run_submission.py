#!/usr/bin/env python3
"""Offline Biohub Kaggle notebook bootstrap.

Targets royerlab/kaggle-cell-tracking-competition commit
075fc5f5a52d11077f9dc2b074644618f26939e2. It never downloads data or
packages, never submits to Kaggle, and keeps hidden dataset names only in
transient files under --work-dir.

Runtime sequence: discover test/*.zarr -> write fold-0 split manifest -> run the
starter predictor ONCE -> verify the exact GEFF set -> geffs_to_csv ->
organizer-compatible Commons validation -> strict-lineage diagnostic -> receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

STARTER_COMMIT = "075fc5f5a52d11077f9dc2b074644618f26939e2"
PINNED_ENTRYPOINT_BLOBS = {
    "scripts/predict_unet_transformer.py": "b7372c6177d4ae79a693e5622e96e0af19a308b9",
    "scripts/geffs_to_csv.py": "9d8effd56d238e96d4586e223379d649b46cfbc2",
}
TEST_DIR = Path("/kaggle/input/competitions/biohub-cell-tracking-during-development/test")
WORK_DIR = Path("/kaggle/working")
METHOD = "unet_transformer"
USER = "biohub_submission"


class BootstrapError(RuntimeError):
    pass


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def verify_blob_map(root: Path, expected: dict[str, str]) -> dict[str, str]:
    actual: dict[str, str] = {}
    for relative, expected_sha in expected.items():
        path = root / relative
        if not path.is_file():
            raise BootstrapError(f"missing pinned starter entrypoint: {relative}")
        actual_sha = git_blob_sha1(path)
        if actual_sha != expected_sha:
            raise BootstrapError(
                f"pinned starter entrypoint mismatch: {relative} "
                f"expected={expected_sha} actual={actual_sha}"
            )
        actual[relative] = actual_sha
    return actual


def verify_starter_entrypoints(starter: Path) -> dict[str, str]:
    return verify_blob_map(starter, PINNED_ENTRYPOINT_BLOBS)


def discover(test_dir: Path) -> list[str]:
    if not test_dir.is_dir():
        raise BootstrapError(f"missing test directory: {test_dir}")
    names = sorted(p.name for p in test_dir.glob("*.zarr"))
    if not names:
        raise BootstrapError("no *.zarr datasets found")
    if len(names) != len(set(names)) or any(n != n.strip() or not n for n in names):
        raise BootstrapError("invalid runtime dataset names")
    return names


def write_manifests(work: Path, names: list[str]) -> tuple[Path, Path]:
    work.mkdir(parents=True, exist_ok=True)
    splits = work / "biohub_runtime_splits.json"
    expected = work / "biohub_expected_test_names.txt"
    splits.write_text(
        json.dumps([{"train": [], "val": [], "test": names}], separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    expected.write_text("".join(f"{name}\n" for name in names), encoding="utf-8")
    return splits, expected


def command_plan(
    python: str,
    starter: Path,
    test_dir: Path,
    splits: Path,
    weights: Path,
    validator: Path,
    work: Path,
    method: str,
    user: str,
    batch: int,
    use_ilp: bool,
) -> dict[str, list[str]]:
    submission = work / "submission.csv"
    pred_dir = starter / "predictions" / user / method / "split_0"
    predict = [
        python, str(starter / "scripts" / "predict_unet_transformer.py"),
        "--data-dir", str(test_dir), "--splits", str(splits), "--split", "0",
        "--weights", str(weights), "--method", method, "--unet-batch-size", str(batch),
    ]
    if use_ilp:
        predict.append("--use-ilp")
    return {
        "predict": predict,
        "convert": [
            python, str(starter / "scripts" / "geffs_to_csv.py"),
            "--in-dir", str(pred_dir), "--csv", str(submission),
        ],
        "organizer": [
            python, str(validator), str(submission),
            "--expected-datasets", str(work / "biohub_expected_test_names.txt"),
            "--organizer-compatible",
        ],
        "strict": [
            python, str(validator), str(submission),
            "--expected-datasets", str(work / "biohub_expected_test_names.txt"),
            "--strict-lineage",
        ],
    }


def verify_geffs(starter: Path, user: str, method: str, names: list[str]) -> dict[str, object]:
    pred_dir = starter / "predictions" / user / method / "split_0"
    actual = sorted(p.name for p in pred_dir.glob("*.geff")) if pred_dir.is_dir() else []
    expected = sorted(f"{name}.geff" for name in names)
    if actual != expected:
        raise BootstrapError(f"GEFF set mismatch: expected={len(expected)} actual={len(actual)}")
    return {"count": len(actual), "name_sha256": digest_bytes("\n".join(actual).encode())}


def run(cmd: list[str], starter: Path, env: dict[str, str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=starter, env=env, check=check, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        test = root / "test"
        test.mkdir()
        (test / "b.zarr").mkdir()
        (test / "a.zarr").mkdir()
        names = discover(test)
        assert names == ["a.zarr", "b.zarr"]
        splits, _ = write_manifests(root / "work", names)
        assert json.loads(splits.read_text()) == [{"train": [], "val": [], "test": names}]
        plan = command_plan(
            "python", root / "starter", test, splits, root / "w.pth",
            root / "validator.py", root / "work", METHOD, USER, 4, False,
        )
        assert plan["predict"].count(str(root / "starter" / "scripts" / "predict_unet_transformer.py")) == 1
        assert "--debug-video" not in plan["predict"]
        assert plan["predict"][plan["predict"].index("--split") + 1] == "0"
        pred = root / "starter" / "predictions" / USER / METHOD / "split_0"
        pred.mkdir(parents=True)
        (pred / "a.zarr.geff").mkdir()
        (pred / "b.zarr.geff").mkdir()
        assert verify_geffs(root / "starter", USER, METHOD, names)["count"] == 2

        entry = root / "entry"
        (entry / "scripts").mkdir(parents=True)
        fake = entry / "scripts" / "predict.py"
        fake.write_text("print('pinned')\n", encoding="utf-8")
        fake_sha = git_blob_sha1(fake)
        assert verify_blob_map(entry, {"scripts/predict.py": fake_sha}) == {"scripts/predict.py": fake_sha}
        fake.write_text("print('changed')\n", encoding="utf-8")
        try:
            verify_blob_map(entry, {"scripts/predict.py": fake_sha})
        except BootstrapError:
            pass
        else:
            raise AssertionError("starter blob mismatch was not rejected")
    print("SELF_TEST PASS cases=6")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--starter-dir", type=Path)
    ap.add_argument("--weights", type=Path)
    ap.add_argument("--validator", type=Path)
    ap.add_argument("--test-dir", type=Path, default=TEST_DIR)
    ap.add_argument("--work-dir", type=Path, default=WORK_DIR)
    ap.add_argument("--method", default=METHOD)
    ap.add_argument("--user-label", default=USER)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--unet-batch-size", type=int, default=4)
    ap.add_argument("--use-ilp", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.starter_dir or not args.weights or not args.validator:
        ap.error("--starter-dir, --weights, and --validator are required unless --self-test")
    if args.unet_batch_size < 1:
        raise BootstrapError("--unet-batch-size must be >= 1")
    if any(not v or v != v.strip() or "/" in v or "\\" in v for v in (args.method, args.user_label)):
        raise BootstrapError("method/user-label must be simple path tokens")

    names = discover(args.test_dir)
    splits, expected = write_manifests(args.work_dir, names)
    plan = command_plan(
        args.python, args.starter_dir, args.test_dir, splits, args.weights, args.validator,
        args.work_dir, args.method, args.user_label, args.unet_batch_size, args.use_ilp,
    )
    name_sha = digest_bytes("\n".join(names).encode())
    plan_file = args.work_dir / "biohub_command_plan.json"
    receipt_file = args.work_dir / "biohub_submission_receipt.json"
    plan_file.write_text(
        json.dumps(
            {
                "starter_commit": STARTER_COMMIT,
                "pinned_entrypoint_blobs": PINNED_ENTRYPOINT_BLOBS,
                "dataset_count": len(names),
                "dataset_name_sha256": name_sha,
                "commands": plan,
            },
            indent=2, sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    if args.dry_run:
        receipt = {
            "starter_commit": STARTER_COMMIT, "dry_run": True,
            "pinned_entrypoint_blobs": PINNED_ENTRYPOINT_BLOBS,
            "dataset_count": len(names), "dataset_name_sha256": name_sha,
            "split_manifest_sha256": digest_file(splits),
        }
        receipt_file.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"DRY_RUN datasets={len(names)} name_sha256={name_sha} plan={plan_file}")
        return 0

    required = [args.weights, args.validator]
    if any(not p.exists() for p in required):
        raise BootstrapError("one or more required local inputs are missing")
    starter_entrypoint_blobs = verify_starter_entrypoints(args.starter_dir)

    env = os.environ.copy()
    env["USER"] = args.user_label
    env["USERNAME"] = args.user_label

    predicted = run(plan["predict"], args.starter_dir, env)
    print(predicted.stdout, end="")
    geff = verify_geffs(args.starter_dir, args.user_label, args.method, names)
    converted = run(plan["convert"], args.starter_dir, env)
    print(converted.stdout, end="")
    organizer = run(plan["organizer"], args.starter_dir, env)
    print(organizer.stdout, end="")
    if "PASS " not in organizer.stdout:
        raise BootstrapError("organizer-compatible validator emitted no PASS receipt")
    strict = run(plan["strict"], args.starter_dir, env, check=False)
    print(strict.stdout, end="")

    submission = args.work_dir / "submission.csv"
    receipt = {
        "starter_commit": STARTER_COMMIT, "dry_run": False,
        "starter_entrypoint_blobs": starter_entrypoint_blobs,
        "dataset_count": len(names), "dataset_name_sha256": name_sha,
        "split_manifest_sha256": digest_file(splits),
        "prediction": geff,
        "submission_sha256": digest_file(submission),
        "organizer_validator_stdout": organizer.stdout.strip(),
        "strict_lineage_diagnostic_passed": strict.returncode == 0,
    }
    receipt_file.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"SUBMISSION_READY datasets={len(names)} submission_sha256={receipt['submission_sha256']} "
        f"strict_lineage={'PASS' if strict.returncode == 0 else 'FAIL'} receipt={receipt_file}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
