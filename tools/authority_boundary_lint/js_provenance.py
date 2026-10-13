"""JavaScript/TypeScript authority-provenance hardening for the advisory linter.

This layer intentionally refuses to treat an authority-sounding local variable
as independent evidence. Only authority-like *direct function parameters* that
are actually referenced by the gate suppress the self-attestation finding.

The module installs the hardened scanner into :mod:`.lint` at package import so
the existing public API and CLI remain unchanged.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import ModuleType


def _param_names(raw: str) -> set[str]:
    """Return only simple direct parameter identifiers.

    Destructuring/default expressions are deliberately not authority proof.
    Conservatism is preferable for an advisory linter because a false negative
    could hide exactly the caller-owned self-attestation class this tool exists
    to surface.
    """
    names: set[str] = set()
    for item in raw.split(","):
        token = item.strip()
        token = re.sub(r"^(?:\.\.\.)", "", token)
        token = token.split("=", 1)[0].strip()
        token = re.sub(r"\?\s*:\s*.*$", "", token)
        token = re.sub(r"\s*:\s*.*$", "", token)
        if re.fullmatch(r"[A-Za-z_$][\w$]*", token):
            names.add(token)
    return names


def _function_context(
    source: str,
    offset: int,
    find_matching,
) -> tuple[str, set[str]]:
    """Best-effort enclosing function name and its direct parameter set.

    Merely being the nearest prior function is insufficient: a closed sibling
    must not donate its receipt/source parameters to a later module-level gate.
    """
    patterns = [
        re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{", re.M),
        re.compile(
            r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"
            r"(?:async\s*)?\(([^)]*)\)\s*=>\s*\{",
            re.M,
        ),
        re.compile(
            r"^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{",
            re.M,
        ),
    ]
    controls = {"if", "for", "while", "switch", "catch", "with"}
    candidates: list[tuple[int, str, set[str]]] = []
    for regex in patterns:
        for match in regex.finditer(source):
            if match.start() >= offset:
                continue
            name = match.group(1)
            if name in controls:
                continue
            open_brace = source.rfind("{", match.start(), match.end())
            if open_brace < 0:
                continue
            close_brace = find_matching(source, open_brace, "{", "}")
            if close_brace is None or not (open_brace < offset < close_brace):
                continue
            candidates.append((match.start(), name, _param_names(match.group(2))))
    if not candidates:
        return "<module>", set()
    _, name, params = max(candidates, key=lambda row: row[0])
    return name, params


def install(base: ModuleType) -> None:
    """Replace ``base.scan_javascript`` with provenance-aware scanning."""

    def has_independent_authority(condition: str, params: set[str]) -> bool:
        identifiers = set(re.findall(r"\b[A-Za-z_$][\w$]*\b", condition))
        authority_params = {
            name for name in params if base._is_authority_name(name)
        }
        return bool(identifiers & authority_params)

    def scan_javascript(relative_path: str, source: str):
        findings = []
        for match in re.finditer(r"\bif\s*\(", source):
            open_paren = source.find("(", match.start())
            close_paren = base._find_matching(source, open_paren, "(", ")")
            if close_paren is None:
                continue
            condition = source[open_paren + 1:close_paren]
            accesses = base._js_accesses(condition)
            function, params = _function_context(
                source,
                match.start(),
                base._find_matching,
            )
            if not accesses or has_independent_authority(condition, params):
                continue

            cursor = close_paren + 1
            while cursor < len(source) and source[cursor].isspace():
                cursor += 1
            if cursor >= len(source) or source[cursor] != "{":
                continue
            close_brace = base._find_matching(source, cursor, "{", "}")
            if close_brace is None:
                continue

            block = source[cursor + 1:close_brace]
            sinks = base._promotions(block)
            if not sinks:
                continue

            line = source.count("\n", 0, match.start()) + 1
            fingerprint = base._sha256_bytes(
                source[match.start():close_brace + 1].encode("utf-8")
            )
            evidence_condition = " ".join(condition.split())
            if len(evidence_condition) > 240:
                evidence_condition = evidence_condition[:237] + "..."
            language = Path(relative_path).suffix.lstrip(".") or "javascript"

            for candidate, field in sorted(accesses):
                for sink in sinks:
                    findings.append(base.Finding(
                        rule_id=base.RULE_SELF_ATTESTED,
                        path=relative_path,
                        line=line,
                        language=language,
                        function=function,
                        candidate=candidate,
                        field=field,
                        sink=sink,
                        evidence=(
                            f"candidate-owned `{candidate}.{field}` controls "
                            "promotion without independently consumed authority: "
                            f"{evidence_condition}"
                        ),
                        content_fingerprint=fingerprint,
                    ))
        return findings

    base.scan_javascript = scan_javascript
