"""Run the existing official-engine evaluator against the pinned public panel."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
EVALUATOR = HERE.parent / "cloud-eval" / "evaluate.py"
CANDIDATE = HERE.parent / "cloud-market" / "main.py"
SEEDS = {
    "development": [9000011, 9000049, 9000061],
    "validation": [9000077, 9000091],
}


def verify_sources(directory: Path) -> None:
    manifest = json.loads((directory / "manifest.json").read_text())
    for key, record in manifest["agents"].items():
        path = directory / f"{key}.py"
        import hashlib
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != record["agent_sha256"]:
            raise ValueError(f"{key}: prepared agent hash mismatch")


def command(engine: Path, sources: Path, candidate: Path, phase: str, output: Path) -> list[str]:
    verify_sources(sources)
    return [
        sys.executable, "-B", str(EVALUATOR), "--engine-dir", str(engine),
        "--candidate", str(candidate),
        "--opponent", f"kaito_v43={sources / 'kaito_v43.py'}",
        "--opponent", f"igor_multiroute={sources / 'igor_multiroute.py'}",
        "--seeds", ",".join(map(str, SEEDS[phase])), "--recheck-first", "--output", str(output),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--sources-dir", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, default=CANDIDATE)
    parser.add_argument("--phase", choices=sorted(SEEDS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return subprocess.run(command(args.engine_dir, args.sources_dir, args.candidate, args.phase, args.output), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
