"""Generate a wholly fictional failed-rollback / forward-repair incident."""
from copy import deepcopy
import json


def packet():
    evidence = []

    def record(key, attempt, minute, excerpt):
        evidence.append({"id": key, "incident_id": "MIG-01", "attempt_id": attempt,
                         "kind": "record", "observed_at": f"2026-09-18T11:{minute}:00Z",
                         "locator": "example.py / fictional record " + key, "excerpt": excerpt})
        return [key]

    def check(key, scope, minute, result="passed"):
        return {"id": key, "scope": scope, "observed_at": f"2026-09-18T11:{minute}:00Z",
                "result": result, "evidence_refs": record(key, "A2", minute, "Fictional " + scope + " result: " + result)}

    detection = record("E-DETECT", None, "02", "Fictional research submission failed after an adapter migration.")
    rollback = record("E-A1", "A1", "10", "Fictional rollback attempted; old adapter could not read the changed schema.")
    repair = record("E-A2", "A2", "30", "Fictional forward repair completed; verification still needed.")
    checks = [check("E-HEALTH", "technical_health", "31"),
              check("E-BUSINESS", "business_behavior", "34"),
              check("E-DATA", "data_integrity", "45")]
    return {"schema_version": "uiowa-recovery-attempts/v1", "packet_id": "SYNTHETIC-RETRY-01",
            "synthetic": True, "as_of": "2026-09-19T00:00:00Z", "evidence": evidence,
            "incidents": [{"id": "MIG-01", "group": "RIS", "service": "Fictional award adapter",
                           "release_id": "REL-17", "context": "exercise", "change_type": "data_migration",
                           "detected_at": "2026-09-18T11:02:00Z", "detection_refs": detection,
                           "history_complete": True, "target_minutes": 30,
                           "attempts": [
                               {"id": "A1", "strategy": "rollback", "started_at": "2026-09-18T11:06:00Z",
                                "finished_at": "2026-09-18T11:10:00Z", "outcome": "failed",
                                "record_refs": rollback, "checks": []},
                               {"id": "A2", "strategy": "forward_repair", "started_at": "2026-09-18T11:15:00Z",
                                "finished_at": "2026-09-18T11:30:00Z", "outcome": "completed",
                                "record_refs": repair, "checks": checks}]}]}


def incomplete_packet():
    value = deepcopy(packet())
    value["packet_id"] = "SYNTHETIC-RETRY-INCOMPLETE"
    check = value["incidents"][0]["attempts"][1]["checks"][2]
    check.update(result="unknown", observed_at=None, evidence_refs=[])
    value["evidence"] = [e for e in value["evidence"] if e["id"] != "E-DATA"]
    return value


if __name__ == "__main__":
    print(json.dumps(packet(), indent=2))
