"""Resolve repository-local Python import closure without executing code."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from tools.workflow_sparse_import_closure_common import Entry, _finding_key


def _module_candidates(root: Path, parts: Sequence[str]) -> list[Path]:
    if not parts:
        return []
    base = root.joinpath(*parts)
    result: list[Path] = []
    direct = base.with_suffix(".py")
    init = base / "__init__.py"
    if direct.is_file():
        result.append(direct)
    if init.is_file():
        result.append(init)
    return result

def _add_initializers(root: Path, path: Path) -> list[Path]:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return []
    result: list[Path] = []
    parent = rel.parent
    built = Path()
    for part in parent.parts:
        built /= part
        init = root / built / "__init__.py"
        if init.is_file():
            result.append(init)
    return result

def _resolve_absolute(
    root: Path,
    module: str,
    entry_parent: Path,
    current_parent: Path,
) -> list[Path]:
    parts = tuple(part for part in module.split(".") if part)
    results: list[Path] = []
    for search in (root, entry_parent, current_parent):
        if search == root:
            candidates = _module_candidates(root, parts)
        else:
            candidates = _module_candidates(search, parts)
        for candidate in candidates:
            if candidate.resolve().is_relative_to(root.resolve()):
                results.extend(_add_initializers(root, candidate))
                results.append(candidate)
    return sorted(set(results), key=lambda path: path.relative_to(root).as_posix())

def _resolve_relative(
    root: Path,
    current: Path,
    level: int,
    module: str | None,
) -> list[Path]:
    rel = current.relative_to(root)
    parent_parts = list(rel.parent.parts)
    climb = level - 1
    if climb > len(parent_parts):
        return []
    base = parent_parts[:len(parent_parts) - climb]
    if module:
        base.extend(part for part in module.split(".") if part)
    results = _module_candidates(root, base)
    expanded: list[Path] = []
    for candidate in results:
        expanded.extend(_add_initializers(root, candidate))
        expanded.append(candidate)
    return sorted(set(expanded), key=lambda path: path.relative_to(root).as_posix())

def _literal_dynamic_calls(tree: ast.AST) -> Iterator[tuple[ast.Call, str | None]]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        function = node.func
        is_import = isinstance(function, ast.Name) and function.id == "__import__"
        is_importlib = (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == "importlib"
            and function.attr == "import_module"
        )
        if not (is_import or is_importlib):
            continue
        value = node.args[0]
        yield node, value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None

def _entry_paths(root: Path, entry: Entry) -> tuple[list[Path], list[dict[str, object]]]:
    findings: list[dict[str, object]] = []
    if entry.kind == "path":
        target = entry.target.lstrip("/")
        if any(char in target for char in "*?[") or "${{" in target:
            return [], [{"code": "DYNAMIC_ENTRYPOINT", "target": entry.target, "command": entry.command}]
        path = (root / target).resolve()
        if not path.is_relative_to(root.resolve()):
            return [], [{"code": "ENTRYPOINT_OUTSIDE_ROOT", "target": entry.target, "command": entry.command}]
        if path.is_dir():
            return sorted(path.rglob("*.py")), []
        if path.is_file():
            return [path], []
        return [], [{"code": "MISSING_ENTRYPOINT", "target": target, "command": entry.command}]
    module_parts = entry.target.split(".")
    if entry.kind == "module-prefix":
        # Longest local module prefix wins; remaining components are unittest
        # class/method selectors.
        for length in range(len(module_parts), 0, -1):
            found = _module_candidates(root, module_parts[:length])
            if found:
                paths: list[Path] = []
                for path in found:
                    paths.extend(_add_initializers(root, path))
                    paths.append(path)
                return sorted(set(paths)), []
        return [], [{"code": "MISSING_ENTRYPOINT", "target": entry.target, "command": entry.command}]
    found = _module_candidates(root, module_parts)
    paths: list[Path] = []
    for path in found:
        paths.extend(_add_initializers(root, path))
        paths.append(path)
    if not paths:
        findings.append({"code": "MISSING_ENTRYPOINT", "target": entry.target, "command": entry.command})
    return sorted(set(paths)), findings

def compile_entry_closure(root: Path, entry: Entry) -> dict[str, object]:
    roots, findings = _entry_paths(root, entry)
    if not roots:
        return {
            "kind": entry.kind,
            "target": entry.target,
            "command": entry.command,
            "files": [],
            "chains": {},
            "findings": sorted(findings, key=_finding_key),
            "status": "FAIL" if any(f["code"] != "DYNAMIC_ENTRYPOINT" for f in findings) else "UNKNOWN",
        }

    entry_parent = roots[-1].parent
    queue: list[tuple[Path, tuple[str, ...]]] = [
        (path, (path.relative_to(root).as_posix(),)) for path in roots
    ]
    visited: set[Path] = set()
    files: set[str] = set()
    chains: dict[str, tuple[str, ...]] = {
        path.relative_to(root).as_posix(): chain for path, chain in queue
    }
    while queue:
        current, chain = queue.pop(0)
        current = current.resolve()
        if current in visited:
            continue
        visited.add(current)
        rel = current.relative_to(root).as_posix()
        files.add(rel)
        try:
            source = current.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            findings.append({"code": "SOURCE_READ_ERROR", "source": rel, "detail": type(exc).__name__, "chain": list(chain)})
            continue
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError as exc:
            findings.append({
                "code": "PYTHON_SYNTAX_ERROR",
                "source": rel,
                "line": exc.lineno or 0,
                "detail": exc.msg,
                "chain": list(chain),
            })
            continue

        def enqueue(paths: Iterable[Path], label: str, line: int) -> None:
            unique = sorted(set(paths), key=lambda path: path.relative_to(root).as_posix())
            for path in unique:
                child_rel = path.relative_to(root).as_posix()
                files.add(child_rel)
                child_chain = chain + (child_rel,)
                chains.setdefault(child_rel, child_chain)
                if path.resolve() not in visited:
                    queue.append((path, child_chain))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    resolved = _resolve_absolute(root, alias.name, entry_parent, current.parent)
                    if resolved:
                        enqueue(resolved, alias.name, node.lineno)
                    else:
                        top = alias.name.split(".", 1)[0]
                        if (root / top).exists() or (current.parent / top).exists():
                            findings.append({
                                "code": "UNRESOLVED_LOCAL_IMPORT",
                                "source": rel,
                                "line": node.lineno,
                                "import": alias.name,
                                "chain": list(chain),
                            })
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = _resolve_relative(root, current, node.level, node.module)
                    if base:
                        enqueue(base, "." * node.level + (node.module or ""), node.lineno)
                    # from . import sibling / from pkg import submodule
                    parent_rel = current.relative_to(root).parent
                    climb = node.level - 1
                    if climb <= len(parent_rel.parts):
                        parent_parts = list(parent_rel.parts[:len(parent_rel.parts) - climb])
                        if node.module:
                            parent_parts.extend(node.module.split("."))
                        for alias in node.names:
                            if alias.name == "*":
                                continue
                            sub = _module_candidates(root, parent_parts + alias.name.split("."))
                            if sub:
                                enqueue(sub, alias.name, node.lineno)
                    if not base and not any(
                        _module_candidates(
                            root,
                            list(parent_rel.parts[:len(parent_rel.parts) - climb])
                            + ((node.module or "").split(".") if node.module else [])
                            + ([] if alias.name == "*" else alias.name.split(".")),
                        )
                        for alias in node.names
                    ):
                        findings.append({
                            "code": "UNRESOLVED_RELATIVE_IMPORT",
                            "source": rel,
                            "line": node.lineno,
                            "import": "." * node.level + (node.module or ""),
                            "chain": list(chain),
                        })
                elif node.module:
                    base = _resolve_absolute(root, node.module, entry_parent, current.parent)
                    if base:
                        enqueue(base, node.module, node.lineno)
                    module_parts = node.module.split(".")
                    found_sub = False
                    for alias in node.names:
                        if alias.name == "*":
                            continue
                        sub = _resolve_absolute(
                            root,
                            node.module + "." + alias.name,
                            entry_parent,
                            current.parent,
                        )
                        if sub:
                            found_sub = True
                            enqueue(sub, node.module + "." + alias.name, node.lineno)
                    if not base and not found_sub:
                        top = module_parts[0]
                        if (root / top).exists() or (current.parent / top).exists():
                            findings.append({
                                "code": "UNRESOLVED_LOCAL_IMPORT",
                                "source": rel,
                                "line": node.lineno,
                                "import": node.module,
                                "chain": list(chain),
                            })
        for node, module in _literal_dynamic_calls(tree):
            if module is None:
                findings.append({
                    "code": "DYNAMIC_IMPORT",
                    "source": rel,
                    "line": node.lineno,
                    "chain": list(chain),
                })
                continue
            resolved = _resolve_absolute(root, module, entry_parent, current.parent)
            if resolved:
                enqueue(resolved, module, node.lineno)
            else:
                top = module.split(".", 1)[0]
                if (root / top).exists() or (current.parent / top).exists():
                    findings.append({
                        "code": "UNRESOLVED_LOCAL_IMPORT",
                        "source": rel,
                        "line": node.lineno,
                        "import": module,
                        "chain": list(chain),
                    })

    status = "PASS"
    fail_codes = {
        "MISSING_ENTRYPOINT", "ENTRYPOINT_OUTSIDE_ROOT", "PYTHON_SYNTAX_ERROR",
        "SOURCE_READ_ERROR", "UNRESOLVED_RELATIVE_IMPORT",
    }
    if any(finding["code"] in fail_codes for finding in findings):
        status = "FAIL"
    elif findings:
        status = "UNKNOWN"
    return {
        "kind": entry.kind,
        "target": entry.target,
        "command": entry.command,
        "files": sorted(files),
        "chains": {key: list(chains[key]) for key in sorted(chains)},
        "findings": sorted(findings, key=_finding_key),
        "status": status,
    }

