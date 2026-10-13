#!/usr/bin/env python3
"""Offline UIOWA-080 toy swap, response validation, and existing-assessor bridge."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path

from guarded_port import GuardedPort
from portlib.caller import route_document, route_documents, summarize_run
from portlib.port import Classification, ClassificationPort, Document, RoutingPolicy, check_conformance
from portlib.providers.fake_alpha import AlphaClassificationAdapter
from portlib.providers.fake_beta import BetaClassificationAdapter

ROOT = Path(__file__).resolve().parent
DONOR_COMMIT = "c3a51c6b16eb2c45ba887e851fd75f7a2d5c5782"
DONOR_BLOBS = {
    "portlib/__init__.py": "1f6b57363b9a6a6b0a6e12ac58bba8af6dd3d4d4",
    "portlib/caller.py": "248a17c399a13a24e48f9cd36aa01de3d8854139",
    "portlib/caller_leaky.py": "0629f3659aac2cacae0cfe811b76a67dcfb6b98c",
    "portlib/port.py": "329dc165a61b141db34cfc8d88f069ebc60e65fc",
    "portlib/providers/__init__.py": "df8717edde71c8b84ec9bea068148dbccac58b70",
    "portlib/providers/fake_alpha.py": "ce02bf78ae1d2f20a3c30b1e5603f97ac526cd50",
    "portlib/providers/fake_beta.py": "28a50f691f7296b8c820dbc4de7fc4f0a8052950",
}


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(",", ":")).encode("utf-8")


def source_snapshot() -> dict:
    result = {}
    for name in (*DONOR_BLOBS, "guarded_port.py", "run_demo.py", "../assess.py"):
        raw = (ROOT / name).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        if name in DONOR_BLOBS and blob != DONOR_BLOBS[name]:
            raise ValueError(f"preserved donor changed: {name}")
        result[name] = {"git_blob": blob, "sha256": hashlib.sha256(raw).hexdigest()}
    return result


def assessor_module():
    spec = importlib.util.spec_from_file_location("uiowa080_existing_assessor", ROOT.parent / "assess.py")
    if spec is None or spec.loader is None:
        raise ValueError("existing assessor cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _LateInvalidToy(ClassificationPort):
    """Deliberate negative control: the first answer is valid, the next is not."""
    capability_class = "fictional-negative-control"

    def __init__(self):
        self.calls = 0

    def classify(self, document: Document) -> Classification:
        self.calls += 1
        return Classification(document.doc_id, "access", 0.9 if self.calls == 1 else float("nan"),
                              "fictional late-invalid response", self.capability_class)

    def health(self) -> dict:
        return {"reachable": True, "capability_class": self.capability_class}


def late_response_example(policy: RoutingPolicy) -> dict:
    unsafe = _LateInvalidToy()
    guarded = GuardedPort(_LateInvalidToy(), policy)
    probe = check_conformance(unsafe, policy)
    guarded_probe = check_conformance(guarded, policy)
    document = Document("negative-control", "synthetic badge request", "synthetic")
    return {
        "scope": "fictional startup-valid then NaN; not a real provider observation",
        "startup_probe": probe,
        "guarded_startup_probe": guarded_probe,
        "unchanged_caller_without_guard": asdict(route_document(unsafe, document, policy)),
        "unchanged_caller_with_guard": asdict(route_document(guarded, document, policy)),
    }


def assessment_input(runs: list[dict], sources: dict) -> dict:
    """Add a new toy case; never modify or upgrade the existing example cases."""
    evidence = {
        run["id"]: {
            "kind": "synthetic",
            "locator": "run:" + run["id"] + "#sha256=" + hashlib.sha256(canonical(run)).hexdigest(),
            "note": "Fixed fictional corpus; routing counts are not quality, labor, latency or uptime.",
        } for run in runs
    }
    evidence["executed-source"] = {
        "kind": "synthetic",
        "locator": "source-set:sha256=" + hashlib.sha256(canonical(sources)).hexdigest(),
        "note": "Local byte identity before and after execution, not source authentication or host attestation.",
    }
    swap_ok = all(run["conformance"]["conformant"] is True for run in runs if run["mode"] == "normal")
    alternatives = []
    for provider in ("alpha", "beta"):
        normal = next(run for run in runs if run["id"] == provider + ":normal")
        faulty = [run["id"] for run in runs if run["provider"] == provider and run["mode"] != "normal"]
        contract_ok = normal["conformance"]["conformant"] is True
        fallback_ok = all(run["summary"]["degraded"] == run["summary"]["items"]
                          and run["summary"]["to_human_review"] == run["summary"]["items"]
                          for run in runs if run["id"] in faulty)
        refs = [provider + ":normal", "executed-source"]
        portability = {key: {"state": "unknown", "note": "Not established by toy classification runs.",
                             "evidence_refs": []}
                       for key in ("request_response_contract", "prompt_export", "evaluation_replay", "adapter_swap", "data_export")}
        for key in ("request_response_contract", "adapter_swap"):
            demonstrated = contract_ok and (key != "adapter_swap" or swap_ok)
            portability[key] = {"state": "demonstrated" if demonstrated else "unknown",
                                "note": "Only this fictional adapter, fixed corpus and unchanged caller; no real-provider equivalence.",
                                "evidence_refs": refs if demonstrated else []}
        alternatives.append({
            "id": provider + "-toy", "pattern": "synchronous_assist",
            "suitable_when": "Demonstrating a domain-shaped port with invented adapters offline.",
            "tradeoffs": "Routing counts differ; real quality, staff capacity and service characteristics are unknown.",
            "change_option": "Swap the adapter behind GuardedPort; preserve caller and policy bytes.",
            "evidence_refs": refs + faulty,
            "response_stages": [{"name": "real response latency not measured", "ms": {"low": None, "high": None}}],
            "completion_stages": [], "latency_basis": "planning_envelope",
            "response_dependencies": [{"name": "real deployment unknown", "availability": None, "window": None}],
            "independence_assumed": False,
            "integration_tasks": [{"name": "actual integration", "hours": {"low": None, "high": None}, "owner_role": None}],
            "maintenance_tasks": [{"name": "actual maintenance", "hours_per_month": {"low": None, "high": None}, "owner_role": None}],
            "migration_tasks": [{"name": "actual migration", "hours": {"low": None, "high": None}, "owner_role": None}],
            "capabilities": ["toy_document_classification"],
            "data_flows": [{"id": "toy-intake", "source": "fixed synthetic corpus", "destination": "in-process fictional adapter",
                            "payload": "invented intake text", "minimization": "No institutional or personal data",
                            "zone": "local_synthetic_process", "retention_days": None}],
            "owners": {key: None for key in ("integration", "support", "data", "evaluation", "change")},
            "portability": portability,
            "degraded_mode": {"behavior": "manual_queue" if fallback_ok else "unknown",
                              "note": "Toy faults route to a person; real staffing and core continuity remain unknown.",
                              "tested": fallback_ok, "evidence_refs": faulty},
        })
    return {
        "schema_version": "1.0", "synthetic": True,
        "basis": "Executed fixed fictional UIOWA-080 portability example; not University evidence or vendor selection.",
        "evidence": evidence,
        "cases": [{"id": "uiowa-080-preserved-provider-integration", "title": "Fictional adapter swap with per-response validation",
                   "recommendation_id": "UIOWA-080",
                   "requirements": {"response_budget_ms": None, "completion_deadline_ms": None,
                                    "monthly_maintenance_hours": None, "migration_budget_hours": None,
                                    "response_availability_target": None, "availability_window": None,
                                    "allowed_zones": None, "max_retention_days": None,
                                    "required_capabilities": ["toy_document_classification"],
                                    "core_must_continue_without_ai": None},
                   "alternatives": alternatives}],
    }


def run_demo() -> dict:
    before = source_snapshot()
    assessor = assessor_module()
    policy = RoutingPolicy()
    documents = [Document(f"synthetic-{i}", text, "synthetic") for i, text in enumerate(
        ("invoice question", "badge access", "thermostat problem", "leak in building", "general enquiry"), 1)]
    runs = []
    for provider, factory, modes in (
        ("alpha", AlphaClassificationAdapter, (None, "timeout", "refused", "garbage")),
        ("beta", BetaClassificationAdapter, (None, "slow", "down", "garbage")),
    ):
        for mode in modes:
            port = GuardedPort(factory(policy, fail_mode=mode), policy)
            conformance = check_conformance(port, policy)
            decisions = route_documents(port, documents, policy)
            runs.append({"id": provider + ":" + (mode or "normal"), "provider": provider,
                         "mode": mode or "normal", "conformance": conformance,
                         "decisions": [asdict(d) for d in decisions], "summary": summarize_run(decisions)})
    architecture_input = assessment_input(runs, before)
    report = {
        "schema_version": "1.0", "synthetic": True, "donor_commit": DONOR_COMMIT,
        "scope": "Local deterministic toy evidence only; no live provider, institutional data, quality, labor or cash claim.",
        "source_identity": before, "policy": asdict(policy), "corpus": [asdict(d) for d in documents],
        "runs": runs, "late_response_example": late_response_example(policy),
        "comparison": {"population": "same five synthetic documents; normal modes only",
                       "alpha_human_review": runs[0]["summary"]["to_human_review"],
                       "beta_human_review": runs[4]["summary"]["to_human_review"],
                       "beta_minus_alpha_human_review": runs[4]["summary"]["to_human_review"] - runs[0]["summary"]["to_human_review"],
                       "interpretation": "Queue counts only, not equivalent quality, staff hours or savings."},
        "assessment_input": architecture_input, "assessment": assessor.assess(architecture_input),
    }
    if source_snapshot() != before:
        raise ValueError("source changed during the demonstration")
    # Normalize tuples to JSON arrays so API and CLI return the same value shape.
    return json.loads(canonical(report))


def verify(report: object) -> None:
    """Re-execute the fixed example and compare every field, including source IDs."""
    if canonical(report) != canonical(run_demo()):
        raise ValueError("report does not match the current fixed-corpus execution and sources")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", type=Path, metavar="REPORT")
    mode.add_argument("--assessment-input", action="store_true")
    mode.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.verify is not None:
            with args.verify.open("rb") as stream:
                raw = stream.read(1_048_577)
            if len(raw) > 1_048_576:
                raise ValueError("report exceeds 1 MiB")
            verify(assessor_module().load(raw))
            print("VERIFIED: current local toy execution and source identity; not production evidence.")
        else:
            report = run_demo()
            if args.markdown:
                print(assessor_module().markdown(report["assessment"]), end="")
            else:
                print(json.dumps(report["assessment_input"] if args.assessment_input else report,
                                 indent=2, ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
