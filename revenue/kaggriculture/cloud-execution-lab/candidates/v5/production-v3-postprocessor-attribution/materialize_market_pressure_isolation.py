#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Materialize the single-knob market-pressure isolation arm for TITAN V5."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Callable

BASELINE_ARCHIVE_SHA256 = "20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239"
BASELINE_CONFIG_SHA256 = "ba18563683125fd89d5473ddb8a5c3e9431db1787a3046f618a9e03af2cb44af"
BASELINE_MEMBER_COUNT = 92
CONFIG_PATH = "TITAN-CONFIG.json"
COMPONENT_SCHEMA = "titan-v5-staging-component/v1"
COMPONENT_ID = "market-pressure-off-isolation"
RECEIPT_SCHEMA = "titan-v5-market-pressure-isolation/v1"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _config_bytes(config: dict) -> bytes:
    return json.dumps(config, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"


def build_from_members(
    baseline: dict[str, bytes],
    pack: Callable[[dict[str, bytes]], bytes],
    *,
    expected_config_sha256: str = BASELINE_CONFIG_SHA256,
    expected_member_count: int = BASELINE_MEMBER_COUNT,
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    """Build candidate + composer artifacts from authenticated baseline members.

    ``materialize()`` is the public authority boundary and pins the exact
    production-v3 archive. The overridable expectations keep this pure builder
    testable with synthetic member maps; the CLI exposes no overrides.
    """
    if len(baseline) != expected_member_count:
        raise ValueError(f"baseline member count mismatch: {len(baseline)} != {expected_member_count}")
    original = baseline.get(CONFIG_PATH)
    if original is None:
        raise ValueError("baseline is missing TITAN-CONFIG.json")
    if digest(original) != expected_config_sha256:
        raise ValueError("baseline config identity mismatch")
    config = json.loads(original)
    if not isinstance(config, dict):
        raise ValueError("TITAN-CONFIG.json must contain an object")
    if type(config.get("market_pressure")) is not bool or config["market_pressure"] is not True:
        raise ValueError("baseline market_pressure preimage must be true")
    if type(config.get("early_capital")) is not bool or config["early_capital"] is not True:
        raise ValueError("baseline early_capital preimage must remain true for this isolation arm")

    treatment_config = dict(config)
    treatment_config["market_pressure"] = False
    treatment_config_raw = _config_bytes(treatment_config)

    treatment = dict(baseline)
    treatment[CONFIG_PATH] = treatment_config_raw
    if set(treatment) != set(baseline):
        raise AssertionError("treatment changed archive membership")
    changed = sorted(name for name in baseline if baseline[name] != treatment[name])
    if changed != [CONFIG_PATH]:
        raise AssertionError(f"unexpected changed members: {changed}")
    for name, body in baseline.items():
        if name != CONFIG_PATH and treatment[name] != body:
            raise AssertionError(f"retained member drift: {name}")

    candidate = pack(treatment)
    config_post_sha = digest(treatment_config_raw)
    candidate_sha = digest(candidate)
    component = {
        "schema": COMPONENT_SCHEMA,
        "component_id": COMPONENT_ID,
        "baseline_archive_sha256": BASELINE_ARCHIVE_SHA256,
        "depends_on": [],
        "conflicts_with": [],
        "overlap_after": {},
        "replacements": {
            CONFIG_PATH: {
                "source": CONFIG_PATH,
                "preimage_sha256": expected_config_sha256,
                "postimage_sha256": config_post_sha,
            }
        },
        "kaggle_submission_hold": True,
    }
    component_raw = (json.dumps(component, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "arm": COMPONENT_ID,
        "baseline_archive_sha256": BASELINE_ARCHIVE_SHA256,
        "baseline_config_sha256": expected_config_sha256,
        "candidate_archive_sha256": candidate_sha,
        "candidate_config_sha256": config_post_sha,
        "component_sha256": digest(component_raw),
        "member_count": len(treatment),
        "changed_members": [CONFIG_PATH],
        "config_changes": {"market_pressure": {"before": True, "after": False}},
        "retained_preimage": {"early_capital": True},
        "native_economics_status": "UNPROVEN",
        "interpretation": (
            "Single-knob localization of market_pressure from full production-v3; "
            "early_capital remains enabled. The retained late_market_off result is "
            "joint evidence only and does not predict this arm's sign."
        ),
        "kaggle_submission_hold": True,
    }
    receipt_raw = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    artifacts = {
        "candidate.tar.gz": candidate,
        CONFIG_PATH: treatment_config_raw,
        "COMPONENT.json": component_raw,
        "RECEIPT.json": receipt_raw,
    }
    return artifacts, treatment


def _prepare_output_dir(path: Path) -> None:
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f"output directory must not be a symlink: {path}")
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"output path is not a directory: {path}")
        if any(path.iterdir()):
            raise ValueError(f"output directory is not empty: {path}")
        return
    path.mkdir(parents=True)


def publish_artifacts(
    out_dir: Path,
    artifacts: dict[str, bytes],
    publisher: Callable,
) -> None:
    _prepare_output_dir(out_dir)
    expected = {"candidate.tar.gz", CONFIG_PATH, "COMPONENT.json", "RECEIPT.json"}
    if set(artifacts) != expected:
        raise ValueError("unexpected market-pressure artifact set")
    publisher([(Path(out_dir) / name, artifacts[name]) for name in sorted(artifacts)])


def materialize(baseline_path: Path, out_dir: Path) -> dict[str, str]:
    here = Path(__file__).resolve().parent
    stage = _load_module("_titan_v5_stage_screen", here / "materialize_stage_knockouts.py")
    publisher_module = _load_module(
        "_titan_v5_publication_custody",
        here.parent / "selective-carrot" / "publication_custody.py",
    )

    baseline_path = Path(baseline_path)
    if not baseline_path.is_file() or baseline_path.is_symlink():
        raise ValueError(f"baseline must be an ordinary file: {baseline_path}")
    raw = baseline_path.read_bytes()
    if digest(raw) != BASELINE_ARCHIVE_SHA256:
        raise ValueError("production-v3 archive identity mismatch")

    members = stage.support.parse_archive_bytes(raw, BASELINE_ARCHIVE_SHA256)
    stage.support.verify_semantic_topology(
        members,
        stage.SEMANTIC_MEMBER_SHA256,
        stage.SEMANTIC_ANCHORS,
    )
    artifacts, _ = build_from_members(members, stage.support.archive_bytes)
    publish_artifacts(out_dir, artifacts, publisher_module.publish_exclusive)
    return {name: digest(body) for name, body in sorted(artifacts.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    hashes = materialize(args.baseline, args.out_dir)
    print(json.dumps({"component_id": COMPONENT_ID, "artifacts": hashes}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
