"""Generate a wholly fictional UIOWA-056 rehearsal input; no real products/CVEs."""
from pathlib import Path
from components import json_bytes


def example():
    doc = {"schema_version": "uiowa.components.v1", "as_of": "2026-09-19",
           "max_evidence_age_days": 120, "horizon_days": 90,
           "services": [{"id": g + "-DEMO", "name": "Fictional " + g + " service", "group": g}
                        for g in ("ESS", "RIS", "IAM")], "components": [], "evidence": []}

    def evidence(cid, kind, observed="2026-09-01", aid=None):
        eid = f"E-{cid}-{kind}-{aid or 'component'}"
        doc["evidence"].append({"id": eid, "kind": kind, "observed_on": observed,
            "locator": "fictional://rehearsal/" + eid, "component_ids": [cid], "advisory_id": aid})
        return [eid]

    def component(cid, support="supported", ends="2027-12-31", groups=("ESS",),
                  owner="Application maintenance lead", inherited=False, low=1, high=2):
        c = {"id": cid, "name": "Fictional component " + cid, "version": "1.0-demo",
             "services": [g + "-DEMO" for g in groups], "owner_role": owner, "inherited": inherited,
             "support": {"state": support, "ends_on": ends,
                         "evidence": evidence(cid, "support") if support != "unknown" else []},
             "inventory_evidence": evidence(cid, "inventory"), "review_due_on": "2026-10-15",
             "last_update_on": "2026-08-25", "advisories": [],
             "maintenance": {"change": "Review records and plan compatibility-tested maintenance where indicated.",
                             "effort_low_days": low, "effort_high_days": high,
                             "coordination_notes": "Coordinate one component decision across listed services; estimates are fictional person-days."}}
        doc["components"].append(c)
        return c

    def advisory(c, disposition="open", exposure="unknown", applicability="affected", current=True):
        aid = "ADV-FICTION-" + c["id"]
        a = {"id": aid, "reported_on": "2026-08-15", "applicability": applicability,
             "applicability_evidence": evidence(c["id"], "advisory", aid=aid) if current else [],
             "exposure": exposure, "exposure_evidence": evidence(c["id"], "exposure", aid=aid) if exposure != "unknown" and current else [],
             "disposition": disposition, "owner_role": "Maintenance triage lead", "due_on": "2026-09-10",
             "exception_until": None, "disposition_evidence": []}
        c["advisories"].append(a)
        return a

    component("C01", groups=("ESS", "IAM"))  # Supported, current, routine review only.
    c = component("C02", "unsupported", "2026-08-31", ("ESS", "RIS"), None, True, 5, 9)
    c["review_due_on"], c["last_update_on"] = "2026-09-01", None
    advisory(c)  # Unsupported is not itself exposure; advisory applicability is separate.
    c = component("C03", "unknown", None, ("IAM",), low=None, high=None)
    a = advisory(c, "accepted_risk", "confirmed", "not_affected", current=False)
    a["exception_until"], a["owner_role"] = "2026-09-18", None
    c = component("C04", ends="2026-10-19", groups=("RIS",), low=2, high=3)
    c["review_due_on"] = None
    doc["evidence"][-1]["observed_on"] = "2026-01-01"
    advisory(c, "resolved")  # A closure label without closure evidence stays unverified.
    c = component("C05", "unsupported", "2026-01-01", ("RIS",), None, True)
    for e in doc["evidence"]:
        if e["component_ids"] == ["C05"] and e["kind"] == "support":
            e["observed_on"] = "2026-01-02"  # Old unsupported claim does not prove current state.
    c = component("C06", ends=None, groups=("ESS", "IAM"))
    a = advisory(c, "accepted_risk", "confirmed")
    a["exception_until"] = "2026-09-20"
    a["disposition_evidence"] = evidence("C06", "exception", aid=a["id"])
    c = component("C07", groups=("IAM",))
    a = advisory(c, "resolved", "not_observed", "not_affected")
    a["disposition_evidence"] = evidence("C07", "closure", aid=a["id"])
    return doc


if __name__ == "__main__":
    Path("sample.json").write_bytes(json_bytes(example()))
