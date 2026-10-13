#!/usr/bin/env python3
"""Generate a portable, explicitly fictional 12-pair calibration rehearsal."""
from __future__ import annotations

import argparse
import copy
import csv
import json
from pathlib import Path

if __package__:
    from .compare import AREAS, DIMENSIONS, SCHEMA, analyze, comparison_csv, markdown
else:
    from compare import AREAS, DIMENSIONS, SCHEMA, analyze, comparison_csv, markdown


def make_packet() -> tuple[dict, dict[str, str]]:
    evidence, practices, pairs, passages = [], [], [], {}
    defaults = dict(criticality="ordinary internal service", workload="bounded service population",
                    release_cadence="monthly", sampling_basis="complete listed opportunities in the stated window")

    def source(ident: str, passage: str, kind: str = "observation", cluster: str | None = None) -> str:
        evidence.append(dict(id=ident, kind=kind, source="synthetic-evidence.md", locator="#" + ident.lower(),
                             observed_on="2026-09-01", valid_through="2026-09-30", independence_key=cluster or ident))
        passages[ident] = passage
        return ident

    def practice(ident: str, group: str, area: str, method: str, outcome: str, criterion: str,
                 basis: str, refs: list[str], claim: str = "meets") -> dict:
        result = dict(id=ident, group=group, area=area, implementation=method, description=basis,
                      outcome=dict(id=outcome, version="v1", criterion=criterion), context=copy.deepcopy(defaults),
                      claim=claim, basis=basis, evidence_ids=refs, dissent_ids=[])
        practices.append(result)
        return result

    def pair(ident: str, a: dict, b: dict, decisions: list | None = None) -> dict:
        result = dict(id=ident, left=a["id"], right=b["id"], context_decisions=decisions or [])
        pairs.append(result)
        return result

    def measure(n: int, d: int) -> dict:
        return dict(definition="changes-reviewed-before-release/v1", population="all listed normal changes",
                    window_start="2026-08-01", window_end="2026-08-31", numerator=n, denominator=d)

    # 01: implementation labels differ; the evidenced outcome is the same.
    e1 = source("E01", "Fictional ESS: four listed normal changes each have a dated, substantive manual review before release; reviewer questions and their resolution are retained.")
    e2 = source("E02", "Fictional RIS: forty listed normal changes each have a dated substantive review and resolved questions before the automated pipeline releases them. Pipeline success alone is not the review evidence.")
    a = practice("dev-manual", "ESS", AREAS[0], "manual", "review-before-release", "Every listed normal change has substantive review before release.", "Four of four normal changes: usable review notes and resolved comments.", [e1])
    b = practice("dev-automated", "RIS", AREAS[0], "automated", a["outcome"]["id"], a["outcome"]["criterion"], "Forty of forty normal changes: review records linked to pipeline events.", [e2])
    a["measurement"], b["measurement"] = measure(4, 4), measure(40, 40)
    pair("01-manual-and-automated", a, b)

    # 02: one common provider observation covers two named consumers, not two replications.
    es = source("E03", "Fictional shared IAM lifecycle exercise: a single retained exercise verifies revocation reaches the named ESS and RIS consumers within the agreed interval. Both consumers occur in this same exercise record.", cluster="shared-lifecycle-exercise-1")
    a = practice("security-ess-consumer", "ESS", AREAS[1], "shared-service", "revocation-propagates", "Named consumers receive revocation within the agreed exercise interval.", "ESS is one named consumer in the common lifecycle exercise.", [es])
    b = practice("security-ris-consumer", "RIS", AREAS[1], "shared-service", a["outcome"]["id"], a["outcome"]["criterion"], "RIS is the other named consumer in that same exercise.", [es])
    pair("02-shared-service-not-independent", a, b)

    # 03: service consequences and scale make direct transfer inappropriate.
    ea = source("E04", "Fictional registration-service exercise: a critical journey recovered in 20 minutes under a seasonal high-concurrency workload. This record covers that exercise only.")
    eb = source("E05", "Fictional research reporting service: an internal low-concurrency journey recovered in 45 minutes. A service inventory records different outage consequences and workload, so the low-load exercise does not establish peak-period capacity.")
    a = practice("ops-peak", "ESS", AREAS[2], "automated", "recover-journey", "The listed exercise recovers its journey within 60 minutes.", "Peak-window journey restored in 20 minutes; no extrapolation beyond this exercise.", [ea])
    b = practice("ops-bounded", "RIS", AREAS[2], "manual", a["outcome"]["id"], a["outcome"]["criterion"], "Small internal journey restored in 45 minutes; different service consequences.", [eb])
    a["context"].update(criticality="registration-critical", workload="seasonal high concurrency")
    decisions = [dict(dimension=d, decision="material_difference", rationale="Different outage consequence or load changes the operating requirement; retain local success without ranking services.", evidence_ids=[ea, eb]) for d in ("criticality", "workload")]
    pair("03-criticality-and-scale", a, b, decisions)

    # 04: a policy does not establish observed operation.
    ep = source("E06", "Fictional AI use guideline: generated development suggestions should be checked against task-specific acceptance criteria. No completed evaluations accompany this policy.", kind="policy")
    eo = source("E07", "Fictional RIS AI-assist trial: all ten listed outputs were checked against retained task criteria; two incorrect suggestions were rejected before use. This is an observed small trial, not organization-wide adoption.")
    a = practice("ai-policy-only", "ESS", AREAS[3], "manual", "check-assistance", "Listed AI-assisted suggestions receive task-specific checking before use.", "Policy describes checking; completed checking records were not supplied.", [ep])
    b = practice("ai-observed", "RIS", AREAS[3], "hybrid", a["outcome"]["id"], a["outcome"]["criterion"], "Ten checked suggestions and two rejected errors in a bounded trial.", [eo])
    pair("04-policy-is-not-execution", a, b)

    # 05: cadence differs, but an explicit source-backed judgment permits this outcome comparison.
    a, b = copy.deepcopy(practices[0]), copy.deepcopy(practices[1])
    a["id"], b["id"] = "cadence-quarterly", "cadence-continuous"
    a["context"]["release_cadence"], b["context"]["release_cadence"] = "quarterly release batch", "continuous small releases"
    practices.extend([a, b])
    ed = source("E08", "Fictional comparison-design note: E01 and E02 list every normal change in the same August window; the common outcome is substantive review before release, not deployment frequency. All four changes in the batch and all forty separately released changes meet that same criterion.", kind="policy")
    pair("05-cadence-aligned-for-review", a, b, [dict(dimension="release_cadence", decision="aligned_for_outcome", rationale="Per-change substantive review is the common outcome; frequency is not a maturity proxy. Denominator sizes remain visible and no statistical equivalence is inferred.", evidence_ids=[ed])])

    # 06: actual observed gaps, not absent evidence assigned a low score.
    eg = source("E09", "Fictional maintenance samples: ESS change M1 and IAM change M2 have acceptance criteria but their retained acceptance records explicitly document an unmet required behavior. Both samples establish a bounded gap, not a staff-performance judgment.")
    a = practice("gap-ess", "ESS", AREAS[0], "manual", "acceptance-behavior", "The named maintenance change meets its required acceptance behavior.", "M1's completed check documents the required behavior failing.", [eg], "does_not_meet")
    b = practice("gap-iam", "IAM", AREAS[0], "automated", a["outcome"]["id"], a["outcome"]["criterion"], "M2's completed check documents the required behavior failing.", [eg], "does_not_meet")
    pair("06-shared-gap-not-low-score", a, b)

    # 07: missing practice evidence remains unknown, even when a comparator has support.
    a = practice("security-unknown", "IAM", AREAS[1], "hybrid", "revocation-propagates", practices[2]["outcome"]["criterion"], "No exercise record supplied for this service; whether the practice works is unknown.", [], "unknown")
    pair("07-missing-evidence-is-unknown", a, practices[2])

    # 08: dissent is retained even when the supporting observation looks polished.
    a = copy.deepcopy(practices[4]); a["id"] = "ops-disputed"; practices.append(a)
    ex = source("E10", "Fictional follow-up account disputes whether the recovered registration journey was the business-critical one. The discrepancy is unresolved; the exercise's successful technical check must not settle this business-scope disagreement.", kind="interview")
    a["dissent_ids"] = [ex]
    pair("08-unresolved-dissent", a, practices[4])

    # 09: the same label with a changed definition cannot be silently equated.
    a = copy.deepcopy(practices[7]); a["id"] = "ai-v2"; practices.append(a)
    a["outcome"]["version"] = "v2"
    a["outcome"]["criterion"] = "Listed suggestions receive task checking plus a separate data-use review."
    a.update(claim="unknown", basis="E07 covers task checking, not the additional v2 data-use review; v2 achievement is unknown.")
    pair("09-definition-drift", practices[7], a)

    # 10: not-applicable is not a passing or failing result.
    a = copy.deepcopy(practices[2]); a["id"] = "security-na"; practices.append(a)
    a.update(claim="not_applicable", evidence_ids=[], applicability_reason="Fictional retired service has no active consumer in this scope.", basis="Applicability judgment requires confirmation against the service inventory; no operating conclusion is made.")
    pair("10-applicability-no-penalty", a, practices[2])

    # 11: unknown context cannot be erased by matching technology or a favorable outcome.
    a = copy.deepcopy(practices[0]); a["id"] = "dev-workload-unknown"; practices.append(a)
    a["context"]["workload"] = None
    pair("11-unknown-context", a, practices[1])

    # 12: qualitative outcome comparison does not license unmatched quantitative periods.
    a = copy.deepcopy(practices[0]); a["id"] = "dev-july"; practices.append(a)
    a["measurement"]["window_start"], a["measurement"]["window_end"] = "2026-07-01", "2026-07-31"
    ej = source("E11", "Fictional July ESS review log: four of four listed normal July changes have retained substantive pre-release review. July and August measurements are different observation windows; this record is not the August E01 sample.")
    a["evidence_ids"] = [ej]
    a["basis"] = "Four of four listed July changes have substantive review; do not compare a July rate with an August rate."
    pair("12-mismatched-measurement-windows", a, practices[1])
    return dict(schema=SCHEMA, synthetic=True, as_of="2026-09-19", evidence=evidence, practices=practices, pairs=pairs), passages


def write_example(destination: Path) -> dict:
    packet, passages = make_packet()
    # Refuse an existing destination so the example generator never overwrites an operator's evidence.
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "synthetic.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    body = ["# Fictional calibration evidence", "", "SYNTHETIC REHEARSAL ONLY — no actual University people, records or findings.", ""]
    for ident, passage in passages.items():
        body += ["## " + ident, "", passage, ""]
    (destination / "synthetic-evidence.md").write_text("\n".join(body), encoding="utf-8")
    report = analyze(packet)
    (destination / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (destination / "comparison.csv").write_text(comparison_csv(report), encoding="utf-8")
    (destination / "comparison.md").write_text(markdown(report), encoding="utf-8")
    with (destination / "context-worksheet.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["synthetic", "as_of", "pair_id", "dimension", "left_context", "right_context", "recorded_treatment", "rationale", "evidence_ids", "follow_up_question", "proposed_owner_role"])
        for row in report["pairs"]:
            for dimension in row["context"]["dimensions"]:
                d = dimension["decision"] or {}
                writer.writerow([packet["synthetic"], packet["as_of"], row["id"], dimension["dimension"], dimension["left"], dimension["right"], dimension["state"], d.get("rationale", ""), ";".join(d.get("evidence_ids", [])), "Which dated artifact establishes this context for the sampled service?" if dimension["state"] in ("UNKNOWN", "UNRESOLVED") else "", "assessor / service owner (proposed)"])
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="New directory for synthetic artifacts")
    args = parser.parse_args()
    result = write_example(args.out)
    print(json.dumps(result["summary"], sort_keys=True))
