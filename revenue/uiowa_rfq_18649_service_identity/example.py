#!/usr/bin/env python3
"""Emit fictional metadata, not a real University inventory or credentials."""
from copy import deepcopy
import json


def sample_inventory():
    owners = [
        {"id": "role-ess", "role": "Fictional ESS service lead", "status": "active", "departure_on": None},
        {"id": "role-ris", "role": "Fictional RIS service lead", "status": "active", "departure_on": None},
        {"id": "role-iam", "role": "Fictional IAM service lead", "status": "active", "departure_on": None},
        {"id": "role-backup", "role": "Fictional continuity duty", "status": "active", "departure_on": None},
        {"id": "role-former", "role": "Fictional former maintainer", "status": "departed", "departure_on": "2026-09-01"},
    ]
    services = [
        {"id": "iam-directory", "group": "IAM", "criticality": "high", "depends_on": []},
        {"id": "ess-registration", "group": "ESS", "criticality": "high", "depends_on": ["iam-directory"]},
        {"id": "ris-submission", "group": "RIS", "criticality": "high", "depends_on": ["iam-directory"]},
        {"id": "ris-export", "group": "RIS", "criticality": "medium", "depends_on": ["ris-submission"]},
    ]
    template = {"id": "svc-shared", "status": "active", "purpose": "Fictional service metadata exchange",
                "privilege_rationale": "Fictional scoped read of required service attributes",
                "owner_id": "role-iam", "continuity_owner_id": "role-backup",
                "consumer_ids": ["iam-directory", "ess-registration"], "consumer_inventory_complete": True,
                "review_due_on": "2026-10-19", "expires_on": "2026-12-01", "owner_transition": None}
    shared = deepcopy(template)
    changed = deepcopy(template)
    changed.update(id="svc-transition", owner_id="role-ris", consumer_ids=["ris-submission"],
                   owner_transition={"from_owner_id": "role-former", "to_owner_id": "role-ris", "effective_on": "2026-09-01"})
    departed = deepcopy(template)
    departed.update(id="svc-departed", owner_id="role-former", consumer_ids=["ris-export"], review_due_on="2026-09-10")
    retired = deepcopy(template)
    retired.update(id="svc-retired-conflict", status="retired", consumer_ids=["ess-registration"])
    unknown = deepcopy(template)
    unknown.update(id="svc-unknown", purpose=None, privilege_rationale=None, owner_id=None, continuity_owner_id=None,
                   consumer_ids=[], consumer_inventory_complete=None, review_due_on=None, expires_on=None)
    retiring = deepcopy(template)
    retiring.update(id="svc-retiring-empty", status="retiring", consumer_ids=[], consumer_inventory_complete=False)
    identities = [shared, changed, departed, retired, unknown, retiring]
    evidence = []
    for identity in identities:
        if identity["id"] == "svc-unknown":
            continue
        for aspect in ("ownership", "purpose", "privilege", "renewal", "continuity", "dependency"):
            evidence.append({"id": f"ev-{identity['id']}-{aspect}", "identity_id": identity["id"], "aspect": aspect,
                             "kind": "demonstration" if aspect == "continuity" else "record", "result": "supports",
                             "observed_on": "2026-08-25" if identity["id"] == "svc-transition" and aspect == "continuity" else "2026-09-10",
                             "owner_id": identity["continuity_owner_id"] if aspect == "continuity" else identity["owner_id"],
                             "reference": f"fictional-register:{identity['id']}:{aspect}"})
    evidence += [
        {"id": "ev-transition-written", "identity_id": "svc-transition", "aspect": "transition", "kind": "procedure",
         "result": "supports", "observed_on": "2026-09-02", "owner_id": "role-ris", "reference": "fictional-register:handoff-plan-only"},
        {"id": "ev-retired-record", "identity_id": "svc-retired-conflict", "aspect": "retirement", "kind": "record",
         "result": "supports", "observed_on": "2026-09-15", "owner_id": "role-iam", "reference": "fictional-register:retirement-ticket"},
        {"id": "ev-retiring-record", "identity_id": "svc-retiring-empty", "aspect": "retirement", "kind": "procedure",
         "result": "supports", "observed_on": "2026-09-15", "owner_id": "role-iam", "reference": "fictional-register:planned-retirement"},
    ]
    return {"schema": "service-identity-inventory/v1", "as_of": "2026-09-19", "evidence_max_age_days": 90,
            "owners": owners, "services": services, "identities": identities, "evidence": evidence}


if __name__ == "__main__":
    print(json.dumps(sample_inventory(), indent=2, sort_keys=True))
