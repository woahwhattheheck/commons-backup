#!/usr/bin/env python3
"""LDA edge routing button. Phone is the hand; Muhlnickel is the computer.

Take a prompt/objective on stdin or --prompt. Subprocess
host/muhl_serve_spec_add.py --run ask (which subprocesses pfc_harness ask).
Print the answer. Die.

Default --dry prints the command. Fail closed if the spec launcher is missing.
Never imports host/muhl_serve_add.py (invented mmap wall). No numpy. No host
forward pass. Does not write titan. Does not WhiteBox Llama.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence


HERE = Path(__file__).resolve().parent
SPEC_LAUNCHER = HERE / "muhl_serve_spec_add.py"
HARNESS = HERE / "pfc_harness.py"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


class MissingTool(RuntimeError):
    """A required existing-tool script is not on disk."""


def _display_command(argv: Sequence[str]) -> str:
    return subprocess.list2cmdline([str(part) for part in argv])


def _require_spec() -> Path:
    if not SPEC_LAUNCHER.is_file():
        raise MissingTool(f"required spec launcher is missing: {SPEC_LAUNCHER}")
    return SPEC_LAUNCHER


def _read_prompt(explicit: str | None) -> str:
    if explicit is not None:
        return explicit
    if not sys.stdin.isatty():
        return sys.stdin.read().rstrip("\r\n")
    return ""


def _spec_ask_cmd(prompt: str) -> list[str]:
    return [sys.executable, str(_require_spec()), "--run", "ask", prompt]


def _harness_ask_cmd(prompt: str) -> list[str]:
    return [sys.executable, str(HARNESS), "ask", prompt]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "LDA edge routing button: inject an objective into the spec path "
            "(muhl_serve_spec_add.py → pfc_harness ask). Default dry."
        )
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="objective/prompt to inject (otherwise read stdin)",
    )
    parser.add_argument(
        "--dry",
        action="store_true",
        default=True,
        help="print the spec ask command and exit (default)",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="subprocess spec_add --run ask (overrides --dry); print answer; die",
    )
    args = parser.parse_args(argv)
    dry = not args.run
    prompt = _read_prompt(args.prompt)

    try:
        if dry:
            _require_spec()
        else:
            if not prompt.strip():
                print(
                    "REFUSED (fail closed): no prompt — pass --prompt or pipe stdin",
                    file=sys.stderr,
                )
                return 2
            command = _spec_ask_cmd(prompt)
    except MissingTool as exc:
        print(f"REFUSED (fail closed): {exc}", file=sys.stderr)
        return 2

    if dry:
        shown = prompt if prompt.strip() else "<PROMPT>"
        print("LDA EDGE (not run):")
        print(f"  {_display_command(_spec_ask_cmd(shown) if prompt.strip() else [sys.executable, str(SPEC_LAUNCHER), '--run', 'ask', '<PROMPT>'])}")
        print(f"  inner: {_display_command(_harness_ask_cmd(shown))}")
        if not prompt.strip():
            print("  prompt: --prompt or stdin")
        return 0

    completed = subprocess.run(command, shell=False, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
