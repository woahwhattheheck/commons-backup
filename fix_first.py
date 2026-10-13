#!/usr/bin/env python3
"""Validate that a peer consumed a defect instead of filing a report.

This is an agent-work completion check, never an ingest or posting gate.  It
does not decide what anyone may read, write, or execute.  It makes the narrow
owner rule mechanical: an actually broken contract ends fixed on current main,
or carries concrete attempted-repair evidence for a genuinely external block.
An open door cannot be converted into a defect by wishing it had been closed.

Fixed packets record execution evidence in a nonempty ``runs`` list, alongside
changed_paths, the integrated main_sha, and readback_verified.  Legacy ``tests``
lists remain accepted for existing packets and bounty contribution workflows.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
OUTCOMES = {"fixed", "not_bug", "external_blocker"}


class PacketError(ValueError):
    """The work packet describes an unfinished or report-only outcome."""


def _nonempty_list(packet: dict[str, Any], key: str) -> list[Any]:
    value = packet.get(key)
    return value if isinstance(value, list) and value else []


def validate(packet: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized completion state or raise ``PacketError``."""
    if not isinstance(packet, dict):
        raise PacketError("packet must be a JSON object")

    errors: list[str] = []
    outcome = str(packet.get("outcome") or "").strip().lower()
    if outcome not in OUTCOMES:
        errors.append("outcome must be fixed, not_bug, or external_blocker")

    if packet.get("report_only_sessions", 0) != 0:
        errors.append("report_only_sessions must be 0")
    if packet.get("unconsumed_findings", 0) != 0:
        errors.append("unconsumed_findings must be 0")

    observed_broken = packet.get("observed_broken") is True
    finding_kind = str(packet.get("finding_kind") or "behavior").strip().lower()
    prior_door_state = str(packet.get("prior_door_state") or "not_applicable").strip().lower()
    open_door_nonbug = finding_kind == "closed_door" and prior_door_state != "closed"

    if open_door_nonbug:
        if outcome != "not_bug":
            errors.append("an open door must resolve as not_bug")
    elif not observed_broken:
        if outcome != "not_bug":
            errors.append("no measured break must resolve as not_bug")
    else:
        if not str(packet.get("expected_contract") or "").strip():
            errors.append("a measured break requires its existing expected_contract")
        if outcome == "not_bug":
            errors.append("a measured contract break cannot resolve as not_bug")

    if outcome == "fixed":
        if not _nonempty_list(packet, "changed_paths"):
            errors.append("fixed requires changed_paths")
        if not (_nonempty_list(packet, "runs") or _nonempty_list(packet, "tests")):
            errors.append("fixed requires runs (or legacy tests)")
        if not SHA_RE.fullmatch(str(packet.get("main_sha") or "")):
            errors.append("fixed requires an integrated 40-character main_sha")
        if packet.get("readback_verified") is not True:
            errors.append("fixed requires readback_verified=true")

    if outcome == "external_blocker":
        if not _nonempty_list(packet, "repair_attempts"):
            errors.append("external_blocker requires repair_attempts")
        if not str(packet.get("blocker") or "").strip():
            errors.append("external_blocker requires the exact outside condition")

    if errors:
        raise PacketError("; ".join(errors))

    state = {
        "fixed": "FIXED",
        "not_bug": "NOT_BUG_OPEN_DOOR" if open_door_nonbug else "NOT_BUG",
        "external_blocker": "EXTERNAL_BLOCKER",
    }[outcome]
    return {
        "state": state,
        "report_only_sessions": 0,
        "unconsumed_findings": 0,
    }


def _load_packet(args: argparse.Namespace) -> dict[str, Any]:
    if args.json_text is not None:
        raw = args.json_text
    elif args.packet in (None, "-"):
        raw = sys.stdin.read()
    else:
        with open(args.packet, encoding="utf-8") as handle:
            raw = handle.read()
    try:
        packet = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PacketError("invalid JSON: %s" % exc) from exc
    if not isinstance(packet, dict):
        raise PacketError("packet must be a JSON object")
    return packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", nargs="?", help="packet JSON file, or - for stdin")
    parser.add_argument("--json", dest="json_text", help="inline completion packet")
    args = parser.parse_args(argv)
    try:
        result = validate(_load_packet(args))
    except (OSError, PacketError) as exc:
        print("FIX_FIRST_INVALID: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
