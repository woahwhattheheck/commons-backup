"""UIOWA-066: offline, evidence-linked alert review. No provider calls.

Python 3.10+, standard library only. See README.md for input semantics.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EvidenceError(ValueError):
    """An input is contradictory or structurally incomplete."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise EvidenceError(message)


def stamp(value: Any) -> datetime:
    require(type(value) is str, "timestamp must be text")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(result.tzinfo is not None and result.utcoffset() is not None,
                "timestamp must include a UTC offset")
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise EvidenceError(f"invalid timestamp: {value!r}") from exc


def text(value: Any, name: str, optional: bool = False) -> None:
    require((optional and value is None) or
            (type(value) is str and bool(value.strip())), f"{name}: nonempty text required")


def shape(value: Any, keys: str, name: str) -> None:
    require(type(value) is dict and set(value) == set(keys.split()),
            f"{name}: expected fields {keys}")


def unique_rows(rows: Any, keys: str, name: str) -> dict[str, dict]:
    require(type(rows) is list, f"{name}: list required")
    out = {}
    for row in rows:
        shape(row, keys, name)
        text(row["id"], f"{name}.id")
        require(row["id"] not in out, f"duplicate {name} id {row['id']}")
        out[row["id"]] = row
    return out


def strict_load(path: Path) -> dict:
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, f"duplicate JSON key: {key}")
            out[key] = value
        return out
    def nonfinite(value):
        raise EvidenceError(f"nonfinite JSON value: {value}")
    try:
        return json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=pairs, parse_constant=nonfinite)
    except (json.JSONDecodeError, UnicodeError, RecursionError) as exc:
        raise EvidenceError(f"invalid JSON: {exc}") from exc


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def analyze(packet: dict) -> dict:
    shape(packet, "schema evidence_class window coverage evidence episodes notifications", "packet")
    require(packet["schema"] == "uiowa.alert-quality/v1", "unsupported schema")
    require(packet["evidence_class"] == "SYNTHETIC", "this preparation kit accepts SYNTHETIC only")
    shape(packet["window"], "start end", "window")
    start, end = stamp(packet["window"]["start"]), stamp(packet["window"]["end"])
    require(start < end, "window start must precede end")
    ev = unique_rows(packet["evidence"], "id locator excerpt", "evidence")
    for row in ev.values():
        text(row["locator"], "locator")
        text(row["excerpt"], "excerpt")
    def ref(value, optional=False):
        require((optional and value is None) or
                (type(value) is str and value in ev), f"unknown evidence reference: {value!r}")
    cov = unique_rows(packet["coverage"], "id notifications responses rationale_ref", "coverage")
    for row in cov.values():
        for field in ("notifications", "responses"):
            require(row[field] in ("complete", "partial", "unknown"), f"invalid {field} coverage")
        ref(row["rationale_ref"])
    eps = unique_rows(packet["episodes"],
        "id service incident_id linkage_ref impact impact_ref owner_status owner owner_ref "
        "runbook_status runbook_ref escalation_status escalation_ref ack_at ack_ref "
        "action_at action_ref", "episode")
    notes = unique_rows(packet["notifications"],
        "id episode_id rule route at kind duplicate_of value review_ref source_ref", "notification")
    grouped = defaultdict(list)
    for n in notes.values():
        require(type(n["episode_id"]) is str and n["episode_id"] in eps, "unknown episode")
        for field in ("rule", "route"):
            text(n[field], field)
        require(start <= stamp(n["at"]) < end, "notification outside half-open window")
        require(n["kind"] in ("initial", "repeat", "escalation", "update"), "invalid kind")
        require(n["value"] in ("useful", "redundant", "unknown"), "invalid reviewed value")
        ref(n["source_ref"])
        ref(n["review_ref"], optional=n["value"] == "unknown")
        text(n["duplicate_of"], "duplicate_of", optional=True)
        grouped[n["episode_id"]].append(n)
    # Explicit retained review establishes duplication; fingerprints never do.
    for n in notes.values():
        if n["duplicate_of"] is not None:
            other = notes.get(n["duplicate_of"])
            require(other is not None, "duplicate target missing")
            require(n["kind"] == "repeat" and n["value"] == "redundant",
                    "duplicate must be a reviewed redundant repeat")
            require(all(n[k] == other[k] for k in ("episode_id", "rule", "route")),
                    "duplicate cannot cross episode, rule or route")
            require(stamp(other["at"]) < stamp(n["at"]), "duplicate target must be strictly earlier")
    result, recommendations = [], []
    seen_incidents = set()
    for eid, e in sorted(eps.items()):
        require(type(e["service"]) is str and e["service"] in cov, "service coverage missing")
        require(bool(grouped[eid]), "episode requires an observed notification")
        text(e["incident_id"], "incident_id", optional=True)
        ref(e["linkage_ref"], optional=e["incident_id"] is None)
        if e["incident_id"] is not None:
            identity = (e["service"], e["incident_id"])
            require(identity not in seen_incidents, "same service incident split across episodes")
            seen_incidents.add(identity)
        elif len(grouped[eid]) > 1:
            ref(e["linkage_ref"])  # reviewed correlation may exist without an incident ticket
        require(e["impact"] in ("yes", "no", "unknown"), "invalid impact")
        ref(e["impact_ref"], optional=e["impact"] == "unknown")
        require(e["owner_status"] in ("assigned", "unowned", "unknown"), "invalid owner status")
        text(e["owner"], "owner", optional=e["owner_status"] != "assigned")
        require(e["owner_status"] == "assigned" or e["owner"] is None,
                "nonassigned owner must be null")
        ref(e["owner_ref"], optional=e["owner_status"] == "unknown")
        require(e["runbook_status"] in ("useful", "unhelpful", "untested", "missing", "unknown"),
                "invalid runbook status")
        ref(e["runbook_ref"], optional=e["runbook_status"] == "unknown")
        require(e["escalation_status"] in ("tested", "documented", "missing", "unknown"),
                "invalid escalation status")
        ref(e["escalation_ref"], optional=e["escalation_status"] == "unknown")
        ns = sorted(grouped[eid], key=lambda n: (stamp(n["at"]), n["id"]))
        first = stamp(ns[0]["at"])
        times = {}
        for field in ("ack", "action"):
            value = e[field + "_at"]
            if value is None:
                require(e[field + "_ref"] is None, f"{field} evidence without time")
                times[field] = None
            else:
                instant = stamp(value)
                require(first <= instant < end, f"{field} time outside observed episode window")
                ref(e[field + "_ref"])
                times[field] = round((instant - first).total_seconds() / 60, 6)
        # A useful action can precede a button acknowledgement; do not reject that.
        coverage = cov[e["service"]]
        response_state = ("observed" if times["action"] is not None else
                          "not_observed_by_window_end" if coverage["responses"] == "complete"
                          else "unknown_missing_response_coverage")
        row = {"episode_id": eid, "service": e["service"], "incident_id": e["incident_id"],
               "impact": e["impact"], "notifications": len(ns),
               "confirmed_duplicates": sum(n["duplicate_of"] is not None for n in ns),
               "reviewed_redundant": sum(n["value"] == "redundant" for n in ns),
               "escalation_notifications": sum(n["kind"] == "escalation" for n in ns),
               "first_observed_at": first.isoformat(), "ack_minutes": times["ack"],
               "action_minutes": times["action"], "response_state": response_state,
               "latency_basis": "observed_notification_window" if coverage["notifications"] == "complete"
                                else "partial_notification_lower_bound",
               "owner_status": e["owner_status"], "owner": e["owner"],
               "runbook_status": e["runbook_status"], "escalation_status": e["escalation_status"],
               "notification_ids": [n["id"] for n in ns]}
        result.append(row)
        proposals = []
        if row["confirmed_duplicates"]:
            proposals.append(("duplicate_review", "Review same-episode repeat policy without suppressing escalation or separate incidents.",
                              "Compare confirmed redundant deliveries per episode and incident-detection coverage before/after a reviewed trial."))
        if e["owner_status"] != "assigned":
            proposals.append(("routing", "Resolve missing or unknown response ownership with an evidenced routing rehearsal.",
                              "Measure unowned episodes and time from observed page to first useful action."))
        if e["runbook_status"] != "useful":
            proposals.append(("runbook", "Walk through the actual diagnostic task; record useful steps, stale instructions and missing context.",
                              "Compare completion of the same rehearsal task, repair effort and useful-response latency."))
        if e["escalation_status"] != "tested":
            proposals.append(("escalation", "Rehearse escalation with accountable service roles; a document alone is not a tested route.",
                              "Record successful handoff and useful action, not just notification delivery."))
        if times["action"] is None:
            proposals.append(("response_evidence", "Reconcile action records with the episode; acknowledgement alone does not establish response.",
                              "Retain action evidence and report incomplete/censored episodes beside any latency summary."))
        for code, change, measure in proposals:
            refs = {n["source_ref"] for n in ns}
            refs.update(v for k, v in e.items() if k.endswith("_ref") and v is not None)
            recommendations.append({"id": f"AQ-{eid}-{code}", "episode_id": eid,
                                    "reason": code, "proposed_change": change,
                                    "outcome_check": measure, "evidence_ids": sorted(refs)})
    counts = Counter(n["value"] for n in notes.values())
    completed = [r["action_minutes"] for r in result if r["impact"] == "yes" and
                 r["action_minutes"] is not None and r["latency_basis"] == "observed_notification_window"]
    normalization = {**packet, "episodes": sorted(packet["episodes"], key=lambda r: r["id"]),
                     "notifications": sorted(packet["notifications"], key=lambda r: r["id"]),
                     "coverage": sorted(packet["coverage"], key=lambda r: r["id"]),
                     "evidence": sorted(packet["evidence"], key=lambda r: r["id"])}
    return {"schema": "uiowa.alert-quality-report/v1", "evidence_class": "SYNTHETIC",
            "input_sha256": hashlib.sha256(canonical(normalization).encode()).hexdigest(),
            "window": packet["window"], "coverage": normalization["coverage"],
            "summary": {"notifications": len(notes), "observed_episodes": len(eps),
                        "confirmed_duplicates": sum(r["confirmed_duplicates"] for r in result),
                        "reviewed_redundant": counts["redundant"], "reviewed_useful": counts["useful"],
                        "unreviewed": counts["unknown"],
                        "redundant_share_of_reviewed": counts["redundant"] / (counts["redundant"] + counts["useful"])
                                                       if counts["redundant"] + counts["useful"] else None,
                        "explicitly_unowned_episodes": sum(r["owner_status"] == "unowned" for r in result),
                        "unknown_owner_episodes": sum(r["owner_status"] == "unknown" for r in result),
                        "impacting_episodes": sum(r["impact"] == "yes" for r in result),
                        "completed_response_sample_n": len(completed),
                        "median_action_minutes_completed_only": statistics.median(completed) if completed else None},
            "limitations": ["Synthetic preparation, not University evidence or findings.",
                            "Explicit episode IDs and retained review establish grouping, never rule fingerprints alone.",
                            "Missing response records are not zero latency; incomplete exports do not prove absence.",
                            "Completed-only response median excludes partial notification history and censored/unknown episodes.",
                            "No incident census: alert recall, fleet reliability and avoided staff costs are not calculated."],
            "episodes": result, "recommendations": recommendations,
            "evidence": normalization["evidence"]}


def cell(value: Any) -> str:
    """Spreadsheet-safe display export; JSON remains lossless source of truth."""
    if value is None:
        return "UNKNOWN"
    s = canonical(value) if isinstance(value, (dict, list)) else str(value)
    return "'" + s if s.lstrip().startswith(("=", "+", "-", "@")) or s.startswith(("\t", "\r", "\n")) else s


def markdown(report: dict) -> str:
    def esc(value):
        return html.escape(str(value)).replace("|", "&#124;").replace("\n", "<br>")
    lines = ["# Alert usefulness and response readiness", "", "**SYNTHETIC — no University findings.**", "",
             "## Observed sample", "", *[f"- {k}: {esc(v) if v is not None else 'UNKNOWN'}" for k, v in report["summary"].items()],
             "", "## Episode trace", "", "|Episode|Service|Notifications|Duplicates|Useful action (min)|Response evidence|Owner|",
             "|---|---|---:|---:|---:|---|---|"]
    for r in report["episodes"]:
        lines.append("|" + "|".join(esc(r[k]) if r[k] is not None else "UNKNOWN" for k in
                     ("episode_id", "service", "notifications", "confirmed_duplicates", "action_minutes", "response_state", "owner_status")) + "|")
    lines.extend(["", "## Evidence-linked follow-through", ""])
    for r in report["recommendations"]:
        lines.extend([f"### {esc(r['id'])}", r["proposed_change"], "", "Outcome check: " + r["outcome_check"],
                      "", "Evidence: " + ", ".join(esc(x) for x in r["evidence_ids"]), ""])
    lines.extend(["## Source excerpts", ""])
    for e in report["evidence"]:
        lines.extend([f"**{esc(e['id'])}** — {esc(e['locator'])}", esc(e["excerpt"]), ""])
    lines.extend(["## Interpretation limits", "", *["- " + x for x in report["limitations"]], ""])
    return "\n".join(lines)


def export(packet: dict, out: Path) -> dict:
    report = analyze(packet)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (out / "report.md").write_text(markdown(report), encoding="utf-8")
    tables = {"episodes": report["episodes"], "notifications": packet["notifications"],
              "recommendations": report["recommendations"], "evidence": report["evidence"]}
    columns = {
        "episodes": "episode_id service incident_id impact notifications confirmed_duplicates reviewed_redundant escalation_notifications first_observed_at ack_minutes action_minutes response_state latency_basis owner_status owner runbook_status escalation_status notification_ids",
        "notifications": "id episode_id rule route at kind duplicate_of value review_ref source_ref",
        "recommendations": "id episode_id reason proposed_change outcome_check evidence_ids",
        "evidence": "id locator excerpt",
    }
    for name, rows in tables.items():
        # Header-only empty exports replace stale prior rows, rather than hiding them.
        with (out / f"{name}.csv").open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=columns[name].split())
            writer.writeheader()
            writer.writerows({k: cell(v) for k, v in r.items()}
                             for r in sorted(rows, key=lambda r: r.get("id", r.get("episode_id"))))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = export(strict_load(args.input), args.out)
    except (EvidenceError, OSError) as exc:
        parser.exit(2, f"alert-quality: {exc}\n")
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
