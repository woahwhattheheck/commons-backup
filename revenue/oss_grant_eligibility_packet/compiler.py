"""Source-bound OSS grant packet readiness compiler.

PACKET_READY means the mechanical eligibility/artifact packet is complete against
one exact retained program-rule generation. It does not mean eligible, selected,
awarded, paid, or revenue-recognized. Subjective selector gates remain HOLD and
never become eligibility facts.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

INPUT_SCHEMA = "oss-grant-eligibility/input/v1"
REFERENCE_SCHEMA = "oss-grant-eligibility/reference-programs/v1"
PACKET_SCHEMA = "oss-grant-eligibility/packet/v1"
RECEIPT_SCHEMA = "oss-grant-eligibility/receipt/v1"
BOUNDARY = "DRAFT_OWNER_REVIEW_ONLY"
MAX_BYTES = 8 * 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,199}$")
TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$")
OPEN_STATES = {"OPEN", "ROLLING"}
RULE_SCOPES = {"ELIGIBILITY", "ARTIFACT", "SELECTOR"}
OPERATORS = {"BOOL_TRUE", "BOOL_FALSE", "INT_MIN", "INT_MAX", "INT_RANGE", "ENUM_IN", "TEXT_PRESENT", "SUBJECTIVE"}
GATE_STATUS = {"VERIFIED", "MISSING", "HOLD"}
REFERENCE_GENERATION_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


class GrantPacketError(ValueError):
    pass


def _bad_number(raw: str) -> Any:
    raise GrantPacketError(f"non-integer JSON number forbidden: {raw}")


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise GrantPacketError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load(raw: bytes, label="input") -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > MAX_BYTES:
        raise GrantPacketError(f"{label}: invalid byte length")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise GrantPacketError(f"{label}: BOM forbidden")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_pairs,
                           parse_float=_bad_number, parse_constant=_bad_number)
    except GrantPacketError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GrantPacketError(f"{label}: invalid JSON/UTF-8") from exc
    if type(value) is not dict:
        raise GrantPacketError(f"{label}: object required")
    return value


def canon(value: Any) -> bytes:
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                           allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise GrantPacketError("non-canonical value") from exc


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _keys(value: Any, expected, where: str):
    if type(value) is not dict or set(value) != set(expected):
        raise GrantPacketError(f"{where}: keys mismatch")
    return value


def _text(value: Any, where: str, limit=4096, token=False, empty=False):
    if type(value) is not str or (not empty and not value) or len(value) > limit:
        raise GrantPacketError(f"{where}: invalid string")
    if any(ord(ch) < 32 for ch in value):
        raise GrantPacketError(f"{where}: control character forbidden")
    if token and not TOKEN.fullmatch(value):
        raise GrantPacketError(f"{where}: invalid token")
    return value


def _sha256(value: Any, where: str):
    value = _text(value, where, limit=64)
    if not SHA256.fullmatch(value):
        raise GrantPacketError(f"{where}: sha256 required")
    return value


def _timestamp(value: Any, where: str):
    value = _text(value, where, limit=35)
    if not TS.fullmatch(value):
        raise GrantPacketError(f"{where}: RFC3339 timestamp required")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise GrantPacketError(f"{where}: RFC3339 timestamp required") from exc
    return value, dt.astimezone(timezone.utc)


def _int(value: Any, where: str, low=0, high=10**12):
    if type(value) is not int or not low <= value <= high:
        raise GrantPacketError(f"{where}: integer out of bounds")
    return value


def _value(value: Any, where: str):
    if value is None or type(value) in {str, bool, int}:
        if type(value) is str:
            _text(value, where, limit=4096, empty=True)
        return value
    if type(value) is list and len(value) <= 128:
        return [_value(item, where + "[]") for item in value]
    raise GrantPacketError(f"{where}: unsupported evidence value")


def _authority():
    return {
        "application_submission_authorized": False,
        "portal_or_form_mutation_authorized": False,
        "email_or_dm_authorized": False,
        "sponsor_contact_authorized": False,
        "muse_request_authorized": False,
        "signature_or_certification_authorized": False,
        "price_commitment_authorized": False,
        "eligibility_guaranteed": False,
        "selection_or_award_claim_authorized": False,
        "payment_or_cash_claim_authorized": False,
        "revenue_recognition_authorized": False,
    }


def _validate_references(refs: dict[str, Any], refs_raw: bytes):
    _keys(refs, ["schema", "truth_boundary", "generated_at", "route_map", "programs", "authority"], "references")
    if refs["schema"] != REFERENCE_SCHEMA or refs["truth_boundary"] != BOUNDARY:
        raise GrantPacketError("references: unsupported schema/boundary")
    _timestamp(refs["generated_at"], "references.generated_at")
    rm = refs["route_map"]
    _keys(rm, ["repository", "pr", "git_blob_sha1"], "references.route_map")
    _text(rm["repository"], "references.route_map.repository", token=True)
    _int(rm["pr"], "references.route_map.pr", 1)
    blob = _text(rm["git_blob_sha1"], "references.route_map.git_blob_sha1", limit=40)
    if not SHA1.fullmatch(blob):
        raise GrantPacketError("references.route_map.git_blob_sha1: git sha1 required")
    if type(refs["authority"]) is not dict or any(type(v) is not bool or v for v in refs["authority"].values()):
        raise GrantPacketError("references.authority must remain hard-false")
    if type(refs["programs"]) is not list or not refs["programs"]:
        raise GrantPacketError("references.programs: non-empty list required")
    programs = {}
    for idx, program in enumerate(refs["programs"]):
        where = f"references.programs[{idx}]"
        _keys(program, ["program_id", "program_name", "program_state", "route_map_source_id", "source_urls",
                        "observed_at", "source_facts", "source_factset_sha256", "source_conflicts",
                        "reference_value", "ai_drafting_policy", "prompts", "rules"], where)
        pid = _text(program["program_id"], where + ".program_id", token=True)
        if pid in programs:
            raise GrantPacketError("references.programs: duplicate program_id")
        _text(program["program_name"], where + ".program_name")
        state = _text(program["program_state"], where + ".program_state", token=True)
        if state not in {"OPEN", "ROLLING", "NOT_ACCEPTING", "CLOSED", "SOURCE_CONFLICT"}:
            raise GrantPacketError(f"{where}: unsupported program_state")
        _text(program["route_map_source_id"], where + ".route_map_source_id", token=True)
        if type(program["source_urls"]) is not list or not program["source_urls"]:
            raise GrantPacketError(f"{where}.source_urls: non-empty list required")
        for j, url in enumerate(program["source_urls"]):
            _text(url, f"{where}.source_urls[{j}]")
        _timestamp(program["observed_at"], where + ".observed_at")
        if type(program["source_facts"]) is not list or not all(type(x) is str and x for x in program["source_facts"]):
            raise GrantPacketError(f"{where}.source_facts invalid")
        fact_sha = _sha256(program["source_factset_sha256"], where + ".source_factset_sha256")
        if digest(canon(program["source_facts"])) != fact_sha:
            raise GrantPacketError(f"{where}: source factset digest mismatch")
        if type(program["source_conflicts"]) is not list or not all(type(x) is str and x for x in program["source_conflicts"]):
            raise GrantPacketError(f"{where}.source_conflicts invalid")
        if type(program["prompts"]) is not list or not all(type(x) is str and x for x in program["prompts"]):
            raise GrantPacketError(f"{where}.prompts invalid")
        if program["ai_drafting_policy"] not in {"DRAFT_OUTLINE_ALLOWED", "OWNER_AUTHORED_ONLY"}:
            raise GrantPacketError(f"{where}.ai_drafting_policy invalid")
        if program["reference_value"] is not None:
            rv = program["reference_value"]
            _keys(rv, ["kind", "currency", "amount_min", "amount_max", "truth"], where + ".reference_value")
            if rv["truth"] != "REFERENCE_ONLY_NOT_AWARD":
                raise GrantPacketError(f"{where}.reference_value truth boundary invalid")
            if rv["amount_min"] is not None: _int(rv["amount_min"], where + ".reference_value.amount_min")
            if rv["amount_max"] is not None: _int(rv["amount_max"], where + ".reference_value.amount_max")
        if type(program["rules"]) is not list or not program["rules"]:
            raise GrantPacketError(f"{where}.rules required")
        rule_ids = set()
        for r_idx, rule in enumerate(program["rules"]):
            rwhere = f"{where}.rules[{r_idx}]"
            _keys(rule, ["rule_id", "scope", "category", "operator", "evidence_key", "expected", "source_url", "fact"], rwhere)
            rid = _text(rule["rule_id"], rwhere + ".rule_id", token=True)
            if rid in rule_ids: raise GrantPacketError(f"{where}: duplicate rule_id")
            rule_ids.add(rid)
            if rule["scope"] not in RULE_SCOPES: raise GrantPacketError(f"{rwhere}.scope invalid")
            if rule["operator"] not in OPERATORS: raise GrantPacketError(f"{rwhere}.operator invalid")
            _text(rule["category"], rwhere + ".category", token=True)
            _text(rule["evidence_key"], rwhere + ".evidence_key", token=True)
            _value(rule["expected"], rwhere + ".expected")
            _text(rule["source_url"], rwhere + ".source_url")
            _text(rule["fact"], rwhere + ".fact")
        programs[pid] = program
    return programs, digest(canon(refs))


def _reference_currentness(refs: dict[str, Any], program: dict[str, Any], evaluated_dt: datetime):
    generated_at, generated_dt = _timestamp(refs["generated_at"], "references.generated_at")
    observed_at, observed_dt = _timestamp(program["observed_at"], "program.observed_at")
    generation_age = int((evaluated_dt - generated_dt).total_seconds())
    program_age = int((evaluated_dt - observed_dt).total_seconds())
    future = generation_age < 0 or program_age < 0
    stale = generation_age > REFERENCE_GENERATION_MAX_AGE_SECONDS or program_age > REFERENCE_GENERATION_MAX_AGE_SECONDS
    current = not future and not stale
    if future:
        reason = "REFERENCE_GENERATION_FUTURE"
    elif stale:
        reason = "REFERENCE_GENERATION_STALE"
    else:
        reason = "REFERENCE_GENERATION_CURRENT"
    return {
        "current": current,
        "reason": reason,
        "policy_max_age_seconds": REFERENCE_GENERATION_MAX_AGE_SECONDS,
        "reference_generated_at": generated_at,
        "reference_age_seconds": generation_age,
        "program_observed_at": observed_at,
        "program_age_seconds": program_age,
    }


def _evidence(doc: dict[str, Any], evaluated_dt: datetime, max_age: int):
    project = doc["project"]
    _keys(project, ["project_id", "repository_url", "evidence"], "input.project")
    _text(project["project_id"], "input.project.project_id", token=True)
    _text(project["repository_url"], "input.project.repository_url")
    if type(project["evidence"]) is not list:
        raise GrantPacketError("input.project.evidence: list required")
    grouped = {}
    ids = set()
    for idx, row in enumerate(project["evidence"]):
        where = f"input.project.evidence[{idx}]"
        _keys(row, ["evidence_id", "key", "value", "source_ref", "source_sha256", "observed_at", "authority"], where)
        eid = _text(row["evidence_id"], where + ".evidence_id", token=True)
        if eid in ids: raise GrantPacketError("input.project.evidence: duplicate evidence_id")
        ids.add(eid)
        key = _text(row["key"], where + ".key", token=True)
        value = _value(row["value"], where + ".value")
        _text(row["source_ref"], where + ".source_ref")
        _sha256(row["source_sha256"], where + ".source_sha256")
        observed, observed_dt = _timestamp(row["observed_at"], where + ".observed_at")
        authority = _text(row["authority"], where + ".authority", token=True)
        age = int((evaluated_dt - observed_dt).total_seconds())
        normalized = dict(row)
        normalized["observed_at"] = observed
        normalized["stale"] = age < 0 or age > max_age
        normalized["age_seconds"] = age
        grouped.setdefault(key, []).append(normalized)
    return project, grouped


def _evaluate(rule: dict[str, Any], rows):
    if rule["operator"] == "SUBJECTIVE":
        return "HOLD", "SUBJECTIVE_REVIEW_REQUIRED", []
    if not rows:
        return "MISSING", "PROJECT_EVIDENCE_MISSING", []
    if any(row["stale"] for row in rows):
        return "HOLD", "PROJECT_EVIDENCE_STALE_OR_FUTURE", sorted(row["evidence_id"] for row in rows)
    normalized_values = [json.dumps(row["value"], sort_keys=True, separators=(",", ":")) for row in rows]
    if len(set(normalized_values)) != 1:
        return "HOLD", "PROJECT_EVIDENCE_CONTRADICTORY", sorted(row["evidence_id"] for row in rows)
    value = rows[0]["value"]
    op = rule["operator"]
    expected = rule["expected"]
    ok = False
    if op == "BOOL_TRUE": ok = value is True
    elif op == "BOOL_FALSE": ok = value is False
    elif op == "INT_MIN": ok = type(value) is int and type(expected) is int and value >= expected
    elif op == "INT_MAX": ok = type(value) is int and type(expected) is int and value <= expected
    elif op == "INT_RANGE": ok = type(value) is int and type(expected) is list and len(expected) == 2 and all(type(x) is int for x in expected) and expected[0] <= value <= expected[1]
    elif op == "ENUM_IN": ok = value in expected if type(expected) is list else False
    elif op == "TEXT_PRESENT": ok = type(value) is str and bool(value.strip())
    if ok:
        return "VERIFIED", "MECHANICAL_RULE_SATISFIED", sorted(row["evidence_id"] for row in rows)
    return "HOLD", "MECHANICAL_RULE_NOT_SATISFIED", sorted(row["evidence_id"] for row in rows)


def compile_packet(reference_bytes: bytes, input_bytes: bytes):
    refs = load(reference_bytes, "references")
    programs, refs_sha = _validate_references(refs, reference_bytes)
    doc = load(input_bytes, "input")
    _keys(doc, ["schema", "truth_boundary", "evaluated_at", "project_evidence_max_age_seconds", "reference_programs_sha256", "route_map_git_blob_sha1", "program_id", "project"], "input")
    if doc["schema"] != INPUT_SCHEMA or doc["truth_boundary"] != BOUNDARY:
        raise GrantPacketError("input: unsupported schema/boundary")
    if _sha256(doc["reference_programs_sha256"], "input.reference_programs_sha256") != refs_sha:
        raise GrantPacketError("input: reference program bytes sha256 mismatch")
    if doc["route_map_git_blob_sha1"] != refs["route_map"]["git_blob_sha1"]:
        raise GrantPacketError("input: route-map generation mismatch")
    evaluated_at, evaluated_dt = _timestamp(doc["evaluated_at"], "input.evaluated_at")
    max_age = _int(doc["project_evidence_max_age_seconds"], "input.project_evidence_max_age_seconds", 1, 31536000)
    program_id = _text(doc["program_id"], "input.program_id", token=True)
    program = programs.get(program_id)
    if program is None:
        raise GrantPacketError("input.program_id: unknown program")
    reference_currentness = _reference_currentness(refs, program, evaluated_dt)
    project, grouped = _evidence(doc, evaluated_dt, max_age)

    gates = []
    for rule in sorted(program["rules"], key=lambda r: r["rule_id"]):
        status, reason, evidence_ids = _evaluate(rule, grouped.get(rule["evidence_key"], []))
        gates.append({
            "rule_id": rule["rule_id"], "scope": rule["scope"], "category": rule["category"],
            "status": status, "reason": reason, "evidence_key": rule["evidence_key"],
            "evidence_ids": evidence_ids, "source_url": rule["source_url"], "source_fact": rule["fact"],
        })

    mechanical = [g for g in gates if g["scope"] in {"ELIGIBILITY", "ARTIFACT"}]
    program_current = program["program_state"] in OPEN_STATES and not program["source_conflicts"] and reference_currentness["current"]
    if not program_current:
        packet_status = "HOLD_PROGRAM_CURRENTNESS"
    elif any(g["status"] == "HOLD" for g in mechanical):
        packet_status = "HOLD_SOURCE_CONFLICT"
    elif any(g["status"] == "MISSING" for g in mechanical):
        packet_status = "OWNER_FACTS_REQUIRED"
    else:
        packet_status = "PACKET_READY"

    missing = [{"rule_id": g["rule_id"], "scope": g["scope"], "reason": g["reason"]}
               for g in gates if g["status"] in {"MISSING", "HOLD"}]
    artifacts = [{"rule_id": g["rule_id"], "evidence_key": g["evidence_key"], "status": g["status"], "reason": g["reason"]}
                 for g in gates if g["scope"] == "ARTIFACT"]
    verified_keys = {g["evidence_key"] for g in gates if g["status"] == "VERIFIED"}
    outline_allowed = program["ai_drafting_policy"] == "DRAFT_OUTLINE_ALLOWED"
    outline = {
        "allowed": outline_allowed,
        "policy": program["ai_drafting_policy"],
        "prompts": [
            {"prompt": prompt, "verified_evidence_refs": sorted(row["evidence_id"] for row in project["evidence"] if row["key"] in verified_keys)}
            for prompt in program["prompts"]
        ] if outline_allowed else [],
        "owner_instruction": "OWNER MUST AUTHOR APPLICATION TEXT" if not outline_allowed else "DRAFT STRUCTURE ONLY; OWNER MUST REVIEW/WRITE FINAL APPLICATION",
    }
    packet = {
        "schema": PACKET_SCHEMA, "truth_boundary": BOUNDARY, "evaluated_at": evaluated_at,
        "status": packet_status,
        "project": {"project_id": project["project_id"], "repository_url": project["repository_url"]},
        "program": {
            "program_id": program_id, "program_name": program["program_name"], "program_state": program["program_state"],
            "route_map_source_id": program["route_map_source_id"], "source_urls": program["source_urls"],
            "observed_at": program["observed_at"], "source_factset_sha256": program["source_factset_sha256"],
            "source_conflicts": program["source_conflicts"], "reference_value": program["reference_value"],
            "currentness": reference_currentness,
        },
        "gates": gates,
        "required_artifacts": artifacts,
        "owner_fact_gaps": missing,
        "draft_application_outline": outline,
        "selector_holds_do_not_imply_ineligibility": True,
        "technical_fit_is_not_eligibility": True,
        "authority": _authority(),
    }
    packet_bytes = canon(packet)
    markdown = render_markdown(packet).encode("utf-8")
    receipt = {
        "schema": RECEIPT_SCHEMA, "truth_boundary": BOUNDARY, "status": packet_status,
        "program_id": program_id, "project_id": project["project_id"],
        "reference_programs_sha256": refs_sha, "input_sha256": digest(input_bytes),
        "packet_sha256": digest(packet_bytes), "markdown_sha256": digest(markdown),
        "route_map_git_blob_sha1": refs["route_map"]["git_blob_sha1"],
        "program_source_factset_sha256": program["source_factset_sha256"],
        "authority": _authority(),
    }
    return packet_bytes, markdown, canon(receipt)


def render_markdown(packet: dict[str, Any]):
    lines = ["# OSS grant packet readiness", "", f"- Program: `{packet['program']['program_id']}`", f"- Project: `{packet['project']['project_id']}`", f"- Status: **{packet['status']}**", f"- Reference currentness: **{packet['program']['currentness']['reason']}** (age limit {packet['program']['currentness']['policy_max_age_seconds']}s)", "- Truth: **packet readiness only; not eligibility, selection, award, payment, or revenue**", "", "## Mechanical eligibility / artifacts", ""]
    for gate in packet["gates"]:
        if gate["scope"] != "SELECTOR":
            lines.append(f"- `{gate['status']}` `{gate['rule_id']}` — {gate['reason']}")
    lines += ["", "## Subjective selector review", ""]
    selectors = [g for g in packet["gates"] if g["scope"] == "SELECTOR"]
    if not selectors: lines.append("No selector rules in this retained generation.")
    for gate in selectors:
        lines.append(f"- `{gate['status']}` `{gate['rule_id']}` — {gate['reason']} (never promoted to eligibility)")
    lines += ["", "## Owner facts / artifacts", ""]
    if not packet["owner_fact_gaps"]: lines.append("No mechanical owner facts are missing or held.")
    for row in packet["owner_fact_gaps"]:
        lines.append(f"- `{row['scope']}` `{row['rule_id']}` — {row['reason']}")
    lines += ["", "## Application drafting", "", packet["draft_application_outline"]["owner_instruction"], "", "## Authority ceiling", "", "No application submission, portal/form mutation, sponsor contact, email/DM, Muse request, signature/certification, price commitment, award/payment/cash claim, or revenue recognition is authorized.", ""]
    return "\n".join(lines)


def verify(reference_bytes: bytes, input_bytes: bytes, packet_bytes: bytes, markdown_bytes: bytes, receipt_bytes: bytes):
    expected = compile_packet(reference_bytes, input_bytes)
    for label, got, want in (("packet", packet_bytes, expected[0]), ("markdown", markdown_bytes, expected[1]), ("receipt", receipt_bytes, expected[2])):
        if label != "markdown":
            obj = load(got, label)
            if canon(obj) != got:
                raise GrantPacketError(f"{label}: non-canonical bytes")
        if got != want:
            raise GrantPacketError(f"{label}: mismatch")
    return {"verified": True, "packet_sha256": digest(expected[0]), "receipt_sha256": digest(expected[2])}
