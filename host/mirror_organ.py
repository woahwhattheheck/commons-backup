#!/usr/bin/env python3
"""MIRROR ORGAN — twin-state sync proof.

Practical application of the Muhlnickel provisional patent family
(muhl/docs/PROVISIONAL_SESSION.pdf, sole inventor Bryce Muhlnickel):
mirror of state (claims 11-13), N-way local worlds (claim 15).
Same topology + same injection = same state.

Manufacture N twins by bitwise copy — copying the file manufactures
another instance. Inject the same germline stream into every twin. Every
twin settles to the same byte-exact state; the wire carries the injection,
never the body. `verify` is the drift alarm: any twin that did not settle
to the family state is named, and the exit code fails closed.

Stdlib only. Exit codes: 0 ok, 2 usage, 3 drift / verification failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parent
if str(HOST_DIR) not in sys.path:
    sys.path.insert(0, str(HOST_DIR))

import germline

def fail(code: int, msg: str) -> None:
    print(f"{code}: {msg}", file=sys.stderr)
    raise SystemExit(code)


MANIFEST = "mirror.json"
SCHEMA = "mirror-organ/v1"


def _manifest_path(directory: Path) -> Path:
    return directory / MANIFEST


def _load_manifest(directory: Path) -> dict:
    path = _manifest_path(directory)
    if not path.is_file():
        fail(2, f"{directory} holds no {MANIFEST}; run twin first")
    return json.loads(path.read_text())


def _save_manifest(directory: Path, manifest: dict) -> None:
    _manifest_path(directory).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _twin_names(n: int) -> list:
    return [f"twin-{i:02d}.bin" for i in range(1, n + 1)]


def cmd_twin(args: argparse.Namespace) -> int:
    src = Path(args.source)
    body = src.read_bytes()
    directory = Path(args.out)
    directory.mkdir(parents=True, exist_ok=True)
    names = _twin_names(args.n)
    for name in names:
        (directory / name).write_bytes(body)
    manifest = {
        "schema": SCHEMA,
        "source": str(src),
        "state_sha256": germline.sha256(body),
        "state_bytes": len(body),
        "n": args.n,
        "twins": names,
        "injections_applied": 0,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _save_manifest(directory, manifest)
    print(json.dumps({"manufactured": args.n, "dir": str(directory),
                      "state_sha256": manifest["state_sha256"]}, indent=2))
    return 0


def cmd_inject(args: argparse.Namespace) -> int:
    directory = Path(args.dir)
    manifest = _load_manifest(directory)
    delta = Path(args.delta)
    for name in manifest["twins"]:
        twin = directory / name
        state, _header = germline.apply_injection_file(twin.read_bytes(), delta)
        twin.write_bytes(state)
        got = germline.sha256(state)
        if got != _header["to_sha256"]:
            fail(3, f"{name} did not settle to the injected state")
    manifest["state_sha256"] = _header["to_sha256"]
    manifest["state_bytes"] = len(state)
    manifest["injections_applied"] = manifest.get("injections_applied", 0) + 1
    _save_manifest(directory, manifest)
    print(json.dumps({"injected": str(delta), "twins": len(manifest["twins"]),
                      "settled_sha256": manifest["state_sha256"]}, indent=2))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    directory = Path(args.dir)
    manifest = _load_manifest(directory)
    report = []
    states = {}
    for name in manifest["twins"]:
        digest = germline.sha256((directory / name).read_bytes())
        states[name] = digest
    family = {}
    for name, digest in states.items():
        family.setdefault(digest, []).append(name)
    same = len(family) == 1
    expected = manifest.get("state_sha256")
    matches_manifest = same and expected in family
    for name, digest in states.items():
        report.append({"twin": name, "sha256": digest,
                       "in_family": same or digest == expected})
    print(json.dumps({"same_state": same, "matches_manifest": matches_manifest,
                      "twins": report}, indent=2))
    if not (same and matches_manifest):
        return 3
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    directory = Path(args.dir)
    manifest = _load_manifest(directory)
    print(json.dumps(manifest, indent=2))
    return 0


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mirror_organ", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("twin", help="manufacture N twins by bitwise copy")
    p.add_argument("source")
    p.add_argument("-n", type=int, required=True)
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(fn=cmd_twin)

    p = sub.add_parser("inject", help="apply the same germline injection to every twin")
    p.add_argument("dir")
    p.add_argument("delta")
    p.set_defaults(fn=cmd_inject)

    p = sub.add_parser("verify", help="prove every twin settled to the same state")
    p.add_argument("dir")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("status", help="print the mirror manifest")
    p.add_argument("dir")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args(argv)
    if args.cmd == "twin" and args.n < 1:
        ap.error("n must be >= 1")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
