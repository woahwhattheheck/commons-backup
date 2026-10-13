"""Produce a fully fictional ESS/RIS/IAM interview and artifact-review packet."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def sample() -> dict:
    sources = []
    def evidence(sid, kind, date, excerpt):
        sources.append({"id": sid, "kind": kind, "observed_at": date,
                        "locator": "synthetic-evidence.md#" + sid.lower(), "excerpt": excerpt})
        return sid
    evidence("EV-QUEUE", "incident_record", "2026-09-03T12:00:00Z",
             "Fictional shared queue reports: retry amplification exhausted the worker pool during both registration and research deadline traffic. These are two incidents, not two independent implementations of a practice.")
    evidence("EV-TIMEOUT", "incident_record", "2026-09-06T12:00:00Z",
             "Fictional sign-in dependency waited without a bounded timeout; no single responder had a current dependency map.")
    evidence("EV-IMPL", "implementation", "2026-09-07T10:00:00Z",
             "Fictional change C-17 applied a bounded retry policy to the registration client; retained version and deployment record match the target service.")
    evidence("EV-VERIFY", "verification", "2026-09-07T11:00:00Z",
             "Fictional rehearsal V-17 confirms bounded attempts under a temporary unavailable dependency and successful registration completion after recovery. This demonstrates the change, not months of operating benefit.")
    evidence("EV-DECISION", "decision", "2026-09-09T10:00:00Z",
             "Fictional operations review D-9 replaces a broad sign-in platform rewrite with bounded timeout and dependency-map work. A small rehearsal isolated the immediate behavior; larger replacement remains an option if residual conditions persist. Service reliability role owns the alternative and its validation.")
    evidence("EV-BEFORE", "measurement", "2026-09-06T23:00:00Z",
             "Fictional registration cohort: September 1–6, six retry storms in 1,000 registration attempts; defined event rule and complete attempt census.")
    evidence("EV-AFTER", "measurement", "2026-09-16T00:00:00Z",
             "Fictional same registration cohort: September 8–15, two retry storms in 2,000 attempts; same event rule and complete census. Demand mix may still differ, so the comparison is descriptive.")
    incidents = []
    specs = [("INC-ESS-1", "ESS", "Registration submission", "2026-09-01", ["COND-QUEUE"], "complete"),
             ("INC-RIS-1", "RIS", "Research submission", "2026-09-03", ["COND-QUEUE"], "partial"),
             ("INC-IAM-1", "IAM", "Sign-in", "2026-09-06", ["COND-TIMEOUT", "COND-MAP"], "partial")]
    for iid, group, service, date, conditions, coverage in specs:
        sid = evidence("EV-" + group, "incident_record", date + "T12:00:00Z",
                       "Fictional " + service + " record: impact 09:00, detection 09:05, coordination 09:10, mitigation 09:20, restoration 10:00, business verification 10:15, review 11:00 UTC. RIS lacks retained verification; IAM lacks impact-start evidence. These omissions limit inference.")
        events = []
        for kind, clock, note in (("impact_start", "09:00", "First reported user-visible failure"),
                                 ("detected", "09:05", "Service investigation began"),
                                 ("coordinated", "09:10", "Service role and dependency role coordinated"),
                                 ("mitigated", "09:20", "Temporary response reduced impact"),
                                 ("restored", "10:00", "Service restoration declared"),
                                 ("verified", "10:15", "Representative business transaction checked"),
                                 ("reviewed", "11:00", "Contributing conditions and open questions discussed")):
            if group == "RIS" and kind == "verified":
                continue
            refs = [] if group == "IAM" and kind == "impact_start" else [sid]
            events.append({"kind": kind, "at": date + "T" + clock + ":00Z", "note": note, "evidence_ids": refs})
        incidents.append({"id": iid, "group": group, "service": service,
                          "impact": "Fictional user transactions delayed; total affected population is not established.",
                          "coverage": coverage, "evidence_ids": [sid], "condition_ids": conditions, "events": events,
                          "review": {"analysis": "The operating conditions and incomplete support context made recurrence possible; examine the conditions, not individual performance.",
                                     "analysis_evidence_ids": [sid], "sharing_evidence_ids": [sid] if group == "ESS" else [],
                                     "unresolved_questions": ["What operating exposure and retained verification would justify the next conclusion?"]}})
    def action(aid, description, incident_ids, condition_ids, status, owner, due, completed=None, impl=None, verify=None):
        return {"id": aid, "description": description, "incident_ids": incident_ids, "condition_ids": condition_ids,
                "status": status, "owner_role": owner, "created_at": "2026-09-06T14:00:00Z", "due_at": due,
                "completed_at": completed, "implementation_evidence_ids": impl or [],
                "verification_evidence_ids": verify or [], "replacement": None, "effectiveness": None}
    actions = [
        action("ACT-01", "Bound registration retries and demonstrate recovery behavior", ["INC-ESS-1"], ["COND-QUEUE"], "closed", "ESS delivery role", "2026-09-08T00:00:00Z", "2026-09-07T10:30:00Z", ["EV-IMPL"], ["EV-VERIFY"]),
        action("ACT-02", "Exercise shared-queue saturation with both consuming services", ["INC-ESS-1", "INC-RIS-1"], ["COND-QUEUE"], "in_progress", "Shared service reliability role", "2026-09-10T00:00:00Z"),
        action("ACT-03", "Retain research-submission business verification evidence", ["INC-RIS-1"], ["COND-QUEUE"], "closed", "RIS service role", "2026-09-12T00:00:00Z", "2026-09-11T10:00:00Z"),
        action("ACT-04", "Replace the sign-in integration platform", ["INC-IAM-1"], ["COND-TIMEOUT"], "replaced", "IAM service role", "2026-09-10T00:00:00Z"),
        action("ACT-05", "Bound dependency timeout and verify sign-in recovery before larger redesign", ["INC-IAM-1"], ["COND-TIMEOUT"], "open", "IAM service reliability role", "2026-09-17T00:00:00Z"),
        action("ACT-06", "Reconstruct and rehearse the dependency ownership map", ["INC-IAM-1"], ["COND-MAP"], "open", None, None)]
    actions[3]["replacement"] = {"action_id": "ACT-05", "reason": "A narrower, testable alternative addresses the same contributing condition with less adoption effort; revisit after rehearsal.", "evidence_ids": ["EV-DECISION"]}
    actions[0]["effectiveness"] = {"metric": "retry storms per registration attempt", "direction": "lower",
        "before": {"start": "2026-09-01T00:00:00Z", "end": "2026-09-06T23:00:00Z", "events": 6, "exposure": 1000,
                   "unit": "registration attempts", "cohort": "registration-client-v1", "complete": True, "evidence_ids": ["EV-BEFORE"]},
        "after": {"start": "2026-09-08T00:00:00Z", "end": "2026-09-16T00:00:00Z", "events": 2, "exposure": 2000,
                  "unit": "registration attempts", "cohort": "registration-client-v1", "complete": True, "evidence_ids": ["EV-AFTER"]}}
    return {"schema": "uiowa-incident-learning/v1", "classification": "synthetic", "as_of": "2026-09-19T00:00:00Z",
            "sources": sources, "incidents": incidents, "actions": actions,
            "conditions": [{"id": "COND-QUEUE", "description": "Shared retry amplification under deadline traffic", "evidence_ids": ["EV-QUEUE"], "shared_dependency": "fictional shared queue"},
                           {"id": "COND-TIMEOUT", "description": "Unbounded dependency wait in sign-in path", "evidence_ids": ["EV-TIMEOUT"], "shared_dependency": None},
                           {"id": "COND-MAP", "description": "Dependency-map freshness not established", "evidence_ids": [], "shared_dependency": None}]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    data = sample()
    (args.directory / "packet.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Synthetic incident evidence", "", "Entirely fictional. Not University observations.", ""]
    for source in data["sources"]:
        lines.extend(["## " + source["id"], "", source["observed_at"] + " / " + source["kind"], "", source["excerpt"], ""])
    (args.directory / "synthetic-evidence.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
