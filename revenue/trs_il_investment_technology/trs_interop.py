#!/usr/bin/env python3
"""TRS Illinois investment-technology pursuit authority/interoperability compiler.

This is internal decision support. It cannot authorize buyer contact, bidding,
submission, investment activity, payment, award, or revenue recognition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "trs.interop.pursuit/v1"
REPORT_SCHEMA = "trs.interop.report/v1"
AUTHORITIES = {"BUYER_FIRST_PARTY", "THIRD_PARTY_DISCOVERY", "OWNER_SUPPLIED"}
CONTENT_STATES = {"METADATA_ONLY", "RETAINED_BYTES"}
PACKET_STATES = {"MISSING", "RETAINED_CURRENT"}
COMMERCIAL_STATE = "PROPOSED_NOT_ACCEPTED"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9_.:-]{0,95}$")

AUTHORITY_CEILING = {
    "buyer_contact": False,
    "portal_registration": False,
    "bid_submission": False,
    "bidder_qualification": False,
    "contract_acceptance": False,
    "award_claim": False,
    "payment_or_funds": False,
    "investment_or_trading": False,
    "accounting_or_compliance_opinion": False,
    "recognized_revenue": False,
}

class ContractError(ValueError):
    pass

def _no_float(_: str) -> Any:
    raise ContractError("floating-point JSON numbers are forbidden")

def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out

def loads_strict(text: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_float=_no_float,
            parse_constant=lambda x: (_ for _ in ()).throw(ContractError(f"invalid constant: {x}")),
        )
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError("root must be an object")
    return value

def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _exact_keys(obj: dict[str, Any], keys: set[str], where: str) -> None:
    got = set(obj)
    if got != keys:
        raise ContractError(f"{where} keys mismatch: missing={sorted(keys-got)} extra={sorted(got-keys)}")

def _str(value: Any, where: str, *, max_len: int = 1000) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise ContractError(f"{where} must be a non-empty string <= {max_len}")
    return value

def _id(value: Any, where: str) -> str:
    s = _str(value, where, max_len=96)
    if not ID_RE.fullmatch(s):
        raise ContractError(f"{where} has invalid id syntax")
    return s

def _sha(value: Any, where: str) -> str:
    s = _str(value, where, max_len=64)
    if not SHA256_RE.fullmatch(s):
        raise ContractError(f"{where} must be lowercase sha256")
    return s

def _list(value: Any, where: str, *, max_items: int) -> list[Any]:
    if not isinstance(value, list) or len(value) > max_items:
        raise ContractError(f"{where} must be a list <= {max_items}")
    return value

def _sorted_unique_strings(value: Any, where: str, *, max_items: int = 32) -> list[str]:
    vals = _list(value, where, max_items=max_items)
    out = []
    seen = set()
    for idx, item in enumerate(vals):
        s = _id(item, f"{where}[{idx}]")
        if s in seen:
            raise ContractError(f"duplicate {where}: {s}")
        seen.add(s)
        out.append(s)
    return sorted(out)

def validate_input(data: dict[str, Any]) -> dict[str, Any]:
    _exact_keys(
        data,
        {"schema","opportunity_id","buyer","sources","controlling_packet","systems",
         "objectives","proposed_controls","commercial"},
        "root",
    )
    if data["schema"] != SCHEMA:
        raise ContractError("unsupported schema")
    opportunity_id = _id(data["opportunity_id"], "opportunity_id")
    buyer = _str(data["buyer"], "buyer", max_len=240)

    sources_in = _list(data["sources"], "sources", max_items=128)
    sources: dict[str, dict[str, Any]] = {}
    for idx, raw in enumerate(sources_in):
        if not isinstance(raw, dict):
            raise ContractError(f"sources[{idx}] must be object")
        _exact_keys(raw, {"source_id","authority","content_state","sha256","observed_at","url","title"}, f"sources[{idx}]")
        sid = _id(raw["source_id"], f"sources[{idx}].source_id")
        if sid in sources:
            raise ContractError(f"duplicate source_id: {sid}")
        authority = _str(raw["authority"], f"sources[{idx}].authority", max_len=32)
        if authority not in AUTHORITIES:
            raise ContractError(f"unsupported authority: {authority}")
        content_state = _str(raw["content_state"], f"sources[{idx}].content_state", max_len=32)
        if content_state not in CONTENT_STATES:
            raise ContractError(f"unsupported content_state: {content_state}")
        source = {
            "source_id": sid,
            "authority": authority,
            "content_state": content_state,
            "sha256": _sha(raw["sha256"], f"sources[{idx}].sha256"),
            "observed_at": _str(raw["observed_at"], f"sources[{idx}].observed_at", max_len=40),
            "url": _str(raw["url"], f"sources[{idx}].url", max_len=1000),
            "title": _str(raw["title"], f"sources[{idx}].title", max_len=300),
        }
        sources[sid] = source

    cp = data["controlling_packet"]
    if not isinstance(cp, dict):
        raise ContractError("controlling_packet must be object")
    _exact_keys(cp, {"status","source_id"}, "controlling_packet")
    cp_status = _str(cp["status"], "controlling_packet.status", max_len=32)
    if cp_status not in PACKET_STATES:
        raise ContractError("unsupported controlling_packet.status")
    cp_source = cp["source_id"]
    if cp_status == "MISSING":
        if cp_source is not None:
            raise ContractError("MISSING controlling packet must have null source_id")
    else:
        cp_source = _id(cp_source, "controlling_packet.source_id")
        if cp_source not in sources:
            raise ContractError("controlling packet references unknown source")

    systems_in = _list(data["systems"], "systems", max_items=64)
    systems: dict[str, dict[str, Any]] = {}
    for idx, raw in enumerate(systems_in):
        if not isinstance(raw, dict):
            raise ContractError(f"systems[{idx}] must be object")
        _exact_keys(raw, {"system_id","vendor","product","roles","domains","evidence_source_id"}, f"systems[{idx}]")
        sid = _id(raw["system_id"], f"systems[{idx}].system_id")
        if sid in systems:
            raise ContractError(f"duplicate system_id: {sid}")
        source_id = _id(raw["evidence_source_id"], f"systems[{idx}].evidence_source_id")
        if source_id not in sources:
            raise ContractError(f"system {sid} references unknown source")
        systems[sid] = {
            "system_id": sid,
            "vendor": _str(raw["vendor"], f"systems[{idx}].vendor", max_len=160),
            "product": _str(raw["product"], f"systems[{idx}].product", max_len=160),
            "roles": _sorted_unique_strings(raw["roles"], f"systems[{idx}].roles", max_items=16),
            "domains": _sorted_unique_strings(raw["domains"], f"systems[{idx}].domains", max_items=24),
            "evidence_source_id": source_id,
        }

    objectives_in = _list(data["objectives"], "objectives", max_items=64)
    objectives: dict[str, dict[str, Any]] = {}
    for idx, raw in enumerate(objectives_in):
        if not isinstance(raw, dict):
            raise ContractError(f"objectives[{idx}] must be object")
        _exact_keys(raw, {"objective_id","text","evidence_source_id"}, f"objectives[{idx}]")
        oid = _id(raw["objective_id"], f"objectives[{idx}].objective_id")
        if oid in objectives:
            raise ContractError(f"duplicate objective_id: {oid}")
        source_id = _id(raw["evidence_source_id"], f"objectives[{idx}].evidence_source_id")
        if source_id not in sources:
            raise ContractError(f"objective {oid} references unknown source")
        objectives[oid] = {
            "objective_id": oid,
            "text": _str(raw["text"], f"objectives[{idx}].text", max_len=1000),
            "evidence_source_id": source_id,
        }

    controls_in = _list(data["proposed_controls"], "proposed_controls", max_items=64)
    controls: dict[str, dict[str, Any]] = {}
    for idx, raw in enumerate(controls_in):
        if not isinstance(raw, dict):
            raise ContractError(f"proposed_controls[{idx}] must be object")
        _exact_keys(raw, {"control_id","domain","systems","evidence_source_ids"}, f"proposed_controls[{idx}]")
        cid = _id(raw["control_id"], f"proposed_controls[{idx}].control_id")
        if cid in controls:
            raise ContractError(f"duplicate control_id: {cid}")
        domain = _id(raw["domain"], f"proposed_controls[{idx}].domain")
        system_ids = _sorted_unique_strings(raw["systems"], f"proposed_controls[{idx}].systems", max_items=16)
        if not system_ids:
            raise ContractError(f"control {cid} must reference at least one system")
        unknown = [x for x in system_ids if x not in systems]
        if unknown:
            raise ContractError(f"control {cid} references unknown systems: {unknown}")
        evidence = _sorted_unique_strings(raw["evidence_source_ids"], f"proposed_controls[{idx}].evidence_source_ids", max_items=16)
        if not evidence:
            raise ContractError(f"control {cid} must reference evidence")
        unknown_e = [x for x in evidence if x not in sources]
        if unknown_e:
            raise ContractError(f"control {cid} references unknown sources: {unknown_e}")
        controls[cid] = {
            "control_id": cid,
            "domain": domain,
            "systems": system_ids,
            "evidence_source_ids": evidence,
        }

    commercial = data["commercial"]
    if not isinstance(commercial, dict):
        raise ContractError("commercial must be object")
    _exact_keys(commercial, {"currency","proposed_fee_minor","state"}, "commercial")
    if commercial["currency"] != "USD":
        raise ContractError("commercial.currency must be USD")
    amount = commercial["proposed_fee_minor"]
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0 or amount > 10**9:
        raise ContractError("proposed_fee_minor must be safe nonnegative integer")
    if commercial["state"] != "PROPOSED_NOT_ACCEPTED":
        raise ContractError("commercial state cannot self-promote beyond PROPOSED_NOT_ACCEPTED")

    return {
        "schema": SCHEMA,
        "opportunity_id": opportunity_id,
        "buyer": buyer,
        "sources": [sources[k] for k in sorted(sources)],
        "controlling_packet": {"status": cp_status, "source_id": cp_source},
        "systems": [systems[k] for k in sorted(systems)],
        "objectives": [objectives[k] for k in sorted(objectives)],
        "proposed_controls": [controls[k] for k in sorted(controls)],
        "commercial": {
            "currency": "USD",
            "proposed_fee_minor": amount,
            "state": "PROPOSED_NOT_ACCEPTED",
        },
    }

def compile_packet(data: dict[str, Any], *, trusted_packet_sha256: str | None = None) -> dict[str, Any]:
    normalized = validate_input(data)
    source_by_id = {x["source_id"]: x for x in normalized["sources"]}
    system_by_id = {x["system_id"]: x for x in normalized["systems"]}

    cp = normalized["controlling_packet"]
    packet_clear = False
    packet_reason = "controlling packet not retained"
    if cp["status"] == "RETAINED_CURRENT":
        src = source_by_id[cp["source_id"]]
        if src["authority"] != "BUYER_FIRST_PARTY":
            packet_reason = "controlling packet source is not BUYER_FIRST_PARTY"
        elif src["content_state"] != "RETAINED_BYTES":
            packet_reason = "controlling packet source does not bind retained bytes"
        elif trusted_packet_sha256 is None:
            packet_reason = "out-of-band trusted packet sha256 absent"
        elif not SHA256_RE.fullmatch(trusted_packet_sha256):
            raise ContractError("trusted_packet_sha256 must be lowercase sha256")
        elif trusted_packet_sha256 != src["sha256"]:
            packet_reason = "out-of-band packet sha256 mismatch"
        else:
            packet_clear = True
            packet_reason = "buyer-first-party packet is retained and out-of-band hash bound"

    unverified_systems = sorted(
        x["system_id"] for x in normalized["systems"]
        if source_by_id[x["evidence_source_id"]]["authority"] != "BUYER_FIRST_PARTY"
    )
    unverified_objectives = sorted(
        x["objective_id"] for x in normalized["objectives"]
        if source_by_id[x["evidence_source_id"]]["authority"] != "BUYER_FIRST_PARTY"
    )
    unverified_controls = sorted(
        c["control_id"] for c in normalized["proposed_controls"]
        if any(source_by_id[s]["authority"] != "BUYER_FIRST_PARTY" for s in c["evidence_source_ids"])
    )

    domain_map: dict[str, list[str]] = {}
    for system in normalized["systems"]:
        for domain in system["domains"]:
            domain_map.setdefault(domain, []).append(system["system_id"])
    domain_authority = []
    for domain in sorted(domain_map):
        ids = sorted(domain_map[domain])
        authorities = sorted({source_by_id[system_by_id[s]["evidence_source_id"]]["authority"] for s in ids})
        domain_authority.append({
            "domain": domain,
            "systems": ids,
            "evidence_authorities": authorities,
            "review_state": "MULTI_SYSTEM_AUTHORITY_REVIEW" if len(ids) > 1 else "SINGLE_DECLARED_SYSTEM",
        })

    if not packet_clear:
        state = "HOLD_CONTROLLING_PACKET"
    elif unverified_systems or unverified_objectives or unverified_controls:
        state = "HOLD_SOURCE_AUTHORITY"
    else:
        state = "READY_FOR_PARTNER_QUALIFICATION"

    normalized_digest = sha256_hex(canonical_bytes(normalized))
    report_core = {
        "schema": REPORT_SCHEMA,
        "opportunity_id": normalized["opportunity_id"],
        "buyer": normalized["buyer"],
        "state": state,
        "packet_gate": {
            "clear": packet_clear,
            "reason": packet_reason,
            "source_id": cp["source_id"],
        },
        "source_authority_holds": {
            "systems": unverified_systems,
            "objectives": unverified_objectives,
            "controls": unverified_controls,
        },
        "domain_authority": domain_authority,
        "controls": normalized["proposed_controls"],
        "commercial": normalized["commercial"],
        "authority_ceiling": {
            "buyer_contact": False,
            "portal_registration": False,
            "bid_submission": False,
            "bidder_qualification": False,
            "contract_acceptance": False,
            "award_claim": False,
            "payment_or_funds": False,
            "investment_or_trading": False,
            "accounting_or_compliance_opinion": False,
            "recognized_revenue": False,
        },
        "normalized_input_sha256": normalized_digest,
    }
    receipt = {
        "report_core_sha256": sha256_hex(canonical_bytes(report_core)),
        "source_count": len(normalized["sources"]),
        "system_count": len(normalized["systems"]),
        "objective_count": len(normalized["objectives"]),
        "control_count": len(normalized["proposed_controls"]),
    }
    return {**report_core, "receipt": receipt}

def verify_packet(data: dict[str, Any], report: dict[str, Any], *, trusted_packet_sha256: str | None = None) -> bool:
    expected = compile_packet(data, trusted_packet_sha256=trusted_packet_sha256)
    return canonical_bytes(expected) == canonical_bytes(report)

def _write_exclusive(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as fh:
        fh.write(content)
        fh.flush()

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile")
    c.add_argument("--input", required=True)
    c.add_argument("--output", required=True)
    c.add_argument("--trusted-packet-sha256")
    v = sub.add_parser("verify")
    v.add_argument("--input", required=True)
    v.add_argument("--report", required=True)
    v.add_argument("--trusted-packet-sha256")
    args = parser.parse_args(argv)

    data = loads_strict(Path(args.input).read_text(encoding="utf-8"))
    if args.cmd == "compile":
        report = compile_packet(data, trusted_packet_sha256=args.trusted_packet_sha256)
        _write_exclusive(Path(args.output), canonical_bytes(report) + b"\n")
        print(report["state"])
        return 0
    report = loads_strict(Path(args.report).read_text(encoding="utf-8"))
    ok = verify_packet(data, report, trusted_packet_sha256=args.trusted_packet_sha256)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 2

if __name__ == "__main__":
    raise SystemExit(main())
