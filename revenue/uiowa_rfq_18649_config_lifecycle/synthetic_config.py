"""Generate coherent fictional records; no institutional systems or findings."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
if __package__:
    from .config_lifecycle import VERSION
else:
    from config_lifecycle import VERSION


def packet() -> dict:
    sources = []
    def evidence(sid, excerpt, *, kind="artifact", on="2026-09-01"):
        sources.append({"id": sid, "kind": kind, "observed_on": on,
                        "locator": f"synthetic.json#/sources/{len(sources)}", "excerpt": excerpt})
        return [sid]
    def component(cid, group, mode, deps=None):
        config = evidence(cid + "_config", f"Fictional {cid} configuration revision r1 with retained parameter inventory.")
        recipe = evidence(cid + "_recipe", f"Fictional {cid} recipe: provision isolated instance from the pinned input; apply described parameters; run the declared service check.")
        owner = evidence(cid + "_owner", f"Fictional {group} platform role owns maintenance, configuration description and reconstruction support for {cid}.")
        change = evidence(cid + "_change", f"Fictional {cid} r1 introduced on 2026-09-01; accepted review records comparison with its described behavior and recovery needs.")
        inp = evidence(cid + "_input", f"Fictional immutable base-image fixture 1.0 for {cid}; retained in this synthetic evidence collection, not a downloadable product.")
        return {"id": cid, "name": f"Fictional {group} {cid} service", "group": group,
                "state": "active", "owner_role": f"{group} platform maintainer", "owner_evidence": owner,
                "revision": "r1", "config_evidence": config, "recipe_mode": mode, "recipe_evidence": recipe,
                "dependencies": deps or [], "inputs": [{"id": "base_image", "version": "1.0", "evidence": inp}],
                "steps": [{"id": "provision", "instruction": "Provision an isolated instance from the named input version.", "evidence": recipe},
                          {"id": "configure", "instruction": "Apply the retained configuration parameters and declared dependency endpoints.", "evidence": recipe}],
                "checks": ["service_behavior"],
                "changes": [{"id": "init", "revision": "r1", "on": "2026-09-01", "record_evidence": change, "review_evidence": change, "review_outcome": "accepted"}],
                "retirement_evidence": []}
    shared = component("BASE", "shared", "manual")
    ess = component("STUDENT", "ESS", "manual", ["BASE"])
    ris = component("RESEARCH", "RIS", "automated", ["BASE", "BUILD_CACHE_NOT_SUPPLIED"])
    ris["inputs"][0]["version"] = None
    ris["steps"][1]["evidence"] = evidence("RESEARCH_recollection", "Fictional interview: a former maintainer recalls an additional compiler flag, but its value and retained build-cache location have not been supplied.", kind="interview")
    iam = component("SIGNIN", "IAM", "mixed", ["BASE"])
    iam["revision"] = "r2"
    iam["config_evidence"] = evidence("SIGNIN_r2", "Fictional SIGNIN r2 changes service endpoint mapping. The old r1 rebuild record does not demonstrate r2.", on="2026-09-10")
    r2_review = evidence("SIGNIN_change_r2", "Fictional r2 endpoint change on 2026-09-10; reviewed and accepted. Rebuild exercise still outstanding.", on="2026-09-10")
    iam["changes"].append({"id": "endpoint", "revision": "r2", "on": "2026-09-10", "record_evidence": r2_review, "review_evidence": r2_review, "review_outcome": "accepted"})
    old = component("RETIRED_BRIDGE", "IAM", "manual")
    old["state"] = "retired"
    old["retirement_evidence"] = evidence("RETIRED_BRIDGE_close", "Fictional retirement ticket says the bridge has been removed. A separate research configuration still names it; records require reconciliation.", on="2026-09-11")
    ris["dependencies"].append("RETIRED_BRIDGE")
    components = [shared, ess, ris, iam, old]
    exercises = []
    def exercise(eid, target, members, on, scope="from_scratch"):
        manifest = {cid: next(c["revision"] for c in components if c["id"] == cid) for cid in members}
        record = evidence(eid + "_record", f"Fictional exercise {eid}: {scope} for {target}; exact versions {manifest}; provision and configure steps recorded complete for each manifest member. Service behavior check passed in this synthetic narrative.", on=on)
        e = {"id": eid, "target": target, "on": on, "scope": scope, "manifest": manifest,
             "executed_steps": {cid: ["provision", "configure"] for cid in members},
             "checks": {"service_behavior": "pass"}, "evidence": record}
        exercises.append(e)
        return e
    exercise("BASE_REBUILD", "BASE", ["BASE"], "2026-09-12")
    exercise("STUDENT_REBUILD", "STUDENT", ["BASE", "STUDENT"], "2026-09-12")
    historical = exercise("SIGNIN_OLD", "SIGNIN", ["BASE", "SIGNIN"], "2026-09-02")
    historical["manifest"]["SIGNIN"] = "r1"
    sources[-1]["excerpt"] = "Fictional from-scratch SIGNIN r1 and BASE r1 exercise on 2026-09-02; provision/configure complete and service behavior passed. This predates the r2 change."
    exercise("SIGNIN_REPAIR", "SIGNIN", ["BASE", "SIGNIN"], "2026-09-12", "in_place_repair")
    return {"schema": VERSION, "synthetic": True, "as_of": "2026-09-19",
            "evidence_max_age_days": 90, "inventory_coverage": "complete",
            "sources": sources, "components": components, "exercises": exercises}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("synthetic.json"),
                        help="new JSON file; existing files are not overwritten")
    args = parser.parse_args(argv)
    try:
        with args.out.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(packet(), ensure_ascii=False, indent=2) + "\n")
        print(args.out)
        return 0
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
