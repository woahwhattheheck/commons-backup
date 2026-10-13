# SPDX-License-Identifier: Apache-2.0
"""Pinned, opt-in port of the existing V4 EOD rescue into the native caller.

This does not run a legacy materializer or touch a checkout in place. It copies
one caller/package into a new local staging directory. No configuration key or
production default is added. Disabled staging preserves every package byte.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

PINS = {
    "main.py": "4a8cf7bcda1f0fea231a144692cb84a779a9e73e",
    "titan_runtime.py": "b952c9c228ecbde592bf3d2df01638677abb0d24",
    "mechanics.py": "044a4f9c0a4a44dde10ada57563238bcaf82075d",
}
DONOR_PIN = "9ad4092453e2332b0914f90ca89791b18f2229c2"
H3C_PIN = "79c3fd029054a2db5931609db06f6b9aa4d4be3c"
OLD_IMPORT = b"    import r04_full_router as r04\n"
NEW_IMPORT = b"    import mechanics as r04\n"
OLD_SEAM = b"""            try:
                return super()._market_pressure_selected(obs, cfg, returned)
            finally:
"""
NEW_SEAM = b"""            try:
                returned = super()._market_pressure_selected(obs, cfg, returned)
                from r04_eod_capacity_rescue import apply_eod_capacity_rescue
                return apply_eod_capacity_rescue(returned, obs, cfg, enabled=True)
            finally:
"""


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def checked(path: Path, expected: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"regular source file required: {path}")
    data = path.read_bytes()
    actual = git_blob(data)
    if actual != expected:
        raise ValueError(f"source drift: {path.name}: expected {expected}, found {actual}")
    return data


def port_sources(main: bytes, runtime: bytes, mechanics: bytes,
                 donor: bytes, h3c: bytes, *, enabled: bool = False) -> dict[str, bytes]:
    """Return only candidate source deltas, with disabled identity and strict pins."""
    if type(enabled) is not bool:
        raise ValueError("enabled must be a literal bool")
    sources = {"main.py": main, "titan_runtime.py": runtime, "mechanics.py": mechanics}
    for name, data in sources.items():
        if git_blob(data) != PINS[name]:
            raise ValueError(f"source drift: {name}")
    if git_blob(donor) != DONOR_PIN or git_blob(h3c) != H3C_PIN:
        raise ValueError("source drift: rescue or H3c dependency")
    if not enabled:
        return {}
    if main.count(OLD_SEAM) != 1 or donor.count(OLD_IMPORT) != 1:
        raise ValueError("expected one native return seam and one legacy product import")
    changes = {
        "main.py": main.replace(OLD_SEAM, NEW_SEAM),
        "r04_eod_capacity_rescue.py": donor.replace(OLD_IMPORT, NEW_IMPORT),
        "h3c_goose_eod_cap_rescue.py": h3c,
    }
    for name, data in changes.items():
        compile(data, name, "exec")
    return changes


def stage(package: Path, donor: Path, h3c: Path, output: Path,
          *, enabled: bool = False) -> dict:
    """Build a new staging copy; refuse drift, existing output, and source overlap."""
    package, donor, h3c, output = map(lambda p: p.resolve(), (package, donor, h3c, output))
    if not package.is_dir():
        raise ValueError("package must be a directory")
    if output.exists() or output == package or package in output.parents or output in package.parents:
        raise ValueError("output must be new and disjoint from the source package")
    # A staged symlink could escape the copy and mutate a checkout through a
    # child path. This packet deliberately supports regular directory trees only.
    if any(p.is_symlink() for p in package.rglob("*")):
        raise ValueError("source package must not contain symlinks")
    inputs = {name: checked(package / name, sha) for name, sha in PINS.items()}
    donor_bytes, h3c_bytes = checked(donor, DONOR_PIN), checked(h3c, H3C_PIN)
    changes = port_sources(inputs["main.py"], inputs["titan_runtime.py"], inputs["mechanics.py"],
                           donor_bytes, h3c_bytes, enabled=enabled)
    if enabled:
        for name in ("r04_eod_capacity_rescue.py", "h3c_goose_eod_cap_rescue.py"):
            target = package / name
            if target.exists() and target.read_bytes() != changes[name]:
                raise ValueError(f"refuse to replace an independently composed module: {name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".native-eod-", dir=output.parent) as tmp:
        staged = Path(tmp) / "package"
        shutil.copytree(package, staged)
        for name, data in changes.items():
            (staged / name).write_bytes(data)
        if output.exists():
            raise ValueError("output appeared during staging; refusing replacement")
        staged.rename(output)
    return {
        "enabled_for_staged_experiment_only": enabled,
        "pins": PINS,
        "donor": DONOR_PIN,
        "h3c": H3C_PIN,
        "changed_files": {name: {"git_blob": git_blob(data), "bytes": len(data),
                                  "sha256": hashlib.sha256(data).hexdigest()}
                          for name, data in changes.items()},
        "production_written": False,
        "configuration_written": False,
        "field_economics_proven": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--donor", type=Path, required=True)
    parser.add_argument("--h3c", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--enabled", action="store_true")
    args = parser.parse_args()
    try:
        receipt = stage(args.package, args.donor, args.h3c, args.output, enabled=args.enabled)
    except (OSError, ValueError, SyntaxError) as error:
        parser.exit(2, f"native EOD port blocked: {error}\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
