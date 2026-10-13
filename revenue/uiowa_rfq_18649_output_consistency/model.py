"""Shared parsing and diagnostic primitives for UIOWA-117."""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class Diagnostic:
    code: str
    artifact: str
    entity_type: str
    entity_id: str
    field: str
    expected: Any
    actual: Any
    detail: str


def diag_rows(diags: list[Diagnostic]) -> list[dict]:
    return [
        asdict(x)
        for x in sorted(
            diags,
            key=lambda d: (d.artifact, d.code, d.entity_type, d.entity_id, d.field),
        )
    ]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def split_ids(value: Any) -> list[str]:
    if value is None:
        return []
    raw = value if isinstance(value, list) else str(value).replace(",", ";").split(";")
    return [str(x).strip() for x in raw if str(x).strip()]


def optional_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid numeric value {value!r}") from exc


def canonical_indexes(payload: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    findings = {str(x["finding_id"]): x for x in payload.get("findings", [])}
    recs = {str(x["recommendation_id"]): x for x in payload.get("recommendations", [])}
    if len(findings) != len(payload.get("findings", [])):
        raise ValueError("canonical findings contain duplicate finding_id values")
    if len(recs) != len(payload.get("recommendations", [])):
        raise ValueError("canonical recommendations contain duplicate recommendation_id values")
    return findings, recs


def index_unique(
    rows: Iterable[dict], key: str, artifact: str, diags: list[Diagnostic]
) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        value = str(row.get(key, "")).strip()
        if not value:
            diags.append(Diagnostic(
                "MISSING_ID", artifact, "row", "", key, "non-empty", value,
                f"{artifact} contains a row without {key}",
            ))
        elif value in out:
            diags.append(Diagnostic(
                "DUPLICATE_ID", artifact, "row", value, key, "unique", value,
                f"{artifact} repeats {key}={value}",
            ))
        else:
            out[value] = row
    return out


def mismatch(
    diags: list[Diagnostic],
    artifact: str,
    entity_type: str,
    entity_id: str,
    field: str,
    expected: Any,
    actual: Any,
) -> None:
    if expected != actual:
        diags.append(Diagnostic(
            "FIELD_MISMATCH", artifact, entity_type, entity_id, field,
            expected, actual,
            f"{artifact} {entity_type} {entity_id} has {field}={actual!r}; expected {expected!r}",
        ))


def unknown(
    diags: list[Diagnostic],
    artifact: str,
    entity_type: str,
    entity_id: str,
    field: str,
    ref: str,
) -> None:
    diags.append(Diagnostic(
        "UNKNOWN_REFERENCE", artifact, entity_type, entity_id, field,
        "known canonical identifier", ref,
        f"{artifact} references unknown {field}={ref}",
    ))
