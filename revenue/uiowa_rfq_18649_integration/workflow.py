#!/usr/bin/env python3
"""UIOWA-098 runnable integration workflow over the currently prepared RFQ components.

This module joins component outputs without inventing a shared score. Native IDs are
qualified by component, missing values remain missing, and maturity/confidence fields
remain in their originating models.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "uiowa-098-integration-run-v1"
GROUPS = {"ESS", "RIS", "IAM", "CROSS"}
AREA_MAP = {
    "software": "software_development", "software_development": "software_development",
    "security": "security", "deployment": "deployment_operations",
    "deployment_operations": "deployment_operations", "ai_readiness": "ai_readiness",
}

class IntegrationError(ValueError):
    pass

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))

def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise IntegrationError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def _dotted(row: dict[str, Any], key: str) -> Any:
    cur: Any = row
    for part in key.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur

def _record(component: str, native_id: str, group: str, kind: str, source: str,
            digest: str, attrs: dict[str, Any]) -> dict[str, Any]:
    if group not in GROUPS:
        raise IntegrationError(f"{component}:{native_id}: invalid group {group!r}")
    return {
        "canonical_id": f"{component}:{native_id}", "component": component,
        "native_id": native_id, "group": group, "record_type": kind,
        "source_path": source, "source_sha256": digest, "attributes": attrs,
    }

def _load_map(root: Path) -> tuple[dict[str, Any], Path]:
    path = root / "revenue/uiowa_rfq_18649_integration/interface_map.json"
    data = _json(path)
    if data.get("schema") != "uiowa-098-interface-map-v1":
        raise IntegrationError("unsupported interface map schema")
    if data.get("boundaries", {}).get("numeric_scores_synthesized") is not False:
        raise IntegrationError("interface map must forbid synthesized numeric scores")
    return data, path

def _mapped_records(root: Path, interface: dict[str, Any]) -> list[dict[str, Any]]:
    integration_dir = root / "revenue/uiowa_rfq_18649_integration"
    if str(integration_dir) not in sys.path:
        sys.path.insert(0, str(integration_dir))
    import adapter_tabular  # type: ignore

    out: list[dict[str, Any]] = []
    for spec in interface["components"]:
        component = spec["component"]
        if component == "delivery_metrics":
            out.extend(adapter_tabular.delivery(root, spec))
            continue
        if component == "prioritization":
            out.extend(adapter_tabular.prioritization(root, spec))
            continue
        path = root / spec["source"]
        payload = _json(path)
        digest = _sha(path)
        if component == "observability":
            for service in payload.get("services", []):
                native_group = service.get(spec["native_group"])
                group = spec["mapping"].get(native_group)
                if not group:
                    raise IntegrationError(f"observability: unmapped service {native_group!r}")
                for objective in service.get("objectives", []):
                    native = objective.get(spec["native_id"])
                    if not native:
                        raise IntegrationError("observability objective missing native id")
                    attrs = {key: _dotted(objective, key) for key in spec["preserve"]}
                    attrs["native_service_id"] = native_group
                    out.append(_record(component, str(native), group, "objective", spec["source"], digest, attrs))
        elif component == "test_data_readiness":
            for row in payload.get("datasets", []):
                native = row.get(spec["native_id"]); native_group = row.get(spec["native_group"])
                group = spec["mapping"].get(native_group)
                if not native or not group:
                    raise IntegrationError("test-data record missing mapped id/group")
                attrs = {key: row.get(key) for key in spec["preserve"]}
                attrs["native_service"] = native_group
                out.append(_record(component, str(native), group, "dataset", spec["source"], digest, attrs))
        else:
            raise IntegrationError(f"no adapter for interface-map component {component!r}")

    seen: dict[str, str] = {}
    for row in out:
        cid = row["canonical_id"]
        digest = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
        if cid in seen and seen[cid] != digest:
            raise IntegrationError(f"canonical id collision: {cid}")
        seen[cid] = digest
    return sorted(out, key=lambda r: r["canonical_id"])

def _workbench(root: Path) -> dict[str, Any]:
    server_path = root / "revenue/uiowa_rfq_18649_workbench/server.py"
    server = _module(server_path, "uiowa098_workbench_server")
    ws = root / "revenue/uiowa_rfq_18649_workshare/fixtures"
    report = server.CompilerAdapter().inspect(_json(ws / "synthetic_packet.json"), _json(ws / "synthetic_authority.json"))
    matrix = report.get("assessment_matrix") or []
    if report.get("mode") != "UNTRUSTED_INSPECTION" or len(matrix) != 12:
        raise IntegrationError("workbench did not return the 12-cell untrusted inspection")
    if report.get("trust", {}).get("current_evidence_review_authority") is not False:
        raise IntegrationError("representative workflow must not mint current review authority")
    cells = []
    for row in matrix:
        area = AREA_MAP.get(row.get("dimension"))
        if not area:
            raise IntegrationError(f"unknown workbench dimension {row.get('dimension')!r}")
        cells.append({
            "cell_id": f"{row['group']}:{area}", "group": row["group"], "area": area,
            "status": row["status"], "source_ids": row.get("source_ids", []),
            "reason_codes": row.get("reason_codes", []),
        })
    return {"receipt_sha256": report["receipt_sha256"], "aggregate_state": report["aggregate_state"], "cells": cells}

def _rating(root: Path) -> dict[str, Any]:
    base = root / "revenue/uiowa_rfq_18649_rating_model"
    mod = _module(base / "rating_model.py", "uiowa098_rating_model")
    payload = _json(base / "synthetic_case_mixed_services.json")
    result = mod.compose(payload)
    return {"model": result["model"], "area_summaries": result["area_summaries"], "input_sha256": _sha(base / "synthetic_case_mixed_services.json")}

def _prioritization(root: Path) -> dict[str, Any]:
    base = root / "revenue/uiowa_rfq_18649_prioritization"
    mod = _module(base / "prioritize.py", "uiowa098_prioritize")
    config = mod.load_weights(base / "weights.json")
    rows = mod.load_recommendations(base / "recommendations.synthetic.csv")
    profiles = {}
    epsilon = float(config.get("tie_epsilon", 0.0))
    for name, weights in config["profiles"].items():
        scored = mod.rank_profile(rows, name, weights, epsilon)
        profiles[name] = {
            "ranked_ids": [r["id"] for r in scored if r["status"] == "RANKED"],
            "held": {r["id"]: r["missing_estimates"] for r in scored if r["status"] != "RANKED"},
        }
    return {"profiles": profiles, "weights_sha256": _sha(base / "weights.json"), "recommendations_sha256": _sha(base / "recommendations.synthetic.csv")}

def _traceability(root: Path) -> dict[str, Any]:
    base = root / "revenue/uiowa_rfq_18649_traceability_rehearsal"
    proc = subprocess.run([sys.executable, str(base / "validate_trace.py"), str(base)], text=True, capture_output=True)
    if proc.returncode != 0:
        raise IntegrationError("traceability validator failed: " + proc.stdout + proc.stderr)
    evidence = _csv(base / "evidence.csv"); findings = _csv(base / "findings.csv")
    recs = _csv(base / "recommendations.csv"); trace = _csv(base / "trace-map.csv")
    return {
        "validator_stdout": proc.stdout.strip(),
        "counts": {"evidence": len(evidence), "findings": len(findings), "recommendations": len(recs), "statements": len(trace)},
        "finding_ids": [r["finding_id"] for r in findings], "recommendation_ids": [r["recommendation_id"] for r in recs],
        "statement_ids": [r["statement_id"] for r in trace],
        "final_report_sha256": _sha(base / "final-report.md"),
    }

def _presenter_receipt(root: Path) -> dict[str, Any]:
    path = root / "revenue/uiowa_rfq_18649_integration/presenter_run.json"
    data = _json(path)
    cells = data.get("matrix") or []
    if len(cells) != 12:
        raise IntegrationError("presenter receipt must contain exactly 12 matrix cells")
    counts: dict[str, int] = {}
    for row in cells:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    if counts != data.get("status_counts"):
        raise IntegrationError("presenter receipt status counts do not match its matrix")
    return data

def _component_status(root: Path) -> dict[str, str]:
    expected = {
        "roadmap": "revenue/uiowa_rfq_18649_roadmap",
        "report_structure": "revenue/uiowa_rfq_18649_report_structure",
        "review_workflow": "revenue/uiowa_rfq_18649_handoff_review",
    }
    return {name: ("AVAILABLE" if (root / path).exists() else "NOT_YET_MERGED") for name, path in expected.items()}

def build(root: Path) -> dict[str, Any]:
    interface, map_path = _load_map(root)
    records = _mapped_records(root, interface)
    workbench = _workbench(root)
    packet = {
        "schema": SCHEMA, "synthetic": True,
        "interface_map": {"path": str(map_path.relative_to(root)), "sha256": _sha(map_path)},
        "mapped_records": records,
        "workbench": workbench,
        "rating_model": _rating(root),
        "prioritization": _prioritization(root),
        "traceability_rehearsal": _traceability(root),
        "presenter_run": _presenter_receipt(root),
        "component_status": _component_status(root),
        "joins": {
            "group_area": "context-only join across workbench/rating outputs; native maturity and confidence are not converted",
            "record_identity": "component-qualified canonical_id prevents same-looking native IDs from silently coalescing",
            "recommendations": "prioritization IDs and traceability recommendation IDs remain separate namespaces",
        },
        "guardrails": [
            "No University finding is created by this integration run.",
            "No numeric maturity/confidence conversion occurs across components.",
            "Missing component outputs remain NOT_YET_MERGED rather than being simulated.",
            "No external submission, outreach, scheduling, or procurement recommendation is performed.",
        ],
    }
    packet["run_sha256"] = hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return packet

def write_outputs(packet: dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "integration-run.json").write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (out / "component-records.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh); w.writerow(["canonical_id","component","native_id","group","record_type","source_path","source_sha256"])
        for r in packet["mapped_records"]:
            w.writerow([r[k] for k in ("canonical_id","component","native_id","group","record_type","source_path","source_sha256")])
    lines = [
        "# UIOWA-098 integration run", "",
        "Synthetic preparation output only; this workflow does not mint University findings or submission authority.", "",
        f"- run SHA-256: `{packet['run_sha256']}`",
        f"- mapped records: **{len(packet['mapped_records'])}**",
        f"- workbench cells: **{len(packet['workbench']['cells'])}**",
        f"- workbench receipt: `{packet['workbench']['receipt_sha256']}`",
        f"- trace validation: `{packet['traceability_rehearsal']['validator_stdout'].splitlines()[-1]}`",
        f"- presenter sample receipt: `{packet['presenter_run']['receipt_sha256']}`",
        "", "## Optional downstream components", "",
    ]
    lines += [f"- {k}: `{v}`" for k,v in sorted(packet["component_status"].items())]
    (out / "RUN_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    try:
        packet = build(a.repo_root.resolve()); write_outputs(packet, a.out)
    except (IntegrationError, OSError, ValueError, KeyError, json.JSONDecodeError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2
    print(f"UIOWA_098_OK {packet['run_sha256']} records={len(packet['mapped_records'])} cells={len(packet['workbench']['cells'])}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
