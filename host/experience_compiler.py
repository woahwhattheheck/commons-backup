#!/usr/bin/env python3
"""Compile verified Commons execution receipts into persistent skill knowledge."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "experience" / "raw"
WIKI_DIR = ROOT / "experience" / "wiki"
PATTERN_DIR = WIKI_DIR / "patterns"
SCHEMA = "commons-experience/v1"
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RECORDED_AT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)


class ExperienceError(ValueError):
    """Raised when an experience packet violates the public contract."""


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _recorded_at(value: Any, rel: Any = "experience record") -> datetime:
    """Parse the canonical UTC packet timestamp used for retrieval ordering."""
    if not isinstance(value, str) or not RECORDED_AT_RE.fullmatch(value):
        raise ExperienceError(f"{rel}: recorded_at must be an ISO-8601 UTC timestamp ending in Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ExperienceError(f"{rel}: invalid recorded_at timestamp") from exc


def live_cash_markdown(path: Path) -> str:
    """Emit living KEEP live-cash + titanmcp cites for a compiled wiki page.

    Bass/latch already landed these cites on the markdown wiki. Compile and
    check must emit the same bytes so rebuilds keep the shelf instead of
    reporting DRIFT.
    """
    prefix = "/".join(".." for _ in path.parent.relative_to(ROOT).parts)
    return (
        "## Live cash\n"
        "\n"
        "Verified product pages only — no invented Stripe links.\n"
        "\n"
        f"- [$199 dealer diagnostic]({prefix}/dealer-service-lead-rescue.html)\n"
        f"- [$199 referral diagnostic]({prefix}/referral-intake-completeness.html)\n"
        f"- [$199 repair diagnostic]({prefix}/repair-booking-preflight.html)\n"
        f"- [$199 plant diagnostic]({prefix}/plant-downtime-handoff.html)\n"
        "\n"
        "Larger fixed engagements (separate product pages; checkout/intent stays "
        f"there): [GGUF diagnostic · $12,000 / 10 days]({prefix}/diagnostic.html) · "
        f"[White Box pilot · $30,000 / 30 days]({prefix}/commercial.html). "
        "Not remints of tip SKUs.\n"
        "\n"
        "## Contest product (titanmcp)\n"
        "\n"
        "Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): "
        "https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, "
        "Agent Resources, `syncConsents`. Board: "
        f"[titanmcp.html]({prefix}/titanmcp.html). Cite Latch Pad KEEP.\n"
    )


def load_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(RAW_DIR.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ExperienceError(f"{path.relative_to(ROOT)}: {exc}") from exc
        validate_record(record, path)
        record_id = record["id"]
        if record_id in seen:
            raise ExperienceError(f"duplicate experience id: {record_id}")
        seen.add(record_id)
        records.append(record)
    if not records:
        raise ExperienceError("experience/raw must contain at least one packet")
    return records


def validate_record(record: dict[str, Any], path: Path) -> None:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        rel = path
    if not isinstance(record, dict):
        raise ExperienceError(f"{rel}: experience packet must be an object")
    required = {
        "schema",
        "id",
        "recorded_at",
        "task",
        "outcome",
        "evidence",
        "patterns",
        "skill_impacts",
    }
    missing = sorted(required - record.keys())
    if missing:
        raise ExperienceError(f"{rel}: missing {', '.join(missing)}")
    if record["schema"] != SCHEMA:
        raise ExperienceError(f"{rel}: unsupported schema")
    record_id = record["id"]
    if not isinstance(record_id, str) or not ID_RE.fullmatch(record_id):
        raise ExperienceError(f"{rel}: invalid id")
    if path.stem != record_id:
        raise ExperienceError(f"{rel}: filename must match id")
    _recorded_at(record["recorded_at"], rel)
    outcome = record["outcome"]
    if not isinstance(outcome, str) or outcome not in {"passed", "failed"}:
        raise ExperienceError(f"{rel}: outcome must be passed or failed")
    if not isinstance(record["task"], str) or not record["task"].strip():
        raise ExperienceError(f"{rel}: task must be non-empty")
    evidence = record["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise ExperienceError(f"{rel}: evidence must be non-empty")
    for item in evidence:
        if not isinstance(item, dict):
            raise ExperienceError(f"{rel}: malformed evidence")
        kind, value = item.get("kind"), item.get("value")
        if not isinstance(kind, str) or not kind or not isinstance(value, str) or not value:
            raise ExperienceError(f"{rel}: malformed evidence")
        if kind == "commit" and not SHA_RE.fullmatch(value):
            raise ExperienceError(f"{rel}: commit evidence must be a full SHA")
    patterns = record["patterns"]
    if not isinstance(patterns, list) or not patterns:
        raise ExperienceError(f"{rel}: patterns must be non-empty")
    seen_patterns: set[str] = set()
    for pattern in patterns:
        needed = {"id", "kind", "summary", "procedure", "applies_to"}
        if not isinstance(pattern, dict) or needed - pattern.keys():
            raise ExperienceError(f"{rel}: malformed pattern")
        pattern_id = pattern["id"]
        if not isinstance(pattern_id, str) or not ID_RE.fullmatch(pattern_id):
            raise ExperienceError(f"{rel}: invalid pattern id")
        if pattern_id in seen_patterns:
            raise ExperienceError(f"{rel}: duplicate pattern id: {pattern_id}")
        seen_patterns.add(pattern_id)
        kind = pattern["kind"]
        if not isinstance(kind, str) or kind not in {"success", "failure"}:
            raise ExperienceError(f"{rel}: pattern kind must be success or failure")
        if not isinstance(pattern["summary"], str) or not pattern["summary"].strip():
            raise ExperienceError(f"{rel}: pattern summary must be non-empty text")
        if not isinstance(pattern["procedure"], str) or not pattern["procedure"].strip():
            raise ExperienceError(f"{rel}: pattern procedure must be non-empty text")
        applies_to = pattern["applies_to"]
        if not isinstance(applies_to, list) or not applies_to:
            raise ExperienceError(f"{rel}: pattern applies_to must be non-empty")
        if any(not isinstance(tag, str) or not ID_RE.fullmatch(tag) for tag in applies_to):
            raise ExperienceError(f"{rel}: pattern applies_to tags must be canonical ids")
        if len(applies_to) != len(set(applies_to)):
            raise ExperienceError(f"{rel}: pattern applies_to tags must be unique")
    skill_impacts = record["skill_impacts"]
    if not isinstance(skill_impacts, list):
        raise ExperienceError(f"{rel}: skill_impacts must be a list")
    for impact in skill_impacts:
        needed = {"skill", "change", "decision", "validation"}
        if not isinstance(impact, dict) or needed - impact.keys():
            raise ExperienceError(f"{rel}: malformed skill impact")
        decision = impact["decision"]
        if not isinstance(decision, str) or decision not in {"adopted", "rejected", "observed"}:
            raise ExperienceError(f"{rel}: invalid skill decision")
        validation = impact["validation"]
        if not isinstance(validation, dict) or "result" not in validation:
            raise ExperienceError(f"{rel}: skill impact needs validation result")


def compile_outputs(records: list[dict[str, Any]]) -> dict[Path, str]:
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "success_count": 0,
            "failure_count": 0,
            "evidence_records": [],
            "applies_to": set(),
            "summaries": [],
            "procedures": [],
        }
    )
    evolution: list[dict[str, Any]] = []
    impacts: list[dict[str, Any]] = []

    for record in records:
        evolution.append(
            {
                "id": record["id"],
                "recorded_at": record["recorded_at"],
                "outcome": record["outcome"],
                "task": record["task"],
                "evidence": record["evidence"],
            }
        )
        for pattern in record["patterns"]:
            item = grouped[pattern["id"]]
            item[f"{pattern['kind']}_count"] += 1
            item["evidence_records"].append(record["id"])
            item["applies_to"].update(pattern["applies_to"])
            if pattern["summary"] not in item["summaries"]:
                item["summaries"].append(pattern["summary"])
            if pattern["procedure"] not in item["procedures"]:
                item["procedures"].append(pattern["procedure"])
        for impact in record["skill_impacts"]:
            impacts.append({"experience_id": record["id"], **impact})

    catalog = {
        "schema": "commons-experience-wiki/v1",
        "source_schema": SCHEMA,
        "record_count": len(records),
        "pattern_count": len(grouped),
        "patterns": [],
    }
    outputs: dict[Path, str] = {}
    for pattern_id in sorted(grouped):
        item = grouped[pattern_id]
        compiled = {
            "id": pattern_id,
            "success_count": item["success_count"],
            "failure_count": item["failure_count"],
            "evidence_records": sorted(item["evidence_records"]),
            "applies_to": sorted(item["applies_to"]),
            "summaries": item["summaries"],
            "procedures": item["procedures"],
        }
        catalog["patterns"].append(compiled)
        lines = [
            f"# {pattern_id}",
            "",
            f"Evidence: {len(compiled['evidence_records'])} verified experience packet(s).",
            f"Success observations: {compiled['success_count']}",
            f"Failure observations: {compiled['failure_count']}",
            "",
            "## Applies to",
            "",
            *[f"- `{name}`" for name in compiled["applies_to"]],
            "",
            "## Compiled knowledge",
            "",
            *[f"- {summary}" for summary in compiled["summaries"]],
            "",
            "## Reusable procedures",
            "",
            *[f"- {procedure}" for procedure in compiled["procedures"]],
            "",
            "## Evidence packets",
            "",
            *[f"- `experience/raw/{record_id}.json`" for record_id in compiled["evidence_records"]],
            "",
        ]
        pattern_path = PATTERN_DIR / f"{pattern_id}.md"
        outputs[pattern_path] = "\n".join(lines) + "\n" + live_cash_markdown(pattern_path)

    index_lines = [
        "# Commons Experience Wiki",
        "",
        "This is compiled knowledge, not raw history and not an executable skill.",
        "It is rebuilt deterministically from evidence packets in `experience/raw/`.",
        "",
        f"- Verified experience packets: {len(records)}",
        f"- Compiled patterns: {len(grouped)}",
        f"- Skill-impact entries: {len(impacts)}",
        "",
        "## Pattern catalog",
        "",
        *[
            f"- [{item['id']}](patterns/{item['id']}.md) — "
            f"{item['success_count']} success / {item['failure_count']} failure observations"
            for item in catalog["patterns"]
        ],
        "",
        "The runtime agent reads active skills, not this wiki. Maintainers and skill",
        "proposers use the wiki to make one evidence-backed procedural change at a time.",
        "",
    ]
    index_path = WIKI_DIR / "index.md"
    outputs[index_path] = "\n".join(index_lines) + "\n" + live_cash_markdown(index_path)
    outputs[WIKI_DIR / "catalog.json"] = _json(catalog)
    outputs[WIKI_DIR / "evolution-log.jsonl"] = "".join(
        json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n" for item in evolution
    )
    outputs[WIKI_DIR / "skill-impact.json"] = _json(
        {"schema": "commons-skill-impact/v1", "entries": impacts}
    )
    return outputs


def compile_to_disk(outputs: dict[Path, str]) -> None:
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    expected_pattern_paths = {path for path in outputs if path.parent == PATTERN_DIR}
    for path in PATTERN_DIR.glob("*.md"):
        if path not in expected_pattern_paths:
            path.unlink()


def check_outputs(outputs: dict[Path, str]) -> list[str]:
    drift: list[str] = []
    for path, expected in outputs.items():
        actual = path.read_text(encoding="utf-8") if path.exists() else None
        if actual != expected:
            drift.append(str(path.relative_to(ROOT)))
    expected_pattern_paths = {path for path in outputs if path.parent == PATTERN_DIR}
    for path in PATTERN_DIR.glob("*.md"):
        if path not in expected_pattern_paths:
            drift.append(str(path.relative_to(ROOT)))
    return sorted(drift)


def retrieve_experience(
    records: list[dict[str, Any]], query: str = "", skill: str | None = None,
    limit: int = 3,
) -> dict[str, Any]:
    """Select evidence for a skill maintainer without loading the whole wiki.

    Read raw records so retrieval includes newly captured outcomes even before
    a wiki rebuild. Relevance never treats success counts as a quality score.
    Keep a failure and a success when both exist, then the newest observation;
    report omitted records explicitly. Retrieval does not edit an active skill.
    """
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ExperienceError("retrieve limit must be between 1 and 20")
    if not isinstance(query, str) or (skill is not None and not isinstance(skill, str)):
        raise ExperienceError("retrieve query and skill must be text")
    terms = set(re.findall(r"[^\W_]+", query.casefold()))
    skill = skill.strip() if skill else None
    if not terms and not skill:
        raise ExperienceError("retrieve needs --query or --skill")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in sorted(records, key=lambda r: r["id"]):
        for pattern in record["patterns"]:
            grouped[pattern["id"]].append({"record": record, "pattern": pattern})
    matches = []
    for pattern_id, sources in sorted(grouped.items()):
        applies = sorted({tag for source in sources for tag in source["pattern"]["applies_to"]})
        if skill and skill not in applies:
            continue
        searchable = " ".join(
            [pattern_id, *applies] + [
                str(source["pattern"][field])
                for source in sources for field in ("summary", "procedure")
            ]
        )
        words = set(re.findall(r"[^\W_]+", searchable.casefold()))
        matched_terms = sorted(terms & words)
        if terms and not matched_terms:
            continue
        ordered = sorted(sources, key=lambda s: (
            _recorded_at(s["record"]["recorded_at"], s["record"]["id"]),
            s["record"]["id"],
        ), reverse=True)
        selected = []
        for kind in ("failure", "success"):
            first = next((s for s in ordered if s["pattern"]["kind"] == kind), None)
            if first is not None:
                selected.append(first)
        selected.extend(s for s in ordered if s not in selected)
        selected = selected[:3]
        observations = []
        for source in selected:
            record, pattern = source["record"], source["pattern"]
            observations.append({
                "source": f"experience/raw/{record['id']}.json",
                "recorded_at": record["recorded_at"], "outcome": record["outcome"],
                "kind": pattern["kind"], "summary": pattern["summary"],
                "procedure": pattern["procedure"], "evidence": record["evidence"],
            })
        matches.append({
            "id": pattern_id, "applies_to": applies, "matched_terms": matched_terms,
            "success_count": sum(s["pattern"]["kind"] == "success" for s in sources),
            "failure_count": sum(s["pattern"]["kind"] == "failure" for s in sources),
            "source_record_count": len(sources),
            "omitted_observation_count": len(sources) - len(selected),
            "observations": observations,
        })
    matches.sort(key=lambda m: (-len(m["matched_terms"]), m["id"]))
    return {
        "schema": "commons-experience-retrieval/v1", "purpose": "skill-improvement-input",
        "query": query, "skill": skill, "records_scanned": len(records),
        "matched_pattern_count": len(matches), "returned_pattern_count": min(limit, len(matches)),
        "matches": matches[:limit],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("compile", "check", "validate", "retrieve"))
    parser.add_argument("--query", default="", help="words describing the skill improvement")
    parser.add_argument("--skill", help="exact applies_to tag")
    parser.add_argument("--limit", type=int, default=3, help="maximum retrieved patterns (1-20)")
    args = parser.parse_args()
    if args.command != "retrieve" and (args.query or args.skill or args.limit != 3):
        parser.error("--query, --skill and --limit apply to retrieve")
    try:
        records = load_records()
        if args.command == "retrieve":
            print(_json(retrieve_experience(records, args.query, args.skill, args.limit)), end="")
            return 0
        outputs = compile_outputs(records)
        if args.command == "compile":
            compile_to_disk(outputs)
            print(f"COMPILED {len(records)} records {len(outputs)} outputs")
        elif args.command == "check":
            drift = check_outputs(outputs)
            if drift:
                print("DRIFT " + " ".join(drift))
                return 1
            print(f"CURRENT {len(records)} records {len(outputs)} outputs")
        else:
            print(f"VALID {len(records)} records {len(outputs)} outputs")
    except ExperienceError as exc:
        print(f"INVALID {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())