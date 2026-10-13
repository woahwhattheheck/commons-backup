#!/usr/bin/env python3
"""UIOWA-109: one synthetic ledger, three real components, no live actions."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile

SCHEMA = "uiowa-release-recovery-case/v1"
HERE = Path(__file__).resolve().parent
COMPONENTS = {
    "provenance": ("uiowa_rfq_18649_release_provenance/provenance.py", "8060d4787fe3152c788e39a3e786812abdded5fc"),
    "environment": ("uiowa_rfq_18649_environment_drift/drift.py", "a952c1a5034fd5c2ea98f02578f16774243c0c6f"),
    "recovery": ("uiowa_rfq_18649_recovery_attempts/replay.py", "70d0c86685c2f23517b9d2e2e089ca71f17d0cc8"),
}
BASELINE = "7f26cecaf675dc41aeaef0e287f3c7c9a324cd24"
SCENARIOS = ("verified", "restart_only", "failed_verification", "foreign_artifact", "incomplete_history", "missing_deployment", "future_verification")
LIMITATION = ("Fictional rehearsal only, not University evidence, authenticity verification, "
              "a causal finding, a deployment decision, or a service commitment. "
              "The environment engine uses calendar dates; this envelope retains exact source timestamps. "
              "Native component results are retained without promoting one component's success into another's.")
IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
EVENT_FIELDS = {
    "approval": {"revision"}, "build": {"started_at"}, "artifact": set(),
    "deployment": {"environment", "observed_version", "observed_sha256"},
    "environment": {"environment", "value"}, "detection": set(),
    "attempt": {"started_at", "strategy", "outcome"},
    "check": {"attempt_id", "scope", "result"},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def stamp(value):
    require(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value),
        "timestamp must include seconds and timezone")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def identifier(value):
    require(isinstance(value, str) and IDENT.fullmatch(value), "invalid identifier")


def fixture(scenario="verified"):
    require(scenario in SCENARIOS, "unknown scenario")
    content = "SYNTHETIC UIOWA-109 artifact; research portal release 2026.09.18-1.\n"
    sha = hashlib.sha256(content.encode()).hexdigest()
    p = {"schema_version": SCHEMA, "synthetic": True, "case_id": "CASE109",
         "release_id": "REL109", "incident_id": "INC109", "service": "Fictional research portal",
         "group": "RIS", "as_of": "2026-09-18T10:00:00Z", "history_complete": True,
         "artifact": {"id": "ART109", "version": "2026.09.18-1", "sha256": sha, "content": content},
         "source": {"id": "SRC109", "revision": "a" * 40, "repository": "synthetic://research-portal"},
         "environment_effort_hours_assumption": [1, 2], "events": [], "extensions": {}}

    def event(eid, time, kind, **data):
        p["events"].append({"id": eid, "at": "2026-09-18T" + time + ":00Z", "kind": kind,
                            "release_id": p["release_id"], "artifact_id": p["artifact"]["id"], "data": data})

    event("E_APPROVE", "08:40", "approval", revision="a" * 40)
    event("E_BUILD", "08:48", "build", started_at="2026-09-18T08:45:00Z")
    event("E_ARTIFACT", "08:49", "artifact")
    event("E_STAGE", "08:50", "environment", environment="staging", value=False)
    event("E_DEPLOY", "09:00", "deployment", environment="production", observed_version=p["artifact"]["version"], observed_sha256=sha)
    event("E_PROD", "09:01", "environment", environment="production", value=True)
    event("E_DETECT", "09:05", "detection")
    event("A_ROLLBACK", "09:14", "attempt", started_at="2026-09-18T09:10:00Z", strategy="rollback", outcome="failed")
    event("E_RESTART", "09:15", "check", attempt_id="A_ROLLBACK", scope="technical_health", result="passed")
    event("E_FAILED", "09:16", "check", attempt_id="A_ROLLBACK", scope="business_behavior", result="failed")
    event("A_REPAIR", "09:26", "attempt", started_at="2026-09-18T09:20:00Z", strategy="forward_repair", outcome="completed")
    event("E_CONFIG_FIXED", "09:26", "environment", environment="production", value=False)
    event("E_HEALTH", "09:27", "check", attempt_id="A_REPAIR", scope="technical_health", result="passed")
    event("E_BEHAVIOR", "09:32", "check", attempt_id="A_REPAIR", scope="business_behavior", result="passed")
    if scenario in ("restart_only", "missing_deployment"):
        omit = "E_BEHAVIOR" if scenario == "restart_only" else "E_DEPLOY"
        p["events"] = [e for e in p["events"] if e["id"] != omit]
    if scenario == "failed_verification":
        p["events"][-1]["data"]["result"] = "failed"
    if scenario == "foreign_artifact":
        p["events"][-1]["artifact_id"] = "OTHER_ARTIFACT"
    if scenario == "incomplete_history":
        p["history_complete"] = False
    if scenario == "future_verification":
        p["events"][-1]["at"] = "2026-09-18T10:01:00Z"
    return p


def validate(packet):
    require(type(packet) is dict, "case must be an object")
    fields = {"schema_version", "synthetic", "case_id", "release_id", "incident_id", "service", "group", "as_of", "history_complete", "artifact", "source", "environment_effort_hours_assumption", "events", "extensions"}
    require(set(packet) == fields, "case fields differ from v1 contract; use extensions for additional material")
    require(packet["schema_version"] == SCHEMA and packet["synthetic"] is True, "only explicitly synthetic v1 cases are accepted")
    require(type(packet["extensions"]) is dict, "extensions must be an object")
    require(len(canonical(packet).encode()) <= 2 * 1024 * 1024, "case exceeds 2 MiB")
    for name in ("case_id", "release_id", "incident_id"):
        identifier(packet[name])
    require(packet["group"] in ("ESS", "RIS", "IAM"), "invalid group")
    require(isinstance(packet["service"], str) and packet["service"].strip(), "service required")
    require(packet["history_complete"] is None or type(packet["history_complete"]) is bool, "history_complete must be bool or null")
    stamp(packet["as_of"])
    a, s = packet["artifact"], packet["source"]
    require(type(a) is dict and set(a) == {"id", "version", "sha256", "content"}, "artifact fields differ")
    require(type(s) is dict and set(s) == {"id", "revision", "repository"}, "source fields differ")
    identifier(a["id"])
    identifier(s["id"])
    for value in (a["content"], a["version"], s["repository"]):
        require(isinstance(value, str) and value.strip(), "nonempty artifact/source text required")
    require(isinstance(a["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", a["sha256"]), "invalid artifact digest")
    require(isinstance(s["revision"], str) and re.fullmatch(r"[0-9a-f]{40}", s["revision"]), "invalid source revision")
    require(type(packet["events"]) is list and len(packet["events"]) <= 500, "events must be a bounded array")
    seen = set()
    for e in packet["events"]:
        require(type(e) is dict and set(e) == {"id", "at", "kind", "release_id", "artifact_id", "data"}, "event fields differ")
        for key in ("id", "release_id", "artifact_id"):
            identifier(e[key])
        require(e["id"] not in seen, "duplicate event id: " + e["id"])
        seen.add(e["id"])
        stamp(e["at"])
        require(isinstance(e["kind"], str) and e["kind"] in EVENT_FIELDS, "unsupported event kind")
        d = e["data"]
        require(type(d) is dict and set(d) == EVENT_FIELDS[e["kind"]], "event data fields differ: " + e["id"])
        if "started_at" in d:
            stamp(d["started_at"])
        if e["kind"] == "check":
            identifier(d["attempt_id"])
            require(d["scope"] in ("technical_health", "business_behavior"), "unsupported verification scope")
            require(d["result"] in ("passed", "failed", "unknown"), "invalid check result")
        if e["kind"] in ("environment", "deployment"):
            require(d["environment"] in ("staging", "production"), "unsupported environment")
    return packet


def load_components():
    modules, bindings = {}, {}
    for name, (relative, expected) in COMPONENTS.items():
        path = HERE.parent / relative
        raw = path.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        spec = importlib.util.spec_from_file_location("uiowa109_" + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules[name] = module
        bindings[name] = {"path": "revenue/" + relative, "git_blob": blob,
                          "tested_git_blob": expected, "tested_baseline": BASELINE,
                          "version_binding": "EXACT_TESTED_BYTES" if blob == expected else "CHANGED_SINCE_TESTED_BASELINE"}
    return modules, bindings


def adapters(packet):
    """Do not copy decisions: generate each native input from the same records."""
    validate(packet)
    p = deepcopy(packet)
    a, s = p["artifact"], p["source"]
    events = sorted(p["events"], key=lambda e: (stamp(e["at"]), e["id"]))
    active, excluded = [], []
    for e in events:
        reason = ("AFTER_AS_OF" if stamp(e["at"]) > stamp(p["as_of"]) else
                  "FOREIGN_RELEASE" if e["release_id"] != p["release_id"] else
                  "FOREIGN_ARTIFACT" if e["artifact_id"] != a["id"] else None)
        if reason:
            excluded.append({"event_id": e["id"], "reason": reason})
        else:
            active.append(e)
    by_kind = {k: [e for e in active if e["kind"] == k] for k in EVENT_FIELDS}
    for k in ("approval", "build", "artifact", "detection", "deployment"):
        require(len(by_kind[k]) <= 1, "ambiguous " + k + " events; distinguish the case rather than select conveniently")
    one = lambda k: by_kind[k][0] if by_kind[k] else None
    locator = lambda e: "synthetic://" + p["case_id"] + "/events/" + e["id"]
    sources = [{"event_id": e["id"], "observed_at": e["at"], "kind": e["kind"],
                "release_id": e["release_id"], "artifact_id": e["artifact_id"], "locator": locator(e)} for e in events]
    approval, build, artifact, detection = (one(k) for k in ("approval", "build", "artifact", "detection"))
    prov = {"schema_version": 1, "packet_id": p["case_id"], "data_class": "synthetic",
            "evidence": [{"id": e["id"], "locator": locator(e), "owner_role": "fictional_operator", "kind": "synthetic", "captured_at": e["at"]} for e in active],
            "sources": [{**s, "approved_revision": approval["data"]["revision"] if approval else None,
                         "approved_at": approval["at"] if approval else None, "approval_evidence_id": approval["id"] if approval else None}],
            "builds": [], "artifacts": [], "deployments": []}
    if build:
        prov["builds"] = [{"id": build["id"], "source_id": s["id"], "observed_repository": s["repository"],
                           "observed_revision": s["revision"], "builder_id": "fictional_builder",
                           "recipe_uri": "synthetic://fixture-recipe", "recipe_sha256": digest("fixture recipe"),
                           "started_at": build["data"]["started_at"], "finished_at": build["at"], "evidence_id": build["id"],
                           "input_coverage": "declared_complete", "materials": [{"uri": s["repository"], "sha256": digest(s["revision"])}]}]
    if artifact:
        prov["artifacts"] = [{"id": a["id"], "build_id": build["id"] if build else None,
                              "version": a["version"], "sha256": a["sha256"], "local_path": "artifact.txt", "evidence_id": artifact["id"]}]
    prov["deployments"] = [{"id": e["id"], "artifact_id": a["id"], **e["data"], "observed_at": e["at"], "evidence_id": e["id"]} for e in by_kind["deployment"]]

    def environment(cutoff):
        observations = [e for e in by_kind["environment"] if stamp(e["at"]) <= cutoff]
        same_time = {}
        for e in observations:
            key = (e["data"]["environment"], stamp(e["at"]))
            value = canonical(e["data"]["value"])
            require(key not in same_time or same_time[key] == value, "conflicting simultaneous environment observations")
            same_time[key] = value
        latest = {e["data"]["environment"]: e for e in observations}
        return {"schema_version": 1, "label": "SYNTHETIC " + p["case_id"], "as_of": cutoff.date().isoformat(),
                "max_age_days": 1, "environments": ["staging", "production"], "baseline": "staging",
                "evidence": [{"id": e["id"], "kind": "artifact", "captured_on": stamp(e["at"]).date().isoformat(), "locator": locator(e)} for e in observations],
                "checks": [{"id": "ENV109", "group": p["group"], "service": p["service"], "dimension": "configuration",
                            "key": "export_feature_enabled", "impact": "Hypothesis: recorded flag difference may affect export behavior; no causality inferred.",
                            "owner_role": "fictional_operator", "effort_hours": p["environment_effort_hours_assumption"], "intentions": [],
                            "values": {env: {"state": "observed", "value": e["data"]["value"], "evidence_id": e["id"]} for env, e in latest.items()}}]}

    attempts = by_kind["attempt"]
    # Chronological start ordering preserves the actual retry sequence; native replay checks overlaps.
    attempts.sort(key=lambda e: (stamp(e["data"]["started_at"]), e["id"]))
    recovery_events = by_kind["detection"] + attempts + by_kind["check"]
    recovery = {"schema_version": "uiowa-recovery-attempts/v1", "packet_id": p["case_id"], "synthetic": True, "as_of": p["as_of"],
                "evidence": [{"id": e["id"], "incident_id": p["incident_id"],
                              "attempt_id": e["id"] if e["kind"] == "attempt" else e["data"].get("attempt_id"),
                              "kind": "record", "observed_at": e["at"], "locator": locator(e), "excerpt": "Synthetic event " + canonical(e["data"])} for e in recovery_events],
                "incidents": [{"id": p["incident_id"], "group": p["group"], "service": p["service"], "release_id": p["release_id"],
                               "context": "exercise", "change_type": "configuration", "detected_at": detection["at"] if detection else None,
                               "detection_refs": [detection["id"]] if detection else [], "history_complete": p["history_complete"],
                               "target_minutes": None, "attempts": [{"id": e["id"], **e["data"], "finished_at": e["at"], "record_refs": [e["id"]],
                               "checks": [{"id": c["id"], "scope": c["data"]["scope"], "observed_at": c["at"], "result": c["data"]["result"], "evidence_refs": [c["id"]]}
                                          for c in by_kind["check"] if c["data"]["attempt_id"] == e["id"]]} for e in attempts]}]}
    cutoff = stamp(detection["at"]) if detection else min([stamp(e["at"]) for e in events] or [stamp(p["as_of"])])
    return {"provenance": prov, "environment_at_detection": environment(cutoff),
            "environment_at_as_of": environment(stamp(p["as_of"])), "recovery": recovery}, sources, excluded


def run(packet):
    inputs, sources, excluded = adapters(packet)
    modules, bindings = load_components()
    with tempfile.TemporaryDirectory(prefix="uiowa109-artifact-") as folder:
        root = Path(folder)
        (root / "artifact.txt").write_bytes(packet["artifact"]["content"].encode())
        outputs = {"provenance": modules["provenance"].inspect(inputs["provenance"], root),
                   "environment_at_detection": modules["environment"].analyze(inputs["environment_at_detection"]),
                   "environment_at_as_of": modules["environment"].analyze(inputs["environment_at_as_of"]),
                   "recovery": modules["recovery"].replay(inputs["recovery"])}
    # Check real output identifiers and source locators, rather than attaching an unverified common label.
    indexed = {s["event_id"]: s for s in sources}
    for name in ("environment_at_detection", "environment_at_as_of"):
        for e in outputs[name]["evidence_register"]:
            require(e["id"] in indexed and e["locator"] == indexed[e["id"]]["locator"], "environment source binding changed")
    for e in outputs["recovery"]["evidence"]:
        require(e["id"] in indexed and e["locator"] == indexed[e["id"]]["locator"] and e["observed_at"] == indexed[e["id"]]["observed_at"], "recovery source binding changed")
    for trace in outputs["provenance"]["traces"]:
        require(trace["deployment_id"] in indexed, "provenance deployment binding changed")
        require(trace["artifact_id"] in (None, packet["artifact"]["id"]), "provenance artifact binding changed")
        require(trace["source_id"] in (None, packet["source"]["id"]), "provenance source binding changed")
    incident = outputs["recovery"]["incidents"][0]
    require(incident["release_id"] == packet["release_id"], "recovery release binding changed")
    prov = outputs["provenance"]
    excluded_ids = {e["event_id"] for e in excluded}
    selected = {e["kind"]: e for e in packet["events"] if e["id"] not in excluded_ids
                and e["kind"] in ("approval", "build", "artifact", "deployment", "detection")}
    join_issues = []
    order = ("approval", "build", "artifact", "deployment", "detection")
    if set(selected) != set(order):
        join_issues.append("MISSING_RELEASE_TIMELINE_EVENT")
    else:
        times = [stamp(selected[k]["at"]) for k in order]
        times.insert(1, stamp(selected["build"]["data"]["started_at"]))
        if times != sorted(times):
            join_issues.append("RELEASE_TIMELINE_CONTRADICTION")
    attempts = inputs["recovery"]["incidents"][0]["attempts"]
    attempt_ids = {a["id"] for a in attempts}
    orphan_checks = [e["id"] for e in packet["events"] if e["id"] not in excluded_ids
                     and e["kind"] == "check" and e["data"]["attempt_id"] not in attempt_ids]
    if orphan_checks:
        join_issues.append("ORPHAN_VERIFICATION_RECORD")
    linked = prov["status"] == "LINKED_RECORDS" and bool(prov["traces"]) and not join_issues
    endpoint_sources = []
    if incident["verified_at"] is not None and attempts:
        checks = attempts[-1]["checks"]
        for scope in ("technical_health", "business_behavior"):
            scoped = [c for c in checks if c["scope"] == scope]
            latest = max(stamp(c["observed_at"]) for c in scoped)
            endpoint_sources.extend(c["id"] for c in scoped if stamp(c["observed_at"]) == latest)
    measured = incident["incident_detection_to_verified_minutes"]
    summary = {"synthetic": True, "case_id": packet["case_id"], "release_id": packet["release_id"],
               "artifact_id": packet["artifact"]["id"], "artifact_version": packet["artifact"]["version"],
               "artifact_sha256": packet["artifact"]["sha256"], "source_id": packet["source"]["id"],
               "provenance_status": prov["status"], "environment_at_detection": outputs["environment_at_detection"]["comparisons"][0]["status"],
               "environment_at_as_of": outputs["environment_at_as_of"]["comparisons"][0]["status"],
               "recovery_status": incident["status"], "detected_at": incident["detected_at"], "verified_at": incident["verified_at"],
               "native_detection_to_verified_minutes": measured,
               "release_linked_recovery_minutes": measured if linked else None,
               "release_link_status": "LINKED_RECORDS" if linked else "NOT_ESTABLISHED",
               "excluded_events": excluded, "join_issues": join_issues, "orphan_check_ids": orphan_checks,
               "verified_source_event_ids": sorted(endpoint_sources), "limitation": LIMITATION}
    return {"schema_version": SCHEMA, "synthetic": True, "input_sha256": digest(packet), "summary": summary,
            "component_bindings": bindings, "source_bindings": sources, "inputs": inputs, "outputs": outputs,
            "extensions": deepcopy(packet["extensions"])}


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result
    with Path(path).open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    require(len(raw) <= 2 * 1024 * 1024, "input exceeds 2 MiB")
    def constant(value):
        raise ValueError("nonfinite JSON value: " + value)
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--scenario", choices=SCENARIOS, default="verified")
    source.add_argument("--ledger", type=Path)
    parser.add_argument("--output", type=Path, help="Create a new output directory; never overwrite")
    args = parser.parse_args(argv)
    try:
        packet = load(args.ledger) if args.ledger else fixture(args.scenario)
        report = run(packet)
        if args.output:
            args.output.mkdir(parents=True, exist_ok=False)
            products = {"ledger.json": packet, "report.json": report, "summary.json": report["summary"]}
            products.update({"input-" + k + ".json": v for k, v in report["inputs"].items()})
            products.update({"output-" + k + ".json": v for k, v in report["outputs"].items()})
            for name, value in products.items():
                (args.output / name).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
            (args.output / "artifact.txt").write_bytes(packet["artifact"]["content"].encode())
            hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.output.iterdir())}
            (args.output / "SHA256SUMS.json").write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report["summary"], indent=2, sort_keys=True))
        return 0
    except (ValueError, TypeError, KeyError, OSError, RecursionError, OverflowError) as exc:
        print("release-recovery-case: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
