#!/usr/bin/env python3
"""Offline AI lifecycle evidence analysis. No model execution or network access."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COMPONENTS = ("model", "prompt", "input_snapshot", "evaluation_set", "rubric",
              "code", "environment", "configuration")
METRICS = ("correctness", "completeness", "usefulness", "repair_minutes", "latency_ms")
KINDS = COMPONENTS + ("case_input", "expectation", "output", "investigation")
ID = {"type": "string", "pattern": r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$"}
TEXT = {"type": "string", "minLength": 1}
STAMP = {"type": "string", "minLength": 1}
NULL_TEXT = {"type": ["string", "null"], "minLength": 1}
REF = {"type": ["string", "null"], "pattern": ID["pattern"]}


def obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


def arr(items: dict[str, Any], minimum: int = 0) -> dict[str, Any]:
    return {"type": "array", "items": items, "minItems": minimum}


def num(maximum: int | None = None) -> dict[str, Any]:
    result = {"type": ["number", "null"], "minimum": 0}
    if maximum is not None:
        result["maximum"] = maximum
    return result


SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "UIOWA-079 AI lifecycle metadata, version 1.0",
    **obj({
        "schema_version": {"type": "string", "enum": ["1.0"]},
        "synthetic": {"type": "boolean"}, "workflow_id": ID,
        "group": {"type": "string", "enum": ["ESS", "RIS", "IAM", "cross-group"]},
        "description": TEXT,
        "artifacts": arr(obj({
            "id": ID, "kind": {"type": "string", "enum": list(KINDS)},
            "sha256": {"type": ["string", "null"], "pattern": r"^[0-9a-f]{64}$"},
            "locator": TEXT, "retained": {"type": "boolean"},
            "text": {"type": ["string", "null"]},
        })),
        "cases": arr(obj({"id": ID, "input_ref": ID, "expectation_ref": ID,
                           "stratum": {"type": "string", "enum": ["ordinary", "ambiguous", "stale-context", "missing-information"]}}), 1),
        "evaluation_sets": arr(obj({"artifact_ref": ID, "protocol_id": ID, "case_ids": arr(ID, 1)}), 1),
        "versions": arr(obj({
            "id": ID, "parent_id": REF, "changed_at": STAMP, "reason": TEXT,
            "support_owner": NULL_TEXT, "model_revision": NULL_TEXT,
            "model_alias_is_mutable": {"type": "boolean"},
            "seed": {"type": ["integer", "null"]},
            "components": obj({key: REF for key in COMPONENTS}),
        }), 1),
        "runs": arr(obj({
            "id": ID, "version_id": ID, "started_at": STAMP, "finished_at": STAMP,
            "observations": arr(obj({
                "case_id": ID, "output_ref": REF, "error": NULL_TEXT,
                "correctness": {"type": ["boolean", "null"]},
                "completeness": num(1), "usefulness": num(1),
                "repair_minutes": num(), "latency_ms": num(),
            })),
        })),
        "comparisons": arr(obj({"id": ID, "baseline_run": ID, "candidate_run": ID})),
        "replays": arr(obj({"id": ID, "original_run": ID, "repeat_run": ID})),
        "events": arr(obj({
            "id": ID, "version_id": ID, "occurred_at": STAMP,
            "kind": {"type": "string", "enum": ["observation", "incident", "investigation", "resolution", "decision"]},
            "summary": TEXT, "owner": NULL_TEXT, "related_run_ids": arr(ID),
            "evidence_refs": arr(ID), "resolves_event_id": REF,
        })),
    }),
}


class ContractError(ValueError):
    """Input metadata is malformed, contradictory, or contains broken references."""


def fail(message: str) -> None:
    raise ContractError(message)


def check_schema(value: Any, spec: dict[str, Any], path: str = "$") -> None:
    """Validate the deliberately small JSON Schema vocabulary used above."""
    types = spec.get("type", [])
    types = [types] if isinstance(types, str) else types
    valid = {"null": value is None, "boolean": type(value) is bool,
             "string": isinstance(value, str), "object": isinstance(value, dict),
             "array": isinstance(value, list), "integer": type(value) is int,
             "number": type(value) in (int, float)}
    if types and not any(valid[t] for t in types):
        fail(f"{path}: expected {'/'.join(types)}")
    if type(value) in (int, float):
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            fail(f"{path}: number must be finite")
        for key, bad in (("minimum", lambda n: value < n), ("maximum", lambda n: value > n)):
            if key in spec and bad(spec[key]):
                fail(f"{path}: violates {key} {spec[key]}")
    if "enum" in spec and value not in spec["enum"]:
        fail(f"{path}: value not in enum")
    if isinstance(value, str):
        if len(value) < spec.get("minLength", 0) or (spec.get("minLength", 0) and not value.strip()):
            fail(f"{path}: text must not be empty")
        if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
            fail(f"{path}: invalid identifier/digest")
    if isinstance(value, list):
        if len(value) < spec.get("minItems", 0):
            fail(f"{path}: too few items")
        for i, child in enumerate(value):
            check_schema(child, spec["items"], f"{path}[{i}]")
    if isinstance(value, dict):
        properties = spec["properties"]
        missing, extra = set(spec["required"]) - value.keys(), value.keys() - properties.keys()
        if missing or extra:
            fail(f"{path}: missing={sorted(missing)} unexpected={sorted(extra)}")
        for key, child in value.items():
            check_schema(child, properties[key], f"{path}.{key}")


def timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            fail(f"timestamp must include timezone: {value}")
        return result.astimezone(timezone.utc)
    except ValueError as exc:
        raise ContractError(f"invalid timestamp: {value}") from exc


def index(rows: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        if row[key] in result:
            fail(f"{label}: duplicate {row[key]}")
        result[row[key]] = row
    return result


def validate(data: dict[str, Any]) -> dict[str, Any]:
    check_schema(data, SCHEMA)
    tables = {name: index(data[name], "artifact_ref" if name == "evaluation_sets" else "id", name)
              for name in ("artifacts", "cases", "evaluation_sets", "versions", "runs", "comparisons", "replays", "events")}
    artifacts, cases, sets, versions, runs, _, _, events = tables.values()

    def ref(table: dict, ident: str, where: str) -> dict:
        if ident not in table:
            fail(f"{where}: unresolved reference {ident}")
        return table[ident]

    def artifact(ident: str, kind: str | None = None) -> dict:
        value = ref(artifacts, ident, "artifact")
        if kind is not None and value["kind"] != kind:
            fail(f"artifact {ident}: expected kind {kind}")
        return value

    for a in artifacts.values():
        if a["text"] is not None:
            if not a["retained"] or hashlib.sha256(a["text"].encode("utf-8")).hexdigest() != a["sha256"]:
                fail(f"artifact {a['id']}: inline content/retention/digest mismatch")
    for c in cases.values():
        artifact(c["input_ref"], "case_input")
        artifact(c["expectation_ref"], "expectation")
    for s in sets.values():
        artifact(s["artifact_ref"], "evaluation_set")
        if len(set(s["case_ids"])) != len(s["case_ids"]):
            fail("evaluation set: duplicate case IDs")
        for ident in s["case_ids"]:
            ref(cases, ident, "evaluation set")
        manifest = {"protocol_id": s["protocol_id"], "cases": [
            {"id": ident, "input_sha256": artifacts[cases[ident]["input_ref"]]["sha256"],
             "expectation_sha256": artifacts[cases[ident]["expectation_ref"]]["sha256"]}
            for ident in sorted(s["case_ids"])]}
        body = artifacts[s["artifact_ref"]]["text"]
        if body is not None and load(body) != manifest:
            fail("evaluation-set bytes do not bind the declared case manifest")
    for v in versions.values():
        when = timestamp(v["changed_at"])
        for kind, ident in v["components"].items():
            if ident is not None:
                artifact(ident, kind)
        if v["components"]["evaluation_set"] is not None:
            ref(sets, v["components"]["evaluation_set"], "version evaluation set")
        if v["parent_id"] is not None:
            parent = ref(versions, v["parent_id"], "version parent")
            if timestamp(parent["changed_at"]) >= when:
                fail("version parent must strictly precede child (cycles are invalid)")
    # Equal digests cannot disguise a different case universe or expected answers.
    manifests = {}
    for s in sets.values():
        digest = artifacts[s["artifact_ref"]]["sha256"]
        signature = sorted((c, artifacts[cases[c]["input_ref"]]["sha256"],
                            artifacts[cases[c]["expectation_ref"]]["sha256"]) for c in s["case_ids"])
        if digest is not None and digest in manifests and manifests[digest] != signature:
            fail("equal evaluation-set digests have inconsistent case manifests")
        if digest is not None:
            manifests[digest] = signature
    for r in runs.values():
        v = ref(versions, r["version_id"], "run version")
        start, end = timestamp(r["started_at"]), timestamp(r["finished_at"])
        if start < timestamp(v["changed_at"]) or end < start:
            fail(f"run {r['id']}: invalid chronology")
        dataset = v["components"]["evaluation_set"]
        if dataset is None:
            fail(f"run {r['id']}: evaluation set needed for expected denominator")
        allowed = set(sets[dataset]["case_ids"])
        observations = index(r["observations"], "case_id", "observations")
        if not observations.keys() <= allowed:
            fail(f"run {r['id']}: observation outside evaluation set")
        for o in observations.values():
            if o["output_ref"] is not None:
                artifact(o["output_ref"], "output")
            if o["error"] is not None and any(o[m] is not None for m in METRICS[:3]):
                fail("execution error must not masquerade as a scored answer")
    for c in tables["comparisons"].values():
        left, right = ref(runs, c["baseline_run"], "comparison"), ref(runs, c["candidate_run"], "comparison")
        if left["id"] == right["id"] or timestamp(left["finished_at"]) > timestamp(right["started_at"]):
            fail("comparison requires distinct chronologically ordered runs")
    for replay in tables["replays"].values():
        a, b = ref(runs, replay["original_run"], "replay"), ref(runs, replay["repeat_run"], "replay")
        if a["id"] == b["id"] or a["version_id"] != b["version_id"] or timestamp(a["finished_at"]) > timestamp(b["started_at"]):
            fail("replay needs distinct ordered runs of the same version")
    resolved = set()
    for e in events.values():
        v = ref(versions, e["version_id"], "event version")
        if timestamp(e["occurred_at"]) < timestamp(v["changed_at"]):
            fail("event precedes workflow version")
        for ident in e["evidence_refs"]:
            artifact(ident)
        for ident in e["related_run_ids"]:
            r = ref(runs, ident, "event run")
            if r["version_id"] != e["version_id"] or timestamp(r["started_at"]) > timestamp(e["occurred_at"]):
                fail("event run/version chronology mismatch")
        if e["resolves_event_id"] is not None:
            prior = ref(events, e["resolves_event_id"], "resolution")
            if e["kind"] != "resolution" or prior["kind"] != "incident" or timestamp(prior["occurred_at"]) >= timestamp(e["occurred_at"]):
                fail("resolution must follow a linked incident")
            if prior["id"] in resolved:
                fail("incident has duplicate resolution events")
            resolved.add(prior["id"])
    return tables


def mean(values: list[float | bool]) -> float | None:
    return round(sum(float(x) / len(values) for x in values), 6) if values else None


def analyze(data: dict[str, Any]) -> dict[str, Any]:
    t = validate(data)
    artifacts, versions, runs, sets = (t[k] for k in ("artifacts", "versions", "runs", "evaluation_sets"))

    def fingerprint(ident: str | None) -> str | None:
        return artifacts[ident]["sha256"] if ident is not None else None

    def expected(run: dict) -> list[str]:
        return sorted(sets[versions[run["version_id"]]["components"]["evaluation_set"]]["case_ids"])

    def obs(run: dict) -> dict:
        return {o["case_id"]: o for o in run["observations"]}

    run_reports = []
    for r in sorted(runs.values(), key=lambda x: (timestamp(x["started_at"]), x["id"])):
        observations, case_ids = obs(r), expected(r)
        metrics = {}
        for m in METRICS:
            values = [observations[c][m] for c in case_ids if c in observations and observations[c][m] is not None]
            metrics[m] = {"known": len(values), "expected": len(case_ids), "missing": len(case_ids)-len(values), "mean_of_known": mean(values)}
        run_reports.append({"run_id": r["id"], "version_id": r["version_id"], "metrics": metrics,
                            "missing_case_ids": sorted(set(case_ids)-observations.keys()),
                            "error_case_ids": sorted(c for c, o in observations.items() if o["error"] is not None)})
    comparisons = []
    for c in sorted(data["comparisons"], key=lambda x: x["id"]):
        a, b = runs[c["baseline_run"]], runs[c["candidate_run"]]
        va, vb = versions[a["version_id"]], versions[b["version_id"]]
        reasons = []
        for key in ("evaluation_set", "rubric"):
            fa, fb = fingerprint(va["components"][key]), fingerprint(vb["components"][key])
            if fa is None or fb is None or fa != fb:
                reasons.append(f"{key} digest missing or changed")
            for version in (va, vb):
                definition = artifacts.get(version["components"][key])
                if definition is not None and definition["text"] is None:
                    reason = f"{key} definition is registered only, not locally verifiable"
                    if reason not in reasons:
                        reasons.append(reason)
        for ident in expected(a):
            case = t["cases"][ident]
            if any(artifacts[case[key]]["text"] is None for key in ("input_ref", "expectation_ref")):
                reasons.append(f"case {ident} input/expectation bytes unavailable")
        if expected(a) != expected(b):
            reasons.append("case universe changed")
        changes = [key for key in COMPONENTS if va["components"][key] != vb["components"][key] or
                   fingerprint(va["components"][key]) != fingerprint(vb["components"][key])]
        for key in ("model_revision", "model_alias_is_mutable", "seed"):
            if va[key] != vb[key]:
                changes.append(key)
        result = {**c, "status": "incomparable" if reasons else "descriptive_comparison",
                  "reasons": reasons, "changed_components": changes, "metrics": {},
                  "interpretation": "Recorded association only; no causal attribution or production benefit is established."}
        if not reasons:
            ao, bo, universe = obs(a), obs(b), expected(a)
            for m in METRICS:
                paired = [ident for ident in universe if ident in ao and ident in bo and ao[ident][m] is not None and bo[ident][m] is not None]
                am, bm = mean([ao[i][m] for i in paired]), mean([bo[i][m] for i in paired])
                result["metrics"][m] = {"paired": len(paired), "expected": len(universe),
                    "excluded_case_ids": sorted(set(universe)-set(paired)),
                    "baseline_mean": am, "candidate_mean": bm,
                    "delta": mean([float(bo[i][m])-float(ao[i][m]) for i in paired]),
                    "coverage": "complete" if len(paired) == len(universe) else "subset_only",
                    "better_direction": "lower" if m in ("repair_minutes", "latency_ms") else "higher"}
        comparisons.append(result)
    replays = []
    for p in sorted(data["replays"], key=lambda x: x["id"]):
        a, b = runs[p["original_run"]], runs[p["repeat_run"]]
        ao, bo, universe = obs(a), obs(b), expected(a)
        eligible = [c for c in universe if c in ao and c in bo and fingerprint(ao[c]["output_ref"]) is not None and fingerprint(bo[c]["output_ref"]) is not None]
        mismatches = [c for c in eligible if fingerprint(ao[c]["output_ref"]) != fingerprint(bo[c]["output_ref"])]
        # Hash equality without retained inline bytes is a metadata claim, not observed replay evidence.
        verified = [c for c in eligible if all(artifacts[o[c]["output_ref"]]["text"] is not None and o[c]["error"] is None for o in (ao, bo))]
        status = "different_recorded_outputs" if mismatches else "exact_on_recorded_cases" if len(verified) == len(universe) else "incomplete"
        replays.append({**p, "version_id": a["version_id"], "status": status,
                        "compared": len(eligible), "content_verified": len(verified), "expected": len(universe),
                        "mismatch_case_ids": mismatches, "missing_case_ids": sorted(set(universe)-set(verified)),
                        "limit": "Finite recorded outputs only; not a guarantee of future provider behavior."})
    timeline = []
    for v in sorted(versions.values(), key=lambda x: (timestamp(x["changed_at"]), x["id"])):
        gaps, artifact_rows = [], []
        for key in COMPONENTS:
            ident = v["components"][key]
            a = artifacts.get(ident)
            state = "missing" if a is None else "not_retained" if not a["retained"] else "digest_missing" if a["sha256"] is None else "inline_digest_verified" if a["text"] is not None else "registered_only"
            artifact_rows.append({"component": key, "artifact_ref": ident, "state": state, "locator": a["locator"] if a else None})
            if state != "inline_digest_verified":
                gaps.append(f"{key}: {state}")
        if not v["support_owner"]:
            gaps.append("support owner not recorded")
        if not v["model_revision"] or v["model_alias_is_mutable"]:
            gaps.append("model version is not pinned to a recorded immutable revision")
        if v["seed"] is None:
            gaps.append("random seed not recorded; deterministic replay cannot be assumed")
        timeline.append({"version_id": v["id"], "parent_id": v["parent_id"], "changed_at": v["changed_at"],
                         "reason": v["reason"], "support_owner": v["support_owner"], "components": artifact_rows,
                         "reproduction_gaps": gaps, "run_ids": [r["run_id"] for r in run_reports if r["version_id"] == v["id"]],
                         "replay_ids": [r["id"] for r in replays if r["version_id"] == v["id"]]})
    resolutions = {e["resolves_event_id"]: e for e in data["events"] if e["resolves_event_id"] is not None}
    event_reports = []
    for e in sorted(data["events"], key=lambda x: (timestamp(x["occurred_at"]), x["id"])):
        resolution = resolutions.get(e["id"])
        status = "not_an_incident"
        if e["kind"] == "incident":
            status = "open" if resolution is None else "resolution_recorded_with_evidence" if resolution["evidence_refs"] else "resolution_claim_without_evidence"
        event_reports.append({**e, "incident_state": status,
                              "resolution_event_id": resolution["id"] if resolution else None})
    return {"schema_version": "1.0", "work_order": "UIOWA-079", "workflow_id": data["workflow_id"], "group": data["group"],
            "provenance": "SYNTHETIC_SUPPLIED_OBSERVATIONS" if data["synthetic"] else "CALLER_SUPPLIED_METADATA_NOT_INDEPENDENTLY_VERIFIED",
            "assessment_area": "AI readiness", "authority": "DRAFT_ANALYSIS_ONLY",
            "timeline": timeline, "runs": run_reports, "comparisons": comparisons, "replays": replays,
            "events": event_reports,
            "limits": ["No model was called or rescored. Fixture observations are not University findings.",
                       "A verified digest checks local bytes, not truth, authorship, model weights, or production reproducibility.",
                       "Incomplete paired subsets must not be generalized to the full workload.",
                       "This report does not set maturity ratings, approve deployment, procure products, or establish savings."]}


def markdown(report: dict[str, Any]) -> str:
    def esc(value: Any) -> str:
        if value is None:
            return "UNKNOWN"
        return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;").replace("\r", " ").replace("\n", " ")

    lines = ["# AI workflow lifecycle review", "", f"**{report['provenance']} — {report['authority']}**", "",
             f"Workflow: {esc(report['workflow_id'])}; group: {esc(report['group'])}.", "", "## Version timeline", "",
             "| Version / parent | Changed | Reason | Support owner |", "|---|---|---|---|"]
    for v in report["timeline"]:
        lines.append(f"| {esc(v['version_id'])} / {esc(v['parent_id'])} | {esc(v['changed_at'])} | {esc(v['reason'])} | {esc(v['support_owner'])} |")
    for v in report["timeline"]:
        lines += ["", f"### {esc(v['version_id'])}: reproduction evidence", "",
                  "Runs: " + esc(", ".join(v["run_ids"]) or "none") + "; replays: " + esc(", ".join(v["replay_ids"]) or "not demonstrated") + ".",
                  "", "| Component | Artifact | Evidence state | Locator |", "|---|---|---|---|"]
        for c in v["components"]:
            lines.append("| " + " | ".join(esc(c[k]) for k in ("component", "artifact_ref", "state", "locator")) + " |")
        lines += ["", "Gaps: " + esc("; ".join(v["reproduction_gaps"]) or "none in required metadata; this is not a reproduction guarantee") + "."]
    lines += ["", "## Explicit run comparisons", "", "All deltas are candidate minus baseline; subset means exclude missing observations."]
    for c in report["comparisons"]:
        lines += ["", f"### {esc(c['id'])}: {c['status']}", "", f"{esc(c['baseline_run'])} → {esc(c['candidate_run'])}; changes: {esc(', '.join(c['changed_components']) or 'none recorded')}."]
        if c["reasons"]:
            lines.append("No numerical delta: " + esc("; ".join(c["reasons"])) + ".")
        else:
            lines += ["", "| Metric | Paired / expected | Baseline | Candidate | Delta | Coverage | Better |", "|---|---|---|---|---|---|---|"]
            for name, m in c["metrics"].items():
                lines.append(f"| {name} | {m['paired']} / {m['expected']} | {esc(m['baseline_mean'])} | {esc(m['candidate_mean'])} | {esc(m['delta'])} | {m['coverage']} | {m['better_direction']} |")
        lines.append(c["interpretation"])
    lines += ["", "## Recorded replay outcomes", ""]
    for r in report["replays"]:
        lines.append(f"- {esc(r['id'])}: {r['status']}; {r['content_verified']}/{r['expected']} content-verified cases; differences: {esc(', '.join(r['mismatch_case_ids']) or 'none')}. {r['limit']}")
    lines += ["", "## Runtime and investigation trace", "", "| Event | Version / time | Kind | State | Owner | Resolves / resolution | Summary | Evidence / runs |", "|---|---|---|---|---|---|---|---|"]
    for e in report["events"]:
        lines.append(f"| {esc(e['id'])} | {esc(e['version_id'])} / {esc(e['occurred_at'])} | {e['kind']} | {e['incident_state']} | {esc(e['owner'])} | {esc(e['resolves_event_id'])} / {esc(e['resolution_event_id'])} | {esc(e['summary'])} | {esc(', '.join(e['evidence_refs'] + e['related_run_ids']))} |")
    lines += ["", "## Interpretation limits", ""] + ["- " + text for text in report["limits"]]
    return "\n".join(lines) + "\n"


def comparison_csv(report: dict[str, Any]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["comparison_id", "baseline_run", "candidate_run", "status", "metric", "paired", "expected", "baseline_mean", "candidate_mean", "delta", "coverage", "reason"])
    for c in report["comparisons"]:
        for name, m in (c["metrics"].items() or [("", {})]):
            row = [c["id"], c["baseline_run"], c["candidate_run"], c["status"], name] + [m.get(k) for k in ("paired", "expected", "baseline_mean", "candidate_mean", "delta", "coverage")] + ["; ".join(c["reasons"])]
            writer.writerow(["'" + x if isinstance(x, str) and x.lstrip().startswith(("=", "+", "-", "@")) else x for x in row])
    return output.getvalue()


def load(text: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            if key in result:
                fail(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs, parse_constant=lambda x: fail(f"nonfinite JSON number: {x}"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="JSON path, or - for stdin")
    parser.add_argument("--format", choices=("json", "markdown", "csv"), default="json")
    parser.add_argument("--schema", action="store_true", help="print the versioned JSON Schema")
    args = parser.parse_args(argv)
    if args.schema:
        print(json.dumps(SCHEMA, indent=2))
        return 0
    if args.input is None:
        parser.error("input is required unless --schema is supplied")
    try:
        text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        report = analyze(load(text))
        result = markdown(report) if args.format == "markdown" else comparison_csv(report) if args.format == "csv" else json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        sys.stdout.write(result)
        return 0
    except (OSError, ValueError, TypeError, RecursionError, OverflowError) as exc:
        print(f"INVALID_INPUT: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
