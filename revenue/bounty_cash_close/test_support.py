from __future__ import annotations

import hashlib

from .engine import (CloseBoardError, INPUT_SCHEMA, ZERO_SHA256, canonical_bounty_key, compile_board, mint_receipt, validate_input, verify_bundle)

AS_OF = "2026-09-14T20:00:00Z"

def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def fixed_value(amount: int = 9000) -> dict:
    return {
        "state": "FIXED",
        "amount_minor": amount,
        "currency": "USD",
        "source_ref": "issue:267",
        "evidence_sha256": h("advertised-value"),
    }

def make_bounty(receipts: list[dict] | None = None, *, suffix: str = "a") -> dict:
    return {
        "sponsor_ref": "sponsor:lilly",
        "program_ref": "program:agentlily",
        "bounty_ref": f"bounty:{suffix}",
        "claimant_ref": "claimant:tjlabs",
        "source_revision": "rev:1",
        "work_fingerprint_sha256": h(f"work-{suffix}"),
        "advertised_value": fixed_value(),
        "receipts": receipts or [],
    }

def make_doc(bounties: list[dict]) -> dict:
    return {
        "schema": INPUT_SCHEMA,
        "board_id": "board:close-1",
        "policy": {
            "gate_followup_after_seconds": 3600,
            "compensation_followup_after_seconds": 7200,
        },
        "bounties": bounties,
    }

def add(chain: list[dict], kind: str, when: str, *, pclass: str = "GITHUB", eid: str | None = None) -> list[dict]:
    previous = chain[-1]["receipt_sha256"] if chain else ZERO_SHA256
    event = mint_receipt({
        "event_id": eid or f"event:{len(chain)+1}:{kind.lower()}",
        "kind": kind,
        "observed_at_utc": when,
        "provider_class": pclass,
        "provider_ref": f"provider:{pclass.lower()}",
        "external_ref": f"external:{len(chain)+1}",
        "evidence_sha256": h(f"{kind}-{when}-{len(chain)}"),
        "previous_receipt_sha256": previous,
    })
    return [*chain, event]

def row_for(chain: list[dict], *, as_of: str = AS_OF) -> dict:
    out, _, _ = compile_board(make_doc([make_bounty(chain)]), as_of)
    return out["rows"][0]
