#!/usr/bin/env python3
"""UIOWA-076: offline, evidence-linked AI coding workflow assessment.

Standard library only. Supplied records are observations, not a causal study,
University findings, maturity scores, or authority to change a live system.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

SCHEMA = "1.0"
STAGES = ("understand", "author", "test", "repair", "integrate", "maintain")
CRITERIA = ("understanding", "verification", "revision", "integration", "maintenance")
COVERAGE = {"complete", "partial", "unknown"}
STATES = {"demonstrated", "stated", "gap", "unknown", "not_applicable", "disputed"}
DIRECT = {"artifact", "observation"}
CONTEXT = ("task_fingerprint", "stack", "complexity", "criticality")
DISCLAIMER = ("SYNTHETIC PREPARATION ONLY. Not University findings or individual ratings. "
              "Matched records support descriptive comparisons, not a causal AI effect. "
              "Evidence hashes establish retained-byte consistency, not authenticity.")


class InputError(ValueError):
    """A structural or source-integrity error that must not become a finding."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InputError(message)


def shape(obj: Any, fields: set[str], label: str) -> None:
    require(isinstance(obj, dict), f"{label}: expected object")
    require(set(obj) == fields, f"{label}: fields mismatch; missing={sorted(fields-set(obj))}, "
            f"extra={sorted(set(obj)-fields)}")


def text(value: Any, label: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{label}: nonempty string required")
    return value


def ident(value: Any, label: str) -> str:
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) is not None,
            f"{label}: use letters, digits, dot, underscore or hyphen")
    return value


def context_known(value: str | None) -> bool:
    """Only null and the explicit UNKNOWN sentinel denote missing context."""
    return value is not None and value.strip().casefold() != "unknown"


def stamp(value: Any, label: str) -> datetime:
    text(value, label)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError(f"{label}: invalid ISO timestamp") from exc
    require(result.tzinfo is not None and result.utcoffset() is not None,
            f"{label}: timezone required")
    return result


def number(value: Any, label: str) -> Decimal:
    require(not isinstance(value, bool) and isinstance(value, (str, int, float, Decimal)),
            f"{label}: decimal number required")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise InputError(f"{label}: invalid decimal") from exc
    require(result.is_finite() and result >= 0, f"{label}: finite nonnegative number required")
    require(result.as_tuple().exponent >= -6, f"{label}: at most six decimal places")
    require(result <= Decimal("1000000000"), f"{label}: unrealistic effort magnitude")
    return result


def dec(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f") if value else "0"


def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def fail_constant(value: str) -> None:
    raise InputError(f"non-finite JSON constant: {value}")


def references(values: Any, registry: dict[str, dict], label: str) -> list[str]:
    require(isinstance(values, list) and all(isinstance(v, str) for v in values),
            f"{label}: expected evidence ID list")
    require(len(set(values)) == len(values), f"{label}: duplicate evidence reference")
    require(all(v in registry for v in values), f"{label}: unresolved evidence reference")
    return values


def direct(values: list[str], registry: dict[str, dict]) -> bool:
    return any(registry[v]["kind"] in DIRECT for v in values)


def support(values: list[str], registry: dict[str, dict]) -> str:
    return "direct" if direct(values, registry) else "statement_only" if values else "missing"


def _source_registry(data: dict, root: Path, as_of: datetime) -> dict[str, dict]:
    require(isinstance(data["evidence"], list), "evidence: expected list")
    registry: dict[str, dict] = {}
    cache: dict[Path, tuple[str, list[str]]] = {}
    root = root.resolve()
    for source in data["evidence"]:
        shape(source, {"id", "path", "sha256", "start_line", "end_line", "kind", "observed_at"}, "source")
        sid = ident(source["id"], "source.id")
        require(sid not in registry, f"duplicate source ID: {sid}")
        require(isinstance(source["kind"], str) and source["kind"] in DIRECT | {"interview"}, f"{sid}: unknown evidence kind")
        require(stamp(source["observed_at"], sid) <= as_of, f"{sid}: future evidence")
        relative = Path(text(source["path"], f"{sid}.path"))
        require(not relative.is_absolute(), f"{sid}: source path must be relative")
        path = (root / relative).resolve()
        require(path.is_relative_to(root), f"{sid}: source path escapes bundle")
        require(path.is_file(), f"{sid}: source file missing")
        if path not in cache:
            raw = path.read_bytes()
            try:
                lines = raw.decode("utf-8").splitlines()
            except UnicodeDecodeError as exc:
                raise InputError(f"{sid}: source must be UTF-8 text") from exc
            cache[path] = (hashlib.sha256(raw).hexdigest(), lines)
        digest, lines = cache[path]
        require(source["sha256"] == digest, f"{sid}: source digest mismatch")
        start, end = source["start_line"], source["end_line"]
        require(type(start) is int and type(end) is int and 1 <= start <= end <= len(lines),
                f"{sid}: invalid line locator")
        registry[sid] = {**source, "excerpt": "\n".join(lines[start-1:end])}
    return registry


def _validate_change(change: dict, registry: dict[str, dict], as_of: datetime,
                     effort_ids: set[str]) -> None:
    shape(change, {"id", "group", "mode", "pair_id", "context", "started_at", "accepted_at",
                   "acceptance_evidence_ids", "effort", "coverage", "practices", "followup"}, "change")
    cid = ident(change["id"], "change.id")
    require(isinstance(change["group"], str) and change["group"] in {"ESS", "RIS", "IAM"}, f"{cid}: unknown group")
    require(isinstance(change["mode"], str) and change["mode"] in {"assisted", "manual"}, f"{cid}: unknown mode")
    ident(change["pair_id"], f"{cid}.pair_id")
    shape(change["context"], set(CONTEXT), f"{cid}.context")
    for field in CONTEXT:
        if change["context"][field] is not None:
            text(change["context"][field], f"{cid}.{field}")
    start = stamp(change["started_at"], f"{cid}.started_at")
    require(start <= as_of, f"{cid}: future start")
    accepted = stamp(change["accepted_at"], f"{cid}.accepted_at") if change["accepted_at"] else None
    require(change["accepted_at"] is None or isinstance(change["accepted_at"], str),
            f"{cid}: accepted_at must be timestamp or null")
    require(change["accepted_at"] is None or accepted is not None,
            f"{cid}: blank acceptance timestamp is not null")
    if accepted:
        require(start <= accepted <= as_of, f"{cid}: acceptance outside observation chronology")
    refs = references(change["acceptance_evidence_ids"], registry, f"{cid}.acceptance")
    require(accepted is not None or not refs, f"{cid}: acceptance evidence without acceptance timestamp")
    require(isinstance(change["effort"], list), f"{cid}: effort list required")
    for entry in change["effort"]:
        shape(entry, {"id", "stage", "minutes", "evidence_ids"}, f"{cid}.effort")
        eid = ident(entry["id"], f"{cid}.effort.id")
        require(eid not in effort_ids, f"duplicate effort ID (double allocation): {eid}")
        effort_ids.add(eid)
        require(entry["stage"] in STAGES, f"{eid}: unknown stage")
        if entry["minutes"] is not None:
            number(entry["minutes"], eid)
        references(entry["evidence_ids"], registry, eid)
    shape(change["coverage"], set(STAGES), f"{cid}.coverage")
    for stage, entry in change["coverage"].items():
        shape(entry, {"state", "basis", "evidence_ids"}, f"{cid}.{stage}.coverage")
        require(isinstance(entry["state"], str) and entry["state"] in COVERAGE, f"{cid}.{stage}: unknown coverage state")
        text(entry["basis"], f"{cid}.{stage}.basis")
        references(entry["evidence_ids"], registry, f"{cid}.{stage}.coverage")
    shape(change["practices"], set(CRITERIA), f"{cid}.practices")
    for criterion, entry in change["practices"].items():
        shape(entry, {"state", "rationale", "evidence_ids"}, f"{cid}.{criterion}")
        require(isinstance(entry["state"], str) and entry["state"] in STATES, f"{cid}.{criterion}: unknown practice state")
        text(entry["rationale"], f"{cid}.{criterion}.rationale")
        references(entry["evidence_ids"], registry, f"{cid}.{criterion}")
    followup = change["followup"]
    shape(followup, {"days", "observed_through", "coverage", "reported_faults", "evidence_ids"},
          f"{cid}.followup")
    require(type(followup["days"]) is int and 1 <= followup["days"] <= 3650,
            f"{cid}: followup days must be positive integer <= 3650")
    require(isinstance(followup["coverage"], str) and followup["coverage"] in COVERAGE, f"{cid}: unknown followup coverage")
    faults = followup["reported_faults"]
    require(faults is None or type(faults) is int and faults >= 0,
            f"{cid}: reported_faults must be nonnegative integer or null")
    if followup["observed_through"] is not None:
        through = stamp(followup["observed_through"], f"{cid}.observed_through")
        require(accepted is not None, f"{cid}: followup endpoint without acceptance")
        require(accepted <= through <= as_of, f"{cid}: followup outside observation chronology")
    references(followup["evidence_ids"], registry, f"{cid}.followup")


def _assess_change(change: dict, registry: dict[str, dict]) -> dict:
    accepted = stamp(change["accepted_at"], "accepted_at") if change["accepted_at"] else None
    acceptance_supported = accepted is not None and direct(change["acceptance_evidence_ids"], registry)
    followup = change["followup"]
    through = stamp(followup["observed_through"], "observed_through") if followup["observed_through"] else None
    try:
        endpoint = accepted + timedelta(days=followup["days"]) if accepted else None
    except OverflowError as exc:
        raise InputError(f"{change['id']}: followup endpoint outside supported calendar") from exc
    mature = bool(acceptance_supported and through and endpoint and through >= endpoint)
    exact_window = bool(mature and through == endpoint)
    full_followup = exact_window and followup["coverage"] == "complete" and direct(followup["evidence_ids"], registry)
    stages = {}
    for stage in STAGES:
        entries = [entry for entry in change["effort"] if entry["stage"] == stage]
        known = sum((number(e["minutes"], e["id"]) for e in entries if e["minutes"] is not None), Decimal(0))
        evidence_ids = sorted({sid for e in entries for sid in e["evidence_ids"]} |
                              set(change["coverage"][stage]["evidence_ids"]))
        reasons = []
        if change["coverage"][stage]["state"] != "complete":
            reasons.append("effort_coverage_not_complete")
        if not direct(change["coverage"][stage]["evidence_ids"], registry):
            reasons.append("coverage_basis_not_directly_supported")
        if any(e["minutes"] is None for e in entries):
            reasons.append("missing_effort_amount")
        if any(not direct(e["evidence_ids"], registry) for e in entries):
            reasons.append("effort_record_not_directly_supported")
        if stage == "maintain" and not full_followup:
            reasons.append("followup_incomplete_or_unsupported")
        stages[stage] = {"recorded_minutes": dec(known), "complete_minutes": dec(known) if not reasons else None,
                         "reasons": reasons, "evidence_ids": evidence_ids}
    def total(selected: tuple[str, ...]) -> str | None:
        if any(stages[s]["complete_minutes"] is None for s in selected):
            return None
        return dec(sum((Decimal(stages[s]["complete_minutes"]) for s in selected), Decimal(0)))
    practices = {}
    for name, entry in change["practices"].items():
        level = support(entry["evidence_ids"], registry)
        state = entry["state"]
        effective = state
        if state in {"demonstrated", "gap", "not_applicable", "disputed"} and level != "direct":
            effective = "stated" if level == "statement_only" else "unknown"
        if state == "stated" and level == "missing":
            effective = "unknown"
        practices[name] = {"claimed_state": state, "effective_state": effective,
                           "support": level, "rationale": entry["rationale"],
                           "evidence_ids": list(entry["evidence_ids"])}
    wall = None
    if acceptance_supported and accepted:
        elapsed = accepted - stamp(change["started_at"], "started_at")
        wall = dec((Decimal(elapsed.days * 86400 + elapsed.seconds) +
                    Decimal(elapsed.microseconds) / Decimal(1000000)) / Decimal(60))
    # Keep the assessment-to-source edges, not only the global registry. These
    # are detached values so a caller cannot silently alter an issued report.
    source_trace = {
        "started_at": change["started_at"],
        "accepted_at": change["accepted_at"],
        "acceptance_evidence_ids": sorted(change["acceptance_evidence_ids"]),
        "followup": {**followup, "evidence_ids": sorted(followup["evidence_ids"])},
        "coverage": {stage: {**change["coverage"][stage],
                    "evidence_ids": sorted(change["coverage"][stage]["evidence_ids"])}
                    for stage in STAGES},
        "effort": [{**entry,
                    "minutes": dec(number(entry["minutes"], entry["id"]))
                               if entry["minutes"] is not None else None,
                    "evidence_ids": sorted(entry["evidence_ids"])}
                   for entry in sorted(change["effort"], key=lambda item: item["id"])],
    }
    return {"id": change["id"], "group": change["group"], "mode": change["mode"],
            "pair_id": change["pair_id"], "context": dict(change["context"]), "stages": stages,
            "source_trace": source_trace,
            "acceptance_supported": acceptance_supported, "wall_delivery_minutes": wall,
            "delivery_effort_minutes": total(STAGES[:-1]), "lifecycle_effort_minutes": total(STAGES),
            "recorded_effort_minutes": dec(sum((Decimal(stages[s]["recorded_minutes"]) for s in STAGES), Decimal(0))),
            "practices": practices, "followup_days": followup["days"], "followup_complete": full_followup,
            "followup_window_exact": exact_window,
            "reported_faults": followup["reported_faults"],
            "comparable_faults": followup["reported_faults"] if full_followup else None}


def _compare(pair_id: str, changes: list[dict]) -> dict:
    modes = {change["mode"]: change for change in changes}
    reasons = []
    if set(modes) != {"assisted", "manual"}:
        reasons.append("missing_comparison_arm")
    assisted, manual = modes.get("assisted"), modes.get("manual")
    if assisted and manual:
        if assisted["group"] != manual["group"]:
            reasons.append("group_mismatch")
        for key in CONTEXT:
            unknown = [row for row in (assisted, manual)
                       if not context_known(row["context"][key])]
            if unknown:
                reasons.extend(f"{row['mode']}_{key}_unknown" for row in unknown)
            elif assisted["context"][key] != manual["context"][key]:
                reasons.append(f"{key}_mismatch")
        if assisted["followup_days"] != manual["followup_days"]:
            reasons.append("followup_window_mismatch")
        for row in (assisted, manual):
            for field in ("acceptance_supported", "followup_complete"):
                if not row[field]:
                    reasons.append(f"{row['mode']}_{field}_missing")
            if row["lifecycle_effort_minutes"] is None:
                reasons.append(f"{row['mode']}_lifecycle_effort_incomplete")
            if row["comparable_faults"] is None:
                reasons.append(f"{row['mode']}_quality_outcome_unknown")
    result = {"pair_id": pair_id, "change_ids": sorted(row["id"] for row in changes),
              "comparable": not reasons, "reasons": reasons, "author_delta_minutes": None,
              "delivery_effort_delta_minutes": None, "lifecycle_delta_minutes": None,
              "faults_delta": None, "effort_direction": "unknown", "quality_direction": "unknown",
              "interpretation": "Assisted minus manual; descriptive within supplied matched records, not causal evidence."}
    if not reasons and assisted and manual:
        for key, field in (("delivery_effort_delta_minutes", "delivery_effort_minutes"),
                           ("lifecycle_delta_minutes", "lifecycle_effort_minutes")):
            result[key] = dec(Decimal(assisted[field]) - Decimal(manual[field]))
        result["author_delta_minutes"] = dec(Decimal(assisted["stages"]["author"]["complete_minutes"]) -
                                              Decimal(manual["stages"]["author"]["complete_minutes"]))
        result["faults_delta"] = assisted["comparable_faults"] - manual["comparable_faults"]
        amount = Decimal(result["lifecycle_delta_minutes"])
        result["effort_direction"] = "less" if amount < 0 else "more" if amount > 0 else "equal"
        faults = result["faults_delta"]
        result["quality_direction"] = "fewer" if faults < 0 else "more" if faults > 0 else "equal"
    return result


def analyze(data: Any, root: Path) -> dict:
    shape(data, {"schema_version", "synthetic", "as_of", "evidence", "changes"}, "dataset")
    require(data["schema_version"] == SCHEMA, "unsupported schema_version")
    require(data["synthetic"] is True, "this rehearsal requires explicit synthetic=true; not a real-data ingestion service")
    as_of = stamp(data["as_of"], "as_of")
    registry = _source_registry(data, root, as_of)
    require(isinstance(data["changes"], list) and data["changes"], "changes: nonempty list required")
    seen: set[str] = set()
    effort_ids: set[str] = set()
    pairs: dict[str, list[dict]] = {}
    outputs = []
    for change in data["changes"]:
        _validate_change(change, registry, as_of, effort_ids)
        require(change["id"] not in seen, f"duplicate change ID: {change['id']}")
        seen.add(change["id"])
        pair = pairs.setdefault(change["pair_id"], [])
        require(all(row["mode"] != change["mode"] for row in pair),
                f"{change['pair_id']}: duplicate comparison mode; do not silently select a record")
        row = _assess_change(change, registry)
        pair.append(row)
        outputs.append(row)
    return {"schema_version": SCHEMA, "as_of": data["as_of"], "synthetic": True,
            "notice": DISCLAIMER, "changes": sorted(outputs, key=lambda row: row["id"]),
            "comparisons": [_compare(key, pairs[key]) for key in sorted(pairs)],
            "evidence": [registry[key] for key in sorted(registry)]}


def load_report(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates,
                      parse_float=Decimal, parse_constant=fail_constant)
    return analyze(data, path.parent)


def escape(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;").replace("\n", "<br>")


def markdown(report: dict) -> str:
    lines = ["# AI-assisted coding workflow evidence", "", report["notice"], "",
             f"Observation cutoff: `{report['as_of']}`. Effort is person-minutes; elapsed delivery is wall-clock minutes.",
             "Missing full totals are **unknown**, not zero. Authoring includes prompting/context and first-draft work.", "",
             "## Full-workflow results", "",
             "| Change | Group / mode | Authoring | Delivery effort | Lifecycle effort | Elapsed delivery | Full follow-up | Faults in complete window |",
             "|---|---|---:|---:|---:|---:|---|---:|"]
    display = lambda value: "UNKNOWN" if value is None else escape(value)
    for row in report["changes"]:
        values = [row["id"], f"{row['group']} / {row['mode']}", row["stages"]["author"]["complete_minutes"],
                  row["delivery_effort_minutes"], row["lifecycle_effort_minutes"], row["wall_delivery_minutes"],
                  "complete" if row["followup_complete"] else "incomplete", row["comparable_faults"]]
        lines.append("| " + " | ".join(display(value) for value in values) + " |")
    lines += ["", "## Matched-record contrasts", "", "Deltas are assisted minus manual. Never extrapolate these fictional counts into an institutional benefit claim.", ""]
    for pair in report["comparisons"]:
        lines.append(f"### {pair['pair_id']}")
        if pair["comparable"]:
            lines.append(f"Authoring delta **{pair['author_delta_minutes']} min**; lifecycle delta **{pair['lifecycle_delta_minutes']} min**; fault delta **{pair['faults_delta']}**. Recorded lifecycle effort: {pair['effort_direction']}; fault count: {pair['quality_direction']}.")
        else:
            lines.append("**Not comparable:** " + "; ".join(pair["reasons"]) + ".")
        lines.append("")
    lines += ["## Practice and effort trace", ""]
    for row in report["changes"]:
        lines += [f"### {row['id']}", ""]
        trace = row["source_trace"]
        citation = lambda ids: ", ".join(f"[{sid}](#{sid.lower()})" for sid in ids) or "no evidence"
        lines.append(f"- Started: {display(trace['started_at'])}; accepted: {display(trace['accepted_at'])}; "
                     f"acceptance evidence: {citation(trace['acceptance_evidence_ids'])}.")
        followup = trace["followup"]
        lines.append(f"- Follow-up: {followup['days']} days after acceptance; observed through "
                     f"{display(followup['observed_through'])}; coverage {followup['coverage']}; "
                     f"reported faults {display(followup['reported_faults'])}; "
                     f"evidence: {citation(followup['evidence_ids'])}.")
        for stage, entry in row["stages"].items():
            refs = ", ".join(f"[{sid}](#{sid.lower()})" for sid in entry["evidence_ids"]) or "no evidence"
            lines.append(f"- {stage}: recorded {entry['recorded_minutes']} min; full total {display(entry['complete_minutes'])}; {', '.join(entry['reasons']) or 'complete supplied records'}; {refs}.")
            coverage = trace["coverage"][stage]
            lines.append(f"  Coverage: {coverage['state']}; {escape(coverage['basis'])}; "
                         f"evidence: {citation(coverage['evidence_ids'])}.")
            for allocation in trace["effort"]:
                if allocation["stage"] == stage:
                    lines.append(f"  Allocation {allocation['id']}: {display(allocation['minutes'])} min; "
                                 f"evidence: {citation(allocation['evidence_ids'])}.")
        for name, entry in row["practices"].items():
            refs = ", ".join(f"[{sid}](#{sid.lower()})" for sid in entry["evidence_ids"]) or "no evidence"
            lines.append(f"- {name}: **{entry['effective_state']}** (claimed {entry['claimed_state']}; {entry['support']}). {escape(entry['rationale'])} Evidence: {refs}.")
        lines.append("")
    lines += ["## Retained evidence locators", "", "Paths are relative to the input JSON directory; hashes cover the complete retained UTF-8 source file.", ""]
    for source in report["evidence"]:
        lines += [f"### {source['id']}", "",
                  f"`{escape(source['path'])}` lines {source['start_line']}–{source['end_line']}; {source['kind']}; observed `{source['observed_at']}`.",
                  f"SHA-256: `{source['sha256']}`", "", "> " + escape(source["excerpt"]), ""]
    return "\n".join(lines) + "\n"


def write_outputs(report: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "report.md").write_text(markdown(report), encoding="utf-8")
    fields = ["id", "group", "mode", "pair_id", "delivery_effort_minutes", "lifecycle_effort_minutes",
              "recorded_effort_minutes", "wall_delivery_minutes", "followup_complete", "comparable_faults"]
    with (out / "changes.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields, lineterminator="\n")
        writer.writeheader()
        for row in report["changes"]:
            writer.writerow({field: "UNKNOWN" if row[field] is None else row[field] for field in fields})
    manifest = {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                for name in ("report.json", "report.md", "changes.csv")}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Synthetic JSON bundle with retained local source files")
    parser.add_argument("--out", type=Path, required=True, help="Output directory, not the input/source directory")
    args = parser.parse_args(argv)
    try:
        report = load_report(args.input)
        source_paths = {(args.input.parent / source["path"]).resolve() for source in report["evidence"]}
        targets = {(args.out / name).resolve() for name in ("report.json", "report.md", "changes.csv", "manifest.json")}
        require(not targets.intersection(source_paths | {args.input.resolve()}), "output would overwrite input evidence")
        write_outputs(report, args.out)
    except (InputError, OSError, json.JSONDecodeError, UnicodeError) as exc:
        print(f"INPUT ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"OK changes={len(report['changes'])} pairs={len(report['comparisons'])} "
          f"comparable={sum(p['comparable'] for p in report['comparisons'])} sources={len(report['evidence'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
