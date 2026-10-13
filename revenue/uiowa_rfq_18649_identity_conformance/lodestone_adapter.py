"""Run the conformance battery against the published LODESTONE identity mapper.

The target is trusted repository Python source, not a data file or remote URL.
An optional Git-blob pin is checked before executing it. No network is used.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Callable

HERE = Path(__file__).resolve().parent


def load_module(path: Path, prefix: str, expected_blob: str | None = None) -> tuple[ModuleType, str]:
    raw = path.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if expected_blob is not None and blob != expected_blob:
        raise ValueError(f"source pin mismatch: expected {expected_blob}, observed {blob}")
    name = prefix + "_" + blob
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("target must be a readable Python source file")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        # Compile the bytes whose identity was checked, not a later reread.
        exec(compile(raw, str(path), "exec"), module.__dict__)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module, blob


def make_adapter(mapper: ModuleType, driver: ModuleType) -> Callable:
    """Project actual mapper reports/resolutions without manufacturing results."""
    if mapper.SCHEMA != "uiowa.identity-map.v1":
        raise ValueError(f"unsupported mapper schema: {mapper.SCHEMA}")

    def adapt(data: dict):
        records = []
        for row in data["records"]:
            records.append({"namespace": row["origin"], "kind": row["kind"],
                            "id": row["local_id"], "revision": row["revision"],
                            "synthetic": row["synthetic"], "payload": deepcopy(row["payload"]),
                            "source_locators": ["synthetic-conformance:" + driver.encode(driver.key(row))]})
        try:
            index = mapper.IdentityMap(records)
            report = index.report()
            output = driver.Projection()
            for observed in report["records"]:
                original = observed["original"]
                key = tuple(original[field] for field in mapper.KEY_FIELDS)
                if key in output.records:
                    raise ValueError("mapper emitted duplicate original identity in its report")
                output.records[key] = observed["occurrence_id"]
                output.retained[key] = (driver.encode(original["payload"]),)
            for collision in report["collisions"]:
                output.diagnostics += ("collision:" + driver.encode(collision),)
            for query in data["references"]:
                fields = {"origin": "namespace", "local_id": "id", "kind": "kind", "revision": "revision"}
                target = {fields[field]: value for field, value in query["target"].items()}
                observed = index.resolve(target)
                status, resolved = observed["status"], observed["resolved_id"]
                if status == "resolved":
                    if not isinstance(resolved, str) or not resolved:
                        raise ValueError("mapper claimed resolution without an actual identifier")
                    output.references[query["id"]] = (resolved,)
                else:
                    if resolved is not None:
                        raise ValueError("mapper supplied a selected ID for an unresolved reference")
                    output.references[query["id"]] = ()
                    output.diagnostics += (status + ":" + query["id"],)
            return output
        except mapper.MappingError as exc:
            # A genuine target rejection is visible, and fails valid-baseline cases.
            return driver.Projection(rejected=True, diagnostics=(str(exc),))

    return adapt


def run_mapper(path: Path, expected_blob: str | None = None) -> dict:
    driver, driver_blob = load_module(HERE / "conformance.py", "cirrus_identity_driver")
    mapper, mapper_blob = load_module(path, "cirrus_lodestone_target", expected_blob)
    report = driver.run(make_adapter(mapper, driver))
    report["target"] = {"schema": mapper.SCHEMA, "git_blob_sha": mapper_blob,
                        "driver_git_blob_sha": driver_blob,
                        "api": "IdentityMap.report and IdentityMap.resolve",
                        "canonical_id_field": "occurrence_id", "source_pin_checked": expected_blob is not None}
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapper", type=Path, default=HERE.parent / "uiowa_rfq_18649_identity_map" / "identity_map.py")
    parser.add_argument("--expect-blob", help="Expected Git blob SHA; fail before target execution on mismatch")
    args = parser.parse_args(argv)
    try:
        report = run_mapper(args.mapper, args.expect_blob)
    except (OSError, ValueError, ImportError, AttributeError) as exc:
        print(f"identity-conformance: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
