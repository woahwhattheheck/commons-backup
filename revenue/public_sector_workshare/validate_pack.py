from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PACK_SCHEMA = "tjl-public-sector-workshare-pack/v1"
OVERLAY_SCHEMA = "tjl-public-sector-workshare-overlay/v1"
TARGET_AUTHORITY_SCHEMA = "tjl-public-sector-target-authority/v1"
LEASE_RECEIPT_SCHEMA = "tjl-public-sector-single-writer-lease/v1"
TARGET_PACKET_SCHEMA = "tjl-public-sector-target-review/v1"
COMMERCIAL_TRUTH = "PROPOSED_NOT_ACCEPTED"
MODULE_IDS = {
    "MIGRATION_EVIDENCE",
    "INTEGRATION_CONFORMANCE",
    "UAT_ACCEPTANCE_EVIDENCE",
    "CUTOVER_REPLAY",
}
LEASE_STATUSES = {"ACQUIRED", "RELEASED", "EXPIRED", "HOLD"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class ContractError(ValueError):
    pass


def _load(path: Path) -> Any:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ContractError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh, object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(ContractError(f"non-finite JSON value: {x}")))


def _exact_bool(value: Any, label: str) -> None:
    if type(value) is not bool:
        raise ContractError(f"{label} must be bool")


def _nonempty_strings(value: Any, label: str) -> None:
    if not isinstance(value, list) or not value or any(type(v) is not str or not v.strip() for v in value):
        raise ContractError(f"{label} must be a non-empty string list")


def _positive_int(value: Any, label: str) -> None:
    if type(value) is not int or value <= 0:
        raise ContractError(f"{label} must be a positive integer")


def _text(value: Any, label: str, *, machine_id: bool = False) -> str:
    if type(value) is not str or not value.strip():
        raise ContractError(f"{label} must be a non-empty string")
    value = value.strip()
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ContractError(f"{label} contains control characters")
    if machine_id and not _ID_RE.fullmatch(value):
        raise ContractError(f"{label} must be a stable machine id")
    return value


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or not _SHA256_RE.fullmatch(value):
        raise ContractError(f"{label} must be lowercase sha256")
    return value


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not str or not _UTC_RE.fullmatch(value):
        raise ContractError(f"{label} must be whole-second UTC ending Z")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ContractError(f"{label} is invalid UTC") from exc


def sha256_obj(value: Any) -> str:
    try:
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ContractError("value cannot be canonically encoded") from exc
    return hashlib.sha256(raw).hexdigest()


def collision_key(opportunity_id: str, organization_id: str, route_id: str) -> str:
    """Stable opportunity × organization × route identity.

    organization_id and route_id come from retained target authority. Display
    company/address spelling is audit text only and never enters this key.
    """
    values = (
        _text(opportunity_id, "opportunity_id"),
        _text(organization_id, "organization_id"),
        _text(route_id, "route_id"),
    )
    canonical = "\n".join(v.lower() for v in values)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_pack(pack: dict[str, Any]) -> None:
    required = {
        "schema","operation","owner_seat","model_family","commercial_truth",
        "buyer_acceptance_asserted","award_asserted","payment_asserted",
        "recognized_revenue_asserted","modules","offers","coordination_contract",
        "proof_refs","authority_ceiling",
    }
    if set(pack) != required:
        raise ContractError(f"pack keys mismatch: {sorted(set(pack) ^ required)}")
    if pack["schema"] != PACK_SCHEMA:
        raise ContractError("wrong pack schema")
    if pack["commercial_truth"] != COMMERCIAL_TRUTH:
        raise ContractError("commercial truth drift")
    for key in ("buyer_acceptance_asserted","award_asserted","payment_asserted","recognized_revenue_asserted"):
        _exact_bool(pack[key], key)
        if pack[key]:
            raise ContractError(f"{key} must remain false absent provider evidence")
    modules = pack["modules"]
    if not isinstance(modules, list) or len(modules) != 4:
        raise ContractError("exactly four modules required")
    seen = set()
    for module in modules:
        expected = {"id","name","required_inputs","outputs","acceptance_tests","exclusions"}
        if not isinstance(module, dict) or set(module) != expected:
            raise ContractError("module keys mismatch")
        mid = module["id"]
        if mid in seen or mid not in MODULE_IDS:
            raise ContractError(f"invalid/duplicate module id: {mid}")
        seen.add(mid)
        for key in ("required_inputs","outputs","acceptance_tests","exclusions"):
            _nonempty_strings(module[key], f"module {mid} {key}")
    if seen != MODULE_IDS:
        raise ContractError("module coverage incomplete")
    offers = pack["offers"]
    if not isinstance(offers, list) or len(offers) < 2:
        raise ContractError("pilot and implementation offers required")
    offer_ids = set()
    for offer in offers:
        expected = {"id","status","price_usd","duration_weeks_min","duration_weeks_max","scope","excludes"}
        if not isinstance(offer, dict) or set(offer) != expected:
            raise ContractError("offer keys mismatch")
        if offer["id"] in offer_ids:
            raise ContractError("duplicate offer id")
        offer_ids.add(offer["id"])
        if offer["status"] != COMMERCIAL_TRUTH:
            raise ContractError("offer status must remain PROPOSED_NOT_ACCEPTED")
        if type(offer["price_usd"]) is not int or offer["price_usd"] <= 0:
            raise ContractError("offer price must be a positive integer USD hypothesis")
        for key in ("duration_weeks_min","duration_weeks_max"):
            if type(offer[key]) is not int or offer[key] <= 0:
                raise ContractError("duration must be positive integer weeks")
        if offer["duration_weeks_min"] > offer["duration_weeks_max"]:
            raise ContractError("duration range inverted")
        _nonempty_strings(offer["excludes"], "offer excludes")
    cc = pack["coordination_contract"]
    expected_cc = {
        "single_writer_key_formula","target_authority_schema","lease_receipt_schema",
        "lease_required","required_pre_send_observations","ambiguous_provider_outcome",
        "send_log_fields","security_authority_created","note",
    }
    if not isinstance(cc, dict) or set(cc) != expected_cc:
        raise ContractError("coordination contract keys mismatch")
    expected_formula = (
        "sha256(lower(opportunity_id) + '\n' + lower(organization_id) + "
        "'\n' + lower(route_id))"
    )
    if cc["single_writer_key_formula"] != expected_formula:
        raise ContractError("single-writer key must use stable authority ids")
    if cc["target_authority_schema"] != TARGET_AUTHORITY_SCHEMA:
        raise ContractError("target authority schema drift")
    if cc["lease_receipt_schema"] != LEASE_RECEIPT_SCHEMA:
        raise ContractError("lease receipt schema drift")
    _exact_bool(cc["lease_required"], "lease_required")
    if not cc["lease_required"]:
        raise ContractError("single-writer lease must be required")
    if cc["ambiguous_provider_outcome"] != "DNR_RECONCILE_NEVER_RESEND":
        raise ContractError("ambiguous provider outcome must fail duplicate-send closed")
    _exact_bool(cc["security_authority_created"], "security_authority_created")
    if cc["security_authority_created"]:
        raise ContractError("coordination may not create auth/permission authority")
    _nonempty_strings(cc["required_pre_send_observations"], "pre-send observations")
    _nonempty_strings(cc["send_log_fields"], "send-log fields")
    if not isinstance(pack["proof_refs"], list) or len(pack["proof_refs"]) < 3:
        raise ContractError("proof refs incomplete")
    _nonempty_strings(pack["authority_ceiling"], "authority ceiling")


def validate_overlay(overlay: dict[str, Any], pack: dict[str, Any]) -> None:
    common = {
        "schema","opportunity_id","buyer","solicitation_id","state","primary_source",
        "source_checked_utc","deadline_local","deadline_timezone","prime_owned",
        "workshare_modules","workshare_wedge","qualification_truth","target_archetypes",
        "named_target_status","commercial_offer_ids","outbound_authorized_by_overlay",
        "submission_authorized","buyer_budget_usd","award_asserted","payment_asserted",
    }
    allowed_extra = {"subcontract_structure_evidence"}
    keys = set(overlay)
    if not common.issubset(keys) or keys - common - allowed_extra:
        raise ContractError(f"overlay keys mismatch: {sorted(keys ^ common)}")
    if overlay["schema"] != OVERLAY_SCHEMA:
        raise ContractError("wrong overlay schema")
    if overlay["state"] != "OPEN_CAPTURE_PARTNER_FIRST":
        raise ContractError("overlay must remain partner-first capture")
    if overlay["qualification_truth"] != "PARTNER_FIRST_NOT_PRIME_ASSERTION":
        raise ContractError("prime-readiness drift")
    if overlay["buyer_budget_usd"] is not None:
        raise ContractError("buyer budget is unknown in this carrier")
    for key in ("outbound_authorized_by_overlay","submission_authorized","award_asserted","payment_asserted"):
        _exact_bool(overlay[key], key)
        if overlay[key]:
            raise ContractError(f"{key} must remain false")
    _nonempty_strings(overlay["prime_owned"], "prime_owned")
    _nonempty_strings(overlay["target_archetypes"], "target_archetypes")
    mods = overlay["workshare_modules"]
    _nonempty_strings(mods, "workshare_modules")
    if set(mods) - MODULE_IDS:
        raise ContractError("overlay references unknown workshare module")
    offer_ids = {o["id"] for o in pack["offers"]}
    _nonempty_strings(overlay["commercial_offer_ids"], "commercial_offer_ids")
    if set(overlay["commercial_offer_ids"]) - offer_ids:
        raise ContractError("overlay references unknown offer")
    if not str(overlay["primary_source"]).startswith("https://"):
        raise ContractError("primary source must be HTTPS")



def validate_target_authority(authority: dict[str, Any], expected_sha256: str) -> str:
    required = {
        "schema","opportunity_id","organization_id","route_id","display_company",
        "display_route","generation","captured_utc","source_ref",
    }
    if type(authority) is not dict or set(authority) != required:
        raise ContractError("target authority keys mismatch")
    if authority["schema"] != TARGET_AUTHORITY_SCHEMA:
        raise ContractError("wrong target authority schema")
    _text(authority["opportunity_id"], "target opportunity_id", machine_id=True)
    _text(authority["organization_id"], "organization_id", machine_id=True)
    _text(authority["route_id"], "route_id", machine_id=True)
    _text(authority["display_company"], "display_company")
    _text(authority["display_route"], "display_route")
    _positive_int(authority["generation"], "target authority generation")
    _utc(authority["captured_utc"], "target authority captured_utc")
    _text(authority["source_ref"], "target authority source_ref")
    expected_sha256 = _sha256(expected_sha256, "expected target authority sha256")
    actual = sha256_obj(authority)
    if actual != expected_sha256:
        raise ContractError("target authority retained-root mismatch")
    return actual


def validate_lease_receipt(
    receipt: dict[str, Any],
    expected_sha256: str,
    *,
    target_authority_sha256: str,
) -> str:
    required = {
        "schema","opportunity_id","organization_id","route_id","arbiter","generation",
        "status","acquired_utc","expires_utc","receipt_ref","target_authority_sha256",
    }
    if type(receipt) is not dict or set(receipt) != required:
        raise ContractError("lease receipt keys mismatch")
    if receipt["schema"] != LEASE_RECEIPT_SCHEMA:
        raise ContractError("wrong lease receipt schema")
    for key in ("opportunity_id","organization_id","route_id"):
        _text(receipt[key], f"lease {key}", machine_id=True)
    _text(receipt["arbiter"], "lease arbiter", machine_id=True)
    _positive_int(receipt["generation"], "lease generation")
    if receipt["status"] not in LEASE_STATUSES:
        raise ContractError("unknown lease status")
    acquired = _utc(receipt["acquired_utc"], "lease acquired_utc")
    expires = _utc(receipt["expires_utc"], "lease expires_utc")
    if expires <= acquired:
        raise ContractError("lease expiry must follow acquisition")
    _text(receipt["receipt_ref"], "lease receipt_ref")
    if receipt["target_authority_sha256"] != _sha256(
        target_authority_sha256, "target authority sha256"
    ):
        raise ContractError("lease is bound to different target authority")
    expected_sha256 = _sha256(expected_sha256, "expected lease receipt sha256")
    actual = sha256_obj(receipt)
    if actual != expected_sha256:
        raise ContractError("lease receipt retained-root mismatch")
    return actual


def _deadline_state(overlay: dict[str, Any], review: datetime) -> str:
    local = _text(overlay["deadline_local"], "deadline_local")
    tz_name = _text(overlay["deadline_timezone"], "deadline_timezone")
    if tz_name.startswith("UNKNOWN_") or "T" not in local:
        return "UNRESOLVED"
    try:
        zone = ZoneInfo(tz_name)
        naive = datetime.fromisoformat(local)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ContractError("deadline timezone/local value invalid") from exc
    if naive.tzinfo is not None:
        raise ContractError("deadline_local must not include timezone")
    deadline = naive.replace(tzinfo=zone).astimezone(timezone.utc)
    return "OPEN" if review < deadline else "CLOSED"


def build_target_packet(
    pack: dict[str, Any],
    overlay: dict[str, Any],
    *,
    target_authority: dict[str, Any],
    expected_target_authority_sha256: str,
    lease_receipt: dict[str, Any],
    expected_lease_receipt_sha256: str,
    review_utc: str,
    relationship_checked: bool,
    provider_history_rechecked: bool,
    opportunity_facts_revalidated: bool,
) -> dict[str, Any]:
    validate_pack(pack)
    validate_overlay(overlay, pack)
    for label, value in (
        ("relationship_checked", relationship_checked),
        ("provider_history_rechecked", provider_history_rechecked),
        ("opportunity_facts_revalidated", opportunity_facts_revalidated),
    ):
        _exact_bool(value, label)
    review = _utc(review_utc, "review_utc")
    target_sha = validate_target_authority(target_authority, expected_target_authority_sha256)
    lease_sha = validate_lease_receipt(
        lease_receipt,
        expected_lease_receipt_sha256,
        target_authority_sha256=target_sha,
    )
    if target_authority["opportunity_id"] != overlay["opportunity_id"]:
        raise ContractError("target authority opportunity does not match overlay")
    for key in ("opportunity_id","organization_id","route_id"):
        if lease_receipt[key] != target_authority[key]:
            raise ContractError(f"lease {key} does not match target authority")
    captured = _utc(target_authority["captured_utc"], "target authority captured_utc")
    acquired = _utc(lease_receipt["acquired_utc"], "lease acquired_utc")
    expires = _utc(lease_receipt["expires_utc"], "lease expires_utc")
    if captured > review:
        raise ContractError("target authority capture is in the future")
    if acquired < captured:
        raise ContractError("lease acquisition predates target authority capture")
    if acquired > review:
        raise ContractError("lease acquisition is in the future")

    hold_reasons = []
    if lease_receipt["status"] != "ACQUIRED":
        hold_reasons.append(f"LEASE_STATUS_{lease_receipt['status']}")
    if review >= expires:
        hold_reasons.append("LEASE_EXPIRED_AT_REVIEW")
    if not relationship_checked:
        hold_reasons.append("RELATIONSHIP_CENSUS_NOT_CURRENT")
    if not provider_history_rechecked:
        hold_reasons.append("PROVIDER_HISTORY_NOT_CURRENT")
    if not opportunity_facts_revalidated:
        hold_reasons.append("OPPORTUNITY_FACTS_NOT_REVALIDATED")
    deadline_state = _deadline_state(overlay, review)
    if deadline_state == "CLOSED":
        hold_reasons.append("OPPORTUNITY_DEADLINE_CLOSED")
    elif deadline_state == "UNRESOLVED":
        hold_reasons.append("OPPORTUNITY_DEADLINE_UNRESOLVED")

    opportunity_id = target_authority["opportunity_id"]
    packet = {
        "schema": TARGET_PACKET_SCHEMA,
        "capture_operation": pack["operation"],
        "opportunity_id": opportunity_id,
        "organization_id": target_authority["organization_id"],
        "route_id": target_authority["route_id"],
        "display_company": target_authority["display_company"],
        "display_route": target_authority["display_route"],
        "collision_key": collision_key(
            opportunity_id, target_authority["organization_id"], target_authority["route_id"]
        ),
        "target_authority_sha256": target_sha,
        "lease_receipt_sha256": lease_sha,
        "lease_generation": lease_receipt["generation"],
        "lease_status": lease_receipt["status"],
        "lease_arbiter": lease_receipt["arbiter"],
        "lease_expires_utc": lease_receipt["expires_utc"],
        "review_utc": review_utc,
        "deadline_state": deadline_state,
        "relationship_checked": relationship_checked,
        "provider_history_rechecked": provider_history_rechecked,
        "opportunity_facts_revalidated": opportunity_facts_revalidated,
        "controls_clear": not hold_reasons,
        "state": "READY_FOR_OWNER_TRANSPORT_REVIEW" if not hold_reasons else "HOLD",
        "hold_reasons": sorted(hold_reasons),
        "external_send_authorized": False,
        "submission_authorized": False,
        "payment_authorized": False,
    }
    packet["packet_sha256"] = sha256_obj(packet)
    return packet


def verify_target_packet(
    packet: dict[str, Any],
    pack: dict[str, Any],
    overlay: dict[str, Any],
    **build_kwargs: Any,
) -> bool:
    try:
        expected = build_target_packet(pack, overlay, **build_kwargs)
    except ContractError:
        return False
    return packet == expected


def validate_tree(root: Path) -> dict[str, Any]:
    pack = _load(root / "pack.json")
    if not isinstance(pack, dict):
        raise ContractError("pack must be an object")
    validate_pack(pack)
    overlay_paths = sorted((root / "overlays").glob("*.json"))
    live = [p for p in overlay_paths if p.name != "EXISTING_MERGED_QUALIFICATIONS.json"]
    if {p.name for p in live} != {
        "IL_DOIT_CDB_27_448DOIT_ADMIN_B_52519.json",
        "NC_DHHS_DHB_30_2025_037_DHB.json",
    }:
        raise ContractError("expected exactly the two still-missing live overlays")
    for path in live:
        overlay = _load(path)
        if not isinstance(overlay, dict):
            raise ContractError("overlay must be an object")
        validate_overlay(overlay, pack)
    refs = _load(root / "overlays" / "EXISTING_MERGED_QUALIFICATIONS.json")
    if refs.get("schema") != "tjl-public-sector-existing-qualification-refs/v1":
        raise ContractError("existing-ref schema mismatch")
    expected = {("OR-ODA-S-DASOBO-00017788", 13907), ("NYSED-RFP-144-OCUE", 13547)}
    actual = {(r.get("opportunity_id"), r.get("pr")) for r in refs.get("refs", [])}
    if actual != expected:
        raise ContractError("existing qualification refs drift")
    return {"schema": pack["schema"], "modules": sorted(MODULE_IDS), "overlays": [p.name for p in live], "offers": [o["id"] for o in pack["offers"]]}


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    print(json.dumps(validate_tree(here), sort_keys=True))
