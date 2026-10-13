#!/usr/bin/env python3
"""Generate a deterministic, wholly fictional UIOWA-047 interview rehearsal."""
from __future__ import annotations

from copy import deepcopy
import json

AS_OF = "2026-09-19T12:00:00Z"


def event(at: str, outcome: str = "succeeded", fixture_version: str = "fixture-1",
          contract_version: str = "v3", evidence_ref: str | None = "SYNTHETIC-RECEIPT") -> dict:
    return {"at": at, "outcome": outcome, "evidence_ref": evidence_ref,
            "fixture_version": fixture_version, "contract_version": contract_version}


def fixture() -> dict:
    return {"id": "SYN-ESS-01", "contract_id": "SYN-enrollment", "contract_version": "v3",
            "fixture_version": "fixture-1", "origin": "synthetic", "state": "active",
            "owner": "Fictional student-systems test-data steward", "maintenance_hours": 2.5,
            "refresh_interval_days": 14, "recipe_ref": "SYNTHETIC-RECIPE-ESS-01",
            "created_at": "2026-09-01T08:00:00Z", "cleanup_due_at": "2026-10-01T08:00:00Z",
            "refreshes": [event("2026-09-17T12:00:00Z")], "cleanups": [],
            "cases": [{"id": "late-withdrawal", "input_class": "Fictional SYN-STUDENT-A requests withdrawal one second after a fictional cutoff.",
                       "expected_behavior": "Return the documented late-request branch; preserve the prior enrollment record.",
                       "runs": [event("2026-09-18T12:00:00Z")]}]}


def minimal_catalog() -> dict:
    return {"schema_version": 1, "context": "synthetic-demo",
            "contracts": [{"id": "SYN-enrollment", "group": "ESS", "version": "v3",
                           "required_cases": ["late-withdrawal"]}], "fixtures": [fixture()]}


def catalog() -> dict:
    packet = minimal_catalog()
    packet["contracts"][0]["required_cases"] += ["duplicate-enrollment", "unicode-student-key"]
    ess = packet["fixtures"][0]
    ess["cases"].append({"id": "duplicate-enrollment",
                         "input_class": "The same fictional enrollment request with SYN-REQUEST-1 is submitted twice.",
                         "expected_behavior": "Create one enrollment and return a stable duplicate-request result.",
                         "runs": [event("2026-09-18T12:01:00Z")]})
    packet["contracts"] += [
        {"id": "SYN-award", "group": "RIS", "version": "v2", "required_cases": ["renewal-boundary", "duplicate-award"]},
        {"id": "SYN-identity", "group": "IAM", "version": "v5", "required_cases": ["contractor-expiry", "role-change", "repeated-deprovision"]}]
    ris = fixture()
    ris.update(id="SYN-RIS-01", contract_id="SYN-award", contract_version="v2",
               owner="Fictional research-systems fixture maintainer", refresh_interval_days=7,
               maintenance_hours=4, recipe_ref="SYNTHETIC-RECIPE-RIS-01", cleanup_due_at="2026-09-10T12:00:00Z",
               refreshes=[event("2026-09-02T12:00:00Z", contract_version="v2")],
               cases=[{"id": "renewal-boundary", "input_class": "A fictional SYN-AWARD-A renewal falls exactly at an invented funding-period boundary.",
                       "expected_behavior": "Route to the explicitly chosen boundary branch without duplicating the award.",
                       "runs": [event("2026-09-03T12:00:00Z", contract_version="v2")]},
                      {"id": "duplicate-award", "input_class": "An identical fictional SYN-AWARD-A import is replayed.",
                       "expected_behavior": "Keep a single award and preserve the original import provenance.", "runs": []}])
    iam = fixture()
    iam.update(id="SYN-IAM-01", contract_id="SYN-identity", contract_version="v5",
               owner="Fictional identity test-data steward", maintenance_hours=1.5,
               recipe_ref="SYNTHETIC-RECIPE-IAM-01", refreshes=[event("2026-09-17T12:00:00Z", contract_version="v5")],
               cases=[{"id": "contractor-expiry", "input_class": "Fictional SYN-CONTRACTOR-A reaches the declared expiration instant.",
                       "expected_behavior": "Transition the fictional entitlement to its expired state with traceable evidence.",
                       "runs": [event("2026-09-18T10:00:00Z", contract_version="v5"),
                                event("2026-09-18T12:00:00Z", "failed", contract_version="v5")]},
                      {"id": "role-change", "input_class": "Fictional SYN-STAFF-B moves between two explicitly invented roles.",
                       "expected_behavior": "Apply the target entitlement set without retaining obsolete fictional privileges.",
                       "runs": [event("2026-09-18T12:10:00Z", contract_version="v5")]},
                      {"id": "repeated-deprovision", "input_class": "A deprovision event for fictional SYN-STAFF-C is delivered twice.",
                       "expected_behavior": "Reach the same inactive state on repeated delivery without duplicate side effects.", "runs": []}])
    legacy = deepcopy(iam)
    legacy.update(id="SYN-IAM-LEGACY", contract_version="v4", owner=None, maintenance_hours=None, recipe_ref=None,
                  refreshes=[event("2026-09-17T12:00:00Z", contract_version="v4")])
    legacy["cases"] = [deepcopy(iam["cases"][1])]
    legacy["cases"][0]["runs"][0]["contract_version"] = "v4"
    packet["fixtures"] += [ris, iam, legacy]
    return packet


if __name__ == "__main__":
    print(json.dumps(catalog(), indent=2, ensure_ascii=False))
