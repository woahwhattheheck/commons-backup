#!/usr/bin/env python3
"""Run the decision records through pinned lifecycle and economics components."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_decision_case import _apply_sets
from case import build_document_ledger
from export import case_document
from model import is_known, load_case

UPSTREAM_COMMIT = "4401ee39b6b6ff7debffafc78b27f9b08e21f4e6"
PINS = {
    "economics": "72b1151521a6801890ba3494a3b3b3d3f4f2997350500977eee59bea47748bea",
    "lifecycle": "db0cf6a6e6a6765088d764555a0513311d9241dd6450b475dfb69cec8057b859",
}
DERIVED = {"monthly_tasks", "baseline_minutes", "author_minutes", "checking_minutes",
           "rework_fraction", "rework_minutes", "loaded_hourly_rate"}


def component(name, path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != PINS[name]:
        raise ValueError(f"{name}: incompatible source revision {digest}; expected {PINS[name]} "
                         f"from {UPSTREAM_COMMIT}. Update the adapter contract before repinning.")
    spec = importlib.util.spec_from_file_location("uiowa111_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def interval(values):
    if not values or any(not is_known(value) for value in values):
        return None
    return {"low": str(min(values)), "base": str(sum(values) / len(values)),
            "high": str(max(values))}


def economics_input(case, costs, engine):
    if not isinstance(costs, dict) or set(costs) != {"currency", "inputs"}:
        raise ValueError("cost assumptions require currency and inputs")
    if not isinstance(costs["inputs"], dict) or set(costs["inputs"]) - (set(engine.FIELDS) - DERIVED):
        raise ValueError("cost assumptions may contain only the remaining canonical economics fields")
    horizon = case.assumption("evaluation_horizon_months")
    if horizon.low != horizon.high or horizon.value != int(horizon.value) or horizon.value <= 0:
        raise ValueError("canonical economics needs one positive whole-month horizon; use separate cases for horizon ranges")
    source = case_document(case)
    digest = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    inputs = {key: {"range": None, "unit": unit, "basis": "unknown",
                    "source": f"Not supplied for {case.case_id}: {key}"}
              for key, (unit, _) in engine.FIELDS.items()}
    inputs.update(costs["inputs"])

    def derived(key, bounds, records):
        inputs[key] = {"range": bounds, "unit": engine.FIELDS[key][0],
                       "basis": "synthetic" if bounds is not None else "unknown",
                       "source": f"case-sha256:{digest}; " + ", ".join(records)}

    for key, name in (("monthly_tasks", "documents_per_month"),
                      ("loaded_hourly_rate", "analyst_hourly_cost")):
        a = case.assumption(name)
        derived(key, dict(low=str(a.low), base=str(a.value), high=str(a.high)), [a.id])
    baseline, assisted = case.docs_for("BASELINE"), case.docs_for("ASSISTED")
    derived("baseline_minutes", interval([build_document_ledger(doc).total for doc in baseline]),
            [doc.id for doc in baseline])
    complete = bool(assisted) and all(build_document_ledger(doc).complete for doc in assisted)

    def totals(kinds):
        return [sum(event.minutes for event in doc.events if event.kind in kinds)
                for doc in assisted] if complete else []

    derived("author_minutes", interval(totals({"AUTHOR", "GENERATE"})), [doc.id for doc in assisted])
    derived("checking_minutes", interval(totals({"CHECK"})), [doc.id for doc in assisted])
    repairs = totals({"REPAIR", "REWORK_AFTER_ACCEPT", "MAINTENANCE_EDIT"})
    repaired = [value for value in repairs if value > 0]
    fraction = len(repaired) / len(repairs) if repairs else None
    derived("rework_fraction", interval([fraction]) if fraction is not None else None,
            [doc.id for doc in assisted])
    derived("rework_minutes", interval(repaired or [0.0]) if complete else None,
            [doc.id for doc in assisted])
    document = {"schema_version": "1.0", "input_basis": "SYNTHETIC",
                "currency": costs["currency"], "horizon_months": int(horizon.value),
                "scenarios": [{"id": case.case_id, "group": "cross-group", "label": case.workflow,
                               "notes": "Fictional effort records mapped to canonical economics. "
                                        "Per-document repair includes post-acceptance maintenance; "
                                        "recurring maintenance_hours excludes that effort.", "inputs": inputs}]}
    engine.validate_document(document)
    return document


def lifecycle_input(case, engine):
    """Project supplied records; do not invent absent document/model evidence."""
    data = dict(schema_version="1.0", synthetic=True, workflow_id=case.case_id,
                group="cross-group", description=case.workflow + "; synthetic ordinal-day projection",
                artifacts=[], cases=[], evaluation_sets=[], versions=[], runs=[],
                comparisons=[], replays=[], events=[])
    anchor = datetime(2000, 1, 1, tzinfo=timezone.utc)

    def timestamp(day):
        return (anchor + timedelta(days=day)).isoformat().replace("+00:00", "Z")

    def artifact(ident, kind, content):
        text = None if content is None else json.dumps(content, sort_keys=True)
        data["artifacts"].append(dict(id=ident, kind=kind, text=text,
            sha256=None if text is None else hashlib.sha256(text.encode()).hexdigest(),
            locator="synthetic://decision-case/" + ident, retained=text is not None))
        return ident

    quality = {row.document_id: row for row in case.quality}
    if len(quality) != len(case.quality):
        raise ValueError("lifecycle adapter needs one quality measurement per document; aggregate explicitly first")
    records = case_document(case)
    snapshot = artifact("source-records", "input_snapshot",
                        {key: records[key] for key in ("documents", "quality_measurements")})
    rubric = artifact("record-projection-rubric", "rubric", {
        "completeness": "Source correct_elements / required_elements; no output was rescored.",
        "repair_minutes": "Sum REPAIR, REWORK_AFTER_ACCEPT and MAINTENANCE_EDIT events.",
        "unknown": "Correctness, usefulness, latency and missing source metrics remain null."})
    for doc in case.documents:
        data["cases"].append(dict(id=doc.id, input_ref=artifact(doc.id + "-input", "case_input", None),
            expectation_ref=artifact(doc.id + "-expectation", "expectation", None), stratum="ordinary"))
    for variant in ("BASELINE", "ASSISTED"):
        docs = case.docs_for(variant)
        if not docs:
            raise ValueError(f"lifecycle adapter needs {variant} documents")
        first = min([0] + [event.day for doc in docs for event in doc.events])
        last = max([0] + [event.day for doc in docs for event in doc.events])
        manifest = {"protocol_id": "source-records", "cases": [
            {"id": doc.id, "input_sha256": None, "expectation_sha256": None} for doc in docs]}
        evaluation = artifact(variant + "-evaluation", "evaluation_set", manifest)
        data["evaluation_sets"].append(dict(artifact_ref=evaluation, protocol_id="source-records",
                                             case_ids=[doc.id for doc in docs]))
        components = {name: None for name in engine.COMPONENTS}
        components["evaluation_set"] = evaluation
        components["input_snapshot"] = snapshot
        components["rubric"] = rubric
        data["versions"].append(dict(id=variant, parent_id=None, changed_at=timestamp(first - 1),
            reason="Source variant projection; model revision and parent history were not recorded.",
            support_owner=None, model_revision=None, model_alias_is_mutable=True, seed=None,
            components=components))
        observations = []
        for doc in docs:
            row = quality.get(doc.id)
            repairs = [event.minutes for event in doc.events
                       if event.kind in {"REPAIR", "REWORK_AFTER_ACCEPT", "MAINTENANCE_EDIT"}]
            repair = sum(repairs) if all(is_known(value) for value in repairs) else None
            observations.append(dict(case_id=doc.id, output_ref=None, error=None,
                correctness=None, completeness=(row.completeness if row and row.required_elements > 0 else None),
                usefulness=None, repair_minutes=repair, latency_ms=None))
            for event in doc.events:
                evidence = artifact(event.id + "-record", "investigation",
                    dict(document_id=doc.id, id=event.id, kind=event.kind, day=event.day,
                         minutes=event.minutes if is_known(event.minutes) else None))
                data["events"].append(dict(id=event.id, version_id=variant, occurred_at=timestamp(event.day),
                    kind="observation", summary=doc.id + ": " + event.kind,
                    owner=None, related_run_ids=[], evidence_refs=[evidence], resolves_event_id=None))
        data["runs"].append(dict(id=variant + "-records", version_id=variant,
            started_at=timestamp(first), finished_at=timestamp(last), observations=observations))
    engine.validate(data)
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--cost-assumptions", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--set", dest="sets", action="append", metavar="NAME=VALUE")
    root = Path(__file__).resolve().parent.parent
    parser.add_argument("--economics-module", type=Path, default=root / "uiowa_rfq_18649_ai_economics/economics.py")
    parser.add_argument("--lifecycle-module", type=Path, default=root / "uiowa_rfq_18649_ai_lifecycle/lifecycle.py")
    args = parser.parse_args(argv)
    try:
        economics = component("economics", args.economics_module)
        lifecycle = component("lifecycle", args.lifecycle_module)
        case = _apply_sets(load_case(args.case), args.sets)
        costs = json.loads(args.cost_assumptions.read_text(), object_pairs_hook=economics.no_duplicates)
        economic_input = economics_input(case, costs, economics)
        history = lifecycle_input(case, lifecycle)
        economic_report = economics.analyze(economic_input)
        lifecycle_report = lifecycle.analyze(history)
        outputs = {"economics/" + name: text for name, text in economics.artifacts(economic_input, economic_report).items()}
        outputs.update({"economics/input.json": json.dumps(economic_input, indent=2) + "\n",
                        "lifecycle/input.json": json.dumps(history, indent=2) + "\n",
                        "lifecycle/report.json": json.dumps(lifecycle_report, indent=2) + "\n",
                        "lifecycle/report.md": lifecycle.markdown(lifecycle_report),
                        "lifecycle/comparisons.csv": lifecycle.comparison_csv(lifecycle_report),
                        "effective_case.json": json.dumps(case_document(case), indent=2) + "\n",
                        "components.json": json.dumps({"source_commit": UPSTREAM_COMMIT, "sha256": PINS}, indent=2) + "\n"})
        for name in outputs:
            target = (args.out / name).resolve()
            if target in {args.case.resolve(), args.cost_assumptions.resolve(),
                          args.economics_module.resolve(), args.lifecycle_module.resolve()}:
                raise ValueError("output would overwrite an input or component")
        for name, text in outputs.items():
            target = args.out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="")
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"WROTE {len(outputs)} artifacts; SYNTHETIC / MODELED_NOT_OBSERVED")
    for row in economic_report["scenarios"]:
        print(f"{row['id']}: economic={row['economic_classification']}; cash={row['cash_classification']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
