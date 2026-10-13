#!/usr/bin/env python3
"""Dependency-free advisory linter for self-attested authority/readiness gates.

The linter detects candidate-owned readiness flags that directly control promotion
states (READY/QUALIFIED/AUTHORIZED/etc.) without an independently consumed
source/receipt/authority input. Findings are review signals only: they do not
prove exploitability, compliance failure, buyer state, or mutation authority.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

REPORT_SCHEMA = "authority-boundary-lint-report/v1"
BASELINE_SCHEMA = "authority-boundary-lint-baseline/v1"
RULE_SELF_ATTESTED = "ABL001_SELF_ATTESTED_PROMOTION"
RULE_STRUCTURED_HINT = "ABL002_STRUCTURED_SELF_ATTESTED_HINT"
SUPPORTED_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml"}
SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", ".venv", "venv", "__pycache__"}

CANDIDATE_WORDS = ("candidate", "payload", "manifest", "request", "state", "input", "submission", "packet", "body", "data", "config")
AUTHORITY_WORDS = ("authority", "receipt", "reference", "retained", "root", "evidence", "source", "verifier", "provider", "audit", "attestation", "trusted", "server")
READINESS_WORDS = ("passed", "approved", "verified", "ready", "qualified", "authorized", "proven", "released", "eligible", "submit", "submitted", "sales", "green", "accepted")
PROMOTION_WORDS = ("READY", "QUALIFIED", "AUTHORIZED", "PROVEN", "RELEASE", "RELEASED", "SUBMIT", "SUBMITTED", "SALES", "APPROVED", "ELIGIBLE", "GREEN")

_PROMOTION_RE = re.compile(r"\b(?:" + "|".join(PROMOTION_WORDS) + r")[A-Z0-9_\-]*\b")
_FIELD_RE = re.compile(r"(?:^|_)(?:" + "|".join(READINESS_WORDS) + r")(?:$|_)", re.I)


def _name_has(name: str, words: Sequence[str]) -> bool:
    separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    lowered = re.sub(r"[^a-z0-9]+", "_", separated.lower())
    pieces = [p for p in lowered.split("_") if p]
    return any(word in pieces or lowered == word or lowered.startswith(word + "_") or lowered.endswith("_" + word) for word in words)


def _is_candidate_name(name: str) -> bool:
    return _name_has(name, CANDIDATE_WORDS)


def _is_authority_name(name: str) -> bool:
    return _name_has(name, AUTHORITY_WORDS)


def _is_readiness_field(name: str) -> bool:
    lowered = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return bool(_FIELD_RE.search(lowered)) or any(lowered.endswith("_" + word) for word in READINESS_WORDS)


def _promotions(text: str) -> tuple[str, ...]:
    return tuple(sorted(set(m.group(0) for m in _PROMOTION_RE.finditer(text.upper()))))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass(frozen=True)
class Finding:
    rule_id: str
    path: str
    line: int
    language: str
    function: str
    candidate: str
    field: str
    sink: str
    evidence: str
    content_fingerprint: str
    baseline_drift: bool = False
    advisory: bool = True

    def sort_key(self) -> tuple[Any, ...]:
        return (self.path, self.line, self.rule_id, self.function, self.candidate, self.field, self.sink)


def _source_segment(source: str, node: ast.AST) -> str:
    segment = ast.get_source_segment(source, node)
    return segment if segment is not None else ""


def _node_names(node: ast.AST) -> set[str]:
    return {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}


def _assigned_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    targets: list[ast.AST] = []
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        else:
            targets.append(node.target)
    for target in targets:
        for item in ast.walk(target):
            if isinstance(item, ast.Name):
                names.add(item.id)
    return names


def _assignment_value(node: ast.AST) -> ast.AST | None:
    if isinstance(node, ast.Assign):
        return node.value
    if isinstance(node, ast.AnnAssign):
        return node.value
    if isinstance(node, ast.NamedExpr):
        return node.value
    return None


def _python_trusted_locals(fn: ast.AST, authority_params: set[str], before_line: int) -> set[str]:
    trusted = set(authority_params)
    changed = True
    while changed:
        changed = False
        for node in ast.walk(fn):
            if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                continue
            if getattr(node, "lineno", before_line) >= before_line:
                continue
            value = _assignment_value(node)
            if value is None or not (_node_names(value) & trusted):
                continue
            for name in _assigned_names(node):
                if name not in trusted:
                    trusted.add(name)
                    changed = True
    return trusted


def _python_candidate_accesses(test: ast.AST, candidate_params: set[str]) -> set[tuple[str, str]]:
    accesses: set[tuple[str, str]] = set()
    for node in ast.walk(test):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in candidate_params:
            if _is_readiness_field(node.attr):
                accesses.add((node.value.id, node.attr))
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id in candidate_params:
            sl = node.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str) and _is_readiness_field(sl.value):
                accesses.add((node.value.id, sl.value))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id in candidate_params and node.func.attr == "get" and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and _is_readiness_field(arg.value):
                    accesses.add((node.func.value.id, arg.value))
    return accesses


def _python_promotions(if_node: ast.If, source: str) -> tuple[str, ...]:
    parts = [_source_segment(source, child) for child in list(if_node.body) + list(if_node.orelse)]
    return _promotions("\n".join(parts))


def scan_python(path: Path, relative_path: str, source: str) -> list[Finding]:
    try:
        tree = ast.parse(source, filename=relative_path)
    except SyntaxError:
        return []
    findings: list[Finding] = []
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for fn in functions:
        params = {arg.arg for arg in list(fn.args.posonlyargs) + list(fn.args.args) + list(fn.args.kwonlyargs)}
        if fn.args.vararg:
            params.add(fn.args.vararg.arg)
        if fn.args.kwarg:
            params.add(fn.args.kwarg.arg)
        candidate_params = {name for name in params if _is_candidate_name(name)}
        authority_params = {name for name in params if _is_authority_name(name)}
        if not candidate_params:
            continue
        for if_node in [node for node in ast.walk(fn) if isinstance(node, ast.If)]:
            accesses = _python_candidate_accesses(if_node.test, candidate_params)
            if not accesses:
                continue
            sinks = _python_promotions(if_node, source)
            if not sinks:
                continue
            trusted_names = _python_trusted_locals(fn, authority_params, if_node.lineno)
            if _node_names(if_node.test) & trusted_names:
                continue
            raw = _source_segment(source, if_node).encode("utf-8")
            fingerprint = _sha256_bytes(raw)
            condition = _source_segment(source, if_node.test).strip().replace("\n", " ")
            if len(condition) > 240:
                condition = condition[:237] + "..."
            for candidate, field in sorted(accesses):
                for sink in sinks:
                    findings.append(Finding(
                        rule_id=RULE_SELF_ATTESTED,
                        path=relative_path,
                        line=if_node.lineno,
                        language="python",
                        function=fn.name,
                        candidate=candidate,
                        field=field,
                        sink=sink,
                        evidence=f"candidate-owned `{candidate}.{field}` controls promotion without independently consumed authority: {condition}",
                        content_fingerprint=fingerprint,
                    ))
    return findings


def _find_matching(text: str, start: int, opener: str, closer: str) -> int | None:
    depth = 0
    quote: str | None = None
    escaped = False
    i = start
    while i < len(text):
        ch = text[i]
        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
        else:
            if ch in {"'", '"', "`"}:
                quote = ch
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return None


def _js_accesses(condition: str) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    dot = re.compile(r"\b([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)")
    bracket = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\[\s*['\"]([^'\"]+)['\"]\s*\]")
    for regex in (dot, bracket):
        for match in regex.finditer(condition):
            root, field = match.group(1), match.group(2)
            if _is_candidate_name(root) and _is_readiness_field(field):
                result.add((root, field))
    return result


def _js_has_independent_authority(condition: str) -> bool:
    identifiers = re.findall(r"\b[A-Za-z_$][\w$]*\b", condition)
    return any(_is_authority_name(name) for name in identifiers)


def _nearest_js_function_name(source: str, offset: int) -> str:
    prefix = source[:offset]
    patterns = [
        re.compile(r"function\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", re.M),
        re.compile(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{", re.M),
        re.compile(r"\b([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", re.M),
    ]
    candidates: list[tuple[int, str]] = []
    for regex in patterns:
        for match in regex.finditer(prefix):
            candidates.append((match.start(), match.group(1)))
    return max(candidates, default=(-1, "<module>"))[1]


def scan_javascript(relative_path: str, source: str) -> list[Finding]:
    findings: list[Finding] = []
    for match in re.finditer(r"\bif\s*\(", source):
        open_paren = source.find("(", match.start())
        close_paren = _find_matching(source, open_paren, "(", ")")
        if close_paren is None:
            continue
        condition = source[open_paren + 1:close_paren]
        accesses = _js_accesses(condition)
        if not accesses or _js_has_independent_authority(condition):
            continue
        cursor = close_paren + 1
        while cursor < len(source) and source[cursor].isspace():
            cursor += 1
        if cursor >= len(source) or source[cursor] != "{":
            continue
        close_brace = _find_matching(source, cursor, "{", "}")
        if close_brace is None:
            continue
        block = source[cursor + 1:close_brace]
        sinks = _promotions(block)
        if not sinks:
            continue
        line = source.count("\n", 0, match.start()) + 1
        function = _nearest_js_function_name(source, match.start())
        fingerprint = _sha256_bytes(source[match.start():close_brace + 1].encode("utf-8"))
        evidence_condition = " ".join(condition.split())
        if len(evidence_condition) > 240:
            evidence_condition = evidence_condition[:237] + "..."
        language = Path(relative_path).suffix.lstrip(".") or "javascript"
        for candidate, field in sorted(accesses):
            for sink in sinks:
                findings.append(Finding(
                    rule_id=RULE_SELF_ATTESTED,
                    path=relative_path,
                    line=line,
                    language=language,
                    function=function,
                    candidate=candidate,
                    field=field,
                    sink=sink,
                    evidence=f"candidate-owned `{candidate}.{field}` controls promotion without independently consumed authority: {evidence_condition}",
                    content_fingerprint=fingerprint,
                ))
    return findings


def _structured_walk(value: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], dict[str, Any]]]:
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from _structured_walk(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _structured_walk(child, path + (str(index),))


def scan_json(relative_path: str, source: str) -> list[Finding]:
    try:
        payload = json.loads(source)
    except json.JSONDecodeError:
        return []
    findings: list[Finding] = []
    for object_path, obj in _structured_walk(payload):
        owner_context = any(_is_candidate_name(piece) for piece in object_path)
        fields = [str(key) for key in obj if _is_readiness_field(str(key))]
        if not fields:
            continue
        serialized = json.dumps(obj, sort_keys=True, ensure_ascii=False)
        sinks = _promotions(serialized)
        if not sinks:
            continue
        independent_keys = [str(key) for key in obj if _is_authority_name(str(key))]
        if independent_keys:
            continue
        if not owner_context and not any(_is_candidate_name(str(key)) for key in obj):
            continue
        object_pointer = "/" + "/".join(object_path) if object_path else "/"
        fingerprint = _sha256_bytes(_canonical_json(obj))
        for field in sorted(fields):
            for sink in sinks:
                findings.append(Finding(
                    rule_id=RULE_STRUCTURED_HINT,
                    path=relative_path,
                    line=1,
                    language="json",
                    function=object_pointer,
                    candidate=object_path[-1] if object_path else "document",
                    field=field,
                    sink=sink,
                    evidence=f"candidate-like structured object {object_pointer} co-locates readiness field `{field}` with promotion token `{sink}` and no independent authority key",
                    content_fingerprint=fingerprint,
                ))
    return findings


def scan_yaml_hint(relative_path: str, source: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = source.splitlines()
    for idx, line in enumerate(lines):
        match = re.match(r"^(\s*)([A-Za-z0-9_.-]+)\s*:\s*(.+)?$", line)
        if not match or not _is_readiness_field(match.group(2)):
            continue
        start = max(0, idx - 5)
        end = min(len(lines), idx + 6)
        window = "\n".join(lines[start:end])
        if not _promotions(window):
            continue
        if not any(_is_candidate_name(k) for k in re.findall(r"^\s*([A-Za-z0-9_.-]+)\s*:", window, re.M)):
            continue
        if any(_is_authority_name(k) for k in re.findall(r"^\s*([A-Za-z0-9_.-]+)\s*:", window, re.M)):
            continue
        sink = _promotions(window)[0]
        fingerprint = _sha256_bytes(window.encode("utf-8"))
        findings.append(Finding(
            rule_id=RULE_STRUCTURED_HINT,
            path=relative_path,
            line=idx + 1,
            language=Path(relative_path).suffix.lstrip("."),
            function="<structured-window>",
            candidate="structured-data",
            field=match.group(2),
            sink=sink,
            evidence=f"candidate-like structured window co-locates readiness field `{match.group(2)}` with promotion token `{sink}` and no independent authority key",
            content_fingerprint=fingerprint,
        ))
    return findings


def scan_file(path: Path, root: Path) -> list[Finding]:
    if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        relative_path = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        relative_path = path.as_posix()
    suffix = path.suffix.lower()
    if suffix == ".py":
        return scan_python(path, relative_path, source)
    if suffix in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}:
        return scan_javascript(relative_path, source)
    if suffix == ".json":
        return scan_json(relative_path, source)
    return scan_yaml_hint(relative_path, source)


def iter_paths(root: Path, supplied: Sequence[str] | None = None) -> Iterator[Path]:
    seen: set[Path] = set()
    if supplied:
        candidates = [Path(item) if Path(item).is_absolute() else root / item for item in supplied]
    else:
        candidates = [root]
    for candidate in candidates:
        if candidate.is_dir():
            iterator = candidate.rglob("*")
        else:
            iterator = (candidate,)
        for path in iterator:
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            try:
                rel_parts = path.resolve().relative_to(root.resolve()).parts
            except ValueError:
                rel_parts = path.parts
            if any(part in SKIP_DIRS for part in rel_parts):
                continue
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield path


def _load_baseline(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {"schema": BASELINE_SCHEMA, "findings": []}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != BASELINE_SCHEMA or not isinstance(payload.get("findings"), list):
        raise ValueError(f"baseline must use schema {BASELINE_SCHEMA}")
    return payload


def apply_baseline(findings: Iterable[Finding], baseline: dict[str, Any]) -> tuple[list[Finding], int]:
    exact: set[tuple[str, str, str]] = set()
    by_path_rule: set[tuple[str, str]] = set()
    for item in baseline.get("findings", []):
        if not isinstance(item, dict):
            raise ValueError("baseline findings must be objects")
        rule = str(item.get("rule_id", ""))
        path = str(item.get("path", ""))
        fingerprint = str(item.get("content_fingerprint", ""))
        if not rule or not path or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise ValueError("baseline finding requires rule_id, path, and lowercase sha256 content_fingerprint")
        exact.add((rule, path, fingerprint))
        by_path_rule.add((rule, path))
    active: list[Finding] = []
    suppressed = 0
    for finding in findings:
        key = (finding.rule_id, finding.path, finding.content_fingerprint)
        if key in exact:
            suppressed += 1
            continue
        drift = (finding.rule_id, finding.path) in by_path_rule
        active.append(replace(finding, baseline_drift=drift))
    return active, suppressed


def build_report(findings: Iterable[Finding], suppressed: int = 0) -> dict[str, Any]:
    rows = sorted(findings, key=Finding.sort_key)
    summary = {
        "findings": len(rows),
        "baseline_suppressed": suppressed,
        "baseline_drift": sum(1 for row in rows if row.baseline_drift),
        "advisory_only": True,
    }
    body: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "summary": summary,
        "findings": [asdict(row) for row in rows],
        "authorization_scope": "REVIEW_SIGNAL_ONLY",
        "mutation_authorized": False,
        "buyer_state_authorized": False,
    }
    body["receipt_digest"] = _sha256_bytes(_canonical_json(body))
    return body


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Authority boundary lint",
        "",
        "> Advisory review signal only. A finding is not proof of exploitability, compliance failure, buyer state, or mutation authority.",
        "",
        f"- Findings: **{summary['findings']}**",
        f"- Exact baseline suppressions: **{summary['baseline_suppressed']}**",
        f"- Baseline drift findings: **{summary['baseline_drift']}**",
        f"- Receipt digest: `{report['receipt_digest']}`",
        "",
    ]
    if not report["findings"]:
        lines.append("No active findings.")
        return "\n".join(lines) + "\n"
    lines += [
        "| Path | Line | Rule | Candidate field | Promotion sink | Baseline drift |",
        "|---|---:|---|---|---|---|",
    ]
    for row in report["findings"]:
        path = str(row["path"]).replace("|", "\\|")
        field = f"{row['candidate']}.{row['field']}".replace("|", "\\|")
        lines.append(f"| `{path}` | {row['line']} | `{row['rule_id']}` | `{field}` | `{row['sink']}` | {'YES' if row['baseline_drift'] else 'no'} |")
    lines += ["", "## Evidence", ""]
    for row in report["findings"]:
        lines.append(f"- `{row['path']}:{row['line']}` — {row['evidence']} (`{row['content_fingerprint']}`)")
    return "\n".join(lines) + "\n"


def run(root: Path, supplied: Sequence[str] | None = None, baseline_path: str | Path | None = None) -> dict[str, Any]:
    raw: list[Finding] = []
    for path in iter_paths(root, supplied):
        raw.extend(scan_file(path, root))
    baseline = _load_baseline(baseline_path)
    active, suppressed = apply_baseline(raw, baseline)
    return build_report(active, suppressed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="files/directories to scan; defaults to --root")
    parser.add_argument("--root", default=".", help="repository root used for relative paths")
    parser.add_argument("--baseline", help=f"exact-fingerprint {BASELINE_SCHEMA} JSON")
    parser.add_argument("--json-out", help="write deterministic JSON report")
    parser.add_argument("--markdown-out", help="write deterministic Markdown report")
    parser.add_argument("--fail-on-findings", action="store_true", help="exit 2 when active findings exist; default is advisory exit 0")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    report = run(root, args.paths or None, args.baseline)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.markdown_out:
        Path(args.markdown_out).write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    return 2 if args.fail_on_findings and report["summary"]["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
