#!/usr/bin/env python3
"""Offline synthetic test-data catalog, maintenance review, and fixture bundles.

A catalog describes intended coverage. Generated examples and internal checks do
not establish any application's correctness or an institution's current practice.
Only the Python standard library is required. No network or production access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "tjlabs.testdata.catalog.v1"
BUNDLE_SCHEMA = "tjlabs.testdata.bundle.v1"
GENERATOR_VERSION = "1.0.0"
ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
MAX_BYTES = 8 * 1024 * 1024
MAX_CATALOG_ITEMS = 1000
MAX_JSON_DEPTH = 64
GROUPS = {"ESS", "RIS", "IAM"}
KINDS = {"term_window", "funding_window", "role_transition"}
BOUNDARY = ("before", "at_start", "inside", "at_end", "after")
SYNTHETIC_NOTICE = (
    "Synthetic assessment rehearsal only. Intended coverage is not executed "
    "application coverage, institutional evidence, or release approval."
)


class CatalogError(ValueError):
    """Invalid or inconsistent input; no external action has occurred."""


def canonical(value: Any) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                           allow_nan=False, indent=2) + "\n").encode("utf-8")
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise CatalogError(f"value is not representable as canonical UTF-8 JSON: {exc}") from exc


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CatalogError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        if not path.is_file():
            raise CatalogError(f"input is not a regular file: {path}")
        if path.stat().st_size > MAX_BYTES:
            raise CatalogError(f"input exceeds {MAX_BYTES} bytes: {path}")
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(
                               CatalogError(f"non-finite JSON number: {value}")))
        pending = [(value, 1)]
        while pending:
            node, depth = pending.pop()
            if isinstance(node, (list, dict)):
                if depth > MAX_JSON_DEPTH:
                    raise CatalogError(f"JSON nesting exceeds {MAX_JSON_DEPTH} container levels")
                children = node.values() if isinstance(node, dict) else node
                pending.extend((child, depth + 1) for child in children)
        return value
    except CatalogError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise CatalogError(f"cannot read {path}: {exc}") from exc


def _object(value: Any, where: str, required: set[str], optional: set[str] | None = None) -> dict:
    if not isinstance(value, dict):
        raise CatalogError(f"{where}: expected object")
    missing = required - value.keys()
    extra = value.keys() - required - (optional or set())
    if missing or extra:
        raise CatalogError(f"{where}: missing={sorted(missing)}, unknown={sorted(extra)}")
    return value


def _text(value: Any, where: str, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise CatalogError(f"{where}: expected nonempty text of at most 2000 characters")
    return value


def _integer(value: Any, where: str, minimum: int = 0, maximum: int = 36500) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise CatalogError(f"{where}: integer required in [{minimum}, {maximum}]")
    return value


def _date(value: Any, where: str, nullable: bool = False) -> date | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise CatalogError(f"{where}: expected YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CatalogError(f"{where}: invalid calendar date") from exc


def _timestamp(value: Any, where: str) -> datetime:
    _text(value, where)
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalogError(f"{where}: invalid timestamp") from exc
    if instant.tzinfo is None:
        raise CatalogError(f"{where}: explicit timezone required")
    try:
        return instant.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise CatalogError(f"{where}: timestamp is outside the supported UTC range") from exc


def _id(value: Any, where: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise CatalogError(f"{where}: expected safe stable identifier")
    return value


def validate_catalog(value: Any) -> dict:
    top = _object(value, "catalog", {"schema", "catalog_id", "synthetic", "fixtures"})
    if top["schema"] != SCHEMA or top["synthetic"] is not True:
        raise CatalogError("catalog must use the supported schema and explicitly mark synthetic=true")
    _id(top["catalog_id"], "catalog_id")
    items = top["fixtures"]
    if not isinstance(items, list) or len(items) > MAX_CATALOG_ITEMS:
        raise CatalogError("fixtures must be a list of at most 1000 items")
    seen: set[str] = set()
    required = {"id", "group", "service", "version", "generator", "purpose", "owner_role",
                "last_refreshed", "review_interval_days", "source_interface_version",
                "target_interface_version", "required_boundaries", "maintenance_hours",
                "retired_on", "cleanup_after_days", "cleanup_evidence", "refresh_evidence",
                "parameters"}
    for n, item in enumerate(items):
        w = f"fixtures[{n}]"
        _object(item, w, required)
        key = _id(item["id"], f"{w}.id")
        if key in seen:
            raise CatalogError(f"duplicate fixture id: {key}")
        seen.add(key)
        if not isinstance(item["group"], str) or item["group"] not in GROUPS:
            raise CatalogError(f"{w}: group must be ESS, RIS, or IAM")
        if not isinstance(item["generator"], str) or item["generator"] not in KINDS:
            raise CatalogError(f"{w}: unsupported generator")
        for field in ("service", "version", "purpose", "source_interface_version"):
            _text(item[field], f"{w}.{field}")
        for field in ("owner_role", "target_interface_version", "cleanup_evidence", "refresh_evidence"):
            _text(item[field], f"{w}.{field}", nullable=True)
        refreshed = _date(item["last_refreshed"], f"{w}.last_refreshed", nullable=True)
        retired = _date(item["retired_on"], f"{w}.retired_on", nullable=True)
        if refreshed and retired and refreshed > retired:
            raise CatalogError(f"{w}: refresh after retirement requires a new active version")
        for field in ("review_interval_days", "cleanup_after_days"):
            _integer(item[field], f"{w}.{field}")
        boundaries = item["required_boundaries"]
        if (not isinstance(boundaries, list) or not boundaries or
                any(not isinstance(x, str) or x not in BOUNDARY for x in boundaries) or
                len(set(boundaries)) != len(boundaries)):
            raise CatalogError(f"{w}: required_boundaries must be unique supported boundary names")
        effort = item["maintenance_hours"]
        if effort is not None:
            _object(effort, f"{w}.maintenance_hours", {"low", "high"})
            for field in ("low", "high"):
                _integer(effort[field], f"{w}.maintenance_hours.{field}", maximum=10000)
            if effort["low"] > effort["high"]:
                raise CatalogError(f"{w}: effort low exceeds high")
        params = _object(item["parameters"], f"{w}.parameters", {"start", "end"})
        start = _timestamp(params["start"], f"{w}.start")
        end = _timestamp(params["end"], f"{w}.end")
        if start >= end:
            raise CatalogError(f"{w}: start must be earlier than end")
        if "inside" in boundaries and end - start < timedelta(microseconds=2):
            raise CatalogError(f"{w}: inside boundary requires a representable interior instant")
        if "before" in boundaries and start == datetime.min.replace(tzinfo=timezone.utc):
            raise CatalogError(f"{w}: before boundary is outside the timestamp range")
        if "after" in boundaries and end == datetime.max.replace(tzinfo=timezone.utc):
            raise CatalogError(f"{w}: after boundary is outside the timestamp range")
    if len(canonical(top)) > MAX_BYTES:
        raise CatalogError("canonical catalog exceeds the supported 8 MiB bundle-member size")
    return top


def assess_catalog(catalog: dict, as_of: date) -> dict:
    validate_catalog(catalog)
    findings: list[dict] = []
    rows = []
    for item in sorted(catalog["fixtures"], key=lambda row: row["id"]):
        issues = []
        def flag(code: str, state: str, question: str) -> None:
            finding = {"fixture_id": item["id"], "code": code, "state": state,
                       "owner_role": item["owner_role"], "follow_up": question,
                       "maintenance_hours": item["maintenance_hours"]}
            findings.append(finding)
            issues.append(code)
        refreshed = _date(item["last_refreshed"], "last_refreshed", nullable=True)
        retired = _date(item["retired_on"], "retired_on", nullable=True)
        retired_now = retired is not None and retired <= as_of
        age = (as_of - refreshed).days if refreshed else None
        if item["owner_role"] is None:
            flag("OWNER_UNKNOWN", "unknown", "Who owns refresh, compatibility review, and retirement?")
        if item["target_interface_version"] is None:
            flag("TARGET_VERSION_UNKNOWN", "unknown", "Which interface revision is currently the review target?")
        elif item["source_interface_version"] != item["target_interface_version"]:
            flag("INTERFACE_REVIEW_REQUIRED", "follow_up", "Review the version difference; a label mismatch does not prove breakage.")
        if refreshed is None:
            flag("REFRESH_DATE_UNKNOWN", "unknown", "Provide the last completed refresh record and its exact fixture version.")
        elif age < 0:
            flag("FUTURE_REFRESH_RECORD", "inconsistent", "Reconcile this refresh date with the assessment cut-off.")
        elif not retired_now and age > item["review_interval_days"]:
            flag("REVIEW_OVERDUE", "follow_up", "Confirm representativeness and record whether regeneration or no change is justified.")
        if item["refresh_evidence"] is None:
            flag("REFRESH_EVIDENCE_UNKNOWN", "unknown", "Supply evidence of the completed refresh, not only an intended cadence.")
        if item["maintenance_hours"] is None:
            flag("EFFORT_UNKNOWN", "unknown", "Estimate preparation, refresh, verification, and cleanup effort as a range.")
        if retired_now:
            if item["cleanup_evidence"] is None:
                days = (as_of - retired).days
                state = "follow_up" if days > item["cleanup_after_days"] else "unknown"
                flag("CLEANUP_UNVERIFIED", state, "Request a cleanup disposition or retention exception; do not infer deletion from a plan.")
            state = "retired"
        else:
            state = "active"
            if item["cleanup_evidence"] is not None:
                flag("CLEANUP_RECORD_WITHOUT_EFFECTIVE_RETIREMENT", "inconsistent", "Explain the cleanup record for this active fixture; use a separate retired version when appropriate.")
        if set(item["required_boundaries"]) != set(BOUNDARY):
            flag("BOUNDARY_PLAN_PARTIAL", "follow_up", "Explain omitted temporal boundaries and the associated testing limitation.")
        rows.append({"id": item["id"], "group": item["group"], "service": item["service"],
                     "version": item["version"], "lifecycle": state, "age_days": age,
                     "issues": issues, "planned_case_count": len(item["required_boundaries"]),
                     "executed_application_cases": None})
    counts = {kind: sum(f["state"] == kind for f in findings)
              for kind in ("unknown", "follow_up", "inconsistent")}
    return {"schema": "tjlabs.testdata.review.v1", "as_of": as_of.isoformat(),
            "catalog_sha256": digest(canonical(catalog)), "notice": SYNTHETIC_NOTICE,
            "summary": {"fixture_count": len(rows), "counts": counts,
                        "assessment_state": "NOT_ASSESSED" if not rows else "REVIEW_INPUT_ONLY"},
            "fixtures": rows, "findings": findings}


def generate_cases(item: dict) -> list[dict]:
    start = _timestamp(item["parameters"]["start"], "start")
    end = _timestamp(item["parameters"]["end"], "end")
    times = {"before": lambda: start - timedelta(microseconds=1), "at_start": lambda: start,
             "inside": lambda: start + (end - start) / 2, "at_end": lambda: end,
             "after": lambda: end + timedelta(microseconds=1)}
    cases = []
    for boundary in BOUNDARY:
        if boundary not in item["required_boundaries"]:
            continue
        instant = times[boundary]()
        active = start <= instant < end
        params = {"start_inclusive": start.isoformat(), "end_exclusive": end.isoformat(),
                  "at": instant.isoformat(), "synthetic_subject_id": "SYNTHETIC-0001"}
        if item["generator"] == "term_window":
            expectation = {"term_active": active, "academic_title": "Synthetic term — Δ"}
        elif item["generator"] == "funding_window":
            expectation = {"funding_period_active": active, "allocation_decimal": "1000.00" if active else "0.00"}
        else:
            expectation = {"effective_roles": ["synthetic-contractor"] if active else [],
                           "stale_previous_role_must_not_persist": boundary in ("at_end", "after")}
        cases.append({"case_id": f"{item['id']}--{boundary}", "boundary": boundary,
                      "synthetic": True, "inputs": params, "reference_expectation": expectation,
                      "application_observation": None,
                      "contract_assumption": "Half-open effective interval [start,end); confirm the application's actual rule before use."})
    return cases


def _normalized_catalog(catalog: dict) -> dict:
    return {**catalog, "fixtures": sorted(catalog["fixtures"], key=lambda x: x["id"])}


def build_bundle(catalog: dict, as_of: date) -> dict[str, bytes]:
    validate_catalog(catalog)
    catalog = _normalized_catalog(catalog)
    files = {"catalog.json": canonical(catalog),
             "review.json": canonical(assess_catalog(catalog, as_of))}
    for item in catalog["fixtures"]:
        payload = {"schema": "tjlabs.testdata.fixture.v1", "fixture_id": item["id"],
                   "fixture_version": item["version"], "generator_version": GENERATOR_VERSION,
                   "definition_sha256": digest(canonical(item)), "notice": SYNTHETIC_NOTICE,
                   "cases": generate_cases(item)}
        files[f"fixtures/{item['id']}.json"] = canonical(payload)
    manifest = {"schema": BUNDLE_SCHEMA, "generator_version": GENERATOR_VERSION,
                "as_of": as_of.isoformat(), "notice": SYNTHETIC_NOTICE,
                "catalog_sha256": digest(files["catalog.json"]),
                "files": [{"path": name, "sha256": digest(data), "bytes": len(data)}
                          for name, data in sorted(files.items())]}
    files["manifest.json"] = canonical(manifest)
    return files


def write_bundle(files: dict[str, bytes], destination: Path) -> None:
    # A fresh directory protects evidence/version history. Never delete old data.
    if destination.exists():
        raise CatalogError(f"destination already exists: {destination}; use a new version directory")
    destination.mkdir(parents=True)
    for name, data in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def verify_bundle(root: Path) -> dict:
    root = root.resolve()
    if (root / "manifest.json").is_symlink():
        raise CatalogError("bundle manifest symlinks are not supported")
    manifest = load_json(root / "manifest.json")
    _object(manifest, "manifest", {"schema", "generator_version", "as_of", "notice", "catalog_sha256", "files"})
    if manifest["schema"] != BUNDLE_SCHEMA or manifest["generator_version"] != GENERATOR_VERSION:
        raise CatalogError("unsupported bundle/generator version")
    as_of = _date(manifest["as_of"], "manifest.as_of")
    if not isinstance(manifest["files"], list) or len(manifest["files"]) > MAX_CATALOG_ITEMS + 2:
        raise CatalogError("invalid manifest file collection")
    seen = set()
    for record in manifest["files"]:
        _object(record, "manifest.files[]", {"path", "sha256", "bytes"})
        name = record["path"]
        if not isinstance(name, str) or not name or "\\" in name:
            raise CatalogError("invalid bundle path")
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or str(relative) != name or name in seen:
            raise CatalogError("noncanonical or duplicate bundle path")
        seen.add(name)
        if not isinstance(record["sha256"], str) or not SHA.fullmatch(record["sha256"]):
            raise CatalogError("invalid manifest digest")
        _integer(record["bytes"], "manifest.bytes", maximum=MAX_BYTES)
        candidate = root / relative
        if candidate.is_symlink() or any(p.is_symlink() for p in candidate.parents if p != root and root in p.parents):
            raise CatalogError("bundle symlinks are not supported")
        if not candidate.resolve().is_relative_to(root):
            raise CatalogError("bundle path escapes root")
        try:
            if candidate.stat().st_size != record["bytes"]:
                raise CatalogError(f"size mismatch: {name}")
            data = candidate.read_bytes()
        except OSError as exc:
            raise CatalogError(f"missing/unreadable bundle member: {name}") from exc
        if digest(data) != record["sha256"]:
            raise CatalogError(f"digest mismatch: {name}")
    expected = build_bundle(validate_catalog(load_json(root / "catalog.json")), as_of)
    actual_paths = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() or p.is_symlink()}
    if actual_paths != set(expected):
        raise CatalogError("bundle contains missing or extra members")
    # Byte regeneration prevents an internally rehashed but altered expectation
    # from passing. This is reproducibility, not authentication or attestation.
    for name, data in expected.items():
        if (root / name).read_bytes() != data:
            raise CatalogError(f"not reproducible from this catalog/generator: {name}")
    return {"state": "REPRODUCIBLE_SYNTHETIC_BUNDLE", "files": len(expected),
            "manifest_sha256": digest(expected["manifest.json"]), "notice": SYNTHETIC_NOTICE}


def render_review(review: dict) -> str:
    def escaped(text: Any) -> str:
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    lines = ["# Test-data maintenance review", "", review["notice"], "",
             f"Cut-off: {review['as_of']}", f"Catalog SHA-256: `{review['catalog_sha256']}`", "",
             "| Fixture | Group | Lifecycle | Age in days | Planned cases | Follow-up codes |",
             "|---|---|---|---:|---:|---|"]
    for row in review["fixtures"]:
        values = [row["id"], row["group"], row["lifecycle"],
                  "UNKNOWN" if row["age_days"] is None else row["age_days"],
                  row["planned_case_count"], ", ".join(row["issues"]) or "No metadata follow-ups"]
        lines.append("| " + " | ".join(escaped(v) for v in values) + " |")
    lines.extend(["", "## Interview and artifact follow-ups", ""])
    for finding in review["findings"]:
        lines.append(f"- **{escaped(finding['fixture_id'])} / {finding['code']}** ({finding['state']}): {escaped(finding['follow_up'])}")
    lines.extend(["", "A listed evidence reference is a supplied pointer, not a verified artifact. No application tests were run.", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "assess", "generate"):
        command = sub.add_parser(name)
        command.add_argument("catalog", type=Path)
        if name != "validate":
            command.add_argument("--as-of", required=True, help="Explicit YYYY-MM-DD cut-off")
        if name == "assess":
            command.add_argument("--format", choices=("json", "markdown"), default="json")
        if name == "generate":
            command.add_argument("--out", type=Path, required=True)
    command = sub.add_parser("verify-bundle")
    command.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-bundle":
            result = verify_bundle(args.directory)
        else:
            catalog = validate_catalog(load_json(args.catalog))
            if args.command == "validate":
                result = {"state": "CATALOG_VALID", "fixtures": len(catalog["fixtures"]), "notice": SYNTHETIC_NOTICE}
            else:
                as_of = _date(args.as_of, "as_of")
                if args.command == "assess":
                    result = assess_catalog(catalog, as_of)
                    if args.format == "markdown":
                        print(render_review(result), end="")
                        return 0
                else:
                    write_bundle(build_bundle(catalog, as_of), args.out)
                    result = verify_bundle(args.out)
        print(canonical(result).decode("utf-8"), end="")
        return 0
    except (CatalogError, OSError, OverflowError) as exc:
        print(f"fixture-lab: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
