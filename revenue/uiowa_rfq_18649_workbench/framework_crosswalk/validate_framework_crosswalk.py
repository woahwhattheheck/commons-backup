#!/usr/bin/env python3
"""Validate the UIOWA-020 NIST framework crosswalk.

Stdlib-only so the artifact can be checked in a bare Python environment.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DEFAULT_CSV = ROOT / "20-framework-crosswalk.csv"

REQUIRED_COLUMNS = {
    "framework",
    "version",
    "publication_date",
    "locator",
    "source_concept",
    "assessment_area",
    "proposed_assessment_use",
    "evidence_examples",
    "adaptation_limit",
    "source_url",
}

ALLOWED_FRAMEWORKS = {
    ("SSDF", "1.1"),
    ("CSF", "2.0"),
    ("AI RMF", "1.0"),
}

ALLOWED_AREAS = {
    "software_development",
    "security",
    "deployment_operations",
    "ai_readiness",
}

FORBIDDEN_CLAIM_FRAGMENTS = (
    "nist certified",
    "nist compliant",
    "nist compliance",
    "certification level",
    "percentile rank",
)


class ValidationError(Exception):
    pass


def validate(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ValidationError(f"crosswalk not found: {path}")

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValidationError(f"missing columns: {sorted(missing)}")
        rows = list(reader)

    if len(rows) < 40:
        raise ValidationError(f"crosswalk is unexpectedly small: {len(rows)} rows")

    framework_counts: Counter[str] = Counter()
    area_counts: Counter[str] = Counter()
    seen_keys: set[tuple[str, str, str]] = set()

    for line_no, row in enumerate(rows, start=2):
        framework = row["framework"].strip()
        version = row["version"].strip()
        locator = row["locator"].strip()

        if (framework, version) not in ALLOWED_FRAMEWORKS:
            raise ValidationError(
                f"line {line_no}: unsupported framework/version {framework!r} {version!r}"
            )

        if not locator:
            raise ValidationError(f"line {line_no}: locator is empty")

        key = (framework, version, locator)
        if key in seen_keys:
            raise ValidationError(f"line {line_no}: duplicate framework locator {key}")
        seen_keys.add(key)

        areas = {item.strip() for item in row["assessment_area"].split("|") if item.strip()}
        unknown_areas = areas - ALLOWED_AREAS
        if not areas:
            raise ValidationError(f"line {line_no}: assessment_area is empty")
        if unknown_areas:
            raise ValidationError(
                f"line {line_no}: unsupported assessment areas {sorted(unknown_areas)}"
            )

        source_url = row["source_url"].strip()
        parsed = urlparse(source_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValidationError(f"line {line_no}: invalid HTTPS source URL {source_url!r}")
        if "nist.gov" not in parsed.netloc:
            raise ValidationError(
                f"line {line_no}: primary source is not on a NIST domain: {source_url!r}"
            )

        for field in (
            "source_concept",
            "proposed_assessment_use",
            "evidence_examples",
            "adaptation_limit",
        ):
            if not row[field].strip():
                raise ValidationError(f"line {line_no}: {field} is empty")

        combined = " ".join(row.values()).lower()
        for fragment in FORBIDDEN_CLAIM_FRAGMENTS:
            if fragment in combined:
                raise ValidationError(
                    f"line {line_no}: prohibited unsupported claim fragment {fragment!r}"
                )

        framework_counts[framework] += 1
        area_counts.update(areas)

    missing_frameworks = {name for name, _ in ALLOWED_FRAMEWORKS} - set(framework_counts)
    if missing_frameworks:
        raise ValidationError(f"missing frameworks: {sorted(missing_frameworks)}")

    missing_areas = ALLOWED_AREAS - set(area_counts)
    if missing_areas:
        raise ValidationError(f"uncovered assessment areas: {sorted(missing_areas)}")

    return {
        "rows": len(rows),
        "framework_counts": dict(sorted(framework_counts.items())),
        "area_counts": dict(sorted(area_counts.items())),
    }


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_CSV
    try:
        summary = validate(path)
    except ValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print("PASS: framework crosswalk is structurally valid")
    print(f"rows={summary['rows']}")
    print(f"framework_counts={summary['framework_counts']}")
    print(f"area_counts={summary['area_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
