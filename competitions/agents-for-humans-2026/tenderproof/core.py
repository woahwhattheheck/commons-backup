from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Iterable

SCHEMA_VERSION = "tenderproof.packet.v1"
ALGORITHM_VERSION = "tenderproof-core/1.0.0"
_MODAL_RE = re.compile(r"\b(must|shall|required|mandatory|no later than|deadline)\b", re.I)
_DATE_RE = re.compile(
    r"\b(20\d{2}-\d{2}-\d{2}|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+20\d{2})\b",
    re.I,
)
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9.+/-]*", re.I)
_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it",
    "of", "on", "or", "that", "the", "this", "to", "vendor", "will", "with", "must", "shall",
    "required", "requirement", "provide", "submit", "have", "has", "their", "its",
}
_HARD_CATEGORIES = {"insurance", "security", "legal", "certification"}
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_CATEGORY_KEYWORDS = {
    "insurance": {"insurance", "liability", "coverage", "insured"},
    "security": {"soc", "security", "breach", "incident", "encryption", "cyber"},
    "certification": {"certified", "certification", "license", "licensed", "accreditation"},
    "references": {"reference", "references", "client", "clients", "customer", "customers"},
    "experience": {"experience", "years", "projects", "deployments"},
    "accessibility": {"accessibility", "accessible", "wcag", "ada"},
    "delivery": {"delivery", "deliver", "timeline", "implementation", "milestone"},
    "pricing": {"price", "pricing", "cost", "fee", "budget"},
    "legal": {"indemnity", "legal", "contract", "terms", "warranty"},
}


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str
    mandatory: bool
    category: str
    source_line: int
    deadline: str | None = None


@dataclass(frozen=True)
class Evidence:
    id: str
    claim: str
    source: str
    confirmed: bool
    tags: tuple[str, ...]
    expires: str | None = None
    synthetic: bool = False


class ContractError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text) if len(w) > 2 and w.lower() not in _STOP}


def _category(text: str) -> str:
    if _DATE_RE.search(text) and re.search(r"\b(deadline|due|received|proposal|submission)\b", text, re.I):
        return "deadline"
    words = _tokens(text)
    best = (0, "general")
    for name, keys in _CATEGORY_KEYWORDS.items():
        score = len(words & keys)
        if score > best[0]:
            best = (score, name)
    return best[1]


def extract_requirements(rfp_text: str) -> list[Requirement]:
    if not isinstance(rfp_text, str) or not rfp_text.strip():
        raise ContractError("rfp_text must be a non-empty string")
    out: list[Requirement] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(rfp_text.splitlines(), start=1):
        line = raw.strip().lstrip("-*• ").strip()
        if not line or line.startswith("#") or not _MODAL_RE.search(line):
            continue
        normalized = " ".join(line.split())
        digest = sha256_text(normalized.lower())
        if digest in seen:
            continue
        seen.add(digest)
        deadline_match = _DATE_RE.search(normalized)
        out.append(
            Requirement(
                id=f"R-{len(out)+1:03d}",
                text=normalized,
                mandatory=True,
                category=_category(normalized),
                source_line=lineno,
                deadline=deadline_match.group(1) if deadline_match else None,
            )
        )
    if not out:
        raise ContractError("no mandatory/required obligations were detected")
    return out


def parse_evidence(records: Any) -> list[Evidence]:
    if not isinstance(records, list):
        raise ContractError("evidence must be a JSON array")
    out: list[Evidence] = []
    ids: set[str] = set()
    for idx, item in enumerate(records):
        if not isinstance(item, dict):
            raise ContractError(f"evidence[{idx}] must be an object")
        eid = item.get("id")
        claim = item.get("claim")
        source = item.get("source")
        confirmed = item.get("confirmed")
        tags = item.get("tags", [])
        expires = item.get("expires")
        synthetic = item.get("synthetic", False)
        if not isinstance(eid, str) or not re.fullmatch(r"E-[A-Z0-9-]{2,40}", eid):
            raise ContractError(f"evidence[{idx}].id must match E-[A-Z0-9-]+")
        if eid in ids:
            raise ContractError(f"duplicate evidence id: {eid}")
        ids.add(eid)
        if not isinstance(claim, str) or not claim.strip():
            raise ContractError(f"evidence[{idx}].claim must be non-empty")
        if not isinstance(source, str) or not source.strip():
            raise ContractError(f"evidence[{idx}].source must be non-empty")
        if type(confirmed) is not bool:
            raise ContractError(f"evidence[{idx}].confirmed must be boolean")
        if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
            raise ContractError(f"evidence[{idx}].tags must be a string array")
        if expires is not None:
            if not isinstance(expires, str):
                raise ContractError(f"evidence[{idx}].expires must be YYYY-MM-DD")
            try:
                date.fromisoformat(expires)
            except ValueError as exc:
                raise ContractError(f"invalid evidence expiry: {expires}") from exc
        if type(synthetic) is not bool:
            raise ContractError(f"evidence[{idx}].synthetic must be boolean")
        out.append(Evidence(eid, claim.strip(), source.strip(), confirmed, tuple(sorted(set(tags))), expires, synthetic))
    return out


def _is_current(evidence: Evidence, as_of: date) -> bool:
    if not evidence.confirmed:
        return False
    return evidence.expires is None or date.fromisoformat(evidence.expires) >= as_of


def _first_count(text: str, noun: str) -> int | None:
    match = re.search(rf"\b(\d+|{'|'.join(_NUMBER_WORDS)})\s+(?:client\s+)?{noun}\b", text, re.I)
    if not match:
        return None
    token = match.group(1).lower()
    return int(token) if token.isdigit() else _NUMBER_WORDS[token]


def _money_amount(text: str) -> int | None:
    match = re.search(r"\$\s*([\d,]+)", text)
    return int(match.group(1).replace(",", "")) if match else None


def _hours(text: str) -> int | None:
    return _first_count(text, "hours?")


def _match_score(req: Requirement, ev: Evidence) -> float:
    ev_text = ev.claim + " " + " ".join(ev.tags)
    if req.category == "references":
        required = _first_count(req.text, "references?")
        offered = _first_count(ev_text, "references?")
        if required is not None and (offered is None or offered < required):
            return 0.0
    if req.category == "insurance":
        required_amount = _money_amount(req.text)
        offered_amount = _money_amount(ev_text)
        if required_amount is not None and (offered_amount is None or offered_amount < required_amount):
            return 0.0
    if req.category == "security" and "incident" in req.text.lower():
        required_hours = _hours(req.text)
        offered_hours = _hours(ev_text)
        if required_hours is not None and "or less" in req.text.lower() and (offered_hours is None or offered_hours > required_hours):
            return 0.0
    if "soc 2" in req.text.lower() and "soc 2" not in ev_text.lower():
        return 0.0
    rt = _tokens(req.text)
    et = _tokens(ev_text)
    if not rt or not et:
        return 0.0
    overlap = len(rt & et) / max(1, min(len(rt), 6))
    category_boost = 0.24 if req.category in {t.lower() for t in ev.tags} else 0.0
    return min(1.0, overlap + category_boost)


def bind_evidence(requirements: Iterable[Requirement], evidence: Iterable[Evidence], *, as_of: date) -> list[dict[str, Any]]:
    current = [e for e in evidence if _is_current(e, as_of)]
    results: list[dict[str, Any]] = []
    for req in requirements:
        if req.category == "deadline":
            results.append({"requirement": asdict(req), "status": "OPERATIONAL", "evidence_id": None, "evidence_score": 0.0})
            continue
        ranked = sorted(((_match_score(req, ev), ev) for ev in current), key=lambda pair: (-pair[0], pair[1].id))
        score, match = ranked[0] if ranked else (0.0, None)
        supported = bool(match and score >= 0.34)
        blocker = bool(req.mandatory and not supported and req.category in _HARD_CATEGORIES)
        results.append(
            {
                "requirement": asdict(req),
                "status": "SUPPORTED" if supported else ("BLOCKER" if blocker else "MISSING"),
                "evidence_id": match.id if supported and match else None,
                "evidence_score": round(score, 4) if match else 0.0,
            }
        )
    return results


def _decision(bindings: list[dict[str, Any]]) -> dict[str, Any]:
    blockers = [b["requirement"]["id"] for b in bindings if b["status"] == "BLOCKER"]
    missing = [b["requirement"]["id"] for b in bindings if b["status"] == "MISSING"]
    if blockers:
        state = "NO_BID"
        reason = "one or more mandatory hard-gate requirements lack current confirmed evidence"
    elif missing:
        state = "CONDITIONAL_BID"
        reason = "no hard gate failed, but mandatory evidence remains incomplete"
    else:
        state = "BID"
        reason = "every extracted mandatory requirement is bound to current confirmed evidence"
    return {"state": state, "reason": reason, "blockers": blockers, "missing": missing}


def build_packet(rfp_text: str, evidence_records: Any, *, as_of: str | None = None) -> dict[str, Any]:
    try:
        as_of_date = date.fromisoformat(as_of) if as_of else datetime.now().astimezone().date()
    except ValueError as exc:
        raise ContractError("as_of must be YYYY-MM-DD") from exc
    requirements = extract_requirements(rfp_text)
    evidence = parse_evidence(evidence_records)
    bindings = bind_evidence(requirements, evidence, as_of=as_of_date)
    ev_by_id = {ev.id: ev for ev in evidence}
    response_sections: list[dict[str, str]] = []
    actions: list[dict[str, str]] = []
    for binding in bindings:
        req = binding["requirement"]
        rid = req["id"]
        if binding["status"] == "OPERATIONAL":
            response_sections.append(
                {
                    "requirement_id": rid,
                    "text": "Operational obligation recorded; verify scheduling/compliance before submission.",
                    "evidence_id": "",
                }
            )
            actions.append(
                {
                    "requirement_id": rid,
                    "priority": "SCHEDULE",
                    "action": f"Calendar and verify operational obligation: {req['text']}",
                }
            )
        elif binding["status"] == "SUPPORTED":
            ev = ev_by_id[binding["evidence_id"]]
            response_sections.append(
                {
                    "requirement_id": rid,
                    "text": f"Supported by {ev.id}: {ev.claim}",
                    "evidence_id": ev.id,
                }
            )
        else:
            response_sections.append(
                {
                    "requirement_id": rid,
                    "text": "DO NOT CLAIM — current confirmed evidence is required before this response can be submitted.",
                    "evidence_id": "",
                }
            )
            actions.append(
                {
                    "requirement_id": rid,
                    "priority": "BLOCKING" if binding["status"] == "BLOCKER" else "REQUIRED",
                    "action": f"Obtain and verify evidence for: {req['text']}",
                }
            )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "as_of": as_of_date.isoformat(),
        "input_hashes": {
            "rfp_sha256": sha256_text(rfp_text),
            "evidence_sha256": sha256_text(canonical_json(evidence_records)),
        },
        "requirements": [asdict(r) for r in requirements],
        "bindings": bindings,
        "decision": _decision(bindings),
        "response_sections": response_sections,
        "actions": actions,
        "evidence_used": sorted({b["evidence_id"] for b in bindings if b["evidence_id"]}),
        "authority": {
            "buyer_send_authorized": False,
            "certification_authorized": False,
            "submission_authorized": False,
            "note": "TenderProof prepares an evidence-bound packet; a human remains responsible for final factual and commercial approval.",
        },
    }
    payload_hash = sha256_text(canonical_json(payload))
    payload["receipt"] = {"payload_sha256": payload_hash, "algorithm_version": ALGORITHM_VERSION}
    return payload


def verify_packet(packet: Any) -> bool:
    if not isinstance(packet, dict):
        return False
    receipt = packet.get("receipt")
    if not isinstance(receipt, dict) or set(receipt) != {"payload_sha256", "algorithm_version"}:
        return False
    if receipt.get("algorithm_version") != ALGORITHM_VERSION:
        return False
    bare = dict(packet)
    bare.pop("receipt", None)
    if receipt.get("payload_sha256") != sha256_text(canonical_json(bare)):
        return False
    auth = bare.get("authority")
    if not isinstance(auth, dict) or any(auth.get(k) is not False for k in ("buyer_send_authorized", "certification_authorized", "submission_authorized")):
        return False
    bindings = bare.get("bindings")
    sections = bare.get("response_sections")
    if not isinstance(bindings, list) or not isinstance(sections, list) or len(bindings) != len(sections):
        return False
    section_by_id = {s.get("requirement_id"): s for s in sections if isinstance(s, dict)}
    for binding in bindings:
        if not isinstance(binding, dict):
            return False
        rid = binding.get("requirement", {}).get("id") if isinstance(binding.get("requirement"), dict) else None
        section = section_by_id.get(rid)
        if not section:
            return False
        if binding.get("status") == "SUPPORTED":
            if not binding.get("evidence_id") or section.get("evidence_id") != binding.get("evidence_id"):
                return False
            if str(section.get("text", "")).startswith("DO NOT CLAIM"):
                return False
        elif binding.get("status") == "OPERATIONAL":
            if section.get("evidence_id") not in ("", None):
                return False
            if not str(section.get("text", "")).startswith("Operational obligation recorded"):
                return False
        else:
            if section.get("evidence_id") not in ("", None):
                return False
            if not str(section.get("text", "")).startswith("DO NOT CLAIM"):
                return False
    return True
