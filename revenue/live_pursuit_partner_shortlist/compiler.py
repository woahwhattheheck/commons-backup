#!/usr/bin/env python3
"""Deterministic source-bound pursuit requirement -> partner-capability shortlist compiler.

This module is deliberately offline. It does not recommend companies or routes and has no
network, messaging, pricing, submission, signature, payment, or provider mutation path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

try:
    from . import trusted_generation as _trusted_generation
except ImportError:
    import trusted_generation as _trusted_generation

SCHEMA_VERSION = "live-pursuit-partner-shortlist/v1"
BLOCKED_NO_CARRIER = "LIVE_MATERIALIZATION_BLOCKED_NO_VERIFIED_CARRIER_SET"
OWNERS = {"TJLABS", "PRIME"}
EVIDENCE_STATUS = {"VERIFIED", "UNVERIFIED", "MISSING", "CONFLICTING"}
SENSITIVE = {"CERTIFICATION", "REFERENCE", "SLA", "SECURITY", "LEGAL"}
CATEGORIES = SENSITIVE | {"CAPABILITY", "GENERIC"}
MODES = {"SYNTHETIC", "LIVE"}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class InputError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _obj(v: Any, where: str) -> dict[str, Any]:
    if type(v) is not dict:
        raise InputError(f"{where}: expected object")
    return v


def _list(v: Any, where: str) -> list[Any]:
    if type(v) is not list:
        raise InputError(f"{where}: expected list")
    return v


def _str(o: dict[str, Any], key: str, where: str) -> str:
    v = o.get(key)
    if type(v) is not str or not v.strip():
        raise InputError(f"{where}.{key}: required non-empty string")
    return v.strip()


def _id(o: dict[str, Any], key: str, where: str) -> str:
    v = _str(o, key, where)
    if not ID_RE.fullmatch(v):
        raise InputError(f"{where}.{key}: invalid identifier")
    return v


def _bool(o: dict[str, Any], key: str, where: str) -> bool:
    v = o.get(key)
    if type(v) is not bool:
        raise InputError(f"{where}.{key}: expected boolean")
    return v


def _dt(raw: str, where: str):
    if type(raw) is not str or not raw.strip():
        raise InputError(f"{where}: timestamp required")
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
    except ValueError as e:
        raise InputError(f"{where}: invalid timestamp") from e
    if d.tzinfo is None:
        raise InputError(f"{where}: timezone required")
    return d.astimezone(timezone.utc)


def _digest(raw: str, where: str) -> str:
    if type(raw) is not str or not SHA_RE.fullmatch(raw):
        raise InputError(f"{where}: expected lowercase sha256")
    return raw


def _source(raw: str, where: str) -> str:
    if type(raw) is not str or not raw.strip():
        raise InputError(f"{where}: source required")
    raw = raw.strip()
    p = urlsplit(raw)
    if p.scheme:
        if p.scheme != "https" or not p.netloc or p.username or p.password:
            raise InputError(f"{where}: only https without userinfo is allowed")
        return raw
    q = PurePosixPath(raw)
    if q.is_absolute() or "\\" in raw or any(part in {"", ".", ".."} for part in q.parts):
        raise InputError(f"{where}: unsafe repository-relative source")
    return raw


def _closed(o: dict[str, Any], allowed: set[str], where: str):
    extra = sorted(set(o) - allowed)
    if extra:
        raise InputError(f"{where}: unexpected keys {extra}")


def _current(observed: str, valid_until: str | None, as_of) -> bool:
    observed_dt = _dt(observed, "observed_at")
    if observed_dt > as_of:
        return False
    if valid_until is None:
        return True
    valid_dt = _dt(valid_until, "valid_until")
    if valid_dt < observed_dt:
        return False
    return valid_dt >= as_of


def _validate_impl(raw: Any, authenticate, live_now, generation_sha) -> dict[str, Any]:
    root = _obj(raw, "root")
    _closed(root, {"schema_version", "as_of", "materialization_mode", "verified_carrier_set", "pursuits"}, "root")
    if _str(root, "schema_version", "root") != SCHEMA_VERSION:
        raise InputError("root.schema_version: unsupported")
    as_of_s = _str(root, "as_of", "root")
    as_of = _dt(as_of_s, "root.as_of")
    mode = _str(root, "materialization_mode", "root")
    if mode not in MODES:
        raise InputError("root.materialization_mode: invalid")
    current_as_of = as_of if mode == "SYNTHETIC" else live_now()
    currentness_basis = "CALLER_HISTORICAL_SYNTHETIC" if mode == "SYNTHETIC" else "PROCESS_UTC"
    carriers_out = []
    carrier_ids = set()
    for i, c0 in enumerate(_list(root.get("verified_carrier_set"), "root.verified_carrier_set")):
        c = _obj(c0, f"carrier[{i}]")
        _closed(c, {"pursuit_id", "source_uri", "source_sha256", "observed_at", "valid_until", "verified"}, f"carrier[{i}]")
        cid = _id(c, "pursuit_id", f"carrier[{i}]")
        if cid in carrier_ids:
            raise InputError("duplicate carrier pursuit_id")
        carrier_ids.add(cid)
        obs = _str(c, "observed_at", f"carrier[{i}]")
        vu = c.get("valid_until")
        if vu is not None and type(vu) is not str:
            raise InputError("carrier.valid_until: string/null")
        carriers_out.append({"pursuit_id": cid, "source_uri": _source(_str(c, "source_uri", f"carrier[{i}]"), f"carrier[{i}].source_uri"), "source_sha256": _digest(_str(c, "source_sha256", f"carrier[{i}]"), f"carrier[{i}].source_sha256"), "observed_at": obs, "valid_until": vu, "verified": _bool(c, "verified", f"carrier[{i}]"), "current": _current(obs, vu, current_as_of)})

    pursuits_out = []
    pursuit_ids = set()
    for pi, p0 in enumerate(_list(root.get("pursuits"), "root.pursuits")):
        p = _obj(p0, f"pursuit[{pi}]")
        _closed(p, {"pursuit_id", "source_uri", "source_sha256", "source_observed_at", "source_valid_until", "requirements", "evidence"}, f"pursuit[{pi}]")
        pid = _id(p, "pursuit_id", f"pursuit[{pi}]")
        if pid in pursuit_ids:
            raise InputError("duplicate pursuit_id")
        pursuit_ids.add(pid)
        ps = _source(_str(p, "source_uri", f"pursuit[{pi}]"), f"pursuit[{pi}].source_uri")
        pd = _digest(_str(p, "source_sha256", f"pursuit[{pi}]"), f"pursuit[{pi}].source_sha256")
        po = _str(p, "source_observed_at", f"pursuit[{pi}]")
        pvu = p.get("source_valid_until")
        if pvu is not None and type(pvu) is not str:
            raise InputError("source_valid_until: string/null")
        pcurrent = _current(po, pvu, current_as_of)

        reqs = []
        req_ids = set()
        raw_requirements = _list(p.get("requirements"), f"pursuit[{pi}].requirements")
        if not raw_requirements:
            raise InputError(f"pursuit[{pi}].requirements: at least one retained requirement is required")
        for ri, r0 in enumerate(raw_requirements):
            r = _obj(r0, f"requirement[{pi}:{ri}]")
            _closed(r, {"requirement_id", "text", "mandatory", "partner_eligible", "category", "capability_key"}, f"requirement[{pi}:{ri}]")
            rid = _id(r, "requirement_id", f"requirement[{pi}:{ri}]")
            if rid in req_ids:
                raise InputError(f"{pid}: duplicate requirement_id")
            req_ids.add(rid)
            cat = _str(r, "category", f"requirement[{pi}:{ri}]")
            if cat not in CATEGORIES:
                raise InputError("requirement.category: invalid")
            reqs.append({"requirement_id": rid, "text": _str(r, "text", f"requirement[{pi}:{ri}]"), "mandatory": _bool(r, "mandatory", f"requirement[{pi}:{ri}]"), "partner_eligible": _bool(r, "partner_eligible", f"requirement[{pi}:{ri}]"), "category": cat, "capability_key": _id(r, "capability_key", f"requirement[{pi}:{ri}]")})

        evs = []
        ev_ids = set()
        for ei, e0 in enumerate(_list(p.get("evidence"), f"pursuit[{pi}].evidence")):
            e = _obj(e0, f"evidence[{pi}:{ei}]")
            _closed(e, {"evidence_id", "owner", "category", "status", "source_uri", "source_sha256", "observed_at", "valid_until", "covers_requirement_ids"}, f"evidence[{pi}:{ei}]")
            eid = _id(e, "evidence_id", f"evidence[{pi}:{ei}]")
            if eid in ev_ids:
                raise InputError(f"{pid}: duplicate evidence_id")
            ev_ids.add(eid)
            owner = _str(e, "owner", f"evidence[{pi}:{ei}]")
            if owner not in OWNERS:
                raise InputError("evidence.owner: invalid")
            cat = _str(e, "category", f"evidence[{pi}:{ei}]")
            if cat not in CATEGORIES:
                raise InputError("evidence.category: invalid")
            status = _str(e, "status", f"evidence[{pi}:{ei}]")
            if status not in EVIDENCE_STATUS:
                raise InputError("evidence.status: invalid")
            covers = []
            for x in _list(e.get("covers_requirement_ids"), f"evidence[{pi}:{ei}].covers_requirement_ids"):
                if type(x) is not str or x not in req_ids:
                    raise InputError(f"{pid}: evidence references unknown requirement")
                if x in covers:
                    raise InputError(f"{pid}: duplicate evidence coverage")
                covers.append(x)
            obs = _str(e, "observed_at", f"evidence[{pi}:{ei}]")
            vu = e.get("valid_until")
            if vu is not None and type(vu) is not str:
                raise InputError("evidence.valid_until: string/null")
            evs.append({"evidence_id": eid, "owner": owner, "category": cat, "status": status, "source_uri": _source(_str(e, "source_uri", f"evidence[{pi}:{ei}]"), f"evidence[{pi}:{ei}].source_uri"), "source_sha256": _digest(_str(e, "source_sha256", f"evidence[{pi}:{ei}]"), f"evidence[{pi}:{ei}].source_sha256"), "observed_at": obs, "valid_until": vu, "current": _current(obs, vu, current_as_of), "covers_requirement_ids": sorted(covers)})
        source_claim = {
            "source_uri": ps,
            "source_sha256": pd,
            "source_observed_at": po,
            "source_valid_until": pvu,
        }
        source_authenticated, requirement_ids, evidence_ids = authenticate(
            mode, pid, source_claim, reqs, evs
        )
        requirement_ids = set(requirement_ids)
        evidence_ids = set(evidence_ids)
        for row in reqs:
            row["authenticated"] = row["requirement_id"] in requirement_ids
        for row in evs:
            row["authenticated"] = row["evidence_id"] in evidence_ids
        pursuits_out.append({
            "pursuit_id": pid,
            "source_uri": ps,
            "source_sha256": pd,
            "source_observed_at": po,
            "source_valid_until": pvu,
            "source_current": pcurrent,
            "source_authenticated": source_authenticated,
            "requirements": sorted(reqs, key=lambda x: x["requirement_id"]),
            "evidence": sorted(evs, key=lambda x: x["evidence_id"]),
        })
    if not pursuits_out:
        raise InputError("root.pursuits: at least one required")
    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": as_of_s,
        "materialization_mode": mode,
        "currentness_basis": currentness_basis,
        "trusted_generation_sha256": generation_sha,
        "verified_carrier_set": sorted(carriers_out, key=lambda x: x["pursuit_id"]),
        "pursuits": sorted(pursuits_out, key=lambda x: x["pursuit_id"]),
    }


def _build_validator():
    authenticate = _trusted_generation.authenticate
    live_now = _trusted_generation.live_now
    generation_sha = _trusted_generation.GENERATION_SHA256
    impl = _validate_impl

    def validate_and_normalize(raw: Any) -> dict[str, Any]:
        return impl(raw, authenticate, live_now, generation_sha)

    return validate_and_normalize


validate_and_normalize = _build_validator()
TRUSTED_GENERATION_SHA256 = _trusted_generation.GENERATION_SHA256
del _trusted_generation


def _state_for(req, pursuit):
    if not pursuit["source_authenticated"]:
        return "OWNER_INPUT", "PURSUIT_SOURCE_NOT_AUTHENTICATED"
    if not req["authenticated"]:
        return "OWNER_INPUT", "REQUIREMENT_CONTRACT_NOT_AUTHENTICATED"
    if not pursuit["source_current"]:
        return "OWNER_INPUT", "PURSUIT_SOURCE_NOT_CURRENT"
    mapped = [e for e in pursuit["evidence"] if req["requirement_id"] in e["covers_requirement_ids"]]
    if any(not e["authenticated"] for e in mapped):
        return "OWNER_INPUT", "MAPPED_EVIDENCE_NOT_AUTHENTICATED"
    if any(e["status"] != "VERIFIED" or not e["current"] for e in mapped):
        return "OWNER_INPUT", "MAPPED_EVIDENCE_NOT_CURRENT_VERIFIED"
    exact = []
    for e in mapped:
        if req["category"] in SENSITIVE:
            if e["category"] != req["category"]:
                continue
        elif e["category"] not in {"CAPABILITY", "GENERIC", req["category"]}:
            continue
        exact.append(e)
    if any(e["owner"] == "TJLABS" for e in exact):
        return "PASS", "CURRENT_EXACT_TJLABS_EVIDENCE"
    if any(e["owner"] == "PRIME" for e in exact):
        return "PRIME_SUPPORTED", "CURRENT_EXACT_PRIME_EVIDENCE"
    if req["mandatory"] and req["partner_eligible"]:
        return "PARTNER_REQUIRED", "MANDATORY_UNCOVERED_PARTNER_ELIGIBLE"
    return "OWNER_INPUT", "NO_SAFE_CURRENT_COVERAGE"


def _compile_impl(raw: Any, normalize, classify, render, canonical, digest) -> dict[str, Any]:
    n = normalize(raw)
    # Caller-provided carrier rows are retained as evidence claims, but cannot authenticate
    # their own presence on repository main. Until a code-owned/main-bound carrier manifest
    # exists, every LIVE invocation must fail closed regardless of caller booleans.
    blocker = [BLOCKED_NO_CARRIER] if n["materialization_mode"] == "LIVE" else []
    rows = []
    needs = {}
    for p in n["pursuits"]:
        for r in p["requirements"]:
            if n["materialization_mode"] == "LIVE":
                state, reason = (
                    "OWNER_INPUT",
                    "LIVE_TRUST_GENERATION_UNAVAILABLE",
                )
            else:
                state, reason = classify(r, p)
            row = {"pursuit_id": p["pursuit_id"], "requirement_id": r["requirement_id"], "text": r["text"], "category": r["category"], "capability_key": r["capability_key"], "mandatory": r["mandatory"], "state": state, "reason": reason, "source_uri": p["source_uri"], "source_sha256": p["source_sha256"]}
            rows.append(row)
            if state == "PARTNER_REQUIRED":
                k = (r["capability_key"], r["category"])
                q = needs.setdefault(k, {"capability_key": r["capability_key"], "proof_category": r["category"], "company": "UNASSIGNED", "route": "UNASSIGNED", "requirement_refs": []})
                q["requirement_refs"].append({"pursuit_id": p["pursuit_id"], "requirement_id": r["requirement_id"]})
    shortlist = []
    for _, q in sorted(needs.items()):
        q["requirement_refs"] = sorted(q["requirement_refs"], key=lambda x: (x["pursuit_id"], x["requirement_id"]))
        shortlist.append(q)
    rows = sorted(rows, key=lambda x: (x["pursuit_id"], x["requirement_id"]))
    status = BLOCKED_NO_CARRIER if blocker else ("OWNER_REVIEW_READY" if not any(r["state"] == "OWNER_INPUT" for r in rows) else "HOLD_OWNER_INPUT")
    core = {"schema_version": SCHEMA_VERSION, "as_of": n["as_of"], "materialization_mode": n["materialization_mode"], "status": status, "blockers": blocker, "crosswalk": rows, "partner_capability_shortlist": shortlist, "authority": {"company_recommendation": False, "route_recommendation": False, "external_contact": False, "buyer_submission": False, "signature": False, "price_commitment": False, "award": False, "payment": False, "revenue": False}}
    core["currentness_basis"] = n["currentness_basis"]
    core["trusted_generation_sha256"] = n["trusted_generation_sha256"]
    md = render(core)
    receipt = {"schema_version": SCHEMA_VERSION, "canonical_input_sha256": digest(canonical(n)), "payload_sha256": digest(canonical(core)), "crosswalk_sha256": digest(canonical(rows)), "shortlist_sha256": digest(canonical(shortlist)), "markdown_sha256": digest(md.encode("utf-8")), "status": status, "blockers": blocker}
    receipt["currentness_basis"] = n["currentness_basis"]
    receipt["trusted_generation_sha256"] = n["trusted_generation_sha256"]
    return {"normalized_input": n, "payload": core, "markdown": md, "receipt": receipt}


def _md(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_markdown(core: dict[str, Any]) -> str:
    lines = ["# Pursuit partner-capability shortlist", "", f"Status: `{core['status']}`", f"Mode: `{core['materialization_mode']}`", ""]
    if core["blockers"]:
        lines += ["## Blockers"] + [f"- `{x}`" for x in core["blockers"]] + [""]
    lines += ["## Requirement crosswalk", "", "| Pursuit | Requirement | State | Capability | Proof |", "|---|---|---|---|---|"]
    for r in core["crosswalk"]:
        lines.append(f"| {r['pursuit_id']} | {r['requirement_id']} | {r['state']} | {r['capability_key']} | {r['category']} |")
        lines.append(f"<!-- requirement-text: {_md(r['text'])} -->")
    lines += ["", "## Partner / prime capability requirements", ""]
    if not core["partner_capability_shortlist"]:
        lines.append("_None mechanically required from current retained inputs._")
    else:
        for s in core["partner_capability_shortlist"]:
            refs = ", ".join(f"{x['pursuit_id']}:{x['requirement_id']}" for x in s["requirement_refs"])
            lines += [f"### {s['capability_key']}", f"- proof category: `{s['proof_category']}`", f"- company: `{s['company']}`", f"- route: `{s['route']}`", f"- requirements: {refs}", ""]
    lines += ["## Authority", "", "This artifact names missing capabilities and proof only. It does not select a company or route and creates no contact, submission, signature, price, award, payment, or revenue authority.", ""]
    return "\n".join(lines)


def _build_compiler():
    normalize = validate_and_normalize
    classify = _state_for
    render = render_markdown
    canonical = canonical_bytes
    digest = sha256
    impl = _compile_impl

    def compile_payload(raw: Any) -> dict[str, Any]:
        return impl(raw, normalize, classify, render, canonical, digest)

    return compile_payload


compile_payload = _build_compiler()


def _write_exclusive(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o644)
    try:
        with os.fdopen(fd, "wb", closefd=False) as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    finally:
        os.close(fd)


def compile_to_dir(input_path: Path, out_dir: Path):
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    c = compile_payload(raw)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_exclusive(out_dir / "canonical_input.json", canonical_bytes(c["normalized_input"]))
    _write_exclusive(out_dir / "crosswalk.json", canonical_bytes(c["payload"]))
    _write_exclusive(out_dir / "shortlist.md", c["markdown"].encode("utf-8"))
    _write_exclusive(out_dir / "receipt.json", canonical_bytes(c["receipt"]))
    return c


def verify(input_path: Path, out_dir: Path) -> bool:
    expected = compile_payload(json.loads(input_path.read_text(encoding="utf-8")))
    checks = {"canonical_input.json": canonical_bytes(expected["normalized_input"]), "crosswalk.json": canonical_bytes(expected["payload"]), "shortlist.md": expected["markdown"].encode("utf-8"), "receipt.json": canonical_bytes(expected["receipt"])}
    return all((out_dir / name).is_file() and (out_dir / name).read_bytes() == data for name, data in checks.items())


def main(argv=None) -> int:
    import sys
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile"); c.add_argument("--input", required=True); c.add_argument("--out-dir", required=True)
    v = sub.add_parser("verify"); v.add_argument("--input", required=True); v.add_argument("--out-dir", required=True)
    ns = ap.parse_args(argv)
    try:
        if ns.cmd == "compile":
            result = compile_to_dir(Path(ns.input), Path(ns.out_dir))
            print(f"COMPILE_OK status={result['payload']['status']} requirements={len(result['payload']['crosswalk'])} shortlist={len(result['payload']['partner_capability_shortlist'])}")
            return 0
        ok = verify(Path(ns.input), Path(ns.out_dir))
        print("VERIFY_OK" if ok else "VERIFY_FAIL")
        return 0 if ok else 2
    except (InputError, ValueError, OSError, json.JSONDecodeError) as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
