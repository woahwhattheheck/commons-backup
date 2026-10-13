#!/usr/bin/env python3
"""Deterministic evidence-bound compiler for Redmond ECM procurement readiness.

This tool does not submit a proposal, accept terms, contact the buyer, or assert that
TokenJunkieLabs is an ECM platform vendor. It converts explicit supplier evidence into
a fail-closed review artifact for a prime/vendor team.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

RATINGS = {"Y", "3P", "C", "F", "N", "NA"}
EFFECTS = {"support", "constraint", "contradiction"}
KINDS = {"artifact", "certification", "contract", "customer_reference", "roadmap", "test", "source"}
ROLES = {"prime", "subcontractor", "advisor", "unknown"}
PROFILE_PATH = Path(__file__).with_name("profile.json")


class ContractError(ValueError):
    pass


def canon(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text(value: Any, field: str, *, max_len: int = 2000, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field}: expected string")
    if not allow_empty and not value.strip():
        raise ContractError(f"{field}: blank")
    if len(value) > max_len:
        raise ContractError(f"{field}: too long")
    return value


def _id(value: Any, field: str) -> str:
    value = _text(value, field, max_len=80)
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_:.")
    if any(ch not in allowed for ch in value):
        raise ContractError(f"{field}: invalid identifier")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{field}: expected list")
    return value


def _dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{field}: expected object")
    return value


def _exact_keys(obj: Mapping[str, Any], keys: Iterable[str], field: str) -> None:
    want = set(keys)
    got = set(obj)
    if got != want:
        extra = sorted(got - want)
        missing = sorted(want - got)
        raise ContractError(f"{field}: keys mismatch missing={missing} extra={extra}")


def _read_regular(path: str | os.PathLike[str]) -> bytes:
    p = os.fspath(path)
    st = os.lstat(p)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise ContractError(f"{p}: input must be a regular non-symlink file")
    with open(p, "rb") as fh:
        data = fh.read()
    if len(data) > 8_000_000:
        raise ContractError(f"{p}: input too large")
    return data


def _write_exclusive(path: str | os.PathLike[str], data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(os.fspath(path), flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    except Exception:
        try:
            os.unlink(os.fspath(path))
        except OSError:
            pass
        raise


def loads_strict(data: bytes) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("input is not UTF-8") from exc

    def reject_constant(value: str) -> None:
        raise ContractError(f"non-finite JSON constant: {value}")

    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ContractError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    try:
        return json.loads(text, parse_constant=reject_constant, object_pairs_hook=reject_pairs)
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON: {exc.msg}") from exc


def load_profile() -> tuple[dict[str, Any], str]:
    raw = _read_regular(PROFILE_PATH)
    profile = _dict(loads_strict(raw), "profile")
    _exact_keys(
        profile,
        {"profile_version", "solicitation", "rating_legend", "evaluation_weights", "requirements"},
        "profile",
    )
    if profile["profile_version"] != 1:
        raise ContractError("profile_version: unsupported")
    requirements = _list(profile["requirements"], "profile.requirements")
    seen: set[str] = set()
    for idx, item in enumerate(requirements):
        req = _dict(item, f"profile.requirements[{idx}]")
        _exact_keys(req, {"id", "category", "critical", "title", "source", "acceptance"}, f"profile.requirements[{idx}]")
        rid = _id(req["id"], f"profile.requirements[{idx}].id")
        if rid in seen:
            raise ContractError(f"profile duplicate requirement id: {rid}")
        seen.add(rid)
        _text(req["category"], f"profile.requirements[{idx}].category", max_len=80)
        if not isinstance(req["critical"], bool):
            raise ContractError(f"profile.requirements[{idx}].critical: expected boolean")
        _text(req["title"], f"profile.requirements[{idx}].title", max_len=300)
        _text(req["source"], f"profile.requirements[{idx}].source", max_len=300)
        _text(req["acceptance"], f"profile.requirements[{idx}].acceptance", max_len=1000)
    return profile, sha256_bytes(raw)


def validate_supplier(raw: Any, requirement_ids: set[str]) -> dict[str, Any]:
    obj = _dict(raw, "input")
    _exact_keys(obj, {"vendor", "responses", "evidence"}, "input")

    vendor = _dict(obj["vendor"], "vendor")
    _exact_keys(vendor, {"name", "role", "scope_notes"}, "vendor")
    _text(vendor["name"], "vendor.name", max_len=200)
    role = _text(vendor["role"], "vendor.role", max_len=40)
    if role not in ROLES:
        raise ContractError(f"vendor.role: expected one of {sorted(ROLES)}")
    _text(vendor["scope_notes"], "vendor.scope_notes", max_len=3000)

    evidence_by_id: dict[str, dict[str, Any]] = {}
    for idx, item in enumerate(_list(obj["evidence"], "evidence")):
        ev = _dict(item, f"evidence[{idx}]")
        _exact_keys(ev, {"id", "kind", "source_ref", "statement", "effects"}, f"evidence[{idx}]")
        eid = _id(ev["id"], f"evidence[{idx}].id")
        if eid in evidence_by_id:
            raise ContractError(f"duplicate evidence id: {eid}")
        kind = _text(ev["kind"], f"evidence[{idx}].kind", max_len=40)
        if kind not in KINDS:
            raise ContractError(f"evidence[{idx}].kind: expected one of {sorted(KINDS)}")
        _text(ev["source_ref"], f"evidence[{idx}].source_ref", max_len=1000)
        _text(ev["statement"], f"evidence[{idx}].statement", max_len=3000)
        effects = _list(ev["effects"], f"evidence[{idx}].effects")
        normalized_effects: list[dict[str, str]] = []
        seen_effects: set[tuple[str, str]] = set()
        for j, effect_raw in enumerate(effects):
            effect = _dict(effect_raw, f"evidence[{idx}].effects[{j}]")
            _exact_keys(effect, {"requirement_id", "effect"}, f"evidence[{idx}].effects[{j}]")
            rid = _id(effect["requirement_id"], f"evidence[{idx}].effects[{j}].requirement_id")
            if rid not in requirement_ids:
                raise ContractError(f"evidence {eid}: unknown requirement {rid}")
            eff = _text(effect["effect"], f"evidence[{idx}].effects[{j}].effect", max_len=30)
            if eff not in EFFECTS:
                raise ContractError(f"evidence {eid}: invalid effect {eff}")
            pair = (rid, eff)
            if pair in seen_effects:
                raise ContractError(f"evidence {eid}: duplicate effect {rid}/{eff}")
            seen_effects.add(pair)
            normalized_effects.append({"requirement_id": rid, "effect": eff})
        ev = dict(ev)
        ev["effects"] = sorted(normalized_effects, key=lambda x: (x["requirement_id"], x["effect"]))
        evidence_by_id[eid] = ev

    response_by_req: dict[str, dict[str, Any]] = {}
    for idx, item in enumerate(_list(obj["responses"], "responses")):
        resp = _dict(item, f"responses[{idx}]")
        _exact_keys(resp, {"requirement_id", "rating", "comment", "evidence_ids"}, f"responses[{idx}]")
        rid = _id(resp["requirement_id"], f"responses[{idx}].requirement_id")
        if rid not in requirement_ids:
            raise ContractError(f"response: unknown requirement {rid}")
        if rid in response_by_req:
            raise ContractError(f"duplicate response requirement: {rid}")
        rating = _text(resp["rating"], f"responses[{idx}].rating", max_len=3)
        if rating not in RATINGS:
            raise ContractError(f"response {rid}: invalid rating {rating}")
        _text(resp["comment"], f"responses[{idx}].comment", max_len=500)
        eids: list[str] = []
        seen_eids: set[str] = set()
        for j, raw_eid in enumerate(_list(resp["evidence_ids"], f"responses[{idx}].evidence_ids")):
            eid = _id(raw_eid, f"responses[{idx}].evidence_ids[{j}]")
            if eid in seen_eids:
                raise ContractError(f"response {rid}: duplicate evidence id {eid}")
            if eid not in evidence_by_id:
                raise ContractError(f"response {rid}: unknown evidence id {eid}")
            seen_eids.add(eid)
            eids.append(eid)
        response_by_req[rid] = {
            "requirement_id": rid,
            "rating": rating,
            "comment": resp["comment"],
            "evidence_ids": sorted(eids),
        }

    return {
        "vendor": vendor,
        "responses": response_by_req,
        "evidence": evidence_by_id,
    }


def _effects_for(req_id: str, evidence_ids: Sequence[str], evidence: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    grouped = {"support": [], "constraint": [], "contradiction": []}
    linked = set(evidence_ids)
    for eid in sorted(evidence):
        for effect in evidence[eid]["effects"]:
            if effect["requirement_id"] != req_id:
                continue
            # Supporting/constraint evidence must be explicitly linked by the response,
            # but contradictory evidence is globally material and cannot be hidden by
            # omitting its ID from a response.
            if eid in linked or effect["effect"] == "contradiction":
                grouped[effect["effect"]].append(eid)
    for values in grouped.values():
        values.sort()
    return grouped


def compile_report(profile: Mapping[str, Any], profile_sha256: str, supplier_raw: Any) -> dict[str, Any]:
    reqs = list(profile["requirements"])
    req_ids = {item["id"] for item in reqs}
    supplier = validate_supplier(supplier_raw, req_ids)
    responses = supplier["responses"]
    evidence = supplier["evidence"]

    matrix: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    contradictions: list[dict[str, Any]] = []
    acceptance_tests: list[dict[str, Any]] = []

    for req in sorted(reqs, key=lambda x: x["id"]):
        rid = req["id"]
        resp = responses.get(rid)
        if resp is None:
            state = "unknown"
            reason_codes = ["MISSING_RESPONSE"]
            rating = None
            comment = ""
            evidence_ids: list[str] = []
            effects = {"support": [], "constraint": [], "contradiction": []}
        else:
            rating = resp["rating"]
            comment = resp["comment"]
            evidence_ids = resp["evidence_ids"]
            effects = _effects_for(rid, evidence_ids, evidence)
            reason_codes = []
            if effects["contradiction"]:
                state = "blocker" if req["critical"] else "partial"
                reason_codes.append("CONTRADICTORY_EVIDENCE")
                if any(eid not in evidence_ids for eid in effects["contradiction"]):
                    reason_codes.append("UNLINKED_CONTRADICTION")
                contradictions.append({
                    "requirement_id": rid,
                    "evidence_ids": effects["contradiction"],
                    "critical": req["critical"],
                })
            elif rating == "N":
                state = "blocker" if req["critical"] else "partial"
                reason_codes.append("NOT_SUPPORTED")
            elif rating == "F":
                state = "blocker" if req["critical"] else "partial"
                reason_codes.append("FUTURE_ONLY")
            elif rating == "NA":
                state = "unknown"
                reason_codes.append("NOT_APPLICABLE_REQUIRES_BUYER_REVIEW" if req["critical"] else "NOT_APPLICABLE")
            elif not effects["support"]:
                state = "unknown"
                reason_codes.append("NO_SUPPORTING_EVIDENCE")
            elif rating == "Y" and not effects["constraint"]:
                state = "met"
                reason_codes.append("EVIDENCE_BOUND_CURRENT_SUPPORT")
            else:
                state = "partial"
                if rating in {"3P", "C"}:
                    reason_codes.append("QUALIFIED_SUPPORT")
                if effects["constraint"]:
                    reason_codes.append("EVIDENCE_CONSTRAINT")
                if not reason_codes:
                    reason_codes.append("PARTIAL")

        row = {
            "requirement_id": rid,
            "category": req["category"],
            "critical": req["critical"],
            "title": req["title"],
            "source": req["source"],
            "state": state,
            "reason_codes": sorted(set(reason_codes)),
            "vendor_rating": rating,
            "comment": comment,
            "evidence_ids": evidence_ids,
            "support_evidence_ids": effects["support"],
            "constraint_evidence_ids": effects["constraint"],
            "contradiction_evidence_ids": effects["contradiction"],
        }
        matrix.append(row)

        if state == "blocker" or (req["critical"] and state == "unknown"):
            blockers.append({
                "requirement_id": rid,
                "state": state,
                "reason_codes": row["reason_codes"],
            })

        acceptance_tests.append({
            "requirement_id": rid,
            "state_at_compile": state,
            "test": req["acceptance"],
            "evidence_prerequisites": evidence_ids,
        })

    counts = {name: sum(1 for row in matrix if row["state"] == name) for name in ("met", "partial", "unknown", "blocker")}
    if blockers:
        readiness = "BLOCKED"
    elif counts["partial"] or counts["unknown"]:
        readiness = "REVIEW_REQUIRED"
    else:
        readiness = "EVIDENCE_READY"

    report = {
        "schema_version": 1,
        "profile_sha256": profile_sha256,
        "solicitation": profile["solicitation"],
        "evaluation_weights": profile["evaluation_weights"],
        "vendor": supplier["vendor"],
        "readiness": readiness,
        "summary": {**counts, "total": len(matrix)},
        "compliance_matrix": matrix,
        "contradiction_ledger": contradictions,
        "blocker_ledger": blockers,
        "acceptance_test_plan": acceptance_tests,
        "evidence_catalog": [
            {
                "id": eid,
                "kind": evidence[eid]["kind"],
                "source_ref": evidence[eid]["source_ref"],
                "statement": evidence[eid]["statement"],
                "effects": evidence[eid]["effects"],
            }
            for eid in sorted(evidence)
        ],
        "authority_boundary": {
            "does_not_assert": [
                "proposal submitted",
                "terms accepted",
                "buyer contacted",
                "payment received",
                "revenue recognized",
                "TokenJunkieLabs is a complete ECM platform vendor",
            ],
            "purpose": "evidence/governance accelerator for prime/vendor review",
        },
    }
    report["report_sha256"] = sha256_bytes(canon(report))
    return report


def render_markdown(report: Mapping[str, Any]) -> bytes:
    lines = [
        "# Redmond ECM evidence-contract review",
        "",
        f"- Solicitation: **{report['solicitation']['id']} — {report['solicitation']['title']}**",
        f"- Vendor / contributor: **{report['vendor']['name']}** (`{report['vendor']['role']}`)",
        f"- Readiness: **{report['readiness']}**",
        f"- Profile SHA-256: `{report['profile_sha256']}`",
        f"- Report SHA-256: `{report['report_sha256']}`",
        "",
        "## Summary",
        "",
        "| met | partial | unknown | blocker | total |",
        "|---:|---:|---:|---:|---:|",
        f"| {report['summary']['met']} | {report['summary']['partial']} | {report['summary']['unknown']} | {report['summary']['blocker']} | {report['summary']['total']} |",
        "",
        "## Compliance matrix",
        "",
        "| ID | Category | Critical | State | Vendor rating | Evidence | Reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in report["compliance_matrix"]:
        evidence = ", ".join(f"`{x}`" for x in row["evidence_ids"]) or "—"
        rating = row["vendor_rating"] or "—"
        reasons = ", ".join(row["reason_codes"])
        lines.append(
            f"| `{row['requirement_id']}` | {row['category']} | {'yes' if row['critical'] else 'no'} | "
            f"**{row['state']}** | {rating} | {evidence} | {reasons} |"
        )

    lines += ["", "## Blocker ledger", ""]
    if report["blocker_ledger"]:
        for item in report["blocker_ledger"]:
            lines.append(f"- `{item['requirement_id']}` — {item['state']}: {', '.join(item['reason_codes'])}")
    else:
        lines.append("- None.")

    lines += ["", "## Contradiction ledger", ""]
    if report["contradiction_ledger"]:
        for item in report["contradiction_ledger"]:
            lines.append(
                f"- `{item['requirement_id']}` — evidence {', '.join('`'+x+'`' for x in item['evidence_ids'])}"
            )
    else:
        lines.append("- None.")

    lines += ["", "## Acceptance-test plan", ""]
    for item in report["acceptance_test_plan"]:
        lines.append(
            f"- `{item['requirement_id']}` [{item['state_at_compile']}] — {item['test']}"
        )

    lines += [
        "",
        "## Authority boundary",
        "",
        "This artifact is an evidence/governance accelerator for prime/vendor review. It does **not** submit a proposal, "
        "accept terms, contact the buyer, claim payment/cash/revenue, or represent TokenJunkieLabs as a complete ECM platform vendor.",
        "",
    ]
    return ("\n".join(lines)).encode("utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile a deterministic Redmond ECM evidence readiness artifact.")
    parser.add_argument("--input", required=True, help="supplier evidence JSON")
    parser.add_argument("--json-out", required=True, help="create-exclusive JSON report path")
    parser.add_argument("--md-out", required=True, help="create-exclusive Markdown report path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        profile, profile_sha = load_profile()
        supplier = loads_strict(_read_regular(args.input))
        report = compile_report(profile, profile_sha, supplier)
        _write_exclusive(args.json_out, canon(report))
        _write_exclusive(args.md_out, render_markdown(report))
        print(report["report_sha256"])
        return 0
    except (ContractError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
