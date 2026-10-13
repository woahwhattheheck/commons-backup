#!/usr/bin/env python3
"""Build the synthetic evidence packet for UIOWA-031.

SYNTHETIC - NOT A UNIVERSITY FINDING. Every document, identifier, name, date and
figure below is fiction, written so the register has real bytes to point at.

The documents are written to disk as actual files in four formats - markdown,
plain text, JSON and CSV - because the order completes when "every example
document can be found from its register entry". A packet whose documents are
imaginary cannot demonstrate that; the locators have to resolve against
something real, in the shapes an engagement actually receives.

The finding and observation identifiers follow the EV-/OBS-/FND- convention from
`workshare/methodology/23-evidence-confidence.md`.
"""

from __future__ import annotations

import argparse
import json
import os

from evidence_register import (MANIFEST_FIELDS, REGISTER_FIELDS, Packet,
                               save_packet_csv, sha256_of)

# --------------------------------------------------------------------------
# The documents themselves
# --------------------------------------------------------------------------

DOCUMENTS: dict[str, str] = {}

DOCUMENTS["docs/ess-branch-protection-standard-v3.md"] = """# ESS Branch Protection Standard

Synthetic document. Not a University artifact.

## Purpose

This standard describes the protection expected on branches that deploy to
production for Enterprise Systems and Services applications.

## Required checks

Every merge into a deploying branch requires a passing build-and-test status
check and at least one approving review from someone other than the author.
Administrators are not exempt.

## Exceptions

An exception requires a recorded approval from the service owner and expires
after thirty days.

## Review

This standard is reviewed annually by the ESS delivery lead.
"""

DOCUMENTS["docs/ris-privileged-access-standard-v1.md"] = """# RIS Privileged Access Standard

Synthetic document. Not a University artifact.

## Scope

Applies to research information systems holding restricted research data.

## Annual review

Privileged access to each in-scope system is reviewed at least annually. The
reviewer confirms that each account still requires its access and records the
outcome.

## Records

The outcome of each review is retained. This standard does not name the system
of record in which it is retained.
"""

DOCUMENTS["docs/iam-privileged-accounts-query.json"] = json.dumps({
    "_synthetic": "Not a University artifact.",
    "query": {
        "name": "privileged-accounts",
        "definition": "accounts holding the platform administrator role",
        "executed_at": "2026-09-12T11:30:00Z",
        "completeness_basis": "single authoritative query; row count matches console",
    },
    "summary": {"accounts_returned": 14, "second_factor_enrolled": 14},
    "accounts": [{"account_ref": f"SYN-ADM-{i:02d}", "second_factor": True,
                  "role": "platform administrator"} for i in range(1, 15)],
}, indent=2)

DOCUMENTS["docs/ess-deploy-log-2026-08.csv"] = """change_id,deployed_at,application,approver_role,rollback_note,status
CHG-SYN-2041,2026-08-04T09:12:00-05:00,SYN-APP-A,service owner,documented,succeeded
CHG-SYN-2042,2026-08-07T14:30:00-05:00,SYN-APP-A,service owner,documented,succeeded
CHG-SYN-2043,2026-08-11T10:05:00-05:00,SYN-APP-A,delivery lead,documented,succeeded
CHG-SYN-2044,2026-08-14T16:40:00-05:00,SYN-APP-A,service owner,documented,rolled back
CHG-SYN-2045,2026-08-19T08:55:00-05:00,SYN-APP-A,service owner,documented,succeeded
CHG-SYN-2046,2026-08-21T13:20:00-05:00,SYN-APP-A,delivery lead,documented,succeeded
CHG-SYN-2047,2026-08-25T11:10:00-05:00,SYN-APP-A,service owner,documented,succeeded
CHG-SYN-2048,2026-08-27T15:45:00-05:00,SYN-APP-A,service owner,documented,succeeded
CHG-SYN-2049,2026-08-31T09:30:00-05:00,SYN-APP-A,delivery lead,documented,succeeded
"""

DOCUMENTS["docs/interview-note-ess-02.txt"] = """Synthetic interview note. Not a University artifact.

Participant: ESS delivery engineer (role only; no individual is identified)
Date: 2026-09-04
Interviewer: assessment team

The participant stated that review before merge is required across ESS and that
the requirement is enforced by the platform rather than by convention.

The participant was not able to say how many repositories are in scope, and
suggested the delivery lead would know.

On deployment: the participant described a change record for every production
deployment, including urgent ones.

On assisted coding tools: the participant said some engineers use them
individually and that there is no written guidance on reviewing generated code.
"""

DOCUMENTS["docs/joint-controls-memo-v2.md"] = """# Joint Controls Memo

Synthetic document. Not a University artifact.

This memo is referenced by more than one assessment cell on purpose: it
describes a control that spans delivery and identity, so both the ESS software
development cell and the IAM security cell cite it.

## Change approval

A production change requires an approver who is not the author. This applies to
application deployments and to identity platform configuration alike.

## Access to the deployment pipeline

Access to run a production deployment is granted through the identity platform
and is reviewed with the platform's privileged accounts.

## Limitations

This memo describes intent. It does not record whether either practice was
followed in any particular month.
"""

# --------------------------------------------------------------------------
# Manifest: one row per document
# --------------------------------------------------------------------------

MANIFEST = [
    dict(source_id="SRC-SYN-001", title="ESS Branch Protection Standard",
         document_location="docs/ess-branch-protection-standard-v3.md",
         document_version="v3", owner="ESS delivery lead (role)",
         supplied_date="2026-09-08", source_type="policy",
         retention_note="Synthetic. Return/destroy per engagement terms."),
    dict(source_id="SRC-SYN-002", title="RIS Privileged Access Standard",
         document_location="docs/ris-privileged-access-standard-v1.md",
         document_version="v1", owner="RIS security contact (role)",
         supplied_date="2026-09-11", source_type="policy",
         retention_note="Synthetic. Return/destroy per engagement terms."),
    dict(source_id="SRC-SYN-003", title="IAM privileged accounts query export",
         document_location="docs/iam-privileged-accounts-query.json",
         document_version="2026-09-12T11:30Z", owner="IAM operations (role)",
         supplied_date="2026-09-12", source_type="inventory_query",
         retention_note="Synthetic. Contains no real account data."),
    dict(source_id="SRC-SYN-004", title="ESS production deployment log, August 2026",
         document_location="docs/ess-deploy-log-2026-08.csv",
         document_version="2026-08 extract", owner="ESS delivery lead (role)",
         supplied_date="2026-09-09", source_type="change_records",
         retention_note="Synthetic. Return/destroy per engagement terms."),
    dict(source_id="SRC-SYN-005", title="Interview note, ESS delivery engineer",
         document_location="docs/interview-note-ess-02.txt",
         document_version="final", owner="assessment team",
         supplied_date="2026-09-04", source_type="interview",
         retention_note="Synthetic. Role only; no individual identified."),
    dict(source_id="SRC-SYN-006", title="Joint Controls Memo",
         document_location="docs/joint-controls-memo-v2.md",
         document_version="v2", owner="ITS governance (role)",
         supplied_date="2026-09-10", source_type="procedure",
         retention_note="Synthetic. Cited by more than one assessment cell."),
]

# --------------------------------------------------------------------------
# Register: one row per evidence item, pointing into a document
# --------------------------------------------------------------------------

def _e(**kw) -> dict:
    row = {f: "" for f in REGISTER_FIELDS}
    row.update(kw)
    return row


REGISTER = [
    _e(evidence_id="EV-SYN-ESS-SD-POL-001", observation_id="OBS-SYN-ESS-SD-001",
       finding_id="FND-SYN-ESS-SD-001", group="ESS", area="SD",
       source_type="policy", source_ref="ESS Branch Protection Standard v3",
       source_id="SRC-SYN-001", excerpt_locator="section:Required checks",
       practice_supported="Peer review and a passing status check before merge",
       captured_at="2026-09-08T13:10:00Z", represented_period="2026-09-08",
       claim="The standard requires a passing check and a non-author approving review",
       scope_limit="Documented intent; does not establish what any team does",
       directness="INDIRECT", recency="CURRENT", representativeness="POPULATION_UNKNOWN",
       corroboration="SAME_SYSTEM", evidence_state="SUPPORTING", confidence="LOW",
       follow_up="Obtain a branch-protection export for the in-scope repositories"),

    _e(evidence_id="EV-SYN-ESS-SD-INT-002", observation_id="OBS-SYN-ESS-SD-002",
       finding_id="FND-SYN-ESS-SD-001", group="ESS", area="SD",
       source_type="interview", source_ref="Interview note ESS-02",
       source_id="SRC-SYN-005", excerpt_locator="lines:8-10",
       practice_supported="Peer review before merge is enforced by the platform",
       captured_at="2026-09-04T15:00:00Z", represented_period="2026-09-04",
       claim="Participant states review before merge is platform-enforced across ESS",
       scope_limit="One participant, role only; perspective not group-wide practice",
       directness="INDIRECT", recency="CURRENT", representativeness="SINGLE",
       corroboration="SAME_SYSTEM", evidence_state="SUPPORTING", confidence="LOW",
       follow_up="Confirm against an authoritative repository inventory"),

    _e(evidence_id="EV-SYN-ESS-DEP-CHG-003", observation_id="OBS-SYN-ESS-DEP-001",
       finding_id="FND-SYN-ESS-DEP-001", group="ESS", area="DEP",
       source_type="change_records", source_ref="ESS deploy log 2026-08",
       source_id="SRC-SYN-004", excerpt_locator="row:CHG-SYN-2044",
       practice_supported="Production deployments carry an approver and a rollback note",
       captured_at="2026-09-09T10:00:00Z", represented_period="2026-08-01/2026-08-31",
       claim="The rolled-back change of 2026-08-14 carries an approver and a rollback note",
       scope_limit="One month, one application; the window contains no emergency change",
       directness="DIRECT", recency="CURRENT", representativeness="POPULATION_BOUNDED",
       corroboration="NO_CORROBORATION", evidence_state="SUPPORTING", confidence="MODERATE",
       follow_up="Extend across a window containing an emergency change"),

    _e(evidence_id="EV-SYN-RIS-SEC-POL-004", observation_id="OBS-SYN-RIS-SEC-001",
       finding_id="FND-SYN-RIS-SEC-001", group="RIS", area="SEC",
       source_type="policy", source_ref="RIS Privileged Access Standard v1",
       source_id="SRC-SYN-002", excerpt_locator="section:Annual review",
       practice_supported="Annual privileged-access review for in-scope research systems",
       captured_at="2026-09-11T14:20:00Z", represented_period="2026-09-11",
       claim="The standard requires an annual privileged-access review with a recorded outcome",
       scope_limit="Policy intent. The standard names no system of record for the outcome, "
                   "and no completed review was supplied.",
       directness="INDIRECT", recency="CURRENT", representativeness="POPULATION_UNKNOWN",
       corroboration="NO_CORROBORATION", evidence_state="SUPPORTING", confidence="LOW",
       follow_up="Ask which system of record holds completed reviews"),

    _e(evidence_id="EV-SYN-IAM-SEC-INV-005", observation_id="OBS-SYN-IAM-SEC-001",
       finding_id="FND-SYN-IAM-SEC-001", group="IAM", area="SEC",
       source_type="inventory_query", source_ref="privileged-accounts query export",
       source_id="SRC-SYN-003", excerpt_locator="key:summary",
       practice_supported="Second factor on every privileged identity-platform account",
       captured_at="2026-09-12T11:30:00Z", represented_period="2026-09-12",
       claim="All 14 accounts returned by the query have a second factor enrolled",
       scope_limit="Complete for the queried universe at capture time",
       directness="DIRECT", recency="CURRENT", representativeness="POPULATION_BOUNDED",
       corroboration="INDEPENDENT", evidence_state="SUPPORTING", confidence="HIGH",
       universe_definition="Accounts holding the platform administrator role at capture",
       enumerator_authority="Identity platform administrative API",
       completeness_basis="Row count returned matches the platform console count",
       follow_up="Re-run at engagement close to confirm the population is unchanged"),

    # ---- the multi-cell document: SRC-SYN-006 cited from two cells ---------
    _e(evidence_id="EV-SYN-ESS-SD-DOC-006", observation_id="OBS-SYN-ESS-SD-003",
       finding_id="FND-SYN-ESS-SD-002", group="ESS", area="SD",
       source_type="procedure", source_ref="Joint Controls Memo v2",
       source_id="SRC-SYN-006", excerpt_locator="section:Change approval",
       practice_supported="A production change requires a non-author approver",
       captured_at="2026-09-10T09:00:00Z", represented_period="2026-09-10",
       claim="The memo requires a non-author approver for application deployments",
       scope_limit="Describes intent; records no instance of the practice",
       directness="INDIRECT", recency="CURRENT", representativeness="POPULATION_UNKNOWN",
       corroboration="NO_CORROBORATION", evidence_state="SUPPORTING", confidence="LOW",
       follow_up="Sample change records against this requirement"),

    _e(evidence_id="EV-SYN-IAM-SEC-DOC-007", observation_id="OBS-SYN-IAM-SEC-002",
       finding_id="FND-SYN-IAM-SEC-002", group="IAM", area="SEC",
       source_type="procedure", source_ref="Joint Controls Memo v2",
       source_id="SRC-SYN-006",
       excerpt_locator="section:Access to the deployment pipeline",
       practice_supported="Deployment access is granted and reviewed through the identity platform",
       captured_at="2026-09-10T09:00:00Z", represented_period="2026-09-10",
       claim="The memo places deployment access under the identity platform's privileged review",
       scope_limit="Same document as EV-SYN-ESS-SD-DOC-006, different section. Intent only.",
       directness="INDIRECT", recency="CURRENT", representativeness="POPULATION_UNKNOWN",
       corroboration="SAME_SYSTEM", evidence_state="SUPPORTING", confidence="LOW",
       follow_up="Confirm deployment access appears in the privileged-account query"),

    _e(evidence_id="EV-SYN-ESS-AI-INT-008", observation_id="OBS-SYN-ESS-AI-001",
       finding_id="FND-SYN-ESS-AI-001", group="ESS", area="AI",
       source_type="interview", source_ref="Interview note ESS-02",
       source_id="SRC-SYN-005", excerpt_locator="lines:16-17",
       practice_supported="Guidance on reviewing AI-generated code",
       captured_at="2026-09-04T15:00:00Z", represented_period="2026-09-04",
       claim="Participant reports individual use of assisted coding tools and no written "
             "guidance on reviewing generated code",
       scope_limit="One participant; no policy or usage record reviewed",
       directness="INDIRECT", recency="CURRENT", representativeness="SINGLE",
       corroboration="NO_CORROBORATION", evidence_state="NO_EVIDENCE_OBSERVED",
       confidence="NOT_EVIDENCED",
       follow_up="Ask whether written guidance exists and who owns it"),
]


def build(root: str) -> Packet:
    os.makedirs(root, exist_ok=True)
    for rel, text in DOCUMENTS.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text if text.endswith("\n") else text + "\n")

    manifest = []
    for d in MANIFEST:
        row = {f: "" for f in MANIFEST_FIELDS}
        row.update(d)
        # The digest is computed from the bytes actually written, so a document
        # edited after registration is detectable rather than assumed intact.
        row["sha256"] = sha256_of(os.path.join(root, row["document_location"]))
        manifest.append(row)

    return Packet(root=root, manifest=manifest, register=[dict(r) for r in REGISTER])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write the synthetic evidence packet.")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "packet"))
    a = ap.parse_args(argv)
    p = build(a.out)
    for path in save_packet_csv(p, a.out):
        print(f"wrote {path}")
    print(f"documents: {len(p.manifest)}  entries: {len(p.register)}  "
          f"multi-cell: {', '.join(p.multi_cell_documents()) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
