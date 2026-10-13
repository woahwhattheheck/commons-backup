"""Deterministic public-sector paid workshare compiler and verifier."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .catalog import (
    COMMERCIAL_SHAPES,
    EXPECTED_COMMERCIAL_STATE,
    MAX_SOURCE_AGE_SECONDS,
    MODULE_CATALOG,
    OUTBOUND_STATE,
    PACKET_SCHEMA,
)
from .schema import (
    canonical_json,
    collision_key,
    exact_keys,
    load_json_strict,
    normalize_manifest,
    parse_date,
    parse_utc,
    sha,
    sha256_obj,
    write_exclusive,
)


def _draft_for(op: dict[str, Any]) -> str:
    modules = ", ".join(MODULE_CATALOG[mid]["title"].lower() for mid in op["allowed_modules"])
    return (
        "NOT AUTHORIZED TO SEND — Paid workshare fit check for "
        f"{op['opportunity_id']}: if your team is pursuing this procurement, Token Junkie Labs can scope a bounded paid "
        f"specialist subcontract covering {modules}. The initial commercial shape is a 2–4 week fixed-fee pilot with exact "
        "inputs, outputs, acceptance tests, and exclusions; implementation workshare can follow if fit and commercial terms are "
        "mutually agreed. This draft does not assert that your organization is bidding or that any workshare has been accepted."
    )


def compile_pack(manifest: Any, *, as_of_utc: str) -> dict[str, Any]:
    normalized, as_of = normalize_manifest(deepcopy(manifest), as_of_utc)
    captured_at = parse_utc(normalized["captured_at_utc"], "captured_at_utc")
    age_seconds = int((as_of - captured_at).total_seconds())
    overlays: list[dict[str, Any]] = []
    any_hold = False
    for op in normalized["opportunities"]:
        deadline_date = parse_date(op["deadline"]["date"], "deadline.date")
        source_age_state = "CURRENT_WITHIN_7D" if age_seconds <= MAX_SOURCE_AGE_SECONDS else "RECHECK_REQUIRED"
        if as_of.date() > deadline_date:
            state = "HOLD_DEADLINE_EXPIRED"
            any_hold = True
        elif as_of.date() == deadline_date:
            state = "HOLD_DEADLINE_DAY_RECHECK_REQUIRED"
            any_hold = True
        elif source_age_state != "CURRENT_WITHIN_7D":
            state = "HOLD_SOURCE_RECHECK_REQUIRED"
            any_hold = True
        elif op["deadline"]["authority"] not in {"OFFICIAL_BUYER", "OFFICIAL_PORTAL"}:
            state = "READY_FOR_PRIME_REVIEW_DEADLINE_RECHECK_REQUIRED"
        else:
            state = "READY_FOR_PRIME_REVIEW"
        targets = [{**target, "collision_key_state": "PENDING_ROUTE_FINGERPRINT", "outbound_state": OUTBOUND_STATE} for target in op["target_candidates"]]
        overlays.append({
            "opportunity_id": op["opportunity_id"],
            "buyer": op["buyer"],
            "solicitation": op["solicitation"],
            "deadline": op["deadline"],
            "source_age_state": source_age_state,
            "overlay_state": state,
            "allowed_modules": op["allowed_modules"],
            "workshare_wedge": op["workshare_wedge"],
            "prime_owned": op["prime_owned"],
            "target_candidates": targets,
            "outreach_draft": _draft_for(op),
            "external_send_authorized": False,
            "bid_submission_authorized": False,
        })
    core = {
        "schema": PACKET_SCHEMA,
        "as_of_utc": as_of.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_manifest": normalized,
        "module_catalog": MODULE_CATALOG,
        "commercial_shapes": list(COMMERCIAL_SHAPES),
        "commercial_truth": {
            "commercial_state": EXPECTED_COMMERCIAL_STATE,
            "fee_state": "OWNER_INPUT_REQUIRED",
            "payment_path_state": "REQUIRED_BEFORE_AUTHORIZED_OUTBOUND",
            "cash_or_revenue_claimed": False,
        },
        "authority_ceiling": {
            "external_send_authorized": False,
            "buyer_contact_authorized": False,
            "prime_contact_authorized": False,
            "bid_submission_authorized": False,
            "portal_mutation_authorized": False,
            "teaming_commitment_authorized": False,
            "price_acceptance_authorized": False,
            "contract_authorized": False,
            "spend_authorized": False,
            "payment_mutation_authorized": False,
            "recognized_revenue_claimed": False,
        },
        "single_writer_rule": {
            "required_before_any_outbound": [
                "fresh organization + opportunity + target + route custody",
                "current mailbox/provider/thread history",
                "current collision key from privacy-safe route fingerprint",
                "one last-inch exclusive send fence immediately before provider mutation",
            ],
            "ambiguous_provider_outcome": "DNR_RECONCILE_NEVER_BLIND_RETRY",
        },
        "overlays": overlays,
        "overall_state": "HOLD" if any_hold else "WORKSHARE_PACK_READY_FOR_PRIME_REVIEW",
    }
    packet = deepcopy(core)
    packet["receipt_sha256"] = sha256_obj(core)
    return packet


def verify_packet(packet: Any, *, current_as_of_utc: str | None = None) -> dict[str, Any]:
    if not isinstance(packet, dict):
        raise ValueError("packet must be object")
    expected = {"schema", "as_of_utc", "input_manifest", "module_catalog", "commercial_shapes", "commercial_truth", "authority_ceiling", "single_writer_rule", "overlays", "overall_state", "receipt_sha256"}
    exact_keys(packet, expected, "packet")
    receipt = sha(packet["receipt_sha256"], "packet.receipt_sha256")
    core = {key: deepcopy(value) for key, value in packet.items() if key != "receipt_sha256"}
    if sha256_obj(core) != receipt:
        raise ValueError("packet receipt mismatch")
    rebuilt = compile_pack(packet["input_manifest"], as_of_utc=packet["as_of_utc"])
    if canonical_json(rebuilt) != canonical_json(packet):
        raise ValueError("packet semantic replay mismatch")
    result: dict[str, Any] = {"historical_integrity": "PASS", "receipt_sha256": receipt}
    if current_as_of_utc is not None:
        current = compile_pack(packet["input_manifest"], as_of_utc=current_as_of_utc)
        result["current_state"] = current["overall_state"]
        result["current_overlay_states"] = {row["opportunity_id"]: row["overlay_state"] for row in current["overlays"]}
    return result


def _md(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("`", "\\`").replace("\n", " ").replace("\r", " ")


def render_markdown(packet: dict[str, Any]) -> str:
    verify_packet(packet)
    lines = [
        "# Public-Sector Integration Workshare Pack", "",
        f"- State: **{_md(packet['overall_state'])}**",
        f"- Evidence time: `{_md(packet['as_of_utc'])}`",
        f"- Commercial state: **{EXPECTED_COMMERCIAL_STATE}**",
        "- External outreach: **NOT AUTHORIZED TO SEND**",
        "- Fee: **OWNER INPUT REQUIRED before any authorized outreach**", "",
        "## Paid workshare modules", "",
    ]
    for module_id in sorted(MODULE_CATALOG):
        module = MODULE_CATALOG[module_id]
        lines.extend([f"### {_md(module['title'])}", "", f"ID: `{module_id}`", ""])
        lines.extend(["**Acceptance:** " + "; ".join(_md(v) for v in module["acceptance"]), ""])
        lines.extend(["**Exclusions:** " + "; ".join(_md(v) for v in module["exclusions"]), ""])
    lines.extend(["## Live opportunity overlays", "", "| Opportunity | State | Workshare | Deadline |", "|---|---|---|---|"])
    for op in packet["overlays"]:
        deadline = op["deadline"]["date"] + (f" {op['deadline']['time_local']} {op['deadline']['timezone']}" if op["deadline"]["time_local"] else " time TBD/recheck")
        lines.append(f"| {_md(op['opportunity_id'])} | {_md(op['overlay_state'])} | {_md('; '.join(op['workshare_wedge']))} | {_md(deadline)} |")
    lines.extend([
        "", "## Single-writer outbound fence", "",
        "No target in this packet is contact-authorized. Before any later external mutation, reacquire exact organization/opportunity/target/route custody, reread current provider/mailbox history, derive the privacy-safe route collision key, and win a last-inch exclusive send fence. Ambiguous provider outcome is DNR/reconcile, never blind retry.",
        "", f"Receipt: `{packet['receipt_sha256']}`", "",
    ])
    return "\n".join(lines)
