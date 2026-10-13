"""Source-bound CLI for the current Arlene route family.

Example from cloud-execution-lab:
  python candidates/v4/research/rival-route-pressure/current_route_probe.py \
      --parent reference/next-panel/vendor/arlene.py \
      --expected-git-blob bdb9cf58148a3c7961c085f4902759537decabf6

The optional observation fixture adds public rival/town evidence; without it the
probe emits only exact route-delta structure.  The CLI never mutates runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from rival_route_pressure import branch_catalog, route_pressure_report  # noqa: E402


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def load_parent(path: Path):
    spec = importlib.util.spec_from_file_location("_parallax_current_parent", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load parent source")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--expected-git-blob", required=True)
    parser.add_argument("--observation", type=Path)
    parser.add_argument("--configuration", type=Path)
    parser.add_argument("--horizon", type=int, default=72)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    parent_path = args.parent.resolve()
    actual_blob = git_blob_sha1(parent_path)
    if actual_blob != args.expected_git_blob:
        raise SystemExit(
            f"parent source drift: expected {args.expected_git_blob}, got {actual_blob}")
    parent = load_parent(parent_path)
    routes = parent.routes()
    catalog = branch_catalog(
        routes, parent.DECISIONS, horizon=args.horizon,
        max_orders=int(getattr(parent, "MAX_ORDERS", 10)))
    result = {
        "schema": "titan-v4-current-route-probe-v1",
        "research_only": True,
        "decision_authority": False,
        "parent": str(parent_path),
        "parent_git_blob": actual_blob,
        "route_ids": sorted(routes),
        "decisions": [list(row) for row in parent.DECISIONS],
        "catalog": catalog,
    }

    if args.observation is not None:
        if args.configuration is None:
            raise SystemExit("--observation requires --configuration")
        obs = json.loads(args.observation.read_text())
        cfg = json.loads(args.configuration.read_text())
        reports = []
        for row in catalog:
            reports.append(route_pressure_report(
                routes, row["incumbent"], row["target"], obs, cfg,
                start=row["turn"], horizon=args.horizon))
        result["public_pressure_reports"] = reports

    text = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
