#!/usr/bin/env python3
"""Build deterministic, source-bound plans from Bryce's public AI toolkit.

The planner performs no training, downloads no weights, and never binds a live
Titan.  It resolves the public source bytes already in the Commons tree and
emits the evidence needed for a later measured implementation run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "ground" / "AI_ENGINEERING_TOOLKIT.json"
EVIDENCE_CLASSES = {"STRUCTURAL_ONLY", "RUNTIME_MEASURED", "CUSTOMER_READY", "UNKNOWN"}
CANONICAL_COMPONENT_IDS = {"muhlnickel", "titan", "whitebox", "subzero"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_blob(path: Path, root: Path) -> str | None:
    try:
        rel = path.relative_to(root).as_posix()
        value = subprocess.check_output(
            ["git", "rev-parse", "HEAD:%s" % rel],
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None
    return value or None


def load_catalog(path: Path = DEFAULT_CATALOG) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "commons-ai-engineering-toolkit-v1":
        raise ValueError("unsupported toolkit schema")
    components = data.get("components")
    if not isinstance(components, list) or len(components) != len(CANONICAL_COMPONENT_IDS):
        raise ValueError("toolkit must compose exactly the four canonical component families")
    if not all(isinstance(row, dict) for row in components):
        raise ValueError("toolkit components must be objects")
    component_ids = [row.get("id") for row in components]
    if set(component_ids) != CANONICAL_COMPONENT_IDS or len(set(component_ids)) != len(component_ids):
        raise ValueError("toolkit must compose exactly the four canonical component families")
    for row in components:
        if row.get("evidence_class") not in EVIDENCE_CLASSES:
            raise ValueError("invalid evidence class for %s" % row.get("id"))
        if not row.get("sources"):
            raise ValueError("component %s has no public sources" % row.get("id"))
    return data


def resolve_sources(catalog: dict[str, Any], root: Path = ROOT) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for component in catalog["components"]:
        for source in component["sources"]:
            path = root / source
            if not path.is_file():
                raise FileNotFoundError("missing toolkit source: %s" % source)
            resolved.append(
                {
                    "component": component["id"],
                    "path": source,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                    "git_blob": _git_blob(path, root),
                }
            )
    return resolved


def build_plan(objective: str, catalog: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    objective = " ".join(str(objective or "").split())
    if not objective:
        raise ValueError("objective must be nonempty")
    sources = resolve_sources(catalog, root)
    return {
        "schema": "commons-ai-engineering-plan-v1",
        "toolkit_id": catalog["toolkit_id"],
        "objective": objective,
        "training_required": False,
        "cash_required_for_planning_usd": 0,
        "selected_components": [row["id"] for row in catalog["components"]],
        "component_roles": {row["id"]: row["role"] for row in catalog["components"]},
        "source_receipts": sources,
        "build_stages": catalog["build_stages"],
        "superiority_state": "BENCHMARK_REQUIRED",
        "benchmark_contract": {
            "candidate": "composed-toolkit-system",
            "baseline": "NAME_A_LANGUAGE_MODEL_AND_VERSION",
            "metric": "NAME_AN_OBJECTIVE_TASK_METRIC",
            "claim_before_measurement": False
        },
        "boundaries": {
            "live_titan_bound": False,
            "private_distro_included": False,
            "weights_downloaded": False,
            "model_trained": False
        }
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("objective", help="system outcome to engineer")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    args = parser.parse_args(argv)
    catalog = load_catalog(args.catalog)
    print(json.dumps(build_plan(args.objective, catalog), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
