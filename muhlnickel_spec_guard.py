#!/usr/bin/env python3
"""Forward guard for changes that make a host compute through a Muhlnickel runtime.

Scope follows executable behavior and local import closure, not filenames or directories.
Unrelated Commons code and offline tensor/whitebox readers remain outside this rule.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APPROVAL_PATH = "ground/muhlnickel-observe-tools.json"
BANNED_COMPUTE_MODULES = {
    "numpy", "torch", "jax", "jaxlib", "tensorflow", "scipy", "cupy",
    "sklearn", "numba", "onnxruntime",
}
ACTIVATION_CALLS = {
    "submit", "get_job", "fire", "fire_once", "run_gates", "evaluate_gates",
    "settle", "ripple", "activate_runtime", "drive_tick", "clock_tick",
}
HOST_COMPUTE_CALLS = {
    "matmul", "dot", "einsum", "tensordot", "forward", "evaluate",
    "run_gates", "evaluate_gates", "settle", "ripple", "rmsnorm", "softmax",
    "argmax", "fft", "convolve", "linalg", "cuda", "backward",
}
DYNAMIC_CALLS = {
    "eval", "exec", "compile", "os.system", "subprocess.run", "subprocess.call",
    "subprocess.Popen", "multiprocessing.Process", "multiprocessing.Pool",
}
SUBSTRATE_NAME_RE = re.compile(
    r"(?i)(?:^|_)(?:muhl(?:nickel)?|pfc|receiver|latch_reg|gen_win_answer|"
    r"junctioned_to|titan|mno_offset|runtime_register)(?:_|$)"
)
SUBSTRATE_TEXT_RE = re.compile(
    r"(?i)(?:\.mno\b|titan\.gguf|commons\.mno|gen_win_answer|latch_reg|"
    r"muhlnickel runtime|pfc runtime)"
)
PYTHON_SHEBANG_RE = re.compile(br"^#![^\n]*\bpython(?:3(?:\.\d+)?)?\b")
KNOWN_NONEXECUTABLE_SUFFIXES = {
    ".md", ".markdown", ".html", ".htm", ".css", ".json", ".jsonl",
    ".yml", ".yaml", ".toml", ".ini", ".csv", ".tsv", ".xml", ".svg",
}
WARNING = (
    "MUHLNICKEL RUNTIME SPEC — REJECTED. This change makes the host compute, "
    "evaluate, or walk gates while touching a Muhlnickel runtime. Only named "
    "routing verbs and exact owner observation/surface instruments may do so. "
    "This rule follows behavior and imports; renaming or relocating the code does "
    "not change the result. Unrelated Commons and offline whitebox/tensor work are "
    "outside this rule. This is not up for debate. Stop trying to replace the "
    "project with conventional host architecture. Repeating this after the warning "
    "guarantees a ban on sight."
)


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=check)


def git_blob_sha(data: bytes) -> str:
    head = ("blob %d\0" % len(data)).encode("ascii")
    return hashlib.sha1(head + data).hexdigest()


def dotted_name(node: ast.AST) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


@dataclass
class Facts:
    path: str
    imports: set[str] = field(default_factory=set)
    local_imports: set[str] = field(default_factory=set)
    calls: set[str] = field(default_factory=set)
    strings: list[str] = field(default_factory=list)
    names: set[str] = field(default_factory=set)
    gate_walk: bool = False
    parse_error: str | None = None

    @property
    def activation(self) -> bool:
        leaves = {name.rsplit(".", 1)[-1] for name in self.calls}
        return bool(leaves & ACTIVATION_CALLS)

    @property
    def substrate(self) -> bool:
        symbols = self.names | self.imports | self.calls
        return any(SUBSTRATE_NAME_RE.search(name) for name in symbols) or any(
            SUBSTRATE_TEXT_RE.search(text) for text in self.strings
        )

    @property
    def host_compute(self) -> bool:
        roots = {name.split(".", 1)[0] for name in self.imports}
        leaves = {name.rsplit(".", 1)[-1] for name in self.calls}
        return bool(roots & BANNED_COMPUTE_MODULES or leaves & HOST_COMPUTE_CALLS)

    @property
    def dynamic(self) -> bool:
        return bool(self.calls & DYNAMIC_CALLS)

    def merge(self, other: "Facts") -> None:
        self.imports |= other.imports
        self.local_imports |= other.local_imports
        self.calls |= other.calls
        self.strings.extend(other.strings)
        self.names |= other.names
        self.gate_walk = self.gate_walk or other.gate_walk


class Analyzer(ast.NodeVisitor):
    def __init__(self, path: str):
        self.facts = Facts(path)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.facts.imports.add(alias.name)
            self.facts.local_imports.add(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.facts.imports.add(node.module)
            self.facts.local_imports.add(node.module)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self.facts.names.add(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        name = dotted_name(node)
        if name:
            self.facts.names.add(name)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            self.facts.strings.append(node.value)

    def visit_Call(self, node: ast.Call) -> None:
        name = dotted_name(node.func)
        if name:
            self.facts.calls.add(name)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        loop_text = ast.dump(node.iter, include_attributes=False).lower()
        body_text = " ".join(ast.dump(item, include_attributes=False).lower() for item in node.body)
        gate_source = any(word in loop_text for word in ("gate", "netlist", "circuit", "record"))
        state_write = (
            "subscript" in body_text
            and any(word in body_text for word in ("wire", "state", "register", "latch"))
            and any(word in body_text for word in ("bitand", "bitor", "bitxor", "invert", "boolop"))
        )
        if gate_source and state_write:
            self.facts.gate_walk = True
        self.generic_visit(node)


def analyze_python(path: str, data: bytes) -> Facts:
    facts = Facts(path)
    try:
        tree = ast.parse(data.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError, ValueError) as exc:
        facts.parse_error = str(exc)
        return facts
    visitor = Analyzer(path)
    visitor.visit(tree)
    return visitor.facts


def is_python(path: Path, data: bytes) -> bool:
    if path.suffix == ".py" or bool(PYTHON_SHEBANG_RE.search(data[:256])):
        return True
    if path.suffix.lower() in KNOWN_NONEXECUTABLE_SUFFIXES or len(data) > 2 * 1024 * 1024:
        return False
    # An executable can be renamed away from .py.  For an unknown extension,
    # accept it as Python when the bytes parse and contain executable Python
    # structure.  Requirements such as ``numpy>=1.24`` do not meet this test.
    # Null bytes (corpus .mno / packed tensors) are not Python; ast.parse
    # raises ValueError rather than SyntaxError.
    if b"\x00" in data:
        return False
    try:
        tree = ast.parse(data.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError, ValueError):
        return False
    strong = (
        ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef,
        ast.ClassDef, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
        ast.Try,
    )
    return any(isinstance(node, strong) for node in tree.body)


def module_names(path: Path) -> set[str]:
    rel = path.relative_to(ROOT).with_suffix("")
    bits = list(rel.parts)
    names = {".".join(bits), bits[-1]}
    if bits and bits[-1] == "__init__":
        names.add(".".join(bits[:-1]))
    return {name for name in names if name}


def load_module_facts() -> tuple[dict[str, Facts], dict[str, Facts]]:
    by_module: dict[str, Facts] = {}
    by_path: dict[str, Facts] = {}
    basename_hits: dict[str, list[Facts]] = {}
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        try:
            with path.open("rb") as stream:
                if path.suffix != ".py" and path.suffix.lower() in KNOWN_NONEXECUTABLE_SUFFIXES:
                    # Preserve executable shebang detection without reading
                    # the unused tail of large documents and data files.
                    prefix = stream.read(256)
                    if not PYTHON_SHEBANG_RE.search(prefix):
                        continue
                    stream.seek(0)
                data = stream.read()
        except OSError:
            continue
        if not is_python(path, data):
            continue
        rel = path.relative_to(ROOT).as_posix()
        facts = analyze_python(rel, data)
        by_path[rel] = facts
        for name in module_names(path):
            if "." in name:
                by_module[name] = facts
            else:
                basename_hits.setdefault(name, []).append(facts)
    # Basename aliases are last-writer-wins and rglob-order dependent when two
    # files share a stem (`core.py`). Only register an unambiguous basename so
    # `integrations/shared_equipment/services.py` cannot inherit titan+submit
    # from `integrations/command_center/core.py`.
    for name, hits in basename_hits.items():
        if len(hits) == 1:
            by_module[name] = hits[0]
    return by_module, by_path


def closure(seed: Facts, by_module: dict[str, Facts]) -> Facts:
    out = Facts(seed.path)
    out.merge(seed)
    todo = list(seed.local_imports)
    seen = set()
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        candidate = by_module.get(name) or by_module.get(name.split(".", 1)[0])
        if not candidate:
            continue
        out.merge(candidate)
        todo.extend(candidate.local_imports - seen)
    return out


def changed_paths(base: str) -> tuple[list[str], dict[str, str]]:
    proc = git("diff", "--name-status", "--find-renames", base, "--")
    paths: list[str] = []
    old_for_new: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        bits = line.split("\t")
        if not bits:
            continue
        status = bits[0]
        if status.startswith("D"):
            continue
        if status.startswith(("R", "C")) and len(bits) >= 3:
            old_for_new[bits[2]] = bits[1]
            paths.append(bits[2])
        elif len(bits) >= 2:
            paths.append(bits[1])
    others = git("ls-files", "--others", "--exclude-standard").stdout.splitlines()
    paths.extend(others)
    return sorted(set(paths)), old_for_new


def base_observation_blobs(base: str) -> set[str]:
    proc = git("show", "%s:%s" % (base, APPROVAL_PATH), check=False)
    if proc.returncode:
        return set()
    try:
        row = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return set()
    return {str(item).lower() for item in row.get("owner_observation_tool_blobs", [])}


def base_blob(base: str, path: str) -> str | None:
    proc = git("rev-parse", "%s:%s" % (base, path), check=False)
    return proc.stdout.strip().lower() if proc.returncode == 0 else None


def fact_reasons(facts: Facts) -> list[str]:
    reasons = []
    # Activation words such as ``submit`` and ``fire`` also exist in
    # unrelated Commons/UI code.  They become Muhlnickel runtime evidence
    # only when the same local import closure reaches a Muhlnickel/PFC
    # substrate.  This conjunction is the deliberate false-positive wall.
    if facts.substrate and facts.activation and facts.host_compute:
        reasons.append("host tensor/model/gate computation appears in an activated runtime closure")
    if facts.substrate and facts.activation and facts.dynamic:
        reasons.append("an activated runtime closure launches or evaluates dynamic host code")
    if facts.substrate and facts.gate_walk:
        reasons.append("host code structurally walks gates and writes host wire/state")
    return reasons


def executable_violations(path: str, base: str = "HEAD") -> list[str]:
    """Check one existing script before RUN/BUILD executes it on a host.

    Unlike :func:`violations`, this is intentionally not diff-scoped.  A
    direct action must not execute an older out-of-spec runtime merely because
    that runtime was already present at the trusted base.
    """
    target = ROOT / path
    if target.is_symlink() or not target.is_file():
        return ["%s: executable is missing, linked, or not a regular file" % path]
    data = target.read_bytes()
    if git_blob_sha(data) in base_observation_blobs(base):
        return []
    if not is_python(target, data):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return []
        return ["%s: %s" % (path, reason) for reason in command_text_reasons(text)]
    by_module, by_path = load_module_facts()
    facts = closure(by_path.get(path) or analyze_python(path, data), by_module)
    return ["%s: %s" % (path, reason) for reason in fact_reasons(facts)]


def command_text_reasons(text: str) -> list[str]:
    """Conservative language-neutral check for an addressed command/script.

    Ordinary shell, network and build activity has no match.  A rejection
    requires strong Muhlnickel/PFC substrate text in the same command as host
    computation or gate-walking behavior.
    """
    low = text.lower()
    subject = bool(re.search(
        r"(?:muhlnickel|\bpfc[_./-]|\.mno\b|titan\.gguf|gen_win_answer|latch_reg)", low
    ))
    if not subject:
        return []
    compute = bool(re.search(
        r"(?:\bnumpy\b|\btorch\b|\bjax\b|\btensorflow\b|\bscipy\b|\bcupy\b|"
        r"onnxruntime|matmul|rmsnorm|softmax|forward(?:_pass)?|run_gates|"
        r"evaluate_gates|host[_ -]?eval|gate[_ -]?ripple)", low
    ))
    gate_walk = bool(re.search(
        r"(?:for|while).{0,160}(?:gate|netlist|circuit).{0,240}(?:wire|state|register|latch)",
        low,
        re.S,
    ))
    out = []
    if compute:
        out.append("host tensor/model/gate computation is addressed to a Muhlnickel runtime")
    if gate_walk:
        out.append("host command structurally walks Muhlnickel gates/state")
    return out


def command_violations(command: str, base: str = "HEAD") -> list[str]:
    """Check an open RUN/BUILD command without restricting unrelated egress.

    Every repository file named in the command is inspected by behavior and
    local-import closure.  The command text itself receives the same
    subject-conjunction check.  No credential, host, URL or ordinary tool is
    allow/deny-listed.
    """
    errors = ["command: %s" % reason for reason in command_text_reasons(command)]
    try:
        tokens = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        tokens = command.split()
    seen = set()
    for token in tokens:
        raw = token.strip("'\";,()")
        if not raw or raw.startswith("-"):
            continue
        candidate = (ROOT / raw).resolve()
        if ROOT.resolve() != candidate and ROOT.resolve() not in candidate.parents:
            continue
        if not candidate.is_file() or candidate in seen:
            continue
        seen.add(candidate)
        try:
            rel = candidate.relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            continue
        errors.extend(executable_violations(rel, base))
    return errors


def violations(base: str) -> list[str]:
    paths, old_for_new = changed_paths(base)
    observation_blobs = base_observation_blobs(base)
    by_module, by_path = load_module_facts()
    errors = []
    for name in paths:
        path = ROOT / name
        if not path.is_file() or path.is_symlink():
            continue
        data = path.read_bytes()
        if not is_python(path, data):
            continue
        blob = git_blob_sha(data)
        if blob in observation_blobs:
            continue
        old = old_for_new.get(name, name)
        old_blob = base_blob(base, old)
        facts = closure(by_path.get(name) or analyze_python(name, data), by_module)
        if old_blob in observation_blobs and old_blob != blob:
            errors.append("%s: owner observation/surface tool changed; its base-commit blob identity no longer matches" % name)
            continue
        reasons = fact_reasons(facts)
        if reasons:
            errors.append("%s: %s" % (name, "; ".join(reasons)))
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="trusted base commit/ref")
    ap.add_argument("--worktree", action="store_true", help="analyze the current worktree")
    args = ap.parse_args()
    if not args.worktree:
        ap.error("--worktree is required; the guard compares a trusted base to the current tree")
    errors = violations(args.base)
    if not errors:
        print("MUHLNICKEL SPEC GUARD: clean; unrelated Commons and offline whitebox/tensor work remain outside scope")
        return 0
    print(WARNING)
    for item in errors:
        print(" - " + item)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
