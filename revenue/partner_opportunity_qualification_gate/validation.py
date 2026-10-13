from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

SCHEMA = "partner-opportunity-qualification-input/v1"
PHASES = {"PRE_OUTREACH", "PRE_SUBMISSION", "PRE_AWARD"}
GATE_STATES = {"SATISFIED", "UNSATISFIED", "UNKNOWN"}
REG_STATES = {"NOT_REQUIRED", "OPEN", "COMPLETE", "CLOSED", "UNKNOWN"}
SOURCE_KINDS = {"SOLICITATION_CONTROL", "PARTNER_EVIDENCE", "REGISTRATION_EVIDENCE", "OWNER_WORKSHARE_EVIDENCE"}
SOURCE_STATES = {"CURRENT", "STALE", "UNKNOWN"}
GATE_EVIDENCE_KINDS = {"PARTNER_EVIDENCE", "REGISTRATION_EVIDENCE"}
PARTNER_SOURCE_KINDS = GATE_EVIDENCE_KINDS


class QualificationError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise QualificationError("value is not canonical-JSON encodable") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_strict_json_text(text_value: str) -> dict[str, Any]:
    def pairs(rows):
        out = {}
        for key, value in rows:
            if key in out:
                raise QualificationError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    def bad(value):
        raise QualificationError(f"non-finite JSON number: {value}")

    try:
        value = json.loads(text_value, object_pairs_hook=pairs, parse_constant=bad)
    except QualificationError:
        raise
    except (TypeError, ValueError) as exc:
        raise QualificationError("invalid JSON") from exc
    if type(value) is not dict:
        raise QualificationError("top-level JSON must be an object")
    return value


def _obj(value: Any, field: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise QualificationError(f"{field} must be an object")
    return value


def _arr(value: Any, field: str) -> list[Any]:
    if type(value) is not list:
        raise QualificationError(f"{field} must be an array")
    return value


def _text(value: Any, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise QualificationError(f"{field} must be a non-empty trimmed string")
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise QualificationError(f"{field} contains a surrogate code point")
    return value


def _integer(value: Any, field: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise QualificationError(f"{field} must be an integer >= {minimum}")
    return value


def _date(value: Any, field: str) -> str:
    text_value = _text(value, field)
    try:
        parsed = date.fromisoformat(text_value)
    except ValueError as exc:
        raise QualificationError(f"{field} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != text_value:
        raise QualificationError(f"{field} must be canonical YYYY-MM-DD")
    return text_value


def _sha(value: Any, field: str) -> str:
    value = _text(value, field).lower()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise QualificationError(f"{field} must be lowercase SHA-256")
    return value


def _url(value: Any, field: str) -> str:
    value = _text(value, field)
    if not value.startswith(("https://", "http://")):
        raise QualificationError(f"{field} must be http(s)")
    return value


def _shape(obj: dict[str, Any], field: str, allowed: set[str], required: set[str] | None = None) -> None:
    extra = set(obj) - allowed
    missing = (required or set()) - set(obj)
    if extra:
        raise QualificationError(f"{field} has unknown keys: {sorted(extra)}")
    if missing:
        raise QualificationError(f"{field} missing keys: {sorted(missing)}")


def _source(raw: Any, field: str) -> dict[str, Any]:
    obj = _obj(raw, field)
    keys = {"source_id", "kind", "status", "url", "sha256", "observed_on", "subject_partner"}
    _shape(obj, field, keys, keys)
    kind, status = _text(obj["kind"], f"{field}.kind"), _text(obj["status"], f"{field}.status")
    if kind not in SOURCE_KINDS or status not in SOURCE_STATES:
        raise QualificationError(f"{field} kind/status invalid")
    if kind in PARTNER_SOURCE_KINDS:
        subject_partner = _text(obj["subject_partner"], f"{field}.subject_partner")
    else:
        if obj["subject_partner"] is not None:
            raise QualificationError(f"{field}.subject_partner must be null for {kind}")
        subject_partner = None
    return {
        "source_id": _text(obj["source_id"], f"{field}.source_id"),
        "kind": kind,
        "status": status,
        "url": _url(obj["url"], f"{field}.url"),
        "sha256": _sha(obj["sha256"], f"{field}.sha256"),
        "observed_on": _date(obj["observed_on"], f"{field}.observed_on"),
        "subject_partner": subject_partner,
    }


def _refs(raw: Any, field: str, sources: dict[str, dict[str, Any]], required: bool = False) -> list[dict[str, str]]:
    out = []
    for i, row in enumerate(_arr(raw, field)):
        obj = _obj(row, f"{field}[{i}]")
        keys = {"source_id", "source_sha256"}
        _shape(obj, f"{field}[{i}]", keys, keys)
        sid = _text(obj["source_id"], f"{field}[{i}].source_id")
        sha = _sha(obj["source_sha256"], f"{field}[{i}].source_sha256")
        if sid not in sources or sources[sid]["sha256"] != sha:
            raise QualificationError(f"{field}[{i}] source identity/digest mismatch")
        out.append({"source_id": sid, "source_sha256": sha})
    identity = [(x["source_id"], x["source_sha256"]) for x in out]
    if len(identity) != len(set(identity)):
        raise QualificationError(f"{field} contains duplicate source references")
    if required and not out:
        raise QualificationError(f"{field} must contain evidence")
    return sorted(out, key=lambda x: (x["source_id"], x["source_sha256"]))


def _gate(raw: Any, field: str, sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    obj = _obj(raw, field)
    keys = {"gate_id", "label", "phase", "requirement", "required_evidence_kind", "source_refs"}
    _shape(obj, field, keys, keys)
    phase = _text(obj["phase"], f"{field}.phase")
    if phase not in PHASES:
        raise QualificationError(f"{field}.phase invalid")
    required_evidence_kind = _text(obj["required_evidence_kind"], f"{field}.required_evidence_kind")
    if required_evidence_kind not in GATE_EVIDENCE_KINDS:
        raise QualificationError(
            f"{field}.required_evidence_kind must be PARTNER_EVIDENCE or REGISTRATION_EVIDENCE"
        )
    refs = _refs(obj["source_refs"], f"{field}.source_refs", sources, True)
    if not any(sources[r["source_id"]]["kind"] == "SOLICITATION_CONTROL" for r in refs):
        raise QualificationError(f"{field} must bind solicitation-control evidence")
    return {
        "gate_id": _text(obj["gate_id"], f"{field}.gate_id"),
        "label": _text(obj["label"], f"{field}.label"),
        "phase": phase,
        "requirement": _text(obj["requirement"], f"{field}.requirement"),
        "required_evidence_kind": required_evidence_kind,
        "source_refs": refs,
    }


def _registration(
    raw: Any,
    field: str,
    sources: dict[str, dict[str, Any]],
    partner_name: str,
) -> dict[str, Any]:
    obj = _obj(raw, field)
    keys = {"state", "deadline", "requirement_refs", "evidence_refs"}
    _shape(obj, field, keys, {"state", "requirement_refs", "evidence_refs"})
    state = _text(obj["state"], f"{field}.state")
    if state not in REG_STATES:
        raise QualificationError(f"{field}.state invalid")
    req = _refs(obj["requirement_refs"], f"{field}.requirement_refs", sources, state != "UNKNOWN")
    evidence = _refs(obj["evidence_refs"], f"{field}.evidence_refs", sources, state == "COMPLETE")
    if state == "UNKNOWN" and (req or evidence):
        raise QualificationError(f"{field}.UNKNOWN cannot claim evidence")
    if state != "UNKNOWN" and not any(sources[r["source_id"]]["kind"] == "SOLICITATION_CONTROL" for r in req):
        raise QualificationError(f"{field} requirement must bind solicitation control")
    if any(
        sources[r["source_id"]]["kind"] != "REGISTRATION_EVIDENCE"
        or sources[r["source_id"]]["subject_partner"] != partner_name
        for r in evidence
    ):
        raise QualificationError(
            f"{field}.evidence_refs may contain only REGISTRATION_EVIDENCE "
            f"bound to partner {partner_name}"
        )
    return {
        "state": state,
        "deadline": None if obj.get("deadline") is None else _date(obj["deadline"], f"{field}.deadline"),
        "requirement_refs": req,
        "evidence_refs": evidence,
    }


def _workshare(raw: Any, field: str) -> dict[str, Any]:
    obj = _obj(raw, field)
    state = _text(obj.get("state"), f"{field}.state")
    if state == "UNDEFINED":
        _shape(obj, field, {"state"}, {"state"})
        return {"state": state}
    if state != "DEFINED":
        raise QualificationError(f"{field}.state invalid")
    keys = {"state", "fixed_fee_minor", "currency", "scope", "acceptance_criteria", "exclusions"}
    _shape(obj, field, keys, keys)
    currency = _text(obj["currency"], f"{field}.currency")
    if len(currency) != 3 or not currency.isalpha() or currency != currency.upper():
        raise QualificationError(f"{field}.currency invalid")
    acceptance = [_text(v, f"{field}.acceptance_criteria[{i}]") for i, v in enumerate(_arr(obj["acceptance_criteria"], f"{field}.acceptance_criteria"))]
    if not acceptance:
        raise QualificationError(f"{field}.acceptance_criteria must not be empty")
    return {
        "state": state,
        "fixed_fee_minor": _integer(obj["fixed_fee_minor"], f"{field}.fixed_fee_minor", 1),
        "currency": currency,
        "scope": _text(obj["scope"], f"{field}.scope"),
        "acceptance_criteria": acceptance,
        "exclusions": [_text(v, f"{field}.exclusions[{i}]") for i, v in enumerate(_arr(obj["exclusions"], f"{field}.exclusions"))],
    }


def _disposition(
    raw: Any,
    field: str,
    sources: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
    partner_name: str,
) -> dict[str, Any]:
    obj = _obj(raw, field)
    keys = {"gate_id", "state", "evidence_refs", "note"}
    _shape(obj, field, keys, {"gate_id", "state", "evidence_refs"})
    gid, state = _text(obj["gate_id"], f"{field}.gate_id"), _text(obj["state"], f"{field}.state")
    gate = gates.get(gid)
    if gate is None or state not in GATE_STATES:
        raise QualificationError(f"{field} gate/state invalid")
    refs = _refs(obj["evidence_refs"], f"{field}.evidence_refs", sources, state != "UNKNOWN")
    if state == "UNKNOWN" and refs:
        raise QualificationError(f"{field}.UNKNOWN cannot claim evidence")
    if state != "UNKNOWN":
        gate_sources = {
            (ref["source_id"], ref["source_sha256"])
            for ref in gate["source_refs"]
        }
        for ref in refs:
            identity = (ref["source_id"], ref["source_sha256"])
            source = sources[ref["source_id"]]
            if identity not in gate_sources:
                raise QualificationError(
                    f"{field}.{state} evidence must be explicitly bound in gate {gid} source_refs"
                )
            if (
                source["kind"] != gate["required_evidence_kind"]
                or source["subject_partner"] != partner_name
            ):
                raise QualificationError(
                    f"{field}.{state} evidence must be only {gate['required_evidence_kind']} "
                    f"bound to partner {partner_name} for gate {gid}"
                )
    return {
        "gate_id": gid,
        "state": state,
        "evidence_refs": refs,
        "note": None if obj.get("note") is None else _text(obj["note"], f"{field}.note"),
    }


def normalize_input(raw: Any) -> dict[str, Any]:
    doc = _obj(raw, "input")
    keys = {"schema", "as_of", "opportunity_id", "runway_input", "sources", "hard_gates", "partners"}
    _shape(doc, "input", keys, keys)
    if doc["schema"] != SCHEMA:
        raise QualificationError(f"schema must be {SCHEMA}")
    as_of, oid = _date(doc["as_of"], "as_of"), _text(doc["opportunity_id"], "opportunity_id")
    runway_input = _obj(doc["runway_input"], "runway_input")
    opps = runway_input.get("opportunities")
    if type(opps) is not list or len(opps) != 1 or opps[0].get("id") != oid or runway_input.get("as_of") != as_of:
        raise QualificationError("runway_input must contain the same as_of and exactly one matching opportunity")

    source_rows = [_source(v, f"sources[{i}]") for i, v in enumerate(_arr(doc["sources"], "sources"))]
    if not source_rows:
        raise QualificationError("sources must not be empty")
    if len({s["source_id"] for s in source_rows}) != len(source_rows):
        raise QualificationError("duplicate source_id")
    if any(s["observed_on"] > as_of for s in source_rows):
        raise QualificationError("source observed_on cannot be after as_of")
    identities = [(s["url"], s["sha256"]) for s in source_rows]
    if len(identities) != len(set(identities)):
        raise QualificationError("duplicate source URL/digest identity")
    sha_scopes: dict[str, tuple[str, str | None]] = {}
    url_scopes: dict[str, tuple[str, str | None]] = {}
    for source in source_rows:
        scope = (source["kind"], source["subject_partner"])
        prior_sha_scope = sha_scopes.setdefault(source["sha256"], scope)
        prior_url_scope = url_scopes.setdefault(source["url"], scope)
        if prior_sha_scope != scope or prior_url_scope != scope:
            raise QualificationError(
                "source bytes/URL cannot be relabeled across evidence kind or partner subject"
            )
    sources = {s["source_id"]: s for s in source_rows}

    raw_partners = _arr(doc["partners"], "partners")
    partner_names = [
        _text(_obj(raw_partner, f"partners[{i}]").get("name"), f"partners[{i}].name")
        for i, raw_partner in enumerate(raw_partners)
    ]
    if not partner_names or len({name.casefold() for name in partner_names}) != len(partner_names):
        raise QualificationError("partners must be non-empty with unique names")
    partner_name_set = set(partner_names)
    if any(
        source["subject_partner"] is not None and source["subject_partner"] not in partner_name_set
        for source in source_rows
    ):
        raise QualificationError("partner-specific source subject must name a partner in this packet")

    gates = [_gate(v, f"hard_gates[{i}]", sources) for i, v in enumerate(_arr(doc["hard_gates"], "hard_gates"))]
    if not gates or len({g["gate_id"] for g in gates}) != len(gates):
        raise QualificationError("hard_gates must be non-empty with unique gate_id")
    gate_map = {g["gate_id"]: g for g in gates}
    gate_ids = set(gate_map)

    partners = []
    for i, raw_partner in enumerate(raw_partners):
        field, pobj = f"partners[{i}]", _obj(raw_partner, f"partners[{i}]")
        pkeys = {"name", "registration", "gate_dispositions", "paid_workshare"}
        _shape(pobj, field, pkeys, pkeys)
        partner_name = partner_names[i]
        dispositions = [
            _disposition(v, f"{field}.gate_dispositions[{j}]", sources, gate_map, partner_name)
            for j, v in enumerate(_arr(pobj["gate_dispositions"], f"{field}.gate_dispositions"))
        ]
        ids = [d["gate_id"] for d in dispositions]
        if len(ids) != len(set(ids)) or set(ids) != gate_ids:
            raise QualificationError(f"{field}.gate_dispositions must cover every hard gate exactly once")
        partners.append({
            "name": partner_name,
            "registration": _registration(
                pobj["registration"], f"{field}.registration", sources, partner_name
            ),
            "gate_dispositions": sorted(dispositions, key=lambda d: d["gate_id"]),
            "paid_workshare": _workshare(pobj["paid_workshare"], f"{field}.paid_workshare"),
        })
    return {
        "schema": SCHEMA,
        "as_of": as_of,
        "opportunity_id": oid,
        "runway_input": runway_input,
        "sources": sorted(source_rows, key=lambda s: s["source_id"]),
        "hard_gates": sorted(gates, key=lambda g: g["gate_id"]),
        "partners": sorted(partners, key=lambda p: (p["name"].casefold(), p["name"])),
    }
