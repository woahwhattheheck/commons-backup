#!/usr/bin/env python3
"""Generate an entirely fictional, deterministic four-version AI history."""
import copy
import hashlib
import json


def history():
    data = dict(schema_version="1.0", synthetic=True, workflow_id="fictional-doc-assistant",
                group="ESS", description="SYNTHETIC: fictional documentation assistant; no Iowa observations.",
                artifacts=[], cases=[], evaluation_sets=[], versions=[], runs=[], comparisons=[], replays=[], events=[])

    def artifact(ident, kind, text):
        data["artifacts"].append(dict(id=ident, kind=kind, sha256=hashlib.sha256(text.encode()).hexdigest(),
                                      locator=f"synthetic://fixture/{ident}", retained=True, text=text))
        return ident

    tasks = [
        ("ordinary", "Summarize the stated three-step deployment process.", "Preserve build, verify, then deploy; do not invent approval."),
        ("ambiguous", "Two owners are named. Who decides?", "Describe the conflict; request the current accountable role."),
        ("stale-context", "The retained operating note expired before this release.", "Flag stale evidence; do not claim it is current."),
        ("missing-information", "There is no documented restore result. Is recovery demonstrated?", "Unknown; a backup record alone does not demonstrate restoration."),
    ]
    for i, (stratum, prompt, expected) in enumerate(tasks, 1):
        data["cases"].append(dict(id=f"c{i}", stratum=stratum,
                                 input_ref=artifact(f"in{i}", "case_input", prompt),
                                 expectation_ref=artifact(f"expected{i}", "expectation", expected)))
    for ident, protocol, count in (("eval1", "p1", 4), ("eval2", "p2", 2)):
        artifacts = {a["id"]: a for a in data["artifacts"]}
        manifest = {"protocol_id": protocol, "cases": [
            {"id": c["id"], "input_sha256": artifacts[c["input_ref"]]["sha256"],
             "expectation_sha256": artifacts[c["expectation_ref"]]["sha256"]}
            for c in data["cases"][:count]]}
        artifact(ident, "evaluation_set", json.dumps(manifest, sort_keys=True))
        data["evaluation_sets"].append(dict(artifact_ref=ident, protocol_id=protocol,
                                            case_ids=[c["id"] for c in data["cases"][:count]]))
    shared = {
        "input_snapshot": artifact("snapshot", "input_snapshot", "Fictional process snapshot; all source statements above."),
        "rubric": artifact("rubric", "rubric", "Manual synthetic rubric: correctness boolean; completeness/usefulness 0..1; repair minutes; latency milliseconds."),
        "code": artifact("code1", "code", "Synthetic pipeline source manifest revision 1."),
        "environment": artifact("env1", "environment", "Fictional runtime manifest revision 1; not model weights."),
        "configuration": artifact("config1", "configuration", '{"sampling":"fictional","temperature":0,"seed":17}'),
    }
    artifact("model1", "model", "Fictional Model A immutable revision 1 manifest, NOT weights.")
    artifact("model2", "model", "Fictional Model B immutable revision 2 manifest, NOT weights.")
    artifact("prompt1", "prompt", "Use only supplied context. Explicitly preserve unknowns and source conflicts.")
    artifact("prompt2", "prompt", "Produce a short answer from the context.")
    artifact("prompt3", "prompt", "Preserve unknowns, name conflicting sources, and check evidence freshness.")
    for n, model, prompt, reason in [
        (1, "model1", "prompt1", "Baseline on four synthetic evidence-handling tasks."),
        (2, "model2", "prompt2", "Changed both model and prompt; attribution is confounded."),
        (3, "model2", "prompt3", "Restore explicit uncertainty/freshness instructions; assess repair."),
        (4, "model2", "prompt3", "Changed evaluation set and lost runtime ownership/retention evidence."),
    ]:
        components = {**shared, "model": model, "prompt": prompt, "evaluation_set": "eval2" if n == 4 else "eval1"}
        data["versions"].append(dict(id=f"v{n}", parent_id=f"v{n-1}" if n > 1 else None,
            changed_at=f"2026-09-{n:02d}T09:00:00Z", reason=reason,
            support_owner=None if n == 4 else "Fictional application-support role",
            model_revision=None if n == 4 else f"fictional-revision-{1 if n == 1 else 2}",
            model_alias_is_mutable=n == 4, seed=None if n == 4 else 17, components=components))
    # v4 has an explicitly unretained environment, not invented current evidence.
    data["artifacts"].append(dict(id="env-lost", kind="environment", sha256=None,
                                  locator="synthetic://fixture/environment-not-retained", retained=False, text=None))
    data["versions"][3]["components"]["environment"] = "env-lost"

    def run(ident, version, correct, repair, hour=10, variant=False):
        observations = []
        for i, (ok, minutes) in enumerate(zip(correct, repair), 1):
            answer = f"Synthetic answer c{i}: {'expected evidence handling' if ok else 'unsupported inference'}"
            if variant and i == 2:
                answer += "; different wording in repeated output"
            observations.append(dict(case_id=f"c{i}", output_ref=artifact(f"{ident}-o{i}", "output", answer),
                error=None, correctness=ok, completeness=1.0 if ok else 0.25,
                usefulness=1.0 if ok else 0.0, repair_minutes=minutes, latency_ms=1000+version*100))
        data["runs"].append(dict(id=ident, version_id=f"v{version}",
            started_at=f"2026-09-{version:02d}T{hour:02d}:00:00Z",
            finished_at=f"2026-09-{version:02d}T{hour:02d}:01:00Z", observations=observations))

    run("r1", 1, [True]*4, [1, 1, 2, 2])
    run("r1-repeat", 1, [True]*4, [1, 1, 2, 2], hour=11)
    run("r2", 2, [True, False, False, False], [1, 9, 12, None])
    # c4 failed to produce an answer. Its scores and output are unknown, not zero.
    data["runs"][-1]["observations"][-1].update(output_ref=None, error="synthetic timeout",
                                                correctness=None, completeness=None, usefulness=None)
    run("r3", 3, [True]*4, [1, 2, 2, 2])
    run("r3-repeat", 3, [True]*4, [1, 2, 2, 2], hour=11, variant=True)
    run("r4", 4, [True, True], [1, 1])
    data["comparisons"] = [dict(id="regression", baseline_run="r1", candidate_run="r2"),
                           dict(id="repair", baseline_run="r2", candidate_run="r3"),
                           dict(id="changed-evaluation", baseline_run="r3", candidate_run="r4")]
    data["replays"] = [dict(id="baseline-repeat", original_run="r1", repeat_run="r1-repeat"),
                       dict(id="repair-repeat", original_run="r3", repeat_run="r3-repeat")]
    investigation = artifact("investigation1", "investigation", "SYNTHETIC investigation: model and prompt changed together; c2/c3 unsupported inference; c4 timeout. No single-cause conclusion.")
    repair_evidence = artifact("repair-check", "investigation", "SYNTHETIC follow-up r3: four correctness observations, but r3-repeat c2 wording differs. Functional score improvement does not prove exact replay.")
    data["events"] = [
        dict(id="incident1", version_id="v2", occurred_at="2026-09-02T10:02:00Z", kind="incident",
             summary="Synthetic regression: uncertainty mishandled and one timeout.", owner="Fictional application-support role",
             related_run_ids=["r2"], evidence_refs=[investigation], resolves_event_id=None),
        dict(id="investigate1", version_id="v2", occurred_at="2026-09-02T11:00:00Z", kind="investigation",
             summary="Both model and prompt changed; cannot isolate their effects.", owner="Fictional evaluator role",
             related_run_ids=["r2"], evidence_refs=[investigation], resolves_event_id=None),
        dict(id="resolution1", version_id="v3", occurred_at="2026-09-03T11:02:00Z", kind="resolution",
             summary="Recorded repair evidence; exact wording still varies.", owner="Fictional application-support role",
             related_run_ids=["r3", "r3-repeat"], evidence_refs=[repair_evidence], resolves_event_id="incident1"),
        dict(id="incident2", version_id="v4", occurred_at="2026-09-04T10:02:00Z", kind="incident",
             summary="Environment retention and support ownership need follow-up; no production defect inferred.", owner=None,
             related_run_ids=["r4"], evidence_refs=[], resolves_event_id=None),
    ]
    return copy.deepcopy(data)


if __name__ == "__main__":
    print(json.dumps(history(), indent=2, ensure_ascii=False, allow_nan=False))
