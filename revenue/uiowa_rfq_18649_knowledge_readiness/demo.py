#!/usr/bin/env python3
"""Generate the fully fictional knowledge collection and run before/after rehearsal.

All people, services, assertions, dates, relevance judgments and repairs below
are invented exercises, not facts about the University of Iowa. ESS/RIS/IAM are
partition labels aligned to the work order, not inventories of actual services.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
from readiness import assess, digest, write_outputs


def document(doc_id, group, title, content, facts, **overrides):
    content = content.strip() + "\n"
    assertions = []
    for scope, key, value, line in facts:
        assertions.append({"scope": scope, "key": key, "value": value,
                           "start_line": line, "end_line": line,
                           "quote": content.splitlines()[line - 1]})
    return {"id": doc_id, "group": group, "title": title, "revision": "1",
            "status": "active", "content": content, "sha256": digest(content),
            "source_locator": f"synthetic-collection/{doc_id}",
            "captured_on": "2026-09-18", "reviewed_on": "2026-09-10",
            "review_interval_days": 30, "owner": f"Fictional {group} documentation steward",
            "access_semantics": "Fictional assessment-team readership; recorded metadata only",
            "assertions": assertions, **overrides}


def query(query_id, group, question, scope, keys, relevant, top_k=3):
    return {"id": query_id, "group": group, "question": question, "top_k": top_k,
            "required_facts": [{"scope": scope, "key": key} for key in keys],
            "relevant_document_ids": relevant}


def snapshots():
    docs = [
        document("ESS-RETRY", "ESS", "Registration retry guidance", """
# Synthetic registration retry guidance
The registration worker retry limit is three attempts.
After the third unsuccessful attempt, preserve the work item for triage.
This record describes an invented exercise, not a deployed University service.
""", [("registration", "retry_limit", "three attempts", 2)]),
        document("ESS-OLD", "ESS", "Registration support handbook", """
# Synthetic registration support handbook
The registration worker retry limit is five attempts.
This older active record has not been reconciled with the current guidance.
""", [("registration", "retry_limit", "five attempts", 2)], reviewed_on="2025-01-10"),
        document("ESS-TERMS", "ESS", "Registration terms and examples", """
# Synthetic registration glossary
Registration means enrolling a fictional student in a fictional class.
This document intentionally contains no retry procedure or numerical limit.
""", []),
        document("RIS-BUDGET", "RIS", "Research submission budget validation", """
# Synthetic research submission budget validation
Budget validation requires both arithmetic reconciliation and category review.
The fictional research-service support role owns the validation handoff.
""", [("research_submission", "validation", "arithmetic reconciliation and category review", 2),
       ("research_submission", "handoff_owner", "research-service support role", 3)],
                 reviewed_on=None, owner=None, source_locator=None, access_semantics=None),
        document("RIS-IMPORT", "RIS", "Grant import batch instructions", """
# Synthetic grant import batch instructions
The grant import batch retry limit is two attempts.
A later attempt requires a documented review of the failed batch.
""", [("grant_import", "retry_limit", "two attempts", 2)]),
        document("RIS-FAQ", "RIS", "Research submission terminology", """
# Synthetic research submission terminology
A proposal is not an award. The example supports research submission vocabulary.
The word budget appears here but no validation steps are specified.
""", []),
        document("IAM-RECOVERY", "IAM", "Identity service recovery contact", """
# Synthetic identity service recovery contact
The identity service recovery contact is the fictional service operations role.
A restoration check is not documented in this packet.
""", [("identity_recovery", "contact", "service operations role", 2)]),
        document("IAM-ARCHIVE", "IAM", "Retired identity procedure", """
# Synthetic retired procedure
A historical procedure required a legacy ping check.
This archived version must not be treated as a current source.
""", [("identity_recovery", "business_check", "legacy ping check", 2)], status="archived", reviewed_on="2024-01-01"),
    ]
    queries = [
        query("Q-ESS-CONFLICT", "ESS", "What is the registration retry limit?", "registration", ["retry_limit"], ["ESS-RETRY", "ESS-OLD"]),
        query("Q-RIS-METADATA", "RIS", "Research submission budget validation and handoff owner", "research_submission", ["validation", "handoff_owner"], ["RIS-BUDGET"]),
        query("Q-RIS-VOCABULARY", "RIS", "Funder records replay cap", "grant_import", ["retry_limit"], ["RIS-IMPORT"]),
        query("Q-IAM-MISSING", "IAM", "Identity service recovery contact and business verification", "identity_recovery", ["contact", "business_check"], ["IAM-RECOVERY"]),
        query("Q-IAM-UNKNOWN-JUDGMENT", "IAM", "Identity service recovery contact", "identity_recovery", ["contact"], None),
    ]
    before = {"schema_version": "1.0", "snapshot_id": "SYNTHETIC-BEFORE", "synthetic": True,
              "as_of": "2026-09-19", "documents": docs, "queries": queries,
              "change_log": []}
    after = copy.deepcopy(before)
    after["snapshot_id"] = "SYNTHETIC-AFTER"
    by_id = {d["id"]: d for d in after["documents"]}
    by_id["ESS-OLD"]["status"] = "superseded"
    after["queries"][0]["relevant_document_ids"] = ["ESS-RETRY"]
    by_id["RIS-BUDGET"].update(owner="Fictional RIS documentation steward", reviewed_on="2026-09-18",
        source_locator="synthetic-collection/RIS-BUDGET/steward-copy",
        access_semantics="Fictional assessment-team readership documented during the exercise")
    item = by_id["RIS-IMPORT"]
    item["content"] += "Vocabulary bridge: funder records replay cap refers to the grant import batch retry limit.\n"
    item["sha256"] = digest(item["content"])
    item["revision"] = "2"
    item["reviewed_on"] = "2026-09-18"
    after["documents"].append(document("IAM-VERIFY", "IAM", "Identity service business recovery verification", """
# Synthetic identity service recovery verification
The business recovery check completes a fictional sign-in and validates its synthetic transaction record.
This is a written exercise procedure, not evidence a restoration was performed.
""", [("identity_recovery", "business_check", "fictional sign-in plus transaction-record validation", 2)], reviewed_on="2026-09-18"))
    after["queries"][3]["relevant_document_ids"].append("IAM-VERIFY")
    after["change_log"] = [
        {"id": "CHANGE-1", "documents": ["ESS-OLD"], "action": "Fictional steward explicitly superseded the five-attempt rule; the tool did not infer authority from age."},
        {"id": "CHANGE-2", "documents": ["RIS-BUDGET"], "action": "Fictional steward supplied owner, source, readership and dated review records; no content fact was changed."},
        {"id": "CHANGE-3", "documents": ["RIS-IMPORT"], "action": "Added analyst-reviewed vocabulary bridge and incremented revision/digest; same retry claim."},
        {"id": "CHANGE-4", "documents": ["IAM-VERIFY"], "action": "Added a missing written verification procedure; no executed recovery or business outcome is claimed."},
    ]
    return before, after


def comparison(before, after):
    lines = ["# UIOWA-073 — measured synthetic before/after rehearsal", "",
             "These are deterministic lexical-retrieval and source-support results, not LLM answers, real team readiness, or evidence of AI benefit.", "",
             "| Query | Before current-supported facts | After current-supported facts | Before source support | After source support |",
             "|---|---|---|---|---|"]
    for left, right in zip(before["queries"], after["queries"]):
        b, a = left["supported_facts"], right["supported_facts"]
        lines.append(f"| {left['query_id']} | {b['numerator']}/{b['denominator']} | {a['numerator']}/{a['denominator']} | {left['answer_support']} | {right['answer_support']} |")
    lines += ["", "## Controlled changes and interpretation", "",
              "The combined repair changes several inputs, so it does not isolate a general causal effect. Each change has a targeted regression test.", "",
              "The vocabulary case is a direct retrieval rehearsal: zero matching terms before repair, then the same query retrieves the relevant revised source after a vocabulary bridge. No embedding or model was used.", "",
              "Conflicts disappear only because the synthetic steward explicitly supersedes one source. Metadata completeness improves only because a fictional review supplies it. The new IAM procedure is written support, not demonstrated restoration.", "",
              "Relevance sets are intentionally versioned when the active corpus changes. Precision/recall across these snapshots is not a controlled model benchmark. Unknown relevance judgments stay unknown."]
    return "\n".join(lines) + "\n"


def run(output: Path):
    packets = snapshots()
    reports = []
    for name, packet in zip(("before", "after"), packets):
        directory = output / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "collection.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        docs = directory / "documents"
        docs.mkdir(exist_ok=True)
        for item in packet["documents"]:
            (docs / f"{item['id']}.md").write_text(item["content"], encoding="utf-8")
        report = assess(packet)
        write_outputs(report, directory)
        reports.append(report)
    (output / "comparison.md").write_text(comparison(*reports), encoding="utf-8")
    print(f"Rehearsal complete: {output}/comparison.md; synthetic documents, collections, JSON/Markdown reports and CSV preparation backlogs included.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
