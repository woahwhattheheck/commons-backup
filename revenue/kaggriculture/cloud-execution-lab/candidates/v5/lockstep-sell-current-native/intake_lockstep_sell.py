# SPDX-License-Identifier: Apache-2.0
"""Fail-closed intake for the exact Whitepill lockstep_sell V5 handoff.

This module does not reconstruct policy from prose and does not activate TITAN.
It authenticates the already-evaluated agent bytes and exact composition card, then
records the current-V5 ReturnBridge composer identity before emitting a receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "titan-v5-lockstep-sell-intake/v1"
EXPECTED_AGENT_SHA256 = "6355999beb5c3f3948bbce9dcbd69380b773b5ebf084226c39f41a07db4bd20e"
EXPECTED_COMPOSER_PATH = (
    "candidates/v4/repairs/gameplay/lockstep-join/compose_native_return_bridge.py"
)


class IntakeError(ValueError):
    """The Whitepill handoff cannot be authenticated from supplied bytes."""


def _reject_constant(value: str) -> None:
    raise IntakeError(f"non-finite JSON constant is forbidden: {value}")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IntakeError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _load_card_bytes(raw: bytes) -> Mapping[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IntakeError("composition card must be UTF-8 JSON") from exc
    try:
        card = json.loads(
            text,
            object_pairs_hook=_object,
            parse_constant=_reject_constant,
        )
    except IntakeError:
        raise
    except json.JSONDecodeError as exc:
        raise IntakeError("composition card is not valid JSON") from exc
    if type(card) is not dict:
        raise IntakeError("composition card must be a JSON object")
    return card


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_blob(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _sha256_text(value: Any, field: str) -> str:
    if type(value) is not str or len(value) != 64:
        raise IntakeError(f"{field} must be a 64-character lowercase SHA-256")
    if any(ch not in "0123456789abcdef" for ch in value):
        raise IntakeError(f"{field} must be a lowercase hexadecimal SHA-256")
    return value


def build_receipt(
    card_bytes: bytes,
    agent_bytes: bytes,
    composer_bytes: bytes,
    *,
    expected_agent_sha256: str = EXPECTED_AGENT_SHA256,
    composer_path: str = EXPECTED_COMPOSER_PATH,
) -> dict[str, Any]:
    """Authenticate one handoff without executing or altering policy bytes."""
    expected_agent_sha256 = _sha256_text(
        expected_agent_sha256, "expected agent sha256"
    )
    card = _load_card_bytes(card_bytes)
    witness = _sha256_text(card.get("agent_sha256"), "card agent_sha256")
    if witness != expected_agent_sha256:
        raise IntakeError("composition card agent witness is not the declared Whitepill agent")

    actual_agent_sha256 = _sha256(agent_bytes)
    if actual_agent_sha256 != expected_agent_sha256:
        raise IntakeError("agent bytes do not match the declared Whitepill witness")

    # The current composer deliberately self-pins every production source it consumes.
    # Its own Git blob changes whenever those source pins are reviewed/rebound (for
    # example after a scheduler correction), so freezing that tooling blob here would
    # create a second stale authority. Record the exact composer identity instead; the
    # composition step remains responsible for enforcing its internal source pins.
    actual_composer_blob = _git_blob(composer_bytes)

    return {
        "schema": SCHEMA,
        "status": "AUTHENTICATED_EVIDENCE_ONLY",
        "promotion": "DEFAULT_OFF_NO_ROOT_MUTATION",
        "agent_sha256": actual_agent_sha256,
        "composition_card_sha256": _sha256(card_bytes),
        "composition_card_top_level_keys": sorted(card),
        "returnbridge_composer": {
            "path": composer_path,
            "git_blob": actual_composer_blob,
        },
    }


def validate_paths(
    card_path: str | Path,
    agent_path: str | Path,
    composer_path: str | Path,
) -> dict[str, Any]:
    """Read exact files and build an authentication receipt."""
    card = Path(card_path)
    agent = Path(agent_path)
    composer = Path(composer_path)
    try:
        card_bytes = card.read_bytes()
        agent_bytes = agent.read_bytes()
        composer_bytes = composer.read_bytes()
    except OSError as exc:
        raise IntakeError(f"cannot read handoff input: {exc.filename}") from exc
    if not card_bytes:
        raise IntakeError("composition card is empty")
    if not agent_bytes:
        raise IntakeError("agent artifact is empty")
    if not composer_bytes:
        raise IntakeError("ReturnBridge composer is empty")
    return build_receipt(card_bytes, agent_bytes, composer_bytes)


def _receipt_text(receipt: Mapping[str, Any]) -> str:
    return json.dumps(receipt, sort_keys=True, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card", required=True, help="exact COMPOSITION-READY.json")
    parser.add_argument("--agent", required=True, help="exact evaluated Whitepill agent file")
    parser.add_argument(
        "--composer",
        required=True,
        help="canonical current compose_native_return_bridge.py",
    )
    parser.add_argument("--output", help="optional receipt path; stdout when omitted")
    args = parser.parse_args(argv)
    try:
        receipt = validate_paths(args.card, args.agent, args.composer)
    except IntakeError as exc:
        parser.exit(2, f"intake error: {exc}\n")
    text = _receipt_text(receipt)
    if args.output:
        destination = Path(args.output)
        try:
            with destination.open("x", encoding="utf-8") as handle:
                handle.write(text)
        except FileExistsError:
            parser.exit(2, "intake error: refusing to overwrite receipt\n")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
