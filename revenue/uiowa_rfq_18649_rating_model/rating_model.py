#!/usr/bin/env python3
"""UIOWA-022 deterministic rating-composition engine.

The engine deliberately refuses to calculate an arithmetic "maturity score".
It composes criterion observations into transparent distributions while keeping
maturity, coverage, confidence, applicability, and material gaps separate.
"""

from __future__ import annotations

import argparse
import html
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ASSESSMENT_STATUSES = {"assessed", "unassessed", "not_applicable"}
CONFIDENCE_ORDER = {"low": 0, "moderate": 1, "high": 2}
CRITICALITIES = {"supporting", "important", "critical"}


class ModelError(ValueError):
    """Raised when an input would make the composition ambiguous."""


@dataclass(frozen=True)
class Settings:
    min_coverage_for_characterization: float = 0.60
    mixed_maturity_spread: int = 2

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Settings":
        raw = payload.get("settings", {})
        if not isinstance(raw, dict):
            raise ModelError("settings must be an object")
        allowed = {"min_coverage_for_characterization", "mixed_maturity_spread"}
        if set(raw) - allowed:
            raise ModelError("settings contains unsupported fields")

        min_cov = raw.get("min_coverage_for_characterization", 0.60)
        if (
            isinstance(min_cov, bool)
            or not isinstance(min_cov, (int, float))
            or not 0.0 <= min_cov <= 1.0
        ):
            raise ModelError(
                "min_coverage_for_characterization must be a number between 0 and 1"
            )
        spread = raw.get("mixed_maturity_spread", 2)
        if (
            isinstance(spread, bool)
            or not isinstance(spread, (int, float))
            or spread < 1
            or (isinstance(spread, float) and not spread.is_integer())
        ):
            raise ModelError("mixed_maturity_spread must be an integer >= 1")
        # JSON Schema integer semantics permit an integral JSON number such as 2.0.
        return cls(float(min_cov), int(spread))


def _require_string(row: dict[str, Any], key: str, index: int) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ModelError(f"criterion[{index}] {key} must be a non-empty string")
    return value.strip()


def normalize_criteria(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("criteria")
    if not isinstance(raw, list) or not raw:
        raise ModelError("criteria must be a non-empty array")

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []

    for index, original in enumerate(raw):
        if not isinstance(original, dict):
            raise ModelError("criterion[{index}] must be an object".format(index=index))
        row = dict(original)
        criterion_id = _require_string(row, "criterion_id", index)
        if criterion_id in seen:
            raise ModelError(f"duplicate criterion_id: {criterion_id}")
        seen.add(criterion_id)

        row["criterion_id"] = criterion_id
        row["area"] = _require_string(row, "area", index)
        row["service"] = _require_string(row, "service", index)
        status = _require_string(row, "assessment_status", index)
        if status not in ASSESSMENT_STATUSES:
            raise ModelError(
                f"criterion[{index}] assessment_status must be one of "
                f"{sorted(ASSESSMENT_STATUSES)}"
            )
        row["assessment_status"] = status

        criticality = str(row.get("criticality", "important")).strip().lower()
        if criticality not in CRITICALITIES:
            raise ModelError(
                f"criterion[{index}] criticality must be one of {sorted(CRITICALITIES)}"
            )
        row["criticality"] = criticality

        if status == "assessed":
            rank = row.get("maturity_rank")
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 0:
                raise ModelError(
                    f"criterion[{index}] assessed maturity_rank must be an integer >= 0"
                )
            row["maturity_rank"] = rank
            row["maturity_label"] = _require_string(row, "maturity_label", index)

            confidence = _require_string(row, "confidence", index).lower()
            if confidence not in CONFIDENCE_ORDER:
                raise ModelError(
                    f"criterion[{index}] confidence must be one of "
                    f"{sorted(CONFIDENCE_ORDER)}"
                )
            row["confidence"] = confidence

            material_gap = row.get("material_gap", False)
            if not isinstance(material_gap, bool):
                raise ModelError(f"criterion[{index}] material_gap must be boolean")
            row["material_gap"] = material_gap

            evidence_ids = row.get("evidence_ids", [])
            if not isinstance(evidence_ids, list) or any(
                not isinstance(value, str) or not value.strip() for value in evidence_ids
            ):
                raise ModelError(
                    f"criterion[{index}] evidence_ids must be an array of non-empty strings"
                )
            row["evidence_ids"] = [value.strip() for value in evidence_ids]
        else:
            for forbidden in ("maturity_rank", "maturity_label", "confidence"):
                if row.get(forbidden) is not None and row.get(forbidden) != "":
                    raise ModelError(
                        f"criterion[{index}] {forbidden} must be empty for {status}"
                    )
            if row.get("material_gap") not in (None, False):
                raise ModelError(
                    f"criterion[{index}] material_gap must be empty or false for {status}"
                )
            row["maturity_rank"] = None
            row["maturity_label"] = None
            row["confidence"] = None
            row["material_gap"] = False
            row["evidence_ids"] = []

            if status == "not_applicable":
                row["applicability_reason"] = _require_string(
                    row, "applicability_reason", index
                )

        normalized.append(row)

    return normalized


def _group_summary(
    rows: list[dict[str, Any]],
    settings: Settings,
    *,
    group_id: str,
) -> dict[str, Any]:
    assessed = [row for row in rows if row["assessment_status"] == "assessed"]
    unassessed = [row for row in rows if row["assessment_status"] == "unassessed"]
    na = [row for row in rows if row["assessment_status"] == "not_applicable"]
    eligible = assessed + unassessed

    coverage = None if not eligible else len(assessed) / len(eligible)
    critical_gaps = [
        row["criterion_id"]
        for row in assessed
        if row["criticality"] == "critical" and row["material_gap"]
    ]
    material_gaps = [
        row["criterion_id"] for row in assessed if row["material_gap"]
    ]

    maturity_by_rank: Counter[int] = Counter(
        int(row["maturity_rank"]) for row in assessed
    )
    maturity_by_label: Counter[str] = Counter(
        str(row["maturity_label"]) for row in assessed
    )
    confidence: Counter[str] = Counter(
        str(row["confidence"]) for row in assessed
    )

    ranks = sorted(maturity_by_rank)
    maturity_range = None if not ranks else {
        "lowest_rank": ranks[0],
        "highest_rank": ranks[-1],
        "spread": ranks[-1] - ranks[0],
    }

    minimum_confidence = None
    if confidence:
        minimum_confidence = min(
            confidence,
            key=lambda label: CONFIDENCE_ORDER[label],
        )

    if not eligible:
        composition_status = "not_applicable"
    elif not assessed:
        composition_status = "unassessed"
    elif coverage is not None and coverage < settings.min_coverage_for_characterization:
        composition_status = "insufficient_coverage"
    elif critical_gaps:
        composition_status = "critical_gap_present"
    elif (
        maturity_range is not None
        and maturity_range["spread"] >= settings.mixed_maturity_spread
    ):
        composition_status = "mixed_practice"
    else:
        composition_status = "coherent_pattern"

    return {
        "group_id": group_id,
        "composition_status": composition_status,
        "counts": {
            "total": len(rows),
            "eligible": len(eligible),
            "assessed": len(assessed),
            "unassessed": len(unassessed),
            "not_applicable": len(na),
        },
        "coverage": coverage,
        "coverage_threshold_used": settings.min_coverage_for_characterization,
        "maturity_distribution_by_rank": {
            str(rank): maturity_by_rank[rank] for rank in sorted(maturity_by_rank)
        },
        "maturity_distribution_by_label": dict(sorted(maturity_by_label.items())),
        "maturity_range": maturity_range,
        "confidence_distribution": {
            label: confidence.get(label, 0)
            for label in ("low", "moderate", "high")
        },
        "minimum_confidence": minimum_confidence,
        "critical_gap_ids": critical_gaps,
        "material_gap_ids": material_gaps,
        "not_applicable_ids": [row["criterion_id"] for row in na],
        "unassessed_ids": [row["criterion_id"] for row in unassessed],
        "guardrails": [
            "No arithmetic mean maturity score was calculated.",
            "Coverage excludes not-applicable criteria from the denominator.",
            "Confidence is reported as a distribution and minimum, not averaged into maturity.",
            "A critical material gap takes precedence over an otherwise coherent observed pattern.",
        ],
    }


def _service_key(area: str, service: str) -> str:
    """Injective tuple encoding, retaining existing keys for ordinary names.

    Encode '%' before ':' so literal escape sequences cannot alias encoded
    delimiters. Preserve Unicode without normalizing distinct identifiers.
    """
    def escape(value: str) -> str:
        return value.replace("%", "%25").replace(":", "%3A")
    return f"{escape(area)}::{escape(service)}"


def compose(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ModelError("input must be a JSON object")

    settings = Settings.from_payload(payload)
    rows = normalize_criteria(payload)

    by_area: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_area_service: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_area[row["area"]].append(row)
        by_area_service[(row["area"], row["service"])].append(row)

    area_summaries = {
        area: _group_summary(group_rows, settings, group_id=area)
        for area, group_rows in sorted(by_area.items())
    }
    service_summaries = {
        _service_key(area, service): {
            **_group_summary(
                group_rows,
                settings,
                group_id=_service_key(area, service),
            ),
            "area": area,
            "service": service,
        }
        for (area, service), group_rows in sorted(by_area_service.items())
    }

    return {
        "model": "UIOWA-022 rating composition v1",
        "engagement": payload.get("engagement"),
        "settings": {
            "min_coverage_for_characterization": settings.min_coverage_for_characterization,
            "mixed_maturity_spread": settings.mixed_maturity_spread,
        },
        "method_statement": (
            "Maturity, evidence coverage, confidence, applicability, and material gaps "
            "are separate dimensions. The model reports distributions and guardrails; "
            "it does not calculate an arithmetic maturity average."
        ),
        "area_summaries": area_summaries,
        "service_key_encoding": "percent-colon-v1",
        "service_summaries": service_summaries,
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _markdown_text(value: Any) -> str:
    """Render source text as text, not Markdown/HTML layout instructions."""
    text = html.escape(str(value), quote=True)
    for char, entity in (
        ("\\", "&#92;"), ("|", "&#124;"), ("`", "&#96;"),
        ("*", "&#42;"), ("_", "&#95;"), ("[", "&#91;"),
        ("]", "&#93;"), ("~", "&#126;"),
    ):
        text = text.replace(char, entity)
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# UIOWA-022 rating composition output",
        "",
        f"**Model:** {_markdown_text(result['model'])}",
        "",
        result["method_statement"],
        "",
        "## Area summaries",
        "",
        "| Area | Composition | Coverage | Maturity range | Confidence floor | Critical gaps | Unassessed |",
        "| --- | --- | ---: | --- | --- | --- | --- |",
    ]

    def cells(summary: dict[str, Any]) -> list[str]:
        rng = summary["maturity_range"]
        range_text = "n/a" if rng is None else (
            f"{rng['lowest_rank']}–{rng['highest_rank']} (spread {rng['spread']})"
        )
        return [
            summary["composition_status"],
            _pct(summary["coverage"]),
            range_text,
            summary["minimum_confidence"] or "n/a",
            ", ".join(summary["critical_gap_ids"]) or "none",
            ", ".join(summary["unassessed_ids"]) or "none",
        ]

    def table_row(values: list[str]) -> str:
        return "| " + " | ".join(_markdown_text(value) for value in values) + " |"

    for area, summary in result["area_summaries"].items():
        lines.append(table_row([area] + cells(summary)))

    lines += [
        "",
        "## Service summaries",
        "",
        "Service differences below are not replaced by the area-level pattern.",
        "",
        "| Area | Service | Composition | Coverage | Maturity range | Confidence floor | Critical gaps | Unassessed |",
        "| --- | --- | --- | ---: | --- | --- | --- | --- |",
    ]
    displayed_services: list[tuple[str, str, dict[str, Any]]] = []
    for key, summary in result["service_summaries"].items():
        if "area" in summary and "service" in summary:
            area_name, service_name = summary["area"], summary["service"]
        else:
            # Old saved results did not retain this tuple. Its combined key is
            # ambiguous when either original name contains '::'. Preserve it
            # verbatim rather than guessing or inventing recovered identities.
            area_name = "Unresolved legacy identity"
            service_name = f"Combined group ID: {summary.get('group_id', key)}"
        displayed_services.append((area_name, service_name, summary))
        lines.append(table_row([area_name, service_name] + cells(summary)))
    if any(area == "Unresolved legacy identity" for area, _, _ in displayed_services):
        lines += [
            "",
            "Legacy output lacks separate area/service labels. Combined identifiers "
            "are shown verbatim. Recompose from the original input to confirm identities; "
            "a prior key collision cannot be recovered from saved summaries.",
        ]

    lines += ["", "## Maturity and confidence distributions", ""]
    groups = [(area, summary) for area, summary in result["area_summaries"].items()]
    groups += [
        (f"{area} / {service}", summary)
        for area, service, summary in displayed_services
    ]
    for label, summary in groups:
        lines += [
            f"### {_markdown_text(label)}",
            "",
            f"- by rank: {_markdown_text(json.dumps(summary['maturity_distribution_by_rank'], sort_keys=True, ensure_ascii=False))}",
            f"- by label: {_markdown_text(json.dumps(summary['maturity_distribution_by_label'], sort_keys=True, ensure_ascii=False))}",
            f"- confidence: {_markdown_text(json.dumps(summary['confidence_distribution'], sort_keys=True))}",
            f"- material gaps: {_markdown_text(', '.join(summary['material_gap_ids']) or 'none')}",
            "",
        ]

    lines += [
        "## Guardrails",
        "",
        "- No arithmetic maturity average is emitted.",
        "- Not-applicable criteria are excluded from coverage; unassessed criteria remain in it.",
        "- Confidence never boosts or suppresses maturity. It is reported independently.",
        "- A critical material gap cannot be hidden by stronger observations elsewhere.",
        "- Mixed practice is preserved when the configured ordinal spread threshold is reached.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    result = compose(payload)

    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        args.json_out.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")

    if args.markdown_out:
        args.markdown_out.write_text(render_markdown(result), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
