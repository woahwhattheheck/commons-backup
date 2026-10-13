#!/usr/bin/env python3
"""Exercise the exact native parser/merge with isolated local observation records."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

from adapter import utc_now
from native_export import NATIVE_COMMIT

PINS = {
    "core.py": "ac5816e15a55555def8639e4f17f8734d3dee1ae",
    "equipment.py": "9e3145d2f33658c18dda17165682eb375a2e0312",
}


def load_exact(directory, filename):
    path = Path(directory) / filename
    raw = path.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if blob != PINS[filename]:
        raise ValueError("Consumer source differs from the specified source pin: " + filename)
    spec = importlib.util.spec_from_file_location("titan_native_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, {"git_blob": blob, "sha256": hashlib.sha256(raw).hexdigest()}


def no_network(*args, **kwargs):
    raise AssertionError("This compatibility check has no provider fetch step")


def check_native(native_directory, document):
    """Use native metadata writes and merge on temporary SQLite only."""
    core, core_pin = load_exact(native_directory, "core.py")
    equipment, equipment_pin = load_exact(native_directory, "equipment.py")
    checks, witness = [], {}
    with tempfile.TemporaryDirectory(prefix="titan-native-consumer-") as tmp:
        def center(name):
            return core.CommandCenter(Path(tmp) / name, fetcher=no_network)

        def source(sessions):
            return [{"id": "titan", "status": "live", "observed_at": "2026-09-08T10:00:00Z",
                     "data": {"sessions": sessions}}]

        def register(instance, session, operation):
            instance.mutate("sessions", {"operation_id": operation, "session": session})

        parser = center("parser")
        schema = next(tool for tool in equipment.CommandCenterEquipment(parser).tools()
                      if tool["name"] == "command_center_session")["inputSchema"]["properties"]["session"]
        for index, session in enumerate(document["sessions"]):
            assert not (set(session) - set(schema["properties"])), session["id"]
            register(parser, session, "catalog-session-" + str(index))
        parsed = center("merge")._merged_sessions(source(document["sessions"]))
        assert {item["id"] for item in parsed} == {item["id"] for item in document["sessions"]}
        assert {"claude-titan-vm", "gpt-titan-vm"} <= {item["id"] for item in parsed}
        checks.append({"name": "actual_native_schema_and_parser", "passed": True,
                       "sessions": len(parsed)})

        local = {"id": "gpt-titan-vm", "label": "Operator label", "cpu": 1,
                 "ram_gib": 2, "gpu": "historical-device", "status": "observed",
                 "observed_at": "2026-09-07T19:00:00Z", "notes": "Retained local note"}
        newer = {"id": "gpt-titan-vm", "cpu": 9, "ram_gib": 21,
                 "gpu": None, "status": "observed", "observed_at": "2026-09-07T20:00:00Z"}
        fresh = center("freshness")
        register(fresh, local, "existing-local-observation")
        merged = fresh._merged_sessions(source([newer]))[0]
        suppressed = merged.get("cpu") != newer["cpu"] or merged.get("observed_at") != newer["observed_at"]
        assert not suppressed
        assert merged["telemetry_source"] == "titan"
        assert merged["gpu"] is None
        assert merged["local_metadata"]["notes"] == local["notes"]
        witness = {"fixture_kind": "synthetic_observations_with_actual_native_consumer",
                   "local_observation": local, "adapter_observation": newer,
                   "merged_observation": merged, "newer_adapter_suppressed": suppressed}
        checks.append({"name": "newer_adapter_over_older_local", "passed": True})
        checks.append({"name": "newer_null_gpu_does_not_inherit_older_measurement", "passed": True})

        late_local = dict(local, observed_at="2026-09-07T21:00:00Z", cpu=4)
        later = center("later-local")
        register(later, late_local, "later-local-observation")
        merged = later._merged_sessions(source([newer]))[0]
        assert merged["cpu"] == 4 and merged["telemetry_source"] == "local-session"
        assert merged["observed_at"] == late_local["observed_at"]
        checks.append({"name": "newer_local_over_older_adapter", "passed": True})

        undated_local = dict(local, observed_at=None)
        undated = center("undated-local")
        register(undated, undated_local, "undated-local-observation")
        merged = undated._merged_sessions(source([newer]))[0]
        assert merged["cpu"] == newer["cpu"] and merged["telemetry_source"] == "titan"
        checks.append({"name": "dated_adapter_over_undated_local", "passed": True})

        undated_adapter = dict(newer, observed_at=None)
        merged = fresh._merged_sessions(source([undated_adapter]))[0]
        assert merged["cpu"] == local["cpu"] and merged["observed_at"] == local["observed_at"]
        assert merged["telemetry_source"] == "local-session"
        checks.append({"name": "source_fetch_time_does_not_refresh_undated_adapter", "passed": True})

    return {"recorded_at": utc_now(), "native_source_commit": NATIVE_COMMIT,
            "native_sources": {"core.py": core_pin, "equipment.py": equipment_pin},
            "checks": checks, "freshness_witness": witness,
            "provider_calls": 0, "native_source_mutations": 0,
            "native_full_suite_reexecuted": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-directory", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, default=Path(__file__).with_name("adapter.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("native-compatibility.json"))
    args = parser.parse_args(argv)
    document = json.loads(args.adapter.read_text())
    result = check_native(args.native_directory, document)
    result["adapter_sha256"] = hashlib.sha256(args.adapter.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"passed": len(result["checks"]),
                      "newer_adapter_suppressed": result["freshness_witness"]["newer_adapter_suppressed"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
