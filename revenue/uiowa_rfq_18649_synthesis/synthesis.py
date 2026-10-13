#!/usr/bin/env python3
"""Offline, evidence-preserving cross-group synthesis. No maturity scoring."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

SCHEMA = "uiowa-synthesis/v1"
GROUPS = ("ESS", "RIS", "IAM")
DIMENSIONS = ("software", "security", "deployment", "ai")


class InputError(ValueError):
    """A malformed or internally inconsistent supplied record."""


def text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{where}: nonempty text required")
    return value


def choice(value: Any, options: tuple[str, ...], where: str) -> str:
    if value not in options:
        raise InputError(f"{where}: expected one of {', '.join(options)}")
    return value


def objects(value: Any, where: str) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(x, dict) for x in value):
        raise InputError(f"{where}: array of objects required")
    return value


def unique_rows(rows: list[dict], key: str, where: str) -> dict[str, dict]:
    result = {}
    for i, row in enumerate(rows):
        identity = text(row.get(key), f"{where}[{i}].{key}")
        if identity in result:
            raise InputError(f"{where}: duplicate {key} {identity!r}")
        result[identity] = row
    return result


def refs(row: dict, field: str, sources: dict, where: str) -> list[str]:
    values = row.get(field)
    if not isinstance(values, list) or any(not isinstance(x, str) for x in values):
        raise InputError(f"{where}.{field}: source-ID array required")
    if len(values) != len(set(values)):
        raise InputError(f"{where}.{field}: duplicate source references")
    for identity in values:
        if identity not in sources:
            raise InputError(f"{where}.{field}: unknown source {identity!r}")
    return values


def load_json(raw: str) -> dict:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise InputError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    def nonfinite(value):
        raise InputError(f"non-finite JSON number: {value}")

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(value, dict):
        raise InputError("root: object required")
    return value


def validate(packet: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    if not isinstance(packet, dict) or packet.get("schema") != SCHEMA:
        raise InputError(f"schema must be {SCHEMA}")
    text(packet.get("dataset_id"), "dataset_id")
    choice(packet.get("data_status"), ("synthetic", "engagement_evidence"), "data_status")
    sources = unique_rows(objects(packet.get("sources"), "sources"), "source_id", "sources")
    findings = unique_rows(objects(packet.get("findings"), "findings"), "finding_id", "findings")
    for identity, source in sources.items():
        for field in ("source_ref", "locator", "version", "excerpt"):
            text(source.get(field), f"source {identity}.{field}")
        choice(source.get("evidence_kind"), ("artifact", "metric", "interview", "policy"),
               f"source {identity}.evidence_kind")
        origin = source.get("origin_id")
        if origin is not None:
            text(origin, f"source {identity}.origin_id")
        digest = source.get("content_sha256")
        if digest is not None and (not isinstance(digest, str) or len(digest) != 64
                                  or any(c not in "0123456789abcdef" for c in digest)):
            raise InputError(f"source {identity}.content_sha256: lower-case SHA-256 required")
    for identity, f in findings.items():
        where = f"finding {identity}"
        for field in ("practice_key", "statement", "context", "service_id"):
            text(f.get(field), f"{where}.{field}")
        choice(f.get("group"), GROUPS, f"{where}.group")
        choice(f.get("dimension"), DIMENSIONS, f"{where}.dimension")
        state = choice(f.get("state"), ("strength", "gap", "unknown", "not_applicable"),
                       f"{where}.state")
        basis = choice(f.get("basis"), ("observed", "reported", "unknown"), f"{where}.basis")
        topology = choice(f.get("topology"), ("local", "shared", "unknown"), f"{where}.topology")
        mechanism = choice(f.get("mechanism_basis"), ("supported", "hypothesis", "unknown"),
                           f"{where}.mechanism_basis")
        for field in ("window_start", "window_end"):
            raw = text(f.get(field), f"{where}.{field}")
            try:
                parsed = date.fromisoformat(raw)
            except ValueError as exc:
                raise InputError(f"{where}.{field}: ISO calendar date required") from exc
            if parsed.isoformat() != raw:
                raise InputError(f"{where}.{field}: use YYYY-MM-DD")
        if f["window_start"] > f["window_end"]:
            raise InputError(f"{where}: observation window is reversed")
        for field in ("support_ids", "dissent_ids", "limitation_ids", "mechanism_source_ids"):
            refs(f, field, sources, where)
        if state in ("strength", "gap") and not f["support_ids"]:
            raise InputError(f"{where}: strength/gap requires support; use unknown when missing")
        if state in ("unknown", "not_applicable"):
            text(f.get("rationale"), f"{where}.rationale")
        if basis == "observed" and not any(sources[s]["evidence_kind"] in ("artifact", "metric")
                                          for s in f["support_ids"]):
            raise InputError(f"{where}: observed needs artifact/metric support, not only policy/interview")
        if topology == "shared":
            text(f.get("dependency_id"), f"{where}.dependency_id")
        elif f.get("dependency_id") is not None:
            raise InputError(f"{where}: dependency_id is only meaningful for shared topology")
        if mechanism != "unknown":
            text(f.get("mechanism_id"), f"{where}.mechanism_id")
        elif f.get("mechanism_id") is not None:
            raise InputError(f"{where}: unknown mechanism must have null mechanism_id")
        if mechanism == "supported" and not f["mechanism_source_ids"]:
            raise InputError(f"{where}: supported mechanism requires source references")
    return sources, findings


def correlation_map(sources: dict[str, dict]) -> dict[str, str]:
    """Connected declared origins / equal content; NEVER proof of independence."""
    parents = {identity: identity for identity in sources}

    def root(identity):
        while parents[identity] != identity:
            parents[identity] = parents[parents[identity]]
            identity = parents[identity]
        return identity

    seen = {}
    for identity, source in sorted(sources.items()):
        for field in ("origin_id", "content_sha256"):
            if source.get(field) is None:
                continue
            token = (field, source[field])
            if token in seen:
                left, right = root(identity), root(seen[token])
                parents[max(left, right)] = min(left, right)
            else:
                seen[token] = identity
    return {identity: root(identity) for identity in sources}


def comparison_key(f: dict) -> tuple[str, ...]:
    return tuple(f[key] for key in ("dimension", "practice_key", "window_start", "window_end"))


def theme_key(f: dict) -> tuple[str, ...]:
    if f["state"] in ("unknown", "not_applicable") or f["mechanism_basis"] != "supported":
        # Unknowns / proposed explanations must not become a common cause by coincidence.
        return comparison_key(f) + ("unresolved", f["finding_id"])
    return comparison_key(f) + (f["topology"], f.get("dependency_id") or "", f["mechanism_id"])


def synthesize(packet: dict) -> dict:
    sources, findings = validate(packet)
    clusters = correlation_map(sources)
    buckets: dict[tuple, list[dict]] = {}
    comparisons: dict[tuple, list[dict]] = {}
    for f in findings.values():
        buckets.setdefault(theme_key(f), []).append(f)
        comparisons.setdefault(comparison_key(f), []).append(f)
    themes = []
    for key, members in sorted(buckets.items()):
        members = sorted(members, key=lambda f: f["finding_id"])
        first = members[0]
        peers = comparisons[comparison_key(first)]
        groups = sorted({f["group"] for f in members})
        states = sorted({f["state"] for f in members})
        support = sorted({s for f in members for s in f["support_ids"]})
        dissent = sorted({s for f in members for s in f["dissent_ids"]})
        limitations = sorted({s for f in members for s in f["limitation_ids"]})
        causes = sorted({s for f in members for s in f["mechanism_source_ids"]})
        unresolved = (any(f["mechanism_basis"] != "supported" or f["topology"] == "unknown"
                          or f["state"] in ("unknown", "not_applicable") for f in members))
        disputed = bool(dissent) or ("strength" in states and "gap" in states)
        if unresolved:
            relationship = "unresolved_or_inapplicable"
        elif first["topology"] == "shared":
            relationship = "shared_capability" if states == ["strength"] else "inherited_dependency"
        elif len(groups) > 1:
            relationship = "repeated_local_practice"
        elif any(theme_key(p) != key and p["state"] in ("strength", "gap") for p in peers):
            relationship = "local_exception"
        else:
            relationship = "local_pattern"
        basis = "observed" if all(f["basis"] == "observed" for f in members) else "reported_or_mixed"
        if unresolved or disputed or basis != "observed":
            action = "focused_follow_up"
        elif first["topology"] == "shared":
            action = "coordinate_shared_owner_and_verify_group_effects"
        elif len(groups) > 1:
            action = "coordinate_options_keep_group_implementation"
        else:
            action = "group_specific_action"
        used = sorted(set(support + dissent + limitations + causes))
        themes.append({
            "theme_id": "TH-" + hashlib.sha256(json.dumps(key).encode()).hexdigest()[:12],
            "dimension": first["dimension"], "practice_key": first["practice_key"],
            "window_start": first["window_start"], "window_end": first["window_end"],
            "relationship": relationship, "states": states, "basis": basis,
            "status": "unresolved" if unresolved else "contested" if disputed else "sample_supported",
            "groups": groups, "groups_not_covered_by_this_theme": sorted(set(GROUPS) - set(groups)),
            "coverage_scope": "sampled_all_three_groups" if len(groups) == 3 else "sampled_groups_only",
            "finding_ids": [f["finding_id"] for f in members],
            "related_findings_outside_theme": sorted(f["finding_id"] for f in peers if theme_key(f) != key),
            "support_ids": support, "dissent_ids": dissent, "limitation_ids": limitations,
            "mechanism_source_ids": causes, "source_count": len(support),
            "declared_support_clusters": len({clusters[s] for s in support}),
            "unknown_origin_ids": [s for s in support if sources[s].get("origin_id") is None],
            "support_cluster_members": {c: sorted(s for s in support if clusters[s] == c)
                                        for c in sorted({clusters[s] for s in support})},
            "recommendation_shape": action,
            "proposed_owner_role": "shared service owner with affected group leads"
                if first["topology"] == "shared" else "affected group practice owners",
            "findings": members, "sources": [sources[s] for s in used],
            "inference_limit": "Supplied sample and analyst annotations only; no population prevalence, "
                "independence, causal proof, maturity, approval or University finding is established.",
        })
    return {"schema": "uiowa-synthesis-report/v1", "dataset_id": packet["dataset_id"],
            "data_status": packet["data_status"], "themes": themes,
            "unreferenced_source_ids": sorted(set(sources) - {
                s["source_id"] for theme in themes for s in theme["sources"]}),
            "interpretation": "Group reach is not corroboration. Correlation clusters are declared, "
                "not proven independent; competing explanations and all evidence roles remain visible."}


def cell(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(
        "|", "&#124;").replace("\r", " ").replace("\n", "<br>")


def render_markdown(report: dict) -> str:
    lines = ["# Cross-group synthesis", "", f"Data status: **{cell(report['data_status'])}**. "
             f"Dataset: {cell(report['dataset_id'])}.", "", report["interpretation"], "",
             "| Theme | Practice | Groups | Relationship | Status | Sources / declared clusters | Action |",
             "|---|---|---|---|---|---|---|"]
    for t in report["themes"]:
        lines.append("| " + " | ".join(cell(x) for x in (t["theme_id"], t["practice_key"],
            ", ".join(t["groups"]), t["relationship"], t["status"],
            f"{t['source_count']} / {t['declared_support_clusters']}", t["recommendation_shape"])) + " |")
    for t in report["themes"]:
        lines.extend(["", "## " + t["theme_id"], "", f"Window: {t['window_start']} to {t['window_end']}. "
                      f"Scope: {t['coverage_scope']}. Basis: {t['basis']}.", "",
                      "Groups not covered by this theme: " + (", ".join(t["groups_not_covered_by_this_theme"]) or "none") + ".",
                      "Related findings outside this theme: " + (", ".join(t["related_findings_outside_theme"]) or "none") + ".",
                      "", "Proposed owner role: " + t["proposed_owner_role"] + ".", ""])
        for f in t["findings"]:
            lines.append(f"- **{cell(f['finding_id'])} / {f['group']} / {f['state']}**: "
                         f"{cell(f['statement'])} Context: {cell(f['context'])} "
                         f"Supports: {cell(', '.join(f['support_ids']) or 'none')}; "
                         f"dissent: {cell(', '.join(f['dissent_ids']) or 'none')}; "
                         f"limitations: {cell(', '.join(f['limitation_ids']) or 'none')}. "
                         f"Mechanism: {cell(f.get('mechanism_id') or 'unknown')} "
                         f"({f['mechanism_basis']}); sources: {cell(', '.join(f['mechanism_source_ids']) or 'none')}. "
                         f"{cell(f.get('rationale', ''))}")
        for s in t["sources"]:
            lines.append(f"- Source **{cell(s['source_id'])}**, {cell(s['evidence_kind'])}, "
                         f"version {cell(s['version'])}, origin {cell(s.get('origin_id') or 'UNKNOWN')}: "
                         f"{cell(s['source_ref'])} — {cell(s['locator'])}. {cell(s['excerpt'])}")
        lines.extend(["", t["inference_limit"]])
    return "\n".join(lines) + "\n"


def render_csv(report: dict) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    fields = ("theme_id", "dimension", "practice_key", "groups", "relationship", "status", "basis",
              "source_count", "declared_support_clusters", "finding_ids", "support_ids", "dissent_ids",
              "limitation_ids", "recommendation_shape")
    writer.writerow(fields)
    for theme in report["themes"]:
        row = []
        for key in fields:
            value = theme[key]
            value = json.dumps(value, ensure_ascii=False) if isinstance(value, list) else str(value)
            # Presentation-only protection: JSON remains the exact interchange format.
            if value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            row.append(value)
        writer.writerow(row)
    return stream.getvalue()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--format", choices=("json", "markdown", "csv"), default="json")
    args = parser.parse_args(argv)
    try:
        report = synthesize(load_json(args.packet.read_text(encoding="utf-8")))
        output = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
                  if args.format == "json" else render_markdown(report)
                  if args.format == "markdown" else render_csv(report))
        sys.stdout.write(output)
    except (InputError, OSError, UnicodeError) as exc:
        print(f"synthesis: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
