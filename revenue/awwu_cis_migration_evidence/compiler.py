"""Evidence-bound paid workshare compiler for utility CIS migration teaming."""
from __future__ import annotations
import argparse, copy, datetime as dt, hashlib, json, os, re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

INPUT_SCHEMA = "awwu-cis-migration-workshare/v1"
RECEIPT_SCHEMA = "awwu-cis-migration-workshare-receipt/v1"
VERIFY_SCHEMA = "awwu-cis-migration-workshare-verification/v1"
READY = "READY_FOR_OWNER_TEAMING_REVIEW"
EVIDENCE_CONSISTENT = "INTERNALLY_CONSISTENT_SELF_ASSERTED_EVIDENCE"
EVIDENCE_HOLD = "SELF_ASSERTED_EVIDENCE_HAS_FAILURES"
PROPOSED = "PROPOSED_NOT_ACCEPTED"
INDEPENDENT_AUTHORITY_BLOCKERS = (
    "INDEPENDENT_SOURCE_AUTHORITY_REQUIRED",
    "INDEPENDENT_REQUIREMENTS_AUTHORITY_REQUIRED",
    "INDEPENDENT_EVIDENCE_AUTHORITY_REQUIRED",
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_SOURCE_AGE_DAYS = 60
AUTHORITY_KEYS = (
    "external_send_authorized", "prime_participation_claimed", "buyer_acceptance_claimed",
    "bid_submission_authorized", "contract_signed", "charge_authorized", "payment_received",
    "revenue_recognized",
)
INTERFACE_CHECKS = ("roundtrip_status", "retry_idempotency_status", "rollback_status", "duplicate_effect_status")
CUTOVER_CHECKS = ("preflight_status", "dry_run_status", "reconciliation_status", "rollback_test_status", "restart_test_status")

class ContractError(ValueError):
    pass

def _no_dupes(pairs: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out

def load_json(path: str | os.PathLike[str]) -> Dict[str, Any]:
    def bad_constant(value: str) -> None:
        raise ContractError(f"non-finite JSON number: {value}")
    with open(path, "r", encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=_no_dupes, parse_constant=bad_constant)
    if not isinstance(value, dict):
        raise ContractError("top-level JSON value must be an object")
    return value

def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()

def parse_time(value: Any, field: str) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{field} must be a non-empty RFC3339 timestamp")
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ContractError(f"{field} is not valid RFC3339") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{field} must include a timezone")
    return parsed.astimezone(dt.timezone.utc)

def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)

def fmt_time(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")

def require_exact_keys(obj: Mapping[str, Any], required: Iterable[str], optional: Iterable[str], field: str) -> None:
    required_set, optional_set = set(required), set(optional)
    keys = set(obj)
    missing = sorted(required_set - keys)
    extra = sorted(keys - required_set - optional_set)
    if missing:
        raise ContractError(f"{field} missing keys: {', '.join(missing)}")
    if extra:
        raise ContractError(f"{field} unknown keys: {', '.join(extra)}")

def text(value: Any, field: str, *, max_len: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be non-empty text")
    value = value.strip()
    if len(value) > max_len:
        raise ContractError(f"{field} is too long")
    return value

def hex64(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise ContractError(f"{field} must be lowercase sha256 hex")
    return value

def nonneg_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{field} must be a non-negative integer")
    return value

def pos_int(value: Any, field: str) -> int:
    value = nonneg_int(value, field)
    if value == 0:
        raise ContractError(f"{field} must be positive")
    return value

def unique_text_list(value: Any, field: str, *, min_items: int = 1) -> List[str]:
    if not isinstance(value, list) or len(value) < min_items:
        raise ContractError(f"{field} must contain at least {min_items} item(s)")
    vals = [text(item, f"{field}[]", max_len=500) for item in value]
    if len(vals) != len(set(vals)):
        raise ContractError(f"{field} contains duplicates")
    return vals

def _validate_packet_shape(packet: Mapping[str, Any]) -> None:
    require_exact_keys(packet, ("schema", "opportunity", "workshare", "migration", "interfaces", "cutover", "authority"), (), "packet")
    if packet["schema"] != INPUT_SCHEMA:
        raise ContractError(f"schema must be {INPUT_SCHEMA}")
    opp = packet["opportunity"]
    if not isinstance(opp, dict): raise ContractError("opportunity must be an object")
    require_exact_keys(opp, ("opportunity_id", "buyer", "solicitation_id", "title", "deadline", "source"), (), "opportunity")
    for key in ("opportunity_id", "buyer", "solicitation_id", "title"): text(opp[key], f"opportunity.{key}")
    source = opp["source"]
    if not isinstance(source, dict): raise ContractError("opportunity.source must be an object")
    require_exact_keys(source, ("source_ref", "source_sha256", "source_kind", "observed_at"), (), "opportunity.source")
    text(source["source_ref"], "opportunity.source.source_ref", max_len=1000)
    hex64(source["source_sha256"], "opportunity.source.source_sha256")
    text(source["source_kind"], "opportunity.source.source_kind")
    parse_time(source["observed_at"], "opportunity.source.observed_at")
    parse_time(opp["deadline"], "opportunity.deadline")
    ws = packet["workshare"]
    if not isinstance(ws, dict): raise ContractError("workshare must be an object")
    require_exact_keys(ws, ("status", "currency", "amount_cents", "duration_business_days", "deliverables", "acceptance_criteria", "scope_exclusions"), (), "workshare")
    if ws["status"] != PROPOSED: raise ContractError(f"workshare.status must be {PROPOSED}")
    currency = text(ws["currency"], "workshare.currency", max_len=3)
    if currency != currency.upper() or len(currency) != 3: raise ContractError("workshare.currency must be a 3-letter uppercase code")
    pos_int(ws["amount_cents"], "workshare.amount_cents")
    pos_int(ws["duration_business_days"], "workshare.duration_business_days")
    unique_text_list(ws["deliverables"], "workshare.deliverables", min_items=2)
    unique_text_list(ws["acceptance_criteria"], "workshare.acceptance_criteria", min_items=2)
    unique_text_list(ws["scope_exclusions"], "workshare.scope_exclusions", min_items=1)
    migration = packet["migration"]
    if not isinstance(migration, dict): raise ContractError("migration must be an object")
    require_exact_keys(migration, ("datasets", "required_interface_ids"), (), "migration")
    if not isinstance(migration["datasets"], list) or not migration["datasets"]: raise ContractError("migration.datasets must be a non-empty list")
    unique_text_list(migration["required_interface_ids"], "migration.required_interface_ids", min_items=1)
    seen_datasets = set()
    for idx, dataset in enumerate(migration["datasets"]):
        if not isinstance(dataset, dict): raise ContractError(f"migration.datasets[{idx}] must be an object")
        require_exact_keys(dataset, ("dataset_id", "source_rows", "target_rows", "source_key_digest", "target_key_digest", "source_control_total_microunits", "target_control_total_microunits", "duplicate_key_count", "missing_key_count", "unexpected_key_count", "rejected_row_count", "transform_spec_sha256"), (), f"migration.datasets[{idx}]")
        did = text(dataset["dataset_id"], f"migration.datasets[{idx}].dataset_id")
        if did in seen_datasets: raise ContractError(f"duplicate dataset_id: {did}")
        seen_datasets.add(did)
        for key in ("source_rows", "target_rows", "duplicate_key_count", "missing_key_count", "unexpected_key_count", "rejected_row_count"):
            nonneg_int(dataset[key], f"migration.datasets[{idx}].{key}")
        for key in ("source_control_total_microunits", "target_control_total_microunits"):
            if isinstance(dataset[key], bool) or not isinstance(dataset[key], int): raise ContractError(f"migration.datasets[{idx}].{key} must be an integer")
        for key in ("source_key_digest", "target_key_digest", "transform_spec_sha256"):
            hex64(dataset[key], f"migration.datasets[{idx}].{key}")
    interfaces = packet["interfaces"]
    if not isinstance(interfaces, list): raise ContractError("interfaces must be a list")
    seen_interfaces = set()
    for idx, interface in enumerate(interfaces):
        if not isinstance(interface, dict): raise ContractError(f"interfaces[{idx}] must be an object")
        require_exact_keys(interface, ("interface_id", "direction", "source_system", "target_system", "contract_sha256", "test_receipt_sha256", *INTERFACE_CHECKS), (), f"interfaces[{idx}]")
        iid = text(interface["interface_id"], f"interfaces[{idx}].interface_id")
        if iid in seen_interfaces: raise ContractError(f"duplicate interface_id: {iid}")
        seen_interfaces.add(iid)
        if text(interface["direction"], f"interfaces[{idx}].direction") not in {"INBOUND", "OUTBOUND", "BIDIRECTIONAL"}: raise ContractError(f"interfaces[{idx}].direction invalid")
        text(interface["source_system"], f"interfaces[{idx}].source_system")
        text(interface["target_system"], f"interfaces[{idx}].target_system")
        hex64(interface["contract_sha256"], f"interfaces[{idx}].contract_sha256")
        hex64(interface["test_receipt_sha256"], f"interfaces[{idx}].test_receipt_sha256")
        for check in INTERFACE_CHECKS:
            if text(interface[check], f"interfaces[{idx}].{check}", max_len=8) not in {"PASS", "FAIL", "MISSING"}: raise ContractError(f"interfaces[{idx}].{check} invalid")
    cutover = packet["cutover"]
    if not isinstance(cutover, dict): raise ContractError("cutover must be an object")
    require_exact_keys(cutover, ("dry_run_id", "baseline_sha256", "post_run_sha256", "rollback_receipt_sha256", *CUTOVER_CHECKS), (), "cutover")
    text(cutover["dry_run_id"], "cutover.dry_run_id")
    for key in ("baseline_sha256", "post_run_sha256", "rollback_receipt_sha256"): hex64(cutover[key], f"cutover.{key}")
    for check in CUTOVER_CHECKS:
        if text(cutover[check], f"cutover.{check}", max_len=8) not in {"PASS", "FAIL", "MISSING"}: raise ContractError(f"cutover.{check} invalid")
    authority = packet["authority"]
    if not isinstance(authority, dict): raise ContractError("authority must be an object")
    require_exact_keys(authority, AUTHORITY_KEYS, (), "authority")
    for key in AUTHORITY_KEYS:
        if not isinstance(authority[key], bool): raise ContractError(f"authority.{key} must be boolean")

def evaluate(packet: Mapping[str, Any], *, trusted_as_of: dt.datetime | None = None) -> Dict[str, Any]:
    _validate_packet_shape(packet)
    as_of = trusted_as_of or now_utc()
    if as_of.tzinfo is None: raise ContractError("trusted_as_of must be timezone-aware")
    as_of = as_of.astimezone(dt.timezone.utc)
    blockers: List[str] = []
    opp, source = packet["opportunity"], packet["opportunity"]["source"]
    observed = parse_time(source["observed_at"], "opportunity.source.observed_at")
    deadline = parse_time(opp["deadline"], "opportunity.deadline")
    if observed > as_of: blockers.append("SOURCE_OBSERVED_IN_FUTURE")
    elif as_of - observed > dt.timedelta(days=MAX_SOURCE_AGE_DAYS): blockers.append("SOURCE_STALE")
    if as_of >= deadline: blockers.append("DEADLINE_CLOSED")
    migration_failures: List[str] = []
    for dataset in packet["migration"]["datasets"]:
        did = dataset["dataset_id"]
        if dataset["source_rows"] != dataset["target_rows"]: migration_failures.append(f"{did}:ROW_COUNT")
        if dataset["source_key_digest"] != dataset["target_key_digest"]: migration_failures.append(f"{did}:KEY_SET")
        if dataset["source_control_total_microunits"] != dataset["target_control_total_microunits"]: migration_failures.append(f"{did}:CONTROL_TOTAL")
        for key, suffix in (("duplicate_key_count", "DUPLICATE_KEYS"), ("missing_key_count", "MISSING_KEYS"), ("unexpected_key_count", "UNEXPECTED_KEYS"), ("rejected_row_count", "REJECTED_ROWS")):
            if dataset[key] != 0: migration_failures.append(f"{did}:{suffix}")
    if migration_failures: blockers.append("MIGRATION_RECONCILIATION_FAILED")
    by_interface = {item["interface_id"]: item for item in packet["interfaces"]}
    interface_failures: List[str] = []
    for iid in packet["migration"]["required_interface_ids"]:
        item = by_interface.get(iid)
        if item is None:
            interface_failures.append(f"{iid}:MISSING_INTERFACE")
            continue
        for name in INTERFACE_CHECKS:
            if item[name] != "PASS": interface_failures.append(f"{iid}:{name}")
    if interface_failures: blockers.append("INTERFACE_EVIDENCE_INCOMPLETE")
    cutover_failures = [name for name in CUTOVER_CHECKS if packet["cutover"][name] != "PASS"]
    if cutover_failures: blockers.append("CUTOVER_EVIDENCE_INCOMPLETE")
    authority_true = [key for key in AUTHORITY_KEYS if packet["authority"][key] is True]
    if authority_true: blockers.append("AUTHORITY_ESCALATION_REFUSED")
    evidence_state = EVIDENCE_CONSISTENT if not blockers else EVIDENCE_HOLD
    # Candidate bytes are never current authority.  Until a separately authenticated
    # host/provider adapter exists, all three independent roots remain mandatory.
    blockers.extend(INDEPENDENT_AUTHORITY_BLOCKERS)
    return {
        "state": "HOLD",
        "evidence_state": evidence_state,
        "blockers": sorted(blockers),
        "migration_failures": sorted(migration_failures),
        "interface_failures": sorted(interface_failures),
        "cutover_failures": sorted(cutover_failures),
        "authority_true": sorted(authority_true),
        "metrics": {
            "dataset_count": len(packet["migration"]["datasets"]),
            "source_rows": sum(item["source_rows"] for item in packet["migration"]["datasets"]),
            "target_rows": sum(item["target_rows"] for item in packet["migration"]["datasets"]),
            "required_interface_count": len(packet["migration"]["required_interface_ids"]),
            "verified_required_interface_count": sum(1 for iid in packet["migration"]["required_interface_ids"] if iid in by_interface and all(by_interface[iid][name] == "PASS" for name in INTERFACE_CHECKS)),
        },
        "evaluated_at": fmt_time(as_of), "deadline": fmt_time(deadline), "source_observed_at": fmt_time(observed),
    }

def build_authority_challenge(packet: Mapping[str, Any]) -> Dict[str, Any]:
    """Bind what an independent authority must attest without treating it as attested."""
    _validate_packet_shape(packet)
    opp = packet["opportunity"]
    request: Dict[str, Any] = {
        "status": "INDEPENDENT_ATTESTATION_REQUIRED",
        "opportunity_id": opp["opportunity_id"],
        "source_binding_sha256": sha256_value({
            "opportunity_id": opp["opportunity_id"],
            "solicitation_id": opp["solicitation_id"],
            "deadline": opp["deadline"],
            "source": opp["source"],
        }),
        "requirements_binding_sha256": sha256_value({
            "dataset_ids": sorted(item["dataset_id"] for item in packet["migration"]["datasets"]),
            "required_interface_ids": sorted(packet["migration"]["required_interface_ids"]),
        }),
        "evidence_binding_sha256": sha256_value({
            "datasets": packet["migration"]["datasets"],
            "interfaces": packet["interfaces"],
            "cutover": packet["cutover"],
        }),
        "commercial_binding_sha256": sha256_value(packet["workshare"]),
        "required_independent_authorities": [
            "source_currentness_and_identity",
            "requirements_and_completeness_universe",
            "evidence_artifact_authenticity",
        ],
    }
    request["challenge_sha256"] = sha256_value(request)
    return request

def compile_receipt(packet: Mapping[str, Any], *, trusted_as_of: dt.datetime | None = None) -> Dict[str, Any]:
    _validate_packet_shape(packet)
    decision = evaluate(packet, trusted_as_of=trusted_as_of)
    opp, ws = packet["opportunity"], packet["workshare"]
    receipt: Dict[str, Any] = {
        "schema": RECEIPT_SCHEMA, "opportunity_id": opp["opportunity_id"], "solicitation_id": opp["solicitation_id"], "buyer": opp["buyer"],
        "input_sha256": sha256_value(packet), "source": copy.deepcopy(opp["source"]), "compiled_at": decision["evaluated_at"], "deadline": decision["deadline"],
        "state": decision["state"], "evidence_state": decision["evidence_state"], "blockers": decision["blockers"], "migration_failures": decision["migration_failures"], "interface_failures": decision["interface_failures"],
        "cutover_failures": decision["cutover_failures"], "metrics": decision["metrics"], "authority_challenge": build_authority_challenge(packet),
        "workshare": {"status": PROPOSED, "currency": ws["currency"], "amount_cents": ws["amount_cents"], "duration_business_days": ws["duration_business_days"], "deliverables": list(ws["deliverables"]), "acceptance_criteria": list(ws["acceptance_criteria"]), "scope_exclusions": list(ws["scope_exclusions"])},
        "authority": {key: False for key in AUTHORITY_KEYS},
    }
    receipt["receipt_sha256"] = sha256_value(receipt)
    return receipt

def verify_receipt(packet: Mapping[str, Any], receipt: Mapping[str, Any], *, trusted_as_of: dt.datetime | None = None) -> Dict[str, Any]:
    if not isinstance(receipt, dict): raise ContractError("receipt must be an object")
    expected = {"schema", "opportunity_id", "solicitation_id", "buyer", "input_sha256", "source", "compiled_at", "deadline", "state", "evidence_state", "blockers", "migration_failures", "interface_failures", "cutover_failures", "metrics", "authority_challenge", "workshare", "authority", "receipt_sha256"}
    if set(receipt) != expected: raise ContractError("receipt keys do not match receipt contract")
    if receipt["schema"] != RECEIPT_SCHEMA: raise ContractError("receipt schema mismatch")
    digest = hex64(receipt["receipt_sha256"], "receipt.receipt_sha256")
    unsigned = dict(receipt); unsigned.pop("receipt_sha256")
    if sha256_value(unsigned) != digest: raise ContractError("receipt digest mismatch")
    if receipt["input_sha256"] != sha256_value(packet): raise ContractError("receipt is not bound to this packet")
    historical_time = parse_time(receipt["compiled_at"], "receipt.compiled_at")
    if compile_receipt(packet, trusted_as_of=historical_time) != receipt: raise ContractError("receipt does not replay to retained historical decision")
    current = evaluate(packet, trusted_as_of=trusted_as_of)
    return {"schema": VERIFY_SCHEMA, "receipt_sha256": digest, "historical_state": receipt["state"], "current_state": current["state"], "current_blockers": current["blockers"], "verified_at": current["evaluated_at"], "historical_receipt_valid": True, "external_action_authorized": False}

def render_markdown(packet: Mapping[str, Any], receipt: Mapping[str, Any]) -> str:
    verify_receipt(packet, receipt, trusted_as_of=parse_time(receipt["compiled_at"], "receipt.compiled_at"))
    ws, m = receipt["workshare"], receipt["metrics"]
    lines = [f"# {receipt['solicitation_id']} migration-evidence workshare", "", f"**Buyer:** {receipt['buyer']}", f"**Current authority state:** `{receipt['state']}`", f"**Self-asserted evidence state:** `{receipt['evidence_state']}`", f"**Paid scope:** {ws['amount_cents']/100:,.2f} {ws['currency']} / {ws['duration_business_days']} business days / `{ws['status']}`", f"**Receipt:** `{receipt['receipt_sha256']}`", "", "## Deliverables"]
    lines += [f"- {item}" for item in ws["deliverables"]]
    lines += ["", "## Acceptance criteria"] + [f"- {item}" for item in ws["acceptance_criteria"]]
    lines += ["", "## Scope exclusions"] + [f"- {item}" for item in ws["scope_exclusions"]]
    lines += ["", "## Evidence summary", f"- Dataset rows reconciled: {m['target_rows']} target / {m['source_rows']} source", f"- Required interfaces verified: {m['verified_required_interface_count']} / {m['required_interface_count']}"]
    if receipt["blockers"]: lines += ["", "## Holds"] + [f"- `{item}`" for item in receipt["blockers"]]
    challenge = receipt["authority_challenge"]
    lines += ["", "## Independent authority challenge", f"- Challenge: `{challenge['challenge_sha256']}`", f"- Source binding: `{challenge['source_binding_sha256']}`", f"- Requirements binding: `{challenge['requirements_binding_sha256']}`", f"- Evidence binding: `{challenge['evidence_binding_sha256']}`"]
    lines += ["", "## Authority boundary", "Candidate packet bytes cannot authorize READY in this carrier. Independent source, requirements/completeness, and evidence-artifact authority must be established outside this packet. This packet is internal evidence history only; it does not authorize outreach, represent a prime's participation, submit a bid, sign a contract, charge a customer, claim payment, or recognize revenue.", ""]
    return "\n".join(lines)

def write_exclusive(path: str | os.PathLike[str], data: bytes) -> None:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "xb") as handle:
        handle.write(data); handle.flush(); os.fsync(handle.fileno())

def _cmd_compile(args: argparse.Namespace) -> int:
    packet=load_json(args.input); receipt=compile_receipt(packet); write_exclusive(args.output, canonical_bytes(receipt)+b"\n")
    print(json.dumps({"state":receipt["state"],"receipt_sha256":receipt["receipt_sha256"]},sort_keys=True)); return 0 if receipt["state"]==READY else 2

def _cmd_verify(args: argparse.Namespace) -> int:
    result=verify_receipt(load_json(args.input), load_json(args.receipt)); print(json.dumps(result,sort_keys=True)); return 0 if result["current_state"]==READY else 2

def _cmd_render(args: argparse.Namespace) -> int:
    packet=load_json(args.input); receipt=load_json(args.receipt); write_exclusive(args.output, render_markdown(packet,receipt).encode()); print(json.dumps({"rendered":args.output,"receipt_sha256":receipt["receipt_sha256"]},sort_keys=True)); return 0

def build_parser() -> argparse.ArgumentParser:
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("compile"); p.add_argument("input"); p.add_argument("output"); p.set_defaults(func=_cmd_compile)
    p=sub.add_parser("verify"); p.add_argument("input"); p.add_argument("receipt"); p.set_defaults(func=_cmd_verify)
    p=sub.add_parser("render"); p.add_argument("input"); p.add_argument("receipt"); p.add_argument("output"); p.set_defaults(func=_cmd_render)
    return parser

def main(argv: List[str] | None=None) -> int:
    args=build_parser().parse_args(argv); return args.func(args)
if __name__ == "__main__": raise SystemExit(main())
