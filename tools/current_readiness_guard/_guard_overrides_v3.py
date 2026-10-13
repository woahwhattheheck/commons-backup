from __future__ import annotations

from collections.abc import Iterable

from ._guard_overrides import analyze_source as _analyze_source_v2, read_source
from ._model import Finding
from ._review_closure_v3 import additional_findings


def _collapse_findings(findings: Iterable[Finding]) -> list[Finding]:
    chosen: dict[tuple[str, int, int, str, str | None], Finding] = {}
    for finding in findings:
        key = (finding.path, finding.line, finding.col, finding.rule, finding.function)
        if key not in chosen:
            chosen[key] = finding
    return sorted(chosen.values())


def analyze_source(source: str | bytes, *, path: str = "<memory>") -> list[Finding]:
    return _collapse_findings(
        [
            *_analyze_source_v2(source, path=path),
            *additional_findings(source, path=path),
        ]
    )


__all__ = ["analyze_source", "read_source"]
