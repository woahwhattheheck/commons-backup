#!/usr/bin/env python3
"""Populate the twelve-cell assessment dataset (UIOWA-035).

SYNTHETIC - NOT A UNIVERSITY FINDING. Every group characterisation, evidence
reference, strength, gap and next step below is fiction.

All twelve cells are present, because the order completes when all twelve *can*
be populated and because an absent cell is how a gap quietly leaves a report.
Nine are assessed. Three are not, and they are deliberately the three different
reasons a cell can lack a position on the scale:

  RIS/ai_readiness   unassessed             never scheduled
  IAM/ai_readiness   insufficient_evidence  we looked; nothing supported a level
  RIS/deployment     not_applicable         the practice does not apply here

Those three are the point of the exercise. None of them is a low level, none
carries a rank, and none may acquire one by being exported and reopened.

Evidence references use the `EV-SYN-...` identifiers from the UIOWA-031 packet
so the two lanes tell one coherent fictional story.
"""

from __future__ import annotations

import argparse
import os

from matrix_dataset import (ASSESSED, INSUFFICIENT_EVIDENCE, LEVEL_LABELS,
                            NOT_APPLICABLE, UNASSESSED, Matrix, edit_cell,
                            save_csv, save_json)

CELLS = [
    ("ESS", "development", ASSESSED, 4,
     ["Merges to the two sampled repositories require a passing check and a non-author review",
      "The requirement is enforced by platform configuration, not convention"],
     ["Repository population was never enumerated, so coverage is a sample statement"],
     "A configuration export and a 22-merge sample agree, and an interview describes the same "
     "practice. Repeatable across the window sampled.",
     ["Obtain an authoritative repository inventory",
      "Re-sample after the inventory to state coverage for the group"],
     ["EV-SYN-ESS-SD-POL-001", "EV-SYN-ESS-SD-INT-002"],
     "Two ESS repositories over one quarter.", ""),

    ("ESS", "security", ASSESSED, 2,
     ["A dependency-scanning stage is defined in the sampled pipeline"],
     ["No record was observed of how scanner findings are triaged or closed",
      "No owner is named for the queue"],
     "The stage exists and can be produced on request. Nothing supplied shows findings being "
     "worked, which is what separates a defined practice from a practised one.",
     ["Supply six months of scanner findings with their disposition",
      "Name the owner of the triage queue"],
     ["EV-SYN-ESS-SEC-CFG-004"],
     "Pipeline definition only; no triage records reviewed.", ""),

    ("ESS", "deployment", ASSESSED, 4,
     ["All nine production deployments in the sampled month carry a change reference, "
      "an approver and a rollback note",
      "The one rolled-back change carries the same record as the successful ones"],
     ["The window contains no emergency change, so the exception path is untested"],
     "A complete month of records for one application, consistent across every row including "
     "the rollback.",
     ["Extend the sample across a window containing an emergency change"],
     ["EV-SYN-ESS-DEP-CHG-003"],
     "One month, one application.", ""),

    ("ESS", "ai_readiness", ASSESSED, 1,
     [],
     ["Assisted coding tools are in individual use with no group-level guidance",
      "No owner is named for guidance on reviewing generated code"],
     "Participants describe what they personally do and the descriptions do not agree. No "
     "written guidance was produced on request.",
     ["Decide and write down how generated code is reviewed before it reaches a production "
      "branch, and name the owner of that guidance"],
     ["EV-SYN-ESS-AI-INT-008"],
     "Two interview statements; no policy or usage record reviewed.", ""),

    ("RIS", "development", ASSESSED, 3,
     ["A documented intake-to-release path exists and the one traced change followed it"],
     ["Review sign-off was recorded after deployment rather than before",
      "A single traced change cannot establish whether that ordering is typical"],
     "One real instance of the practice, with records that are not the procedure document "
     "itself. Whether it repeats is not established.",
     ["Trace five further RIS changes, including at least one urgent change"],
     ["EV-SYN-RIS-SD-CHG-007"],
     "A single traced change.", ""),

    ("RIS", "security", ASSESSED, 2,
     ["A published standard requires an annual privileged-access review"],
     ["No completed review record was observed for any in-scope system",
      "The standard names no system of record in which outcomes are retained"],
     "The standard exists and can be produced. Nothing supplied shows a review being carried "
     "out, and absence of a record in the material supplied is not evidence the review did "
     "not happen.",
     ["Establish where completed reviews are retained and make that part of the standard",
      "Provide the most recent completed review for two systems"],
     ["EV-SYN-RIS-SEC-POL-004"],
     "Policy intent only.", ""),

    # not_applicable - the practice does not apply, nothing is missing
    ("RIS", "deployment", NOT_APPLICABLE, None, [], [],
     "", [],
     [],
     "This group's in-scope systems are vendor-hosted and the group does not perform "
     "deployments. Nothing is missing; the practice does not apply to how it operates.",
     ""),

    # unassessed - never reached
    ("RIS", "ai_readiness", UNASSESSED, None, [], [],
     "", [],
     [],
     "No session was held and no evidence of any kind was supplied. This is a statement "
     "about the evidence collected, not about the group.",
     "Schedule the AI-readiness session with RIS, or record the cell as out of scope by "
     "agreement."),

    ("IAM", "development", ASSESSED, 4,
     ["Connector changes are developed in version control with peer review recorded"],
     ["Configuration changes made directly in the vendor console are outside version control"],
     "Every merge in the quarter carries an approving review, over a documented population "
     "of one repository.",
     ["Establish how direct console configuration changes are reviewed"],
     ["EV-SYN-IAM-SD-CFG-012"],
     "One connector repository over one quarter.", ""),

    ("IAM", "security", ASSESSED, 5,
     ["All 14 accounts in the enumerated privileged population had a second factor at "
      "capture time",
      "The query definition and its completeness basis are both recorded"],
     ["The enumeration is a point in time and the population may change"],
     "An authoritative bounded query whose completeness is itself documented, corroborated "
     "by the platform policy export. The strongest evidence in this engagement.",
     ["Re-run the enumeration at engagement close to confirm the population is unchanged"],
     ["EV-SYN-IAM-SEC-INV-005", "EV-SYN-IAM-SEC-DOC-007"],
     "Point-in-time enumeration, 2026-09-12.", ""),

    ("IAM", "deployment", ASSESSED, 2,
     ["A memo places deployment access under the identity platform's privileged review"],
     ["Interviews and the change export disagree: 3 of 14 emergency changes carry no "
      "linked record",
      "The conflict is unresolved and the evidence cannot distinguish an incomplete export "
      "from an undocumented exception path"],
     "The intended practice is stated and recognised. The records contradict it for emergency "
     "changes, so nothing here shows the practice running.",
     ["Identify the system of record for emergency identity changes and confirm whether the "
      "supplied export is complete for that path - investigate before changing the process"],
     ["EV-SYN-IAM-DEP-INT-015", "EV-SYN-IAM-DEP-CHG-016"],
     "The conflict is open.", ""),

    # insufficient_evidence - we looked, nothing supported a level
    ("IAM", "ai_readiness", INSUFFICIENT_EVIDENCE, None, [], [],
     "", [],
     ["EV-SYN-IAM-AI-SEARCH-017"],
     "A session was held and a document search was run. Neither produced material that "
     "supports any level. This is not a low level; it is an absence of evidence.",
     "Ask whether any AI use, planned or informal, exists in IAM and who would know."),
]


def build() -> Matrix:
    m = Matrix.empty()
    for (group, area, status, rank, strengths, gaps, rationale, next_steps,
         evidence, scope, follow_up) in CELLS:
        changes = dict(assessment_status=status, strengths=strengths, gaps=gaps,
                       rationale=rationale, next_steps=next_steps,
                       evidence_refs=evidence, scope_limit=scope,
                       follow_up_question=follow_up)
        if status == ASSESSED:
            changes["maturity_rank"] = rank
            changes["maturity_label"] = LEVEL_LABELS[rank]
        edit_cell(m, group, area, **changes)
    return m


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write the populated twelve-cell dataset.")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "dataset"))
    a = ap.parse_args(argv)
    m = build()
    print("wrote " + save_json(m, os.path.join(a.out, "matrix.json")))
    print("wrote " + save_csv(m, os.path.join(a.out, "matrix.csv")))
    c = m.counts()
    print(f"cells: {len(m.cells)}  assessed: {c[ASSESSED]}  "
          f"unassessed: {c[UNASSESSED]}  not_applicable: {c[NOT_APPLICABLE]}  "
          f"insufficient_evidence: {c[INSUFFICIENT_EVIDENCE]}")
    issues = m.validate()
    print(f"validation issues: {len(issues)}")
    for i in issues:
        print("  " + i)
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
