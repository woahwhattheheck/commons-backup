from __future__ import annotations

from collections import defaultdict
from typing import Any

from .model import (
    DELIVERY_MODES, REQUIRED_PATHWAYS, SCHEMA_VERSION, SERVICES,
    _aware_timestamp, _curriculum_valid, _finite_number, _is_int,
    _list_of_nonempty_strings, _report, _valid_id,
)

def validate_bundle(bundle: Any) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(bundle, dict):
        return _report(bundle, ["bundle must be a JSON object"], [])

    if bundle.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must equal {SCHEMA_VERSION}")
    if not _valid_id(bundle.get("program_id")):
        errors.append("program_id must be a non-empty stable identifier")
    planning_target = bundle.get("planning_target")
    if not _is_int(planning_target) or planning_target <= 0:
        errors.append("planning_target must be a positive integer")
        planning_target = 0

    curricula = bundle.get("curricula")
    if not isinstance(curricula, dict):
        errors.append("curricula must be an object")
        curricula = {}
    service_a = curricula.get("service_a") if isinstance(curricula, dict) else None
    service_b = curricula.get("service_b") if isinstance(curricula, dict) else None
    if not isinstance(service_a, dict):
        errors.append("curricula.service_a must map all five pathways")
        service_a = {}
    missing_pathways = [p for p in REQUIRED_PATHWAYS if p not in service_a]
    extra_pathways = sorted(set(service_a) - set(REQUIRED_PATHWAYS))
    if missing_pathways:
        errors.append("missing Service A pathway curriculum: " + ", ".join(missing_pathways))
    if extra_pathways:
        errors.append("unknown Service A pathway curriculum: " + ", ".join(extra_pathways))
    for pathway in REQUIRED_PATHWAYS:
        if pathway in service_a:
            _curriculum_valid(f"curricula.service_a.{pathway}", service_a[pathway], errors)
    _curriculum_valid("curricula.service_b", service_b, errors)

    instructors = bundle.get("instructors")
    if not isinstance(instructors, list):
        errors.append("instructors must be a list")
        instructors = []
    instructor_by_id: dict[str, dict[str, Any]] = {}
    capability: dict[str, set[str]] = defaultdict(set)
    for idx, row in enumerate(instructors):
        prefix = f"instructors[{idx}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        iid = row.get("instructor_id")
        if not _valid_id(iid):
            errors.append(f"{prefix}.instructor_id is invalid")
            continue
        if iid in instructor_by_id:
            errors.append(f"duplicate instructor_id: {iid}")
            continue
        modes = row.get("delivery_modes")
        if not isinstance(modes, list) or not modes or any(mode not in DELIVERY_MODES for mode in modes):
            errors.append(f"{prefix}.delivery_modes must use live_remote/in_person")
            modes = []
        coverage = row.get("coverage")
        if not isinstance(coverage, list) or not coverage:
            errors.append(f"{prefix}.coverage must be non-empty")
            coverage = []
        allowed_coverage = set(REQUIRED_PATHWAYS) | {"service_b"}
        unknown = sorted({str(x) for x in coverage if x not in allowed_coverage})
        if unknown:
            errors.append(f"{prefix}.coverage contains unknown values: {', '.join(unknown)}")
        qualifications = row.get("qualifications")
        if not _list_of_nonempty_strings(qualifications):
            errors.append(f"{prefix}.qualifications must be a non-empty string list")
        instructor_by_id[iid] = row
        for scope in coverage:
            if scope in allowed_coverage:
                capability[scope].update(modes)

    for pathway in REQUIRED_PATHWAYS:
        missing_modes = sorted(DELIVERY_MODES - capability[pathway])
        if missing_modes:
            errors.append(f"pathway {pathway} lacks instructor capability for: {', '.join(missing_modes)}")
    missing_b_modes = sorted(DELIVERY_MODES - capability["service_b"])
    if missing_b_modes:
        errors.append(f"Service B lacks instructor capability for: {', '.join(missing_b_modes)}")

    cohorts = bundle.get("cohorts")
    if not isinstance(cohorts, list):
        errors.append("cohorts must be a list")
        cohorts = []
    cohort_ids: set[str] = set()
    cohort_scope: dict[str, str] = {}
    session_by_id: dict[str, dict[str, Any]] = {}
    session_cohort: dict[str, str] = {}
    planned_seats = 0
    pathway_sessions: dict[str, int] = defaultdict(int)
    service_b_sessions = 0
    planned_minutes = 0
    for idx, cohort in enumerate(cohorts):
        prefix = f"cohorts[{idx}]"
        if not isinstance(cohort, dict):
            errors.append(f"{prefix} must be an object")
            continue
        cid = cohort.get("cohort_id")
        if not _valid_id(cid):
            errors.append(f"{prefix}.cohort_id is invalid")
            continue
        if cid in cohort_ids:
            errors.append(f"duplicate cohort_id: {cid}")
        cohort_ids.add(cid)
        service = cohort.get("service")
        if service not in SERVICES:
            errors.append(f"{prefix}.service must be A or B")
        pathway = cohort.get("pathway")
        if service == "A":
            if pathway not in REQUIRED_PATHWAYS:
                errors.append(f"{prefix}.pathway must be one of the five Service A pathways")
        elif pathway is not None:
            errors.append(f"{prefix}.pathway must be omitted/null for Service B")
        if service == "A" and pathway in REQUIRED_PATHWAYS:
            cohort_scope[cid] = pathway
        elif service == "B":
            cohort_scope[cid] = "service_b"
        seat_capacity = cohort.get("seat_capacity")
        if not _is_int(seat_capacity) or seat_capacity <= 0:
            errors.append(f"{prefix}.seat_capacity must be a positive integer")
        else:
            planned_seats += seat_capacity
        sessions = cohort.get("sessions")
        if not isinstance(sessions, list) or not sessions:
            errors.append(f"{prefix}.sessions must be non-empty")
            sessions = []
        for sidx, session in enumerate(sessions):
            sp = f"{prefix}.sessions[{sidx}]"
            if not isinstance(session, dict):
                errors.append(f"{sp} must be an object")
                continue
            sid = session.get("session_id")
            if not _valid_id(sid):
                errors.append(f"{sp}.session_id is invalid")
                continue
            if sid in session_by_id:
                errors.append(f"duplicate session_id: {sid}")
                continue
            iid = session.get("instructor_id")
            if iid not in instructor_by_id:
                errors.append(f"{sp}.instructor_id references unknown instructor")
            mode = session.get("delivery_mode")
            if mode not in DELIVERY_MODES:
                errors.append(f"{sp}.delivery_mode must be live_remote or in_person")
            if not _aware_timestamp(session.get("scheduled_at")):
                errors.append(f"{sp}.scheduled_at must be timezone-aware ISO-8601")
            duration = session.get("scheduled_minutes")
            if not _is_int(duration) or duration <= 0:
                errors.append(f"{sp}.scheduled_minutes must be a positive integer")
            else:
                planned_minutes += duration
            if iid in instructor_by_id and mode in DELIVERY_MODES:
                row = instructor_by_id[iid]
                modes = row.get("delivery_modes", [])
                scope = pathway if service == "A" else "service_b"
                if mode not in modes or scope not in row.get("coverage", []):
                    errors.append(f"{sp} instructor is not qualified for {scope}/{mode}")
            session_by_id[sid] = session
            session_cohort[sid] = cid
            scope = pathway if service == "A" else "service_b"
            if service == "A" and pathway in REQUIRED_PATHWAYS:
                pathway_sessions[pathway] += 1
            elif service == "B":
                service_b_sessions += 1

    for pathway in REQUIRED_PATHWAYS:
        if pathway_sessions[pathway] == 0:
            errors.append(f"no planned Service A session for pathway: {pathway}")
    if service_b_sessions == 0:
        errors.append("no planned Service B session")

    participants = bundle.get("participants")
    if not isinstance(participants, list):
        errors.append("participants must be a list")
        participants = []
    participant_ids: set[str] = set()
    enrollment: dict[str, set[str]] = defaultdict(set)
    for idx, row in enumerate(participants):
        prefix = f"participants[{idx}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        pid = row.get("participant_id")
        if isinstance(pid, str) and "@" in pid:
            errors.append(f"{prefix}.participant_id must be opaque, not an email address")
        if not _valid_id(pid):
            errors.append(f"{prefix}.participant_id is invalid")
            continue
        if pid in participant_ids:
            errors.append(f"duplicate participant_id: {pid}")
        participant_ids.add(pid)
        enrolled = row.get("cohort_ids")
        if not isinstance(enrolled, list) or not enrolled:
            errors.append(f"{prefix}.cohort_ids must be non-empty")
            enrolled = []
        for cid in enrolled:
            if cid not in cohort_ids:
                errors.append(f"{prefix}.cohort_ids references unknown cohort: {cid}")
            elif cid in enrollment[pid]:
                errors.append(f"{prefix}.cohort_ids duplicates cohort: {cid}")
            enrollment[pid].add(cid)

    attendance = bundle.get("attendance", [])
    if not isinstance(attendance, list):
        errors.append("attendance must be a list")
        attendance = []
    attendance_keys: set[tuple[str, str]] = set()
    attended_minutes = 0
    complete_attendance = 0
    for idx, row in enumerate(attendance):
        prefix = f"attendance[{idx}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        pid = row.get("participant_id")
        sid = row.get("session_id")
        if pid not in participant_ids:
            errors.append(f"{prefix}.participant_id references unknown participant")
        if sid not in session_by_id:
            errors.append(f"{prefix}.session_id references unknown session")
        elif pid in participant_ids:
            cid = session_cohort.get(str(sid))
            if cid is not None and cid not in enrollment.get(str(pid), set()):
                errors.append(f"{prefix} participant is not enrolled in session cohort: {cid}")
        key = (str(pid), str(sid))
        if key in attendance_keys:
            errors.append(f"duplicate attendance row: {pid}/{sid}")
        attendance_keys.add(key)
        present = row.get("present_minutes")
        if not _is_int(present) or present < 0:
            errors.append(f"{prefix}.present_minutes must be a non-negative integer")
            continue
        if sid in session_by_id:
            scheduled = session_by_id[sid].get("scheduled_minutes")
            if _is_int(scheduled) and present > scheduled:
                errors.append(f"{prefix}.present_minutes exceeds scheduled_minutes")
            elif _is_int(scheduled) and scheduled > 0:
                attended_minutes += present
                if present * 100 >= scheduled * 80:
                    complete_attendance += 1

    assessments = bundle.get("assessments", [])
    if not isinstance(assessments, list):
        errors.append("assessments must be a list")
        assessments = []
    assessment_keys: set[tuple[str, str]] = set()
    assessment_deltas: list[float] = []
    for idx, row in enumerate(assessments):
        prefix = f"assessments[{idx}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        pid = row.get("participant_id")
        scope = row.get("scope")
        if pid not in participant_ids:
            errors.append(f"{prefix}.participant_id references unknown participant")
        allowed_scopes = set(REQUIRED_PATHWAYS) | {"service_b"}
        if scope not in allowed_scopes:
            errors.append(f"{prefix}.scope is invalid")
        elif pid in participant_ids:
            participant_scopes = {
                cohort_scope[cid]
                for cid in enrollment.get(str(pid), set())
                if cid in cohort_scope
            }
            if scope not in participant_scopes:
                errors.append(f"{prefix} scope is not covered by participant enrollment: {scope}")
        key = (str(pid), str(scope))
        if key in assessment_keys:
            errors.append(f"duplicate assessment row: {pid}/{scope}")
        assessment_keys.add(key)
        pre = _finite_number(row.get("pre_score"))
        post = _finite_number(row.get("post_score"))
        if pre is None or not 0 <= pre <= 100:
            errors.append(f"{prefix}.pre_score must be finite and within 0..100")
        if post is None or not 0 <= post <= 100:
            errors.append(f"{prefix}.post_score must be finite and within 0..100")
        if pre is not None and post is not None and 0 <= pre <= 100 and 0 <= post <= 100:
            assessment_deltas.append(post - pre)

    reporting = bundle.get("reporting")
    if not isinstance(reporting, dict):
        errors.append("reporting must be an object")
        reporting = {}
    if not _list_of_nonempty_strings(reporting.get("outcome_fields")):
        errors.append("reporting.outcome_fields must be a non-empty string list")
    if not _list_of_nonempty_strings(reporting.get("record_retention_controls")):
        errors.append("reporting.record_retention_controls must be a non-empty string list")
    if not _list_of_nonempty_strings(reporting.get("accessibility_controls")):
        errors.append("reporting.accessibility_controls must be a non-empty string list")

    if planning_target and planned_seats < planning_target:
        warnings.append(
            f"planned seat capacity {planned_seats} is below planning target {planning_target}; "
            "the target is planning evidence, not a guaranteed participant minimum"
        )
    if participants and len(participants) > planned_seats:
        errors.append("participant count exceeds aggregate planned seat capacity")
    if not attendance:
        warnings.append("no attendance evidence yet; bundle is planning-only for attendance")
    if not assessments:
        warnings.append("no assessment evidence yet; bundle is planning-only for outcomes")

    stats = {
        "planning_target": planning_target,
        "planned_seats": planned_seats,
        "planned_capacity_ratio": round(planned_seats / planning_target, 6) if planning_target else None,
        "participants": len(participant_ids),
        "cohorts": len(cohort_ids),
        "sessions": len(session_by_id),
        "planned_instruction_minutes": planned_minutes,
        "attendance_records": len(attendance_keys),
        "attendance_records_at_least_80_percent": complete_attendance,
        "attended_minutes": attended_minutes,
        "assessment_records": len(assessment_keys),
        "average_assessment_delta": round(sum(assessment_deltas) / len(assessment_deltas), 6) if assessment_deltas else None,
        "service_a_session_counts": {p: pathway_sessions[p] for p in REQUIRED_PATHWAYS},
        "service_b_session_count": service_b_sessions,
    }
    coverage = {
        "required_service_a_pathways": list(REQUIRED_PATHWAYS),
        "service_a_curriculum_complete": not missing_pathways and not extra_pathways,
        "service_a_delivery_modes": {p: sorted(capability[p]) for p in REQUIRED_PATHWAYS},
        "service_b_delivery_modes": sorted(capability["service_b"]),
        "routine_remote_and_requested_in_person_capability": all(
            DELIVERY_MODES <= capability[scope] for scope in (*REQUIRED_PATHWAYS, "service_b")
        ),
    }
    return _report(bundle, errors, warnings, stats=stats, coverage=coverage)

