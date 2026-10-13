#!/usr/bin/env python3
"""Export the source catalog into the native command center's sessions contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from adapter import catalog_records, parse_time, utc_now
from work_export import build_work_items, load_catalog

NATIVE_COMMIT = "54bd539954d67ed82288e0404411c86f6e2fbe7d"
NATIVE_BRANCH = "codex/command-center-20260907"
BASE = "https://github.com/woahwhattheheck/commons/blob/" + NATIVE_COMMIT + "/integrations/command_center/"
SESSION_IDS = {
    "gpt-sell": "gpt-titan-vm",
    "claude-harvest": "claude-titan-vm",
    "gpt-t11": "gpt-t11-vm",
    "01a07d73-a79b-7d33-8451-0c1acbc2f000": "gpt-t14-vm",
}
T14_SUBJECT = "01a07d73-a79b-7d33-8451-0c1acbc2f000"
SESSION_KEYS = ("id", "label", "url", "provider", "model", "cpu", "ram_gib", "gpu",
                "workspace", "observed_at", "status", "objective", "origin", "notes",
                "artifact_transport")


def build_adapter(catalog, vm_observation, *, generated_at, work_catalog=None):
    """Bind measurements only to their actual runtime; keep other capacity unknown."""
    parse_time(generated_at)
    records = catalog_records(catalog, recorded_at=generated_at)
    sessions = []
    for record in records:
        if record["kind"] != "session":
            continue
        data = record["data"]
        session = dict.fromkeys(SESSION_KEYS)
        session.update(
            id=SESSION_IDS.get(record["subject_id"], record["subject_id"]),
            label=data.get("role"), url=data.get("url"), provider=data.get("provider"),
            objective=data.get("role"), observed_at=record["observed_at"],
            status=data.get("observed_state"),
            origin={"catalog_subject_id": record["subject_id"],
                    "source_ref": record["source"]["ref"],
                    "source_published_at": record["source"].get("published_at"),
                    "repository": data.get("repository"), "path": data.get("path"),
                    "provider_status": record["provider"].get("status")})
        # A source catalog's reference is not a VM hardware observation.
        if (record["subject_id"] == T14_SUBJECT and vm_observation is not None
                and vm_observation.get("kind") == "vm"
                and vm_observation.get("subject_id") == "work-runtime:" + T14_SUBJECT):
            vm = vm_observation["data"]
            memory = vm.get("memory_total_bytes")
            session.update(
                cpu=vm.get("cpu_logical"), ram_gib=None if memory is None else memory / 2**30,
                workspace=str(Path(vm["disk_path"]).parents[2]) if vm.get("disk_path") else None,
                observed_at=vm_observation.get("observed_at"), status="observed",
                notes=("CPU and RAM are the host-visible observation. The separate VM resource "
                       "retains the cgroup CPU quota, memory limit, and current usage. "
                       "The observation timestamp is retained from local-vm.json."),
                artifact_transport={
                    "provider": "GitHub Actions",
                    "connector": "GitHub.download_workflow_artifact",
                    "artifact_ids": [10030763484, 10005621438],
                    "reported_state": "downloaded_to_cloud_vm",
                    "source_ref": data.get("claim_ref"),
                    "provider_completion": None})
            session["origin"]["measurement_ref"] = "local-vm.json"
            session["origin"]["measurement_record_id"] = vm_observation.get("record_id")
        sessions.append(session)
    work_items = build_work_items(load_catalog() if work_catalog is None else work_catalog)
    # Preserve the existing session identity and measurement time during reassignment.
    t15 = next((item for item in work_items if item.get("lane") == "T15"), None)
    if t15:
        for session in sessions:
            if session["id"] == "gpt-t11-vm":
                session["label"] = "T15 market game theory (existing T11 VM)"
                session["objective"] = t15["objective"]
    return {
        "schema_version": "titan.command-center-native.v1",
        "generated_at": generated_at,
        "native_consumer": {
            "source_commit": NATIVE_COMMIT, "branch": NATIVE_BRANCH,
            "import_path": "integrations.command_center.core.CommandCenter",
            "schema_ref": BASE + "equipment.py",
            "merge_ref": BASE + "core.py",
            "adapter_path": "revenue/kaggriculture/command-center-adapter/adapter.json"},
        "sessions": sessions,
        "work_schema_version": "titan.work-items.v1",
        "work_items": work_items,
        "sources": [record for record in records if record["kind"] == "source"],
        "artifacts": [record for record in records if record["kind"] == "artifact"],
        "operations": [record for record in records if record["kind"] == "operation"],
        "resources": [vm_observation] if vm_observation is not None else [],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path(__file__).with_name("fleet.json"))
    parser.add_argument("--vm-observation", type=Path, default=Path(__file__).with_name("local-vm.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("adapter.json"))
    parser.add_argument("--generated-at", default=None)
    args = parser.parse_args(argv)
    result = build_adapter(json.loads(args.catalog.read_text()),
                           json.loads(args.vm_observation.read_text()),
                           generated_at=args.generated_at or utc_now())
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
