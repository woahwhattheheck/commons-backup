"""Run stable SOL-ARC3 v2 and experimental v3 through the official local runner.

This wrapper intentionally delegates game execution to the pinned organizer starter's
`scripts/play_local.py`. It only swaps `agent/my_agent.py` between arms, restores the
original bytes in a finally block, and emits hashed stdout/stderr plus a JSON receipt.
It performs local evaluation only and invokes no competition-upload target or provider action.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_STABLE = HERE.parent / "kaggle_my_agent.py"
DEFAULT_BUILDER = HERE / "build_kaggle_v3.py"
DEFAULT_STARTER_COMMIT = "eeb1535404f321d280a8f9194bbc1d7aca5f05fc"

SUMMARY_RE = re.compile(
    r"^\s*(?P<game>\S+)\s+levels=\s*(?P<levels>\d+)\s+actions=\s*(?P<actions>\d+)\s+state=(?P<state>.+?)\s*$"
)
SCORE_RE = re.compile(r"Aggregate scorecard score:\s*(?P<score>[-+0-9.eE]+)")
LIST_RE = re.compile(r"^\s+(?P<game_id>[A-Za-z0-9_-]+-[A-Za-z0-9]+):(?:\s|$)")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def read_git_head(starter: Path) -> str | None:
    process = subprocess.run(
        ["git", "-C", str(starter), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        return None
    value = process.stdout.strip()
    return value if re.fullmatch(r"[0-9a-fA-F]{40}", value) else None


def resolve_python(starter: Path, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    candidate = starter / ".venv" / "bin" / "python"
    return candidate if candidate.exists() else Path(sys.executable)


def list_versions(python: Path, play_local: Path, starter: Path) -> dict[str, str]:
    process = run_command([str(python), str(play_local), "--list"], starter)
    if process.returncode != 0:
        raise RuntimeError(
            "official --list failed\n"
            f"exit={process.returncode}\nstdout={process.stdout}\nstderr={process.stderr}"
        )
    versions: dict[str, str] = {}
    for line in process.stdout.splitlines():
        match = LIST_RE.match(line)
        if not match:
            continue
        full = match.group("game_id")
        short = full.split("-", 1)[0]
        versions[short] = full
    if not versions:
        raise RuntimeError("official --list returned no parseable exact environment ids")
    return versions


def parse_run(stdout: str, requested_game: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        match = SUMMARY_RE.match(line)
        if match:
            rows.append(
                {
                    "game": match.group("game"),
                    "levels": int(match.group("levels")),
                    "actions": int(match.group("actions")),
                    "state": match.group("state"),
                }
            )
    score_match = SCORE_RE.search(stdout)
    if score_match is None:
        raise ValueError("aggregate scorecard score not found in official runner stdout")
    matching = [row for row in rows if row["game"].split("-", 1)[0] == requested_game]
    if len(matching) != 1:
        raise ValueError(f"expected exactly one summary row for {requested_game!r}, got {matching!r}")
    return {"summary": matching[0], "score": float(score_match.group("score"))}


def build_v3(builder: Path, stable: Path, output: Path) -> None:
    process = run_command(
        [
            sys.executable,
            str(builder),
            "--base",
            str(stable),
            "--output",
            str(output),
        ],
        builder.parent,
    )
    if process.returncode != 0:
        raise RuntimeError(
            "v3 builder failed\n"
            f"exit={process.returncode}\nstdout={process.stdout}\nstderr={process.stderr}"
        )


def run_arm(
    *,
    label: str,
    source: Path,
    agent_target: Path,
    python: Path,
    play_local: Path,
    starter: Path,
    game: str,
    max_steps: int,
    output_dir: Path,
) -> dict[str, Any]:
    shutil.copyfile(source, agent_target)
    command = [str(python), str(play_local), "--game", game, "--max-steps", str(max_steps)]
    process = run_command(command, starter)
    stdout_path = output_dir / f"{label}.stdout.txt"
    stderr_path = output_dir / f"{label}.stderr.txt"
    stdout_path.write_text(process.stdout)
    stderr_path.write_text(process.stderr)

    parsed: dict[str, Any] | None = None
    parse_error: str | None = None
    if process.returncode == 0:
        try:
            parsed = parse_run(process.stdout, game)
        except Exception as exc:  # evidence should preserve parser failure, not hide it
            parse_error = f"{type(exc).__name__}: {exc}"

    return {
        "label": label,
        "command": command,
        "exit_code": process.returncode,
        "agent_sha256": sha256_file(source),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_sha256": sha256_file(stderr_path),
        "stdout_file": stdout_path.name,
        "stderr_file": stderr_path.name,
        "parsed": parsed,
        "parse_error": parse_error,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--starter-root", type=Path, required=True)
    parser.add_argument("--game", default="ls20")
    parser.add_argument("--max-steps", type=int, default=400)
    parser.add_argument("--stable", type=Path, default=DEFAULT_STABLE)
    parser.add_argument("--builder", type=Path, default=DEFAULT_BUILDER)
    parser.add_argument("--python", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--starter-commit", default=DEFAULT_STARTER_COMMIT)
    args = parser.parse_args()

    starter = args.starter_root.resolve()
    play_local = starter / "scripts" / "play_local.py"
    agent_target = starter / "agent" / "my_agent.py"
    stable = args.stable.resolve()
    builder = args.builder.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    for path in (play_local, agent_target, stable, builder):
        if not path.exists():
            raise SystemExit(f"required path not found: {path}")
    if args.max_steps <= 0:
        raise SystemExit("--max-steps must be positive")

    python = resolve_python(starter, args.python.resolve() if args.python else None)
    original_agent = agent_target.read_bytes()
    original_sha = sha256_bytes(original_agent)

    actual_starter_commit = read_git_head(starter)
    before_versions = list_versions(python, play_local, starter)
    if args.game not in before_versions:
        raise SystemExit(f"game {args.game!r} absent from official --list: {sorted(before_versions)}")

    with tempfile.TemporaryDirectory(prefix="sol-arc3-v3-") as temp:
        generated_v3 = Path(temp) / "my_agent.v3.py"
        build_v3(builder, stable, generated_v3)
        arms: list[dict[str, Any]] = []
        try:
            arms.append(
                run_arm(
                    label="stable_v2",
                    source=stable,
                    agent_target=agent_target,
                    python=python,
                    play_local=play_local,
                    starter=starter,
                    game=args.game,
                    max_steps=args.max_steps,
                    output_dir=output_dir,
                )
            )
            arms.append(
                run_arm(
                    label="experimental_v3",
                    source=generated_v3,
                    agent_target=agent_target,
                    python=python,
                    play_local=play_local,
                    starter=starter,
                    game=args.game,
                    max_steps=args.max_steps,
                    output_dir=output_dir,
                )
            )
        finally:
            agent_target.write_bytes(original_agent)

        after_versions = list_versions(python, play_local, starter)
        exact_before = before_versions[args.game]
        exact_after = after_versions.get(args.game)
        starter_commit_matches = (
            actual_starter_commit is None or actual_starter_commit == args.starter_commit
        )
        comparable = (
            starter_commit_matches
            and exact_after == exact_before
            and all(arm["exit_code"] == 0 and arm["parsed"] is not None for arm in arms)
            and sha256_file(agent_target) == original_sha
        )
        receipt = {
            "schema": "sol-arc3-official-local-ab-v1",
            "competition_submission_performed": False,
            "starter_root": str(starter),
            "starter_commit_expected": args.starter_commit,
            "starter_commit_actual": actual_starter_commit,
            "starter_commit_matches": starter_commit_matches,
            "official_play_local_sha256": sha256_file(play_local),
            "python": str(python),
            "game_short_id": args.game,
            "game_exact_id_before": exact_before,
            "game_exact_id_after": exact_after,
            "max_steps": args.max_steps,
            "original_agent_sha256": original_sha,
            "original_agent_restored": sha256_file(agent_target) == original_sha,
            "comparable": comparable,
            "arms": arms,
        }
        receipt_path = output_dir / "ab-receipt.json"
        canonical = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        receipt_path.write_text(canonical)
        print(canonical, end="")
        print(f"receipt_sha256={sha256_file(receipt_path)}")
        if not comparable:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
