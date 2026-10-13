#!/usr/bin/env python3
"""Offline release-record consistency inspector; not an authenticity verifier."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime
from pathlib import Path
import re
import sys
from typing import Any

LIMITATION = ("Record consistency only: no signature, builder-trust, approval authority, "
              "live deployment, dependency completeness or SLSA-level verification. "
              "Missing or conflicting records do not establish compromise.")
TEXT = {"type": "string", "minLength": 1, "pattern": r"\S"}
SHA256 = {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"}
REVISION = {"type": ["string", "null"], "pattern": "^(?:[0-9a-f]{40}|[0-9a-f]{64})$"}
TIME = {"type": ["string", "null"], "format": "date-time"}
MAYBE = {"type": ["string", "null"], "minLength": 1, "pattern": r"\S"}


def obj(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


def schema() -> dict:
    """The same small JSON Schema subset drives documentation and validation."""
    records = {
        "evidence": obj({"id": TEXT, "locator": TEXT, "owner_role": MAYBE,
            "kind": {"enum": ["synthetic", "artifact", "interview"]}, "captured_at": TIME}),
        "sources": obj({"id": TEXT, "repository": MAYBE, "revision": REVISION,
            "approved_revision": REVISION, "approved_at": TIME, "approval_evidence_id": MAYBE}),
        "builds": obj({"id": TEXT, "source_id": MAYBE, "observed_repository": MAYBE, "observed_revision": REVISION,
            "builder_id": MAYBE, "recipe_uri": MAYBE, "recipe_sha256": SHA256,
            "started_at": TIME, "finished_at": TIME, "evidence_id": MAYBE,
            "input_coverage": {"enum": ["declared_complete", "partial", "unknown"]},
            "materials": {"type": "array", "items": obj({"uri": TEXT, "sha256": SHA256})}}),
        "artifacts": obj({"id": TEXT, "build_id": MAYBE, "version": MAYBE,
            "sha256": SHA256, "local_path": MAYBE, "evidence_id": MAYBE}),
        "deployments": obj({"id": TEXT, "artifact_id": MAYBE, "environment": MAYBE,
            "observed_version": MAYBE, "observed_sha256": SHA256,
            "observed_at": TIME, "evidence_id": MAYBE}),
    }
    properties = {"schema_version": {"const": 1}, "packet_id": TEXT,
                  "data_class": {"enum": ["synthetic", "assessment"]}}
    properties.update({name: {"type": "array", "items": record}
                       for name, record in records.items()})
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Release provenance assessment packet v1", **obj(properties)}


def timestamp(value: str) -> datetime:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value):
        raise ValueError("expected a timestamp with seconds and an explicit timezone")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed


def validate(value: Any, rule: dict | None = None, path: str = "$") -> None:
    rule = schema() if rule is None else rule
    if "const" in rule and (type(value) is not type(rule["const"]) or value != rule["const"]):
        raise ValueError(f"{path}: expected {rule['const']!r}")
    if "enum" in rule and value not in rule["enum"]:
        raise ValueError(f"{path}: unexpected value")
    types = rule.get("type", [])
    types = [types] if isinstance(types, str) else types
    actual = {dict: "object", list: "array", str: "string", type(None): "null"}.get(type(value))
    if types and actual not in types:
        raise ValueError(f"{path}: expected {' or '.join(types)}")
    if value is None:
        return
    if isinstance(value, dict):
        props = rule.get("properties", {})
        missing = set(rule.get("required", [])) - value.keys()
        extra = value.keys() - props.keys()
        if missing or (extra and rule.get("additionalProperties") is False):
            raise ValueError(f"{path}: missing={sorted(missing)}, unexpected={sorted(extra)}")
        for key, item in value.items():
            validate(item, props.get(key, {}), f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate(item, rule.get("items", {}), f"{path}[{index}]")
    elif isinstance(value, str):
        if len(value) < rule.get("minLength", 0) or ("pattern" in rule and not re.search(rule["pattern"], value)):
            raise ValueError(f"{path}: invalid string")
        if rule.get("format") == "date-time":
            try:
                timestamp(value)
            except ValueError as exc:
                raise ValueError(f"{path}: {exc}") from exc


def inspect(packet: dict, artifact_root: Path | None = None) -> dict:
    validate(packet)
    tables = {}
    for name in ("evidence", "sources", "builds", "artifacts", "deployments"):
        rows = packet[name]
        tables[name] = {row["id"]: row for row in rows}
        if len(tables[name]) != len(rows):
            raise ValueError(f"$.{name}: duplicate record IDs are ambiguous")
    checks: list[dict] = []
    traces: list[dict] = []

    def emit(status: str, code: str, path: str, detail: str, follow_up: str = "") -> None:
        checks.append(dict(status=status, code=code, path=path, detail=detail, follow_up=follow_up))

    def present(value: Any, path: str) -> bool:
        if value is None:
            emit("UNKNOWN", "MISSING_VALUE", path, "Value not supplied.", "Recover the existing source record; do not infer a value.")
            return False
        return True

    def link(table: str, key: str | None, path: str) -> dict | None:
        found = tables[table].get(key)
        if found is None:
            emit("UNKNOWN", "MISSING_LINK", path, f"No {table} record for {key!r}.", f"Request the matching {table} record and its source locator.")
        else:
            emit("LINKED", "RECORD_LINK", path, f"Resolved {table}/{key}.")
        return found

    def evidence(key: str | None, path: str) -> None:
        record = link("evidence", key, path)
        if record is not None:
            present(record["owner_role"], path + ".owner_role")
            present(record["captured_at"], path + ".captured_at")
            if record["kind"] == "interview":
                emit("UNKNOWN", "INTERVIEW_ONLY", path, "Statement has no artifact corroboration in this link.", "Request a concrete release example or retain this as an interview statement.")
            if packet["data_class"] == "assessment" and record["kind"] == "synthetic":
                emit("UNKNOWN", "SYNTHETIC_EVIDENCE", path, "Fictional evidence cannot establish an assessed practice.", "Use supplied assessment evidence, or label the whole packet synthetic.")

    def equal(left: Any, right: Any, path: str) -> None:
        left_present = present(left, path + ".expected")
        right_present = present(right, path + ".observed")
        if left_present and right_present:
            emit("LINKED" if left == right else "MISMATCH", "VALUE_MATCH" if left == right else "VALUE_MISMATCH", path,
                 f"expected={left!r}; observed={right!r}", "" if left == right else "Reconcile original records, build attempts and release identity; mismatch alone is not compromise.")

    def before(left: str | None, right: str | None, path: str) -> None:
        left_present = present(left, path + ".earlier")
        right_present = present(right, path + ".later")
        if left_present and right_present:
            valid = timestamp(left) <= timestamp(right)
            emit("LINKED" if valid else "MISMATCH", "TIME_ORDER" if valid else "TIME_INVERSION", path,
                 f"{left} <= {right}", "" if valid else "Check clock conventions, export times and the selected build attempt.")

    if not packet["deployments"]:
        emit("UNKNOWN", "NO_DEPLOYMENTS", "$.deployments", "No observed release supplied.", "Sample a deployment record before making a chain claim.")
    for deployment in packet["deployments"]:
        path = "deployments/" + deployment["id"]
        trace = {"deployment_id": deployment["id"], "artifact_id": None,
                 "build_id": None, "source_id": None, "checks_start": len(checks)}
        traces.append(trace)
        evidence(deployment["evidence_id"], path + ".evidence_id")
        present(deployment["environment"], path + ".environment")
        artifact = link("artifacts", deployment["artifact_id"], path + ".artifact_id")
        if artifact is None:
            continue
        trace["artifact_id"] = artifact["id"]
        evidence(artifact["evidence_id"], path + ".artifact.evidence_id")
        equal(artifact["sha256"], deployment["observed_sha256"], path + ".artifact_digest")
        equal(artifact["version"], deployment["observed_version"], path + ".version_label")
        if artifact_root is not None:
            name = artifact["local_path"]
            if present(name, path + ".artifact.local_path"):
                root = Path(artifact_root).resolve()
                relative = Path(name)
                file = (root / relative).resolve()
                if relative.is_absolute() or ".." in relative.parts or "\\" in name or not file.is_relative_to(root):
                    emit("UNKNOWN", "OUTSIDE_ARTIFACT_ROOT", path, "Local artifact path is not a contained relative path.", "Supply a copy of the intended artifact inside the selected root.")
                elif not file.is_file():
                    emit("UNKNOWN", "ARTIFACT_UNAVAILABLE", path, "Local artifact bytes unavailable.", "Recover the exact artifact, not a rebuilt substitute.")
                else:
                    try:
                        digest = hashlib.sha256()
                        with file.open("rb") as stream:
                            for block in iter(lambda: stream.read(1024 * 1024), b""):
                                digest.update(block)
                        equal(artifact["sha256"], digest.hexdigest(), path + ".local_bytes")
                    except OSError:
                        emit("UNKNOWN", "ARTIFACT_UNREADABLE", path, "Could not read local artifact bytes.", "Check file availability and retry the explicit local inspection.")
        build = link("builds", artifact["build_id"], path + ".build_id")
        if build is None:
            continue
        trace["build_id"] = build["id"]
        evidence(build["evidence_id"], path + ".build.evidence_id")
        for field in ("builder_id", "recipe_uri", "recipe_sha256"):
            present(build[field], path + ".build." + field)
        before(build["started_at"], build["finished_at"], path + ".build_interval")
        before(build["finished_at"], deployment["observed_at"], path + ".build_to_deployment")
        if build["input_coverage"] != "declared_complete" or not build["materials"]:
            emit("UNKNOWN", "INPUT_COVERAGE", path + ".build.materials", "Resolved-input inventory is empty, partial or unknown.", "Ask which build inputs were captured and which were not.")
        uris = [material["uri"] for material in build["materials"]]
        if len(set(uris)) != len(uris):
            emit("MISMATCH", "AMBIGUOUS_MATERIAL", path + ".build.materials", "A material URI occurs more than once.", "Distinguish resolved versions and their roles before reconciling.")
        for index, material in enumerate(build["materials"]):
            if present(material["sha256"], path + f".build.materials[{index}].sha256"):
                emit("LINKED", "RESOLVED_INPUT", path + f".build.materials[{index}]",
                     f"Recorded input {material['uri']} at sha256:{material['sha256']}; inventory completeness is only declared.")
        source = link("sources", build["source_id"], path + ".source_id")
        if source is not None:
            trace["source_id"] = source["id"]
            equal(source["repository"], build["observed_repository"], path + ".source_repository")
            equal(source["revision"], build["observed_revision"], path + ".source_revision")
            equal(source["revision"], source["approved_revision"], path + ".approved_revision")
            evidence(source["approval_evidence_id"], path + ".source.approval_evidence_id")
            before(source["approved_at"], deployment["observed_at"], path + ".approval_to_deployment")
    for index, trace in enumerate(traces):
        end = traces[index + 1]["checks_start"] if index + 1 < len(traces) else len(checks)
        trace["checks_end"] = end
        statuses = {c["status"] for c in checks[trace["checks_start"]:end]}
        trace["status"] = "CONTRADICTORY_RECORDS" if "MISMATCH" in statuses else "GAPS" if "UNKNOWN" in statuses else "LINKED_RECORDS"
    statuses = {check["status"] for check in checks}
    return {"schema_version": 1, "packet_id": packet["packet_id"], "data_class": packet["data_class"],
            "status": "CONTRADICTORY_RECORDS" if "MISMATCH" in statuses else "GAPS" if "UNKNOWN" in statuses else "LINKED_RECORDS",
            "scope": "Only chains reachable from supplied deployment records; unused records are not assessed.",
            "local_bytes": "REQUESTED" if artifact_root is not None else "NOT_REQUESTED",
            "limitation": LIMITATION, "traces": traces, "checks": checks}


def markdown(report: dict) -> str:
    def safe(value: Any) -> str:
        return html.escape(str(value)).replace("|", "&#124;").replace("\n", " ").replace("`", "&#96;").replace("[", "&#91;")
    lines = ["# Release-record inspection", "", f"**{report['status']}** | {safe(report['data_class'])}",
             "", safe(report["limitation"]), "", safe(report["scope"]), "",
             f"Local artifact-byte inspection: {report['local_bytes']}.", "",
             "| Status | Code | Record path | Observation / follow-up |", "|---|---|---|---|"]
    for check in report["checks"]:
        lines.append("| " + " | ".join(safe(check[key]) for key in ("status", "code", "path")) + " | " + safe(check["detail"] + " " + check["follow_up"]) + " |")
    return "\n".join(lines) + "\n"


def load(path: Path) -> Any:
    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")
    with path.open("rb") as stream:
        raw = stream.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError("input exceeds 4 MiB")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", nargs="?", type=Path)
    parser.add_argument("--case", help="select a named packet from a fixture collection")
    parser.add_argument("--schema", action="store_true", help="print JSON Schema; no input needed")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--artifact-root", type=Path, help="optionally hash supplied local artifacts; no network")
    args = parser.parse_args(argv)
    try:
        if args.schema:
            print(json.dumps(schema(), indent=2, sort_keys=True))
            return 0
        if args.packet is None:
            parser.error("packet is required unless --schema is used")
        packet = load(args.packet)
        if args.case:
            if not isinstance(packet, dict) or args.case not in packet:
                raise ValueError("fixture case not found")
            packet = packet[args.case]
        report = inspect(packet, args.artifact_root)
        print(json.dumps(report, indent=2, sort_keys=True) if args.format == "json" else markdown(report), end="\n" if args.format == "json" else "")
        return 0 if report["status"] == "LINKED_RECORDS" else 1
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
