from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Mapping

try:
    from .schema import (
        SCHEMA, MAX_SOURCE_AGE, _STATES, _SHA, DeltaError, canonical, sha, _dt, _utc,
        normalize_generation, normalize_decisions, requirement_identity, _doc_projection,
        _index, _decision_coverage,
    )
except ImportError:
    from schema import (
        SCHEMA, MAX_SOURCE_AGE, _STATES, _SHA, DeltaError, canonical, sha, _dt, _utc,
        normalize_generation, normalize_decisions, requirement_identity, _doc_projection,
        _index, _decision_coverage,
    )

MAX_RECEIPT_AGE = timedelta(minutes=5)
PROCESS_CLOCK = "PROCESS_UTC"
HISTORICAL_CLOCK = "CALLER_SUPPLIED_HISTORICAL"


def _process_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _change_fields(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[str]:
    fields = []
    for key in (
        "document_id", "coordinate", "statement_sha256", "class", "category", "route",
        "curable", "response_artifact", "deadline_utc", "review_class",
    ):
        if old[key] != new[key]:
            fields.append(key)
    return fields


def _semantic_projection(
    old: dict[str, Any],
    new: dict[str, Any],
    decisions: list[dict[str, Any]],
    evaluated_at: str,
) -> dict[str, Any]:
    """Pure semantic projection at a supplied instant.

    This object is deliberately *not* an authoritative report: it contains no
    schema, evaluated-at field, clock-authority label, or receipt digest. Public
    current authority is minted only by compile_current(), which owns process UTC.
    """
    if old["opportunity_id"] != new["opportunity_id"]:
        raise DeltaError("old/new opportunity_id mismatch")
    if old["generation_id"] == new["generation_id"] and sha(old) != sha(new):
        raise DeltaError("same generation_id carries different content")
    if _dt(new["captured_at"]) < _dt(old["captured_at"]):
        raise DeltaError("new generation predates old generation")

    now = _dt(_utc(evaluated_at, "evaluated_at"))
    if _dt(old["captured_at"]) > now or _dt(new["captured_at"]) > now:
        raise DeltaError("future source generation")
    for row in decisions:
        if _dt(row["decided_at"]) > now:
            raise DeltaError(f"decision {row['decision_id']} is from the future")

    coverage = _decision_coverage(old, decisions)
    decisions_by_id = {row["decision_id"]: row for row in decisions}
    stale_review_decisions = []
    conflicts = []

    old_docs = _index(old["documents"], "document_id")
    new_docs = _index(new["documents"], "document_id")
    doc_added, doc_removed, doc_changed, doc_unchanged = [], [], [], []

    for doc_id in sorted(set(old_docs) & set(new_docs)):
        o, n = old_docs[doc_id], new_docs[doc_id]
        if _doc_projection(o) == _doc_projection(n):
            doc_unchanged.append(doc_id)
        else:
            if n["supersedes_sha256"] != o["sha256"]:
                conflicts.append(f"document_changed_without_exact_supersession:{doc_id}")
            doc_changed.append({
                "old_document_id": doc_id,
                "new_document_id": doc_id,
                "old_sha256": o["sha256"],
                "new_sha256": n["sha256"],
                "old_role": o["role"],
                "new_role": n["role"],
            })

    old_only = {k: v for k, v in old_docs.items() if k not in new_docs}
    new_only = {k: v for k, v in new_docs.items() if k not in old_docs}
    successors: dict[str, list[dict[str, Any]]] = {}
    predecessors: dict[str, list[dict[str, Any]]] = {}
    for o in old_only.values():
        predecessors.setdefault(o["sha256"], []).append(o)
    for n in new_only.values():
        if n["supersedes_sha256"] is not None:
            successors.setdefault(n["supersedes_sha256"], []).append(n)

    consumed_new_ids: set[str] = set()
    for old_id in sorted(old_only):
        o = old_only[old_id]
        matches = successors.get(o["sha256"], [])
        old_matches = predecessors.get(o["sha256"], [])
        if matches and len(old_matches) > 1:
            doc_removed.append(old_id)
            conflicts.append(f"controlling_document_ambiguous_predecessor:{old_id}")
        elif len(matches) == 1:
            n = matches[0]
            consumed_new_ids.add(n["document_id"])
            doc_changed.append({
                "old_document_id": old_id,
                "new_document_id": n["document_id"],
                "old_sha256": o["sha256"],
                "new_sha256": n["sha256"],
                "old_role": o["role"],
                "new_role": n["role"],
            })
        elif len(matches) > 1:
            doc_removed.append(old_id)
            conflicts.append(f"controlling_document_multiple_successors:{old_id}")
        else:
            doc_removed.append(old_id)
            conflicts.append(f"controlling_document_removed:{old_id}")

    for new_id in sorted(new_only):
        if new_id not in consumed_new_ids:
            doc_added.append(new_id)

    old_req = _index(old["requirements"], "requirement_id")
    new_req = _index(new["requirements"], "requirement_id")
    added, removed, changed, unchanged = [], [], [], []
    carry_decisions = []
    review_required = set()

    for req_id in sorted(set(old_req) | set(new_req)):
        o, n = old_req.get(req_id), new_req.get(req_id)
        if o is None:
            added.append(req_id)
            if n["class"] != "INFORMATIONAL":
                review_required.add(req_id)
            continue
        if n is None:
            # Removed rows remain in historical delta evidence but are no longer
            # current obligations. Their removal is still a material packet change.
            removed.append(req_id)
            continue

        old_ident, new_ident = requirement_identity(o), requirement_identity(n)
        if old_ident == new_ident:
            unchanged.append(req_id)
            if o["class"] != "INFORMATIONAL":
                if not old["complete"]:
                    review_required.add(req_id)
                elif req_id in coverage:
                    decision_id = coverage[req_id]
                    decision = decisions_by_id[decision_id]
                    if now - _dt(decision["decided_at"]) > MAX_SOURCE_AGE:
                        stale_review_decisions.append({
                            "requirement_id": req_id,
                            "decision_id": decision_id,
                        })
                        review_required.add(req_id)
                    else:
                        carry_decisions.append({
                            "requirement_id": req_id,
                            "decision_id": decision_id,
                        })
                else:
                    review_required.add(req_id)
        else:
            fields = _change_fields(o, n)
            if n["supersedes_sha256"] != o["statement_sha256"]:
                conflicts.append(f"requirement_changed_without_exact_supersession:{req_id}")
            changed.append({
                "requirement_id": req_id,
                "fields": fields,
                "old_identity_sha256": old_ident,
                "new_identity_sha256": new_ident,
            })
            if n["class"] != "INFORMATIONAL" or o["class"] != "INFORMATIONAL":
                review_required.add(req_id)

    source_stale = now - _dt(new["captured_at"]) > MAX_SOURCE_AGE
    completeness_changed = old["complete"] != new["complete"]
    material_change = bool(
        completeness_changed or doc_added or doc_removed or doc_changed or added or removed or changed
    )

    if conflicts:
        state = "CONFLICT"
    elif not new["complete"] or source_stale:
        state = "SOURCE_REFRESH_REQUIRED"
    elif material_change or review_required:
        state = "REVIEW_REQUIRED"
    else:
        state = "NO_MATERIAL_CHANGE"

    return {
        "opportunity_id": old["opportunity_id"],
        "old_generation_id": old["generation_id"],
        "new_generation_id": new["generation_id"],
        "state": state,
        "source_freshness_days": MAX_SOURCE_AGE.days,
        "decision_freshness_days": MAX_SOURCE_AGE.days,
        "source_set_delta": {"old_complete": old["complete"], "new_complete": new["complete"]},
        "old_generation_sha256": sha(old),
        "new_generation_sha256": sha(new),
        "decisions_sha256": sha(decisions),
        "document_delta": {
            "added": doc_added,
            "removed": doc_removed,
            "changed": doc_changed,
            "unchanged": doc_unchanged,
        },
        "requirement_delta": {
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged": unchanged,
        },
        "carried_review_decisions": sorted(carry_decisions, key=lambda x: x["requirement_id"]),
        "stale_review_decisions": sorted(stale_review_decisions, key=lambda x: x["requirement_id"]),
        "review_required": sorted(review_required),
        "conflicts": sorted(conflicts),
        "authority": {
            "buyer_contact": False,
            "question_submission": False,
            "portal_action": False,
            "bid_submission": False,
            "signature": False,
            "commercial_commitment": False,
            "payment": False,
            "revenue_recognition": False,
        },
    }


def _normalize_inputs(old_generation: Any, new_generation: Any, decisions: Any):
    return (
        normalize_generation(old_generation),
        normalize_generation(new_generation),
        normalize_decisions(decisions),
    )


def compile_current(old_generation: Any, new_generation: Any, decisions: Any) -> dict[str, Any]:
    evaluated_at = _utc(_process_now(), "process_now")
    old, new, dec = _normalize_inputs(old_generation, new_generation, decisions)
    projection = _semantic_projection(old, new, dec, evaluated_at)
    report = {
        "schema": SCHEMA,
        "evaluated_at": evaluated_at,
        "clock_authority": PROCESS_CLOCK,
        **projection,
    }
    report["semantic_sha256"] = sha(report)
    return report


def compile_historical(
    old_generation: Any,
    new_generation: Any,
    decisions: Any,
    *,
    trusted_as_of: str,
) -> dict[str, Any]:
    """Deterministic non-current analysis. It can never mint current authority."""
    evaluated_at = _utc(trusted_as_of, "trusted_as_of")
    old, new, dec = _normalize_inputs(old_generation, new_generation, decisions)
    projection = _semantic_projection(old, new, dec, evaluated_at)
    projection["state"] = "HOLD"
    report = {
        "schema": SCHEMA,
        "evaluated_at": evaluated_at,
        "clock_authority": HISTORICAL_CLOCK,
        **projection,
    }
    report["semantic_sha256"] = sha(report)
    return report


def verify_report(
    old_generation: Any,
    new_generation: Any,
    decisions: Any,
    report: Any,
) -> tuple[bool, str]:
    if type(report) is not dict:
        return False, "report_not_object"
    if set(report) != {
        "schema", "opportunity_id", "old_generation_id", "new_generation_id",
        "evaluated_at", "clock_authority", "state", "source_freshness_days",
        "decision_freshness_days", "source_set_delta", "old_generation_sha256",
        "new_generation_sha256", "decisions_sha256", "document_delta",
        "requirement_delta", "carried_review_decisions", "stale_review_decisions",
        "review_required", "conflicts", "authority", "semantic_sha256",
    }:
        return False, "report_shape"
    if report.get("schema") != SCHEMA or report.get("state") not in _STATES:
        return False, "report_schema_or_state"
    if report.get("clock_authority") != PROCESS_CLOCK:
        return False, "report_not_current_clock"

    claimed = report.get("semantic_sha256")
    if type(claimed) is not str or not _SHA.fullmatch(claimed):
        return False, "report_digest_shape"
    unsigned = dict(report)
    unsigned.pop("semantic_sha256")
    if sha(unsigned) != claimed:
        return False, "report_digest"

    try:
        checked_now = _utc(_process_now(), "process_now")
        report_time = _dt(_utc(report["evaluated_at"], "evaluated_at"))
        now_dt = _dt(checked_now)
        if report_time > now_dt:
            return False, "report_from_future"
        if now_dt - report_time > MAX_RECEIPT_AGE:
            return False, "report_stale"

        old, new, dec = _normalize_inputs(old_generation, new_generation, decisions)
        retained = _semantic_projection(old, new, dec, report["evaluated_at"])
        current = _semantic_projection(old, new, dec, checked_now)
    except DeltaError as exc:
        return False, f"recompile:{exc}"

    # Compare canonical JSON, not Python equality: bool/int aliases such as
    # False == 0 must not survive a re-sealed receipt.
    for key, value in retained.items():
        if canonical(report.get(key)) != canonical(value):
            return False, "report_recompile_mismatch"

    for key in (
        "state", "source_set_delta", "review_required", "stale_review_decisions", "conflicts"
    ):
        if canonical(current[key]) != canonical(report[key]):
            return False, "report_currentness_changed"
    return True, "ok"


def markdown(report: Mapping[str, Any]) -> str:
    if type(report) is not dict:
        raise DeltaError("report must be object")
    lines = [
        "# RFP / Addenda Delta Review",
        "",
        f"- Opportunity: `{report['opportunity_id']}`",
        f"- Generation: `{report['old_generation_id']}` → `{report['new_generation_id']}`",
        f"- State: **{report['state']}**",
        f"- Evaluated: `{report['evaluated_at']}`",
        f"- Clock authority: `{report['clock_authority']}`",
        f"- Receipt: `{report['semantic_sha256']}`",
        "",
        "## Source-set custody",
        f"- Old generation complete: {str(report['source_set_delta']['old_complete']).lower()}",
        f"- New generation complete: {str(report['source_set_delta']['new_complete']).lower()}",
        f"- Carried review freshness ceiling: {report['decision_freshness_days']} days",
        "",
        "## Controlling-document delta",
    ]
    dd = report["document_delta"]
    changed_docs = []
    for row in dd["changed"]:
        old_id, new_id = row["old_document_id"], row["new_document_id"]
        changed_docs.append(old_id if old_id == new_id else f"{old_id}->{new_id}")
    lines += [
        f"- Added: {', '.join(dd['added']) or 'none'}",
        f"- Removed: {', '.join(dd['removed']) or 'none'}",
        f"- Changed: {', '.join(changed_docs) or 'none'}",
        "",
        "## Requirement delta",
    ]
    rd = report["requirement_delta"]
    lines += [
        f"- Added: {', '.join(rd['added']) or 'none'}",
        f"- Removed: {', '.join(rd['removed']) or 'none'}",
        f"- Changed: {', '.join(x['requirement_id'] for x in rd['changed']) or 'none'}",
        f"- Unchanged: {len(rd['unchanged'])}",
        "",
        "## Review",
        f"- Review required: {', '.join(report['review_required']) or 'none'}",
        f"- Carried decisions: {len(report['carried_review_decisions'])}",
        f"- Stale decisions: {', '.join(x['decision_id'] for x in report['stale_review_decisions']) or 'none'}",
        f"- Conflicts: {', '.join(report['conflicts']) or 'none'}",
        "",
        "## Authority ceiling",
        "Evidence-only owner review. This report authorizes no buyer contact, portal action,",
        "question/addendum acknowledgement, signature, bid/proposal submission, commercial",
        "commitment, payment, cash assertion, award claim, or revenue recognition.",
        "",
    ]
    return "\n".join(lines)
