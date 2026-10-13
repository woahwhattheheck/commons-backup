"""Build the two-stage enrollment demo packet (append-only)."""

from __future__ import annotations

import json
import os

try:
    from .canonical import MANIFEST_FIELDS, REGISTER_FIELDS, SCHEMA
    from .timeline import DemoError, empty_register_row, sha256_text, write_csv
except ImportError:
    from canonical import MANIFEST_FIELDS, REGISTER_FIELDS, SCHEMA
    from timeline import DemoError, empty_register_row, sha256_text, write_csv

HERE = os.path.dirname(os.path.abspath(__file__))

DOC_CAL = """SYNTHETIC ESS registration calendar v1
Window-NEW: Spring add/drop 2026-W12 (relative week 12 of the planning calendar).
Window-OLD: Spring add/drop 2026-W10.
This file is fiction. Not a University calendar.
"""
DOC_DEP = """SYNTHETIC ESS deployment config excerpt
registration_window_id = Window-OLD
pipeline applies the calendar id at deploy time.
This file is fiction. Not a live system export.
"""
DOC_IAM = """SYNTHETIC IAM group-provisioning job
job: student-enrolled-group-sync
calendar_window_id = Window-OLD
membership changes fire at Window-OLD close, not Window-NEW.
This file is fiction. Not a live IAM export.
"""
DOC_OPS = """SYNTHETIC operational outcome note
Relative week 13: Window-NEW closed; IAM job still keyed to Window-OLD.
Enrolled-student group membership was not refreshed for the new window.
This file is fiction. Not an operational incident.
"""


def _manifest(source_id, title, location, version, supplied, source_type, body):
    return {
        "source_id": source_id,
        "title": title,
        "document_location": location,
        "document_version": version,
        "owner": "SYNTHETIC_FIXTURE",
        "supplied_date": supplied,
        "source_type": source_type,
        "sha256": sha256_text(body),
        "retention_note": "synthetic; not University evidence",
    }


def _row(**kwargs):
    row = empty_register_row()
    row.update(kwargs)
    row["custodian_or_owner"] = row.get("custodian_or_owner") or "SYNTHETIC_FIXTURE"
    return {k: row[k] for k in REGISTER_FIELDS}


def stage1():
    docs = {
        "documents/ess-registration-calendar-v1.txt": DOC_CAL,
        "documents/ess-deploy-config-excerpt.txt": DOC_DEP,
    }
    manifest = [
        _manifest("SRC-ESS-CAL-01", "ESS registration calendar v1", "documents/ess-registration-calendar-v1.txt", "1", "2026-W10", "policy", DOC_CAL),
        _manifest("SRC-ESS-DEP-01", "ESS deploy config excerpt", "documents/ess-deploy-config-excerpt.txt", "1", "2026-W10", "configuration_export", DOC_DEP),
    ]
    register = [
        _row(
            evidence_id="EV-ESS-SD-001",
            observation_id="OBS-ESS-SD-001",
            finding_id="FND-ESS-SD-001",
            group="ESS",
            area="SD",
            source_type="policy",
            source_ref="ESS registration calendar v1",
            content_digest=sha256_text(DOC_CAL),
            captured_at="2026-W10",
            represented_period="2026-W10",
            claim="The published ESS add/drop window moved from Window-OLD (W10) to Window-NEW (W12).",
            scope_limit="Synthetic calendar only; not a University publication.",
            directness="DIRECT",
            recency="CURRENT",
            representativeness="SINGLE",
            corroboration="NO_CORROBORATION",
            evidence_state="SUPPORTING",
            confidence="MODERATE",
            source_id="SRC-ESS-CAL-01",
            excerpt_locator="line:Window-NEW",
            practice_supported="Enrollment-period calendar is an explicit ESS configuration.",
        ),
        _row(
            evidence_id="EV-ESS-DEP-001",
            observation_id="OBS-ESS-DEP-001",
            finding_id="FND-ESS-DEP-001",
            group="ESS",
            area="DEP",
            source_type="configuration_export",
            source_ref="ESS deploy config excerpt",
            content_digest=sha256_text(DOC_DEP),
            captured_at="2026-W10",
            represented_period="2026-W10",
            claim="The ESS deployment pipeline still pins registration_window_id to Window-OLD.",
            scope_limit="One synthetic excerpt; rollback/emergency path unknown.",
            directness="DIRECT",
            recency="CURRENT",
            representativeness="SINGLE",
            corroboration="SAME_SYSTEM",
            evidence_state="SUPPORTING",
            confidence="MODERATE",
            source_id="SRC-ESS-DEP-01",
            excerpt_locator="line:registration_window_id",
            practice_supported="Deployed ESS config names the enrollment window it uses.",
        ),
        _row(
            evidence_id="EV-IAM-SEC-001",
            observation_id="OBS-IAM-SEC-001",
            finding_id="FND-IAM-SEC-001",
            group="IAM",
            area="SEC",
            source_type="review_note",
            source_ref="Review note RN-001",
            content_digest="NOT_RETAINED_SYNTHETIC_NOTE",
            captured_at="2026-W10",
            represented_period="2026-W10",
            claim="No authorized evidence yet shows whether IAM group provisioning is keyed to Window-NEW.",
            scope_limit="Absence of evidence is not evidence of absence.",
            directness="INDIRECT",
            recency="CURRENT",
            representativeness="UNKNOWN",
            corroboration="NO_CORROBORATION",
            evidence_state="HOLD",
            confidence="NOT_EVIDENCED",
            follow_up="Obtain the IAM provisioning job definition.",
            source_id="SRC-ESS-CAL-01",
            excerpt_locator="line:Window-NEW",
            practice_supported="",
        ),
    ]
    events = [
        {"id": "EVT-001", "week": "2026-W10", "kind": "ess_calendar_published", "source_id": "SRC-ESS-CAL-01"},
        {"id": "EVT-002", "week": "2026-W10", "kind": "review_note_iam_unknown", "source_id": "SRC-ESS-CAL-01"},
    ]
    return docs, manifest, register, events


def stage2(stage1_pack):
    docs, manifest, register, events = stage1_pack
    docs = dict(docs)
    docs["documents/iam-group-sync-job.txt"] = DOC_IAM
    docs["documents/ops-outcome-note.txt"] = DOC_OPS
    manifest = list(manifest) + [
        _manifest("SRC-IAM-JOB-02", "IAM group-provisioning job", "documents/iam-group-sync-job.txt", "1", "2026-W13", "configuration_export", DOC_IAM),
        _manifest("SRC-OPS-OUT-03", "Operational outcome note", "documents/ops-outcome-note.txt", "1", "2026-W13", "change_records", DOC_OPS),
    ]
    register = list(register) + [
        _row(
            evidence_id="EV-IAM-SEC-002",
            observation_id="OBS-IAM-SEC-002",
            finding_id="FND-IAM-SEC-001",
            group="IAM",
            area="SEC",
            source_type="configuration_export",
            source_ref="IAM group-provisioning job",
            content_digest=sha256_text(DOC_IAM),
            captured_at="2026-W13",
            represented_period="2026-W13",
            claim="The IAM student-enrolled-group-sync job is still keyed to Window-OLD, not Window-NEW.",
            scope_limit="Synthetic job text only; not a live directory export.",
            directness="DIRECT",
            recency="CURRENT",
            representativeness="SINGLE",
            corroboration="SAME_SYSTEM",
            evidence_state="SUPPORTING",
            confidence="MODERATE",
            source_id="SRC-IAM-JOB-02",
            excerpt_locator="line:calendar_window_id",
            practice_supported="IAM membership refresh is bound to a named enrollment window.",
        ),
        _row(
            evidence_id="EV-IAM-SEC-003",
            observation_id="OBS-IAM-SEC-003",
            finding_id="FND-IAM-SEC-001",
            group="IAM",
            area="SEC",
            source_type="change_records",
            source_ref="Operational outcome note",
            content_digest=sha256_text(DOC_OPS),
            captured_at="2026-W13",
            represented_period="2026-W13",
            claim="After Window-NEW closed, the IAM job did not refresh enrolled-student group membership.",
            scope_limit="One synthetic outcome note; not an incident record.",
            directness="DIRECT",
            recency="CURRENT",
            representativeness="SINGLE",
            corroboration="SAME_SYSTEM",
            evidence_state="SUPPORTING",
            confidence="MODERATE",
            source_id="SRC-OPS-OUT-03",
            excerpt_locator="line:Window-NEW closed",
            practice_supported="Operational outcome of a window mismatch is observable.",
        ),
    ]
    events = list(events) + [
        {"id": "EVT-003", "week": "2026-W13", "kind": "iam_job_supplied", "source_id": "SRC-IAM-JOB-02"},
        {"id": "EVT-004", "week": "2026-W13", "kind": "operational_outcome", "source_id": "SRC-OPS-OUT-03"},
    ]
    return docs, manifest, register, events


def write_stage(root, docs, manifest, register, events):
    os.makedirs(os.path.join(root, "documents"), exist_ok=True)
    for rel, body in docs.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
    with open(os.path.join(root, "manifest.csv"), "w", encoding="utf-8") as fh:
        fh.write(write_csv(MANIFEST_FIELDS, manifest))
    with open(os.path.join(root, "register.csv"), "w", encoding="utf-8") as fh:
        fh.write(write_csv(REGISTER_FIELDS, register))
    with open(os.path.join(root, "events.jsonl"), "w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, sort_keys=True) + "\n")
    with open(os.path.join(root, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema": SCHEMA, "synthetic": True}, fh, indent=2)
        fh.write("\n")


def materialize(out_root):
    if os.path.exists(out_root):
        raise DemoError("output already exists (%s)" % out_root)
    os.makedirs(out_root)
    s1 = stage1()
    s2 = stage2(s1)
    write_stage(os.path.join(out_root, "stage1"), *s1)
    write_stage(os.path.join(out_root, "stage2"), *s2)
    return out_root
