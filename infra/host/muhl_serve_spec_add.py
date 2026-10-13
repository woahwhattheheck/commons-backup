#!/usr/bin/env python3
"""Additive spec-path launcher. Host injects+surfaces; cpu_fwd is the computer.

Subprocesses the existing tools only:
  pfc_load.py <model>
  pfc_harness.py connect <model>
  pfc_harness.py ask <prompt>

Default is --dry: print those commands, run nothing. Fail-closed only if a
required script is missing. Does not inspect, rewrite, or replace the harness.
Does not implement a forward pass, evaluate gates, import numpy, or WhiteBox.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence


HERE = Path(__file__).resolve().parent
DEFAULT_MODEL_NAME = "Llama-3.3-70B-Instruct-Q4_K_M.gguf"
DEFAULT_PROMPT = "The capital of France is"

try:
    sys.path.insert(0, str(HERE))
    from pfc_paths import p as pfc_path  # type: ignore

    DEFAULT_MODEL = pfc_path(f"models/{DEFAULT_MODEL_NAME}")
except (ImportError, AttributeError):
    PFC_ROOT = os.environ.get("PFC_ROOT", "C:/llm").replace("\\", "/").rstrip("/")
    DEFAULT_MODEL = f"{PFC_ROOT}/models/{DEFAULT_MODEL_NAME}"


class MissingTool(RuntimeError):
    """A required existing-tool script is not on disk."""


def _display_command(argv: Sequence[str]) -> str:
    return subprocess.list2cmdline([str(part) for part in argv])


def _require(name: str) -> Path:
    path = HERE / name
    if not path.is_file():
        raise MissingTool(f"required tool is missing: {path}")
    return path


def _load_cmd(model: str) -> list[str]:
    return [sys.executable, str(_require("pfc_load.py")), model]


def _connect_cmd(model: str) -> list[str]:
    return [sys.executable, str(_require("pfc_harness.py")), "connect", model]


def _ask_cmd(prompt: str) -> list[str]:
    return [sys.executable, str(_require("pfc_harness.py")), "ask", prompt]


def _print_commands(commands: Sequence[Sequence[str]]) -> int:
    print("SPEC PATH (not run):")
    for command in commands:
        print(f"  {_display_command(command)}")
    return 0


def _run(command: Sequence[str]) -> int:
    completed = subprocess.run(list(command), shell=False, check=False)
    return int(completed.returncode)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Additive dry-default launcher for the existing load/connect/ask spec path."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"connected GGUF software (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--dry",
        action="store_true",
        default=True,
        help="print the existing-tool command(s) and exit (default)",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="subprocess the selected existing-tool command (overrides --dry)",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("load", help="pfc_load.py <model>")
    subparsers.add_parser("connect", help="pfc_harness.py connect <model>")
    ask_parser = subparsers.add_parser("ask", help="pfc_harness.py ask <prompt>")
    ask_parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT, help="prompt to inject")
    args = parser.parse_args(argv)
    dry = not args.run

    try:
        planned = {
            "load": _load_cmd(args.model),
            "connect": _connect_cmd(args.model),
            "ask": _ask_cmd(args.prompt if args.command == "ask" else DEFAULT_PROMPT),
        }
    except MissingTool as exc:
        print(f"REFUSED (fail closed): {exc}", file=sys.stderr)
        return 2

    if args.command is None:
        if not dry:
            print("REFUSED (fail closed): --run requires load, connect, or ask", file=sys.stderr)
            return 2
        return _print_commands([planned["load"], planned["connect"], planned["ask"]])

    command = planned[args.command]
    if dry:
        return _print_commands([command])
    return _run(command)


if __name__ == "__main__":
    raise SystemExit(main())
