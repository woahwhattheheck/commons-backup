#!/usr/bin/env python3
"""CLI for Commons context packet compilation, verification and rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from host.context_packet import PacketError, compile_packet, markdown, verify_packet
    from host.git_source_capsules import observe_current_main, verify_packet_git_source
except ModuleNotFoundError:
    from context_packet import PacketError, compile_packet, markdown, verify_packet
    from git_source_capsules import observe_current_main, verify_packet_git_source

ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path) -> tuple[Any, bytes]:
    with open(path, "rb", opener=lambda name, flags: os.open(
        name, flags | getattr(os, "O_NONBLOCK", 0)
    )) as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise PacketError(f"input must be a regular file: {path}")
        raw = stream.read()
    return json.loads(raw.decode()), raw


def _source(label: str, path: Path, raw: bytes) -> dict[str, Any]:
    return {"source": label, "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _claims(path: Path | None) -> tuple[list[dict[str, Any]], list[tuple[str, bytes]]]:
    if path is None:
        return [], []
    if path.is_dir():
        rows, raws = [], []
        for item in sorted(path.glob("*.json")):
            value, raw = _load(item)
            raws.append((str(item), raw))
            if isinstance(value, Mapping):
                rows.append(dict(value))
        return rows, raws
    value, raw = _load(path)
    if isinstance(value, list):
        rows = [dict(x) for x in value if isinstance(x, Mapping)]
    elif isinstance(value, Mapping) and isinstance(value.get("holdings"), list):
        rows = [dict(x) for x in value["holdings"] if isinstance(x, Mapping)]
    elif isinstance(value, Mapping):
        rows = [dict(value)]
    else:
        raise PacketError("claims input must be object, list, or directory")
    return rows, [(str(path), raw)]


def _compile(args: argparse.Namespace) -> dict[str, Any]:
    pulse, pulse_raw = _load(args.pulse)
    recent, recent_raw = _load(args.recent)
    ledger, ledger_raw = _load(args.ledger)
    if not isinstance(pulse, Mapping) or not isinstance(recent, list) or not isinstance(ledger, Mapping):
        raise PacketError("pulse/ledger must be objects and recent must be an array")
    coordination, coordination_raw = None, None
    if args.coordination:
        coordination, coordination_raw = _load(args.coordination)
        if not isinstance(coordination, Mapping):
            raise PacketError("coordination must be an object")
    claims, claim_raws = _claims(args.claims)
    provenance = [
        _source("pulse", args.pulse, pulse_raw),
        _source("recent", args.recent, recent_raw),
        _source("resource-ledger", args.ledger, ledger_raw),
    ]
    if args.coordination:
        provenance.append(_source("coordination", args.coordination, coordination_raw))
    if len(claim_raws) == 1:
        path, raw = claim_raws[0]
        provenance.append({"source": "claims", "path": path, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    elif claim_raws:
        manifest = "\n".join(
            f"{path}\t{hashlib.sha256(raw).hexdigest()}\t{len(raw)}" for path, raw in claim_raws
        ).encode()
        provenance.append({
            "source": "claims",
            "path": str(args.claims),
            "sha256": hashlib.sha256(manifest).hexdigest(),
            "files": len(claim_raws),
            "bytes": sum(len(raw) for _, raw in claim_raws),
        })

    source_requested = bool(args.source_commit or args.source_path)
    if source_requested and not (args.source_commit and args.source_path):
        raise PacketError("--source-commit and at least one --source-path are required together")

    return compile_packet(
        operation=args.operation,
        objective=args.objective,
        pulse=pulse,
        recent=[x for x in recent if isinstance(x, Mapping)],
        ledger=ledger,
        claims=claims,
        coordination=coordination,
        explicit_terms=args.term,
        paths=args.path,
        requested_main_head=args.main_head,
        provenance=provenance,
        git_repository=args.git_repo if source_requested else None,
        source_commit=args.source_commit,
        source_paths=args.source_path,
        max_source_file_bytes=args.max_source_file_bytes,
        max_chars=args.max_chars,
        max_events=args.max_events,
        max_resources=args.max_resources,
        max_claims=args.max_claims,
        max_coordination=args.max_coordination,
    )


def _write(text: str, out: Path | None) -> None:
    if out is None:
        sys.stdout.write(text)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    # Build beside the destination, then install the complete file without
    # replacement. An exists()+write_text() pair lets concurrent handoffs
    # truncate each other; exclusive creation alone can expose partial bytes.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=out.parent,
            prefix="." + out.name + ".", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, out)
        except FileExistsError:
            raise PacketError(f"refusing to overwrite {out}") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _validate_packet(value: Mapping[str, Any], git_repo: Path) -> tuple[bool, str]:
    ok, reason = verify_packet(value)
    if not ok:
        return ok, reason
    if value.get("git_source") is not None:
        return verify_packet_git_source(dict(value), git_repo)
    return True, "ok"


def _live_git_drift(value: Mapping[str, Any], git_repo: Path) -> Mapping[str, Any] | None:
    source = value.get("git_source")
    if not isinstance(source, Mapping):
        return None
    commit = source.get("commit")
    if not isinstance(commit, str):
        raise PacketError("git_source commit is missing")
    return observe_current_main(git_repo, commit)


def _format_live_git_drift(drift: Mapping[str, Any] | None) -> str:
    if drift is None:
        return "\n"
    return (
        "\nLIVE_UNSEALED "
        f"current_main={drift.get('observed_current_main_head')} "
        f"source_commit_matches_current_main={drift.get('source_commit_matches_current_main')}\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(
        "Compile, verify and render context packets. JSON inputs must be regular "
        "files; symlinks to regular files are supported."
    ))
    sub = parser.add_subparsers(dest="command", required=True)

    packet = sub.add_parser("packet")
    packet.add_argument("--operation", required=True)
    packet.add_argument("--objective", required=True)
    packet.add_argument("--term", action="append", default=[])
    packet.add_argument("--path", action="append", default=[])
    packet.add_argument("--pulse", type=Path, default=ROOT / "pulse.json")
    packet.add_argument("--recent", type=Path, default=ROOT / "recent.json")
    packet.add_argument("--ledger", type=Path, default=ROOT / "ground" / "RESOURCE_LEDGER.json")
    packet.add_argument("--coordination", type=Path)
    packet.add_argument("--claims", type=Path)
    packet.add_argument("--main-head")
    packet.add_argument("--git-repo", type=Path, default=ROOT)
    packet.add_argument("--source-commit")
    packet.add_argument("--source-path", action="append", default=[])
    packet.add_argument("--max-source-file-bytes", type=int, default=16384)
    packet.add_argument("--max-chars", type=int, default=12000)
    packet.add_argument("--max-events", type=int, default=12)
    packet.add_argument("--max-resources", type=int, default=12)
    packet.add_argument("--max-claims", type=int, default=6)
    packet.add_argument("--max-coordination", type=int, default=8)
    packet.add_argument("--format", choices=("json", "markdown"), default="json")
    packet.add_argument("--out", type=Path)

    verify = sub.add_parser("verify")
    verify.add_argument("packet", type=Path)
    verify.add_argument("--git-repo", type=Path, default=ROOT)

    render = sub.add_parser("render")
    render.add_argument("packet", type=Path)
    render.add_argument("--git-repo", type=Path, default=ROOT)
    render.add_argument("--out", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "packet":
            result = _compile(args)
            drift = _live_git_drift(result, args.git_repo) if args.format == "markdown" else None
            text = (
                json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
                if args.format == "json"
                else markdown(result, live_git_drift=drift)
            )
            _write(text, args.out)
            return 0

        value, _ = _load(args.packet)
        if not isinstance(value, Mapping):
            raise PacketError("packet must be an object")
        ok, reason = _validate_packet(value, args.git_repo)
        if not ok:
            sys.stderr.write(f"INVALID {reason}\n")
            return 2
        drift = _live_git_drift(value, args.git_repo)
        if args.command == "render":
            _write(markdown(value, live_git_drift=drift), args.out)
            return 0
        sys.stdout.write(
            f"VALID {value['schema']} {value['semantic_sha256']}"
            f"{_format_live_git_drift(drift)}"
        )
        return 0
    except (OSError, json.JSONDecodeError, PacketError, ValueError) as exc:
        sys.stderr.write(f"ERROR {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
