#!/usr/bin/env python3
"""UIOWA-015 -- peer-university software delivery practice cards.

Run:
    python3 peerpack.py --render            # writes 15-development-peer-pack.md
    python3 peerpack.py --check             # validate cards against sources, exit 1 on a problem
    python3 peerpack.py --print

Python 3 standard library only. No network AT RUNTIME: the sources were
retrieved once, on the date recorded in sources.json, and this program reads
only the local JSON. Re-retrieval is a human act, not something this tool
does silently.

The order requires cards that distinguish **published policy** from
**reported implementation**. That distinction is the whole point, because a
policy document says what is required, not what happens. Four rules enforce
it, and all CLI output modes fail on invalid data:

  1. A card may only be built on a source marked VERIFIED. A source that
     could not be read, or that was read and had nothing relevant in it,
     carries no cards and is listed separately with the reason.
  2. `obligation_basis` must appear verbatim inside `quote`. You cannot
     assert a card is mandatory on wording that is not in the source.
  3. Advisory wording cannot be labelled MANDATORY. A "should" or an
     "encouraged" stays advisory -- upgrading it is the most common way a
     benchmark pack overstates what a peer actually requires.
  4. Conditional requirements keep structured scope cases and clause locators;
     a quoted should can be subject to an overriding contextual requirement.
  5. Draft status and later fetch failures remain visibly distinct from adoption.
  6. Every card carries transferable questions, at least one of which asks
     for a concrete artifact or instance rather than restating the policy
     back at the reader.

Nothing in this pack is a statement about the University of Iowa, and no
peer is ranked, scored, or described as a leader.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

SOURCE_KINDS = ("PUBLISHED_POLICY", "REPORTED_IMPLEMENTATION")
VERIFICATION = ("VERIFIED", "VERIFIED_NO_RELEVANT_CONTENT", "NOT_VERIFIED")
DOC_STATUS = ("EFFECTIVE", "DRAFT", "UNKNOWN")
OBLIGATION = ("MANDATORY", "CONDITIONAL", "ADVISORY", "UNKNOWN")

PRACTICE_AREAS = ("code_review", "testing", "environments", "documentation",
                  "change_control", "security_testing")

# Wording that cannot support a MANDATORY label.
ADVISORY_MARKERS = ("should", "encouraged", "recommended", "may", "where practical",
                    "where feasible", "is expected to")

# A question that asks for something that exists.
CONCRETE_MARKERS = ("show me", "can you show", "can you open", "open one", "pull the",
                    "a recent", "the last", "recent change", "has one ever",
                    "has a deployment ever", "when was", "what happened", "which of these",
                    "who would notice", "what data is")

# What a card built on each kind of source is evidence OF. A policy card is
# never evidence that anything is done.
EVIDENCE_MEANING = {
    "PUBLISHED_POLICY": "what this organization publishes as required or expected",
    "REPORTED_IMPLEMENTATION": "what this organization reports it actually did",
}


class PackError(ValueError):
    pass


def load(name):
    with open(os.path.join(HERE, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def build(sources_doc, cards_doc):
    if not isinstance(sources_doc, dict) or not isinstance(cards_doc, dict):
        raise PackError("source and card documents must be JSON objects")
    if not isinstance(sources_doc.get("sources"), list) or not isinstance(cards_doc.get("cards"), list):
        raise PackError("sources and cards must be arrays")
    if sources_doc.get("pack_id") != cards_doc.get("pack_id") or not sources_doc.get("pack_id"):
        raise PackError("source and card pack_id must match and be nonempty")
    sources = {}
    problems = []
    for s in sources_doc["sources"]:
        if not isinstance(s, dict):
            raise PackError("each source must be an object")
        sid = s.get("source_id")
        if not isinstance(sid, str) or not sid.strip():
            problems.append({"where": "<source>", "problem": "source has no source_id"})
            continue
        if sid in sources:
            problems.append({"where": sid, "problem": "duplicate source_id"})
        for field in ("organization", "document_title", "url", "retrieved_at"):
            if not isinstance(s.get(field), str) or not s[field].strip():
                problems.append({"where": sid, "problem": "%s is empty" % field})
        if s.get("source_kind") not in SOURCE_KINDS:
            problems.append({"where": sid, "problem": "source_kind %r is outside the vocabulary"
                                                      % s.get("source_kind")})
        if s.get("verification") not in VERIFICATION:
            problems.append({"where": sid, "problem": "verification %r is outside the vocabulary"
                                                      % s.get("verification")})
        if s.get("document_status") not in DOC_STATUS:
            problems.append({"where": sid, "problem": "document_status %r is outside the vocabulary"
                                                      % s.get("document_status")})
        sources[sid] = s

    cards = []
    seen_cards = set()
    for c in cards_doc["cards"]:
        if not isinstance(c, dict):
            raise PackError("each card must be an object")
        cid = c.get("card_id", "<no id>")
        if not isinstance(cid, str) or not cid.strip() or cid == "<no id>":
            problems.append({"where": "<card>", "problem": "card has no card_id"})
            continue
        if cid in seen_cards:
            problems.append({"where": cid, "problem": "duplicate card_id"})
        seen_cards.add(cid)
        sid = c.get("source_id")
        if not isinstance(sid, str):
            problems.append({"where": cid, "problem": "source_id must be text"})
            continue
        source = sources.get(sid)
        if source is None:
            problems.append({"where": cid, "problem": "source_id %r does not resolve" % sid})
            continue
        if source.get("verification") != "VERIFIED":
            problems.append({"where": cid,
                             "problem": "built on source %s, which is %s; only a VERIFIED source "
                                        "may carry a card" % (sid, source.get("verification"))})
            continue

        quote = c.get("quote", "")
        basis = c.get("obligation_basis", "")
        if not isinstance(quote, str) or not isinstance(basis, str):
            problems.append({"where": cid, "problem": "quote and obligation_basis must be text"})
            continue
        quote, basis = quote.strip(), basis.strip()
        strength = c.get("obligation_strength")

        if not quote:
            problems.append({"where": cid, "problem": "no quote; a card without the source's own "
                                                      "words is an assertion, not a citation"})
        if strength not in OBLIGATION:
            problems.append({"where": cid, "problem": "obligation_strength %r is outside the "
                                                      "vocabulary" % strength})
        if not basis:
            problems.append({"where": cid, "problem": "no obligation_basis"})
        elif basis not in quote:
            problems.append({"where": cid,
                             "problem": "obligation_basis %r does not appear in the quote; the "
                                        "strength is asserted on wording the source does not use"
                                        % basis})
        elif strength == "MANDATORY" and any(re.search(r"\b" + re.escape(m) + r"\b", basis.lower()) for m in ADVISORY_MARKERS):
            problems.append({"where": cid,
                             "problem": "labelled MANDATORY on advisory wording %r; a should is "
                                        "not a must" % basis})

        for field in ("source_locator", "applicability", "what_it_says", "why_transferable"):
            if not isinstance(c.get(field), str) or not c[field].strip():
                problems.append({"where": cid, "problem": "%s is empty or not text" % field})
        cases = c.get("obligation_cases", [])
        if not isinstance(cases, list):
            problems.append({"where": cid, "problem": "obligation_cases must be an array"})
            cases = []
        if strength == "CONDITIONAL" and not cases:
            problems.append({"where": cid, "problem": "CONDITIONAL needs explicit obligation_cases"})
        if cases and strength != "CONDITIONAL":
            problems.append({"where": cid, "problem": "scoped obligation_cases require CONDITIONAL, not a universal label"})
        for case in cases:
            if not isinstance(case, dict) or not isinstance(case.get("condition"), str) or not case["condition"].strip() or case.get("strength") not in ("MANDATORY", "ADVISORY", "UNKNOWN"):
                problems.append({"where": cid, "problem": "invalid obligation case"})

        if c.get("practice_area") not in PRACTICE_AREAS:
            problems.append({"where": cid, "problem": "practice_area %r is outside the vocabulary"
                                                      % c.get("practice_area")})

        questions = c.get("transferable_questions") or []
        if not isinstance(questions, list) or not all(isinstance(q, str) and q.strip() for q in questions):
            problems.append({"where": cid, "problem": "transferable_questions must be an array of nonempty text"})
            questions = []
        if len(questions) < 2:
            problems.append({"where": cid, "problem": "fewer than two transferable questions"})
        if not any(any(m in q.lower() for m in CONCRETE_MARKERS) for q in questions):
            problems.append({"where": cid,
                             "problem": "no question asks for a concrete artifact or instance; "
                                        "the card restates the policy instead of testing it"})

        card = dict(c)
        card["source"] = source
        card["evidence_of"] = EVIDENCE_MEANING.get(source.get("source_kind"), "UNKNOWN source kind")
        card["effective_obligation"] = "DRAFT_INTENT" if source.get("document_status") == "DRAFT" else strength
        cards.append(card)

    return cards, sources, problems


def coverage(cards, sources):
    by_area = {}
    for c in cards:
        by_area.setdefault(c["practice_area"], []).append(c["card_id"])
    orgs = sorted(set(c["source"]["organization"] for c in cards))
    kinds = {}
    for c in cards:
        kinds[c["source"]["source_kind"]] = kinds.get(c["source"]["source_kind"], 0) + 1
    return {
        "cards": len(cards),
        "organizations": orgs,
        "practice_areas": dict((k, sorted(v)) for k, v in sorted(by_area.items())),
        "uncovered_practice_areas": sorted(set(PRACTICE_AREAS) - set(by_area)),
        "cards_by_source_kind": kinds,
        "sources_checked": len(sources),
        "sources_carrying_cards": len(set(c["source_id"] for c in cards)),
    }


def render(cards, sources, sources_doc, problems):
    cov = coverage(cards, sources)
    L = []
    L.append("# 15 — Higher-education software delivery peer pack")
    L.append("")
    L.append("Solicitation 18649, work order UIOWA-015. Practice cards drawn from")
    L.append("**official, published** peer-university sources, each cited to a URL and a")
    L.append("retrieval date.")
    L.append("")
    L.append("**Nothing in this pack is a statement about the University of Iowa.** No peer")
    L.append("is ranked, scored, or described as a leader; the cards record what these")
    L.append("organizations publish, not how well they do it.")
    L.append("")
    L.append("> %s" % sources_doc["retrieval_note"])
    L.append("")
    L.append("## The distinction this pack turns on")
    L.append("")
    L.append("A policy document states what is **required**. It is not evidence that")
    L.append("anything is **done**. Every card below records which of the two its source")
    L.append("is. The tool preserves that classification; it does not independently verify the source or interpret arbitrary claims.")
    L.append("")
    L.append("| | |")
    L.append("| --- | ---: |")
    L.append("| Sources checked | %d |" % cov["sources_checked"])
    L.append("| Sources carrying cards | %d |" % cov["sources_carrying_cards"])
    L.append("| Practice cards | %d |" % cov["cards"])
    for kind, n in sorted(cov["cards_by_source_kind"].items()):
        L.append("| Cards from %s | %d |" % (kind, n))
    L.append("")
    reported = cov["cards_by_source_kind"].get("REPORTED_IMPLEMENTATION", 0)
    if not reported:
        L.append("**No card in this pack rests on reported implementation.** The selected policy")
        L.append("clauses describe expectations, not observed performance. Uncollected evidence")
        L.append("remains unknown; this is not an exhaustive search of institutional practice.")
        L.append("")
    L.append("## Something worth noticing across the published wording")
    L.append("")
    L.append("Of the %d cards, %d state the practice as **advisory** (`should`,"
             % (len(cards), len([c for c in cards if c["obligation_strength"] == "ADVISORY"])))
    L.append("`encouraged`) rather than mandatory, and one peer publishes an explicit")
    L.append("fallback for when peer review is not feasible. A pack that reported these as")
    L.append("requirements would overstate what peers actually commit to. The tooling")
    L.append("refuses universal labels when structured scope cases are present. CONDITIONAL")
    L.append("cards carry the source's classification or applicability limits; isolated wording")
    L.append("does not override the document context. DRAFT_INTENT remains separate from adoption.")
    L.append("")
    L.append("## Practice cards")
    L.append("")
    for c in sorted(cards, key=lambda x: x["card_id"]):
        s = c["source"]
        L.append("### %s — %s (%s)" % (c["card_id"], c["practice_area"], s["organization"]))
        L.append("")
        L.append("| Field | Value |")
        L.append("| --- | --- |")
        L.append("| Organization | %s |" % s["organization"])
        L.append("| Document | %s |" % s["document_title"])
        L.append("| Owning unit | %s |" % s.get("owning_unit", "UNKNOWN"))
        L.append("| Document date | %s |" % s.get("document_date", "UNKNOWN"))
        L.append("| Document status | **%s** |" % s["document_status"])
        L.append("| Source kind | **%s** — %s |" % (s["source_kind"], c["evidence_of"]))
        L.append("| Obligation | **%s** (on the wording \"%s\") |"
                 % (c["obligation_strength"], c["obligation_basis"]))
        L.append("| Source | %s |" % s["url"])
        L.append("| Retrieved | %s |" % s["retrieved_at"])
        L.append("| Interpretation state | **%s** |" % c["effective_obligation"])
        L.append("| Source locator | %s |" % c["source_locator"])
        L.append("| Applicability | %s |" % c["applicability"])
        L.append("| Source scope | %s |" % s.get("scope_note", "UNKNOWN"))
        for case in c.get("obligation_cases", []):
            L.append("| Scope case | %s: **%s** |" % (case["condition"], case["strength"]))
        check = s.get("recheck", {})
        if check:
            L.append("| Recheck | %s; %s; %s |" % (check["date"], check["status"], check["note"]))
        L.append("")
        L.append("> %s" % c["quote"])
        L.append("")
        L.append("**What it says.** %s" % c["what_it_says"])
        L.append("")
        L.append("**Why it transfers.** %s" % c["why_transferable"])
        L.append("")
        L.append("**Transferable assessment questions**")
        L.append("")
        for q in c["transferable_questions"]:
            L.append("- %s" % q)
        L.append("")
        if s["document_status"] == "DRAFT":
            L.append("*This document identifies itself as a draft. It shows an intended")
            L.append("requirement, not a settled one.*")
            L.append("")
    L.append("## Coverage")
    L.append("")
    L.append("| Practice area | Cards |")
    L.append("| --- | --- |")
    for area, ids in sorted(cov["practice_areas"].items()):
        L.append("| %s | %s |" % (area, ", ".join(ids)))
    for area in cov["uncovered_practice_areas"]:
        L.append("| %s | **none — not collected** |" % area)
    L.append("")
    L.append("An area with no card means no verified source was found for it in this")
    L.append("pass. It does not mean peers have no such practice.")
    L.append("")
    L.append("## Sources checked that carry no card")
    L.append("")
    L.append("| Source | Organization | Status | Why |")
    L.append("| --- | --- | --- | --- |")
    carrying = set(c["source_id"] for c in cards)
    for s in sources_doc["sources"]:
        if s["source_id"] in carrying:
            continue
        L.append("| %s | %s | `%s` | %s |" % (s["source_id"], s["organization"],
                                              s["verification"], s["verification_note"]))
    L.append("")
    L.append("These are recorded rather than dropped. A source that could not be read is")
    L.append("not the same as a source that says nothing, and neither is the same as an")
    L.append("organization that lacks the practice.")
    L.append("")
    if problems:
        L.append("## Validation problems")
        L.append("")
        for p in problems:
            L.append("- `%s`: %s" % (p["where"], p["problem"]))
        L.append("")
    L.append("## Still UNKNOWN")
    L.append("")
    for item in (
        "whether any of these published requirements is actually followed at the "
        "organization that published it — no source checked reports that these collected practices are consistently followed",
        "how lifecycle tailoring works in practice; DSU publishes a tailoring provision, but operating examples were not obtained",
        "whether the peers selected here are comparable in size, funding or application "
        "portfolio to a multiple-application central IT organization; no such comparison "
        "was made",
        "what the University of Iowa's own published expectations are — not collected, "
        "and deliberately not inferred from any peer",
    ):
        L.append("- %s" % item)
    L.append("")
    L.append("## How this pack was built")
    L.append("")
    L.append("Original collection by OP5-KELVIN; source-context integration by ZZ-TRACEFORGE.")
    L.append("See original_observation and recheck fields for what each pass actually read.")
    L.append("Recheck current source wording and applicability before external reliance. `sources.json` and")
    L.append("`cards.json` are the data; `peerpack.py --check` enforces the citation rules")
    L.append("and this document is generated, not hand-written.")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    p = argparse.ArgumentParser(description="Peer delivery practice pack.")
    p.add_argument("--render", action="store_true", help="write 15-development-peer-pack.md")
    p.add_argument("--check", action="store_true", help="validate only")
    p.add_argument("--print", dest="do_print", action="store_true")
    args = p.parse_args(argv)

    try:
        sources_doc, cards_doc = load("sources.json"), load("cards.json")
        cards, sources, problems = build(sources_doc, cards_doc)
    except (OSError, ValueError) as exc:
        sys.stderr.write("PACK ERROR: %s\n" % exc)
        return 2
    if problems:
        for pr in problems:
            sys.stderr.write("PROBLEM %s: %s\n" % (pr["where"], pr["problem"]))
        sys.stderr.write("cards=%d sources=%d problems=%d; deliverable unchanged\n" %
                         (len(cards), len(sources), len(problems)))
        return 1

    if args.check and not (args.render or args.do_print):
        for pr in problems:
            sys.stderr.write("PROBLEM %s: %s\n" % (pr["where"], pr["problem"]))
        sys.stderr.write("cards=%d sources=%d problems=%d\n"
                         % (len(cards), len(sources), len(problems)))
        return 1 if problems else 0

    text = render(cards, sources, sources_doc, problems)
    if args.render:
        with open(os.path.join(HERE, "15-development-peer-pack.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
        sys.stdout.write("wrote 15-development-peer-pack.md\n")
    if args.do_print or not args.render:
        sys.stdout.write(text)

    cov = coverage(cards, sources)
    sys.stderr.write("cards=%d orgs=%d sources_checked=%d carrying=%d problems=%d "
                     "reported_implementation_cards=%d\n"
                     % (cov["cards"], len(cov["organizations"]), cov["sources_checked"],
                        cov["sources_carrying_cards"], len(problems),
                        cov["cards_by_source_kind"].get("REPORTED_IMPLEMENTATION", 0)))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
