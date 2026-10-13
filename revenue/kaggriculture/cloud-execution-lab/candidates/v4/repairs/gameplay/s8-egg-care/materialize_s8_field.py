#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Materialize disposable S8 field tests, never a production/native composer.

Native mode is SHADOW ONLY: it measures the exact source owner's proposed action
but returns unmodified main.py::agent output. Active modes use the legal service
fixture, NOT TITAN. All original native files remain byte-identical.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tarfile

ARCHIVE_SHA256 = "b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9"
PINS = {"s8_egg_care.py": "30a0e05c0cd7a435a59316d9d070da59eb2bb865",
        "compose_reopened_s8.py": "7cc261b907e377961e204c47d594cf3cfc85663c"}
GENERATED_SHA256 = "86be29534c8cfedef7d0b13043ec86586632b40eac2b16084dd1a9b6ac06d213"
HERE = Path(__file__).resolve().parent


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def build(archive, sources, output, telemetry, *, kind, mode):
    archive, sources, output = Path(archive), Path(sources), Path(output)
    if kind not in ("native_shadow", "grower", "disposal") or mode not in ("off", "donor", "spread", "discard", "spread_or_discard"):
        raise ValueError("Unsupported test-only S8 mode")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Reference archive drift; not silently testing a different native base")
    for name, expected in PINS.items():
        if git_blob((sources / name).read_bytes()) != expected:
            raise ValueError("Source-owner pin changed: " + name)
    spec = importlib.util.spec_from_file_location("henhouse_s8_composer", sources / "compose_reopened_s8.py")
    composer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(composer)
    generated = composer.compose((sources / "s8_egg_care.py").read_bytes())
    if hashlib.sha256(generated).hexdigest() != GENERATED_SHA256:
        raise ValueError("Generated S8 source mismatch")
    output.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive) as bundle:
        bundle.extractall(output, filter="data")
    (output / "henhouse_s8.py").write_bytes(generated)
    shutil.copyfile(HERE / "reachable_goose.py", output / "henhouse_grower.py")
    report = str(Path(telemetry).resolve())
    entry = '''# Generated TEST-ONLY harness. No production native action rewriting.
import importlib.util
import json
from pathlib import Path
import sys
import henhouse_s8 as helper
import henhouse_grower as grower
ROOT = Path(__file__).resolve().parent
KIND = {kind!r}
MODE = {mode!r}
REPORT = Path({report!r})
_native = None
stats = {{"calls": 0, "transformed_actions": 0, "changed_unit_rows": 0,
         "first_change_step": None, "last_change_step": None, "kind": KIND, "mode": MODE}}

def agent(observation, configuration=None):
    global _native
    if KIND == "native_shadow":
        if _native is None:
            spec = importlib.util.spec_from_file_location("henhouse_native_entry", ROOT / "main.py")
            _native = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = _native
            spec.loader.exec_module(_native)
        parent = _native.agent(observation, configuration)
    else:
        parent = grower.parent_action(observation, configuration, disposal=KIND == "disposal")
    changed = helper.apply_egg_care(observation, parent, configuration,
                                  enabled=MODE != "off",
                                  price_mode=MODE if MODE != "off" else "spread_or_discard")
    stats["calls"] += 1
    if parent != changed:
        stats["transformed_actions"] += 1
        before = [parent["farmer"], *parent["hands"]]
        after = [changed["farmer"], *changed["hands"]]
        stats["changed_unit_rows"] += sum(a != b for a, b in zip(before, after))
        stats["last_change_step"] = observation["step"]
        if stats["first_change_step"] is None:
            stats["first_change_step"] = observation["step"]
    if observation["step"] == (configuration or {{}}).get("episodeSteps", 720) - 2:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({{**stats, "helper_telemetry": dict(helper.telemetry)}}, sort_keys=True) + "\\n")
    return parent if KIND == "native_shadow" else changed
'''.format(kind=kind, mode=mode, report=report)
    (output / "henhouse_entry.py").write_text(entry)
    manifest = {"schema": "titan.s8.henhouse.fixture.v1", "kind": kind, "mode": mode,
                "native_actions_unchanged": kind == "native_shadow",
                "production_composer": False, "archive_sha256": ARCHIVE_SHA256,
                "source_git_blobs": PINS, "generated_helper_sha256": GENERATED_SHA256,
                "fixture_sha256": hashlib.sha256((HERE / "reachable_goose.py").read_bytes()).hexdigest(),
                "harness_sha256": hashlib.sha256(entry.encode()).hexdigest(),
                "entrypoint": "henhouse_entry.py::agent"}
    (output / "HENHOUSE-FIELD.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sources", type=Path, default=HERE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--kind", choices=("native_shadow", "grower", "disposal"), required=True)
    parser.add_argument("--mode", choices=("off", "donor", "spread", "discard", "spread_or_discard"), required=True)
    args = parser.parse_args()
    result = build(args.archive, args.sources, args.output, args.telemetry, kind=args.kind, mode=args.mode)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
