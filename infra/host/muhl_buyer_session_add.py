#!/usr/bin/env python3
"""host/muhl_buyer_session_add.py — paid closed-room NDA session runtime.

The computer is the file. Proven on this device. Ring electrons traverse; they
do not deplete. Copying the file copies the computer. cpu_fwd runs model
software. White Box edits meaning without inference. The host injects and
surfaces. This script does not implement inference, does not fabricate, does
not write titan.gguf, and does not dump foundry gene, allocator internals, or
live titan offsets to stdout.

Default is dry: print the session statement and SHOW vs SECRET, run nothing.
Optional wraps call existing instruments through subprocess only:

  python host/muhl_buyer_session_add.py
  python host/muhl_buyer_session_add.py --inspect pfc_cpu32
  python host/muhl_buyer_session_add.py --speed life
  python host/muhl_buyer_session_add.py --live --inspect pfc_cpu32
  python host/muhl_buyer_session_add.py --live --speed cpu32
  python host/muhl_buyer_session_add.py --live --connect
  python host/muhl_buyer_session_add.py --live --connect --ask "The capital of France is"
"""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Sequence


HERE = Path(__file__).resolve().parent
DEFAULT_MODEL_NAME = "Llama-3.3-70B-Instruct-Q4_K_M.gguf"

try:
    sys.path.insert(0, str(HERE))
    from pfc_paths import p as pfc_path  # type: ignore
    from pfc_paths import REG as PFC_REG  # type: ignore

    DEFAULT_MODEL = pfc_path(f"models/{DEFAULT_MODEL_NAME}")
    REG = PFC_REG
except (ImportError, AttributeError):
    _root = os.environ.get("PFC_ROOT", "C:/llm").replace("\\", "/").rstrip("/")
    DEFAULT_MODEL = f"{_root}/models/{DEFAULT_MODEL_NAME}"
    REG = f"{_root}/models/titan_circuits.json"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


COMPUTER_IS_THE_FILE = """\
THE COMPUTER IS THE FILE.
Proven on this device. The bytes are the machine. Ring electrons traverse;
they do not deplete. Copying the file copies the computer. cpu_fwd runs
model software. White Box edits meaning without inference. The host injects
a bounded signal and surfaces a bounded answer. That is the runtime.
"""

SHOW_ITEMS = (
    "File is a computer — the bytes are the machine (copy the file, copy the computer).",
    "Ring power — electrons traverse; they do not deplete.",
    "Inject / surface — host writes a bounded inject; host reads a bounded surface.",
    "White Box sighted edit — meaning from the bits, no inference.",
    "Named-organ look already in the registry (MAGIC, gate/in/out counts, depth).",
    "Power-cycle fact — killing the host process does not kill a process that was never the computer.",
)

SECRET_ITEMS = (
    "Foundry gene space and autofab search.",
    "Allocator internals and layout.",
    "Live titan offsets, lane banks, titan internals.",
    "How Titan was pruned / rewritten.",
    "White Box writer-path internals beyond what the session must show.",
    "Pocket .mno recipes; DISTRO / LOOM / ROOKERY genomes as take-away artifacts.",
    "Anything that would let a buyer reconstruct the fabricator.",
)

SECRET_KEYS = {
    "addr",
    "address",
    "allocator",
    "autofab",
    "banks",
    "base",
    "cursor",
    "foundry",
    "gene",
    "genome",
    "junction",
    "junctioned_to",
    "lane_bank",
    "lanes",
    "len",
    "off",
    "offset",
    "ram",
    "recv",
    "tensor",
}

SECRET_LINE = re.compile(
    r"(?i)\b(foundry|autofab|allocator|genome|gene[ _-]?space|lane[ _-]?bank|"
    r"titan internals|live offset)\b"
)
KEY_LINE = re.compile(r"^(\s*)([A-Za-z_][\w]*)(\s*[:=]\s*)(.*)$")
LAYOUT_ASSIGN = re.compile(
    r"(?i)\b(offset|off|len|recv|addr|address)\s*=\s*(0x[0-9A-Fa-f]+|\d+)"
)
AT_OFFSET = re.compile(r"(@\s*)(\d{5,})")
JSON_OFFSET = re.compile(
    r'(?i)("(?:offset|off|addr|address|recv|len)"\s*:\s*)(0x[0-9A-Fa-f]+|\d+)'
)


class UnsafeTool(RuntimeError):
    """Delegated tool is missing, unreadable, or fails the closed-room laws."""


def _display_command(argv: Sequence[str]) -> str:
    return subprocess.list2cmdline([str(part) for part in argv])


def _print_banner() -> None:
    print("=" * 72, flush=True)
    print("MUHLNICKEL CLOSED-ROOM NDA SESSION", flush=True)
    print("Inventor: Bryce Muhlnickel", flush=True)
    print("Paid look. Not a repo. Not a dump. Not a license of the factory.", flush=True)
    print("=" * 72, flush=True)
    print(flush=True)
    print(COMPUTER_IS_THE_FILE, flush=True)
    print("SHOW  (in the room, under NDA):", flush=True)
    for item in SHOW_ITEMS:
        print(f"  + {item}", flush=True)
    print(flush=True)
    print("SECRET  (never leave the room; this script redacts from stdout):", flush=True)
    for item in SECRET_ITEMS:
        print(f"  - {item}", flush=True)
    print(flush=True)
    print("Operator: do not over-disclose. If a line is SECRET, do not screenshot it,", flush=True)
    print("do not paste it into a buyer deck, do not send it off this machine.", flush=True)
    print(flush=True)


def _redact_secret(text: str) -> str:
    """Strip foundry gene, allocator internals, and live titan offsets."""
    out: list[str] = []
    for raw in text.splitlines():
        if SECRET_LINE.search(raw):
            out.append("[SECRET redacted]")
            continue
        line = raw
        keyed = KEY_LINE.match(line)
        if keyed and keyed.group(2).lower() in SECRET_KEYS:
            line = f"{keyed.group(1)}{keyed.group(2)}{keyed.group(3)}<SECRET>"
        line = LAYOUT_ASSIGN.sub(lambda m: f"{m.group(1)}=<SECRET>", line)
        line = AT_OFFSET.sub(r"\1<SECRET>", line)
        line = JSON_OFFSET.sub(r"\1<SECRET>", line)
        out.append(line)
    if text.endswith("\n"):
        return "\n".join(out) + "\n"
    return "\n".join(out)


def _tool_source(name: str) -> tuple[Path, str, ast.Module]:
    path = HERE / name
    if not path.is_file():
        raise UnsafeTool(f"required tool is missing: {path}")
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise UnsafeTool(f"required tool cannot be safely inspected: {path}: {exc}") from exc
    return path, source, tree


def _import_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _refuse_host_inference_imports(path: Path, tree: ast.AST) -> None:
    forbidden = sorted(_import_roots(tree).intersection({"numpy", "torch", "tensorflow", "jax"}))
    if forbidden:
        raise UnsafeTool(f"{path.name} imports host inference package(s): {', '.join(forbidden)}")


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _whole_file_mmaps(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_mmap = (
            isinstance(func, ast.Attribute)
            and func.attr == "mmap"
            or isinstance(func, ast.Name)
            and func.id == "mmap"
        )
        if is_mmap and len(node.args) >= 2:
            length = node.args[1]
            if isinstance(length, ast.Constant) and length.value == 0:
                lines.append(node.lineno)
    return lines


def _validate_instrument(tool_name: str) -> Path:
    path, _source, tree = _tool_source(tool_name)
    _refuse_host_inference_imports(path, tree)
    return path


def _validate_harness(action: str) -> Path:
    path, source, tree = _tool_source("pfc_harness.py")
    _refuse_host_inference_imports(path, tree)
    required = _function(tree, action)
    if required is None:
        raise UnsafeTool(f"{path.name} does not expose the required {action!r} operation")

    source_lower = source.lower()
    recreated_ops = ("def matmul", "def attention", "def softmax", "def rmsnorm", "def rope")
    found_ops = [term[4:] for term in recreated_ops if term in source_lower]
    if found_ops:
        raise UnsafeTool(
            f"{path.name} appears to recreate forward-pass operations on the host: "
            + ", ".join(found_ops)
        )

    if action == "ask":
        mmap_lines = _whole_file_mmaps(tree)
        if mmap_lines:
            joined = ", ".join(str(line) for line in mmap_lines)
            raise UnsafeTool(
                f"{path.name} whole-file mmaps titan-compatible storage at line(s) {joined}"
            )
        defaults = required.args.defaults
        if defaults and any(
            isinstance(default, ast.Constant)
            and isinstance(default.value, int)
            and default.value > 0
            for default in defaults
        ):
            raise UnsafeTool(f"{path.name} has a fixed integer generation cap in ask()")
    return path


def _registry_names() -> set[str]:
    path = Path(REG)
    if not path.is_file():
        raise UnsafeTool(f"registry missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UnsafeTool(f"registry unreadable: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise UnsafeTool(f"registry is not an object: {path}")
    return set(data.keys())


def _speed_loader_names(tree: ast.Module) -> set[str]:
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "main":
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == "loaders":
                    if not isinstance(stmt.value, ast.Dict):
                        break
                    names: set[str] = set()
                    for key in stmt.value.keys:
                        if isinstance(key, ast.Constant) and isinstance(key.value, str):
                            names.add(key.value)
                    if names:
                        return names
    raise UnsafeTool("pfc_speed.py does not expose a parseable loaders table")


def _refuse(exc: BaseException, intended: Sequence[str]) -> int:
    print(f"REFUSED (fail closed): {exc}", flush=True)
    print("Intended existing-tool command (not run):", flush=True)
    print(f"  {_display_command(intended)}", flush=True)
    return 2


def _run_existing(argv: Sequence[str], live: bool) -> int:
    displayed = _display_command(argv)
    if not live:
        print(f"DRY (not run): {displayed}", flush=True)
        return 0
    print(f"LIVE wrap: {displayed}", flush=True)
    completed = subprocess.run(
        [str(part) for part in argv],
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.stdout:
        sys.stdout.write(_redact_secret(completed.stdout))
        if not completed.stdout.endswith("\n"):
            sys.stdout.write("\n")
    if completed.stderr:
        sys.stderr.write(_redact_secret(completed.stderr))
        if not completed.stderr.endswith("\n"):
            sys.stderr.write("\n")
    return int(completed.returncode)


def _wrap_inspect(name: str, live: bool) -> int:
    intended = [sys.executable, str(HERE / "pfc_inspect.py"), name]
    try:
        tool = _validate_instrument("pfc_inspect.py")
        names = _registry_names()
    except UnsafeTool as exc:
        return _refuse(exc, intended)
    if name not in names:
        return _refuse(UnsafeTool(f"circuit {name!r} is not in the registry"), intended)
    return _run_existing([sys.executable, str(tool), name], live)


def _wrap_speed(name: str, live: bool) -> int:
    intended = [sys.executable, str(HERE / "pfc_speed.py"), name]
    try:
        tool = _validate_instrument("pfc_speed.py")
        _, _, tree = _tool_source("pfc_speed.py")
        loaders = _speed_loader_names(tree)
    except UnsafeTool as exc:
        return _refuse(exc, intended)
    if name not in loaders:
        available = ", ".join(sorted(loaders))
        return _refuse(
            UnsafeTool(f"pfc_speed.py has no loader for {name!r} (present: {available})"),
            intended,
        )
    return _run_existing([sys.executable, str(tool), name], live)


def _wrap_harness(action: str, arguments: Sequence[str], live: bool) -> int:
    intended = [sys.executable, str(HERE / "pfc_harness.py"), action, *arguments]
    try:
        tool = _validate_harness(action)
    except UnsafeTool as exc:
        return _refuse(exc, intended)
    return _run_existing([sys.executable, str(tool), action, *arguments], live)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Closed-room NDA session runtime. States that the computer is the file, "
            "prints SHOW vs SECRET, and optionally wraps existing inspect/speed/harness "
            "tools. Default dry. Does not reimplement inference."
        )
    )
    parser.add_argument(
        "--dry",
        action="store_true",
        help="print the session plan; do not run instruments (default)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="run wrapped existing tools (stdout SECRET-redacted)",
    )
    parser.add_argument(
        "--inspect",
        metavar="CIRCUIT",
        help="wrap pfc_inspect.py for a named circuit if it is in the registry",
    )
    parser.add_argument(
        "--speed",
        metavar="CIRCUIT",
        help="wrap pfc_speed.py for a named loader if present (life, cpu32, cpu_fwd, …)",
    )
    parser.add_argument(
        "--connect",
        action="store_true",
        help="wrap pfc_harness.py connect if present (fail closed; no inference here)",
    )
    parser.add_argument(
        "--ask",
        metavar="PROMPT",
        help="wrap pfc_harness.py ask if present (fail closed; no inference here)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"connected GGUF software for --connect (default: {DEFAULT_MODEL})",
    )
    args = parser.parse_args(argv)

    if args.dry and args.live:
        print("REFUSED (fail closed): pass --dry or --live, not both.", flush=True)
        return 2

    live = bool(args.live)
    _print_banner()
    print(
        f"Mode: {'LIVE (instruments wrapped; SECRET redacted)' if live else 'DRY (default; nothing run)'}",
        flush=True,
    )
    print(flush=True)

    if not any((args.inspect, args.speed, args.connect, args.ask)):
        print("No instrument wrap requested. Optional:", flush=True)
        print("  --inspect CIRCUIT   existing pfc_inspect.py", flush=True)
        print("  --speed CIRCUIT     existing pfc_speed.py", flush=True)
        print("  --connect           existing pfc_harness.py connect", flush=True)
        print("  --ask PROMPT        existing pfc_harness.py ask", flush=True)
        print("Add --live to run a wrap. This script never fabricates and never writes titan.gguf.", flush=True)
        return 0

    rc = 0
    if args.inspect:
        print("--- inspect wrap ---", flush=True)
        rc = _wrap_inspect(args.inspect, live) or rc
        print(flush=True)
    if args.speed:
        print("--- speed wrap ---", flush=True)
        speed_rc = _wrap_speed(args.speed, live)
        rc = speed_rc or rc
        print(flush=True)
    if args.connect:
        print("--- harness connect wrap ---", flush=True)
        connect_rc = _wrap_harness("connect", [args.model], live)
        rc = connect_rc or rc
        print(flush=True)
    if args.ask is not None:
        print("--- harness ask wrap ---", flush=True)
        ask_rc = _wrap_harness("ask", [args.ask], live)
        rc = ask_rc or rc
        print(flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
