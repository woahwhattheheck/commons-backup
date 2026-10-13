#!/usr/bin/env python3
"""Offline discussion cards composed from the existing search/report/register contracts."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REVENUE = HERE.parent
for sibling in ("uiowa_rfq_18649_workshare", "uiowa_rfq_18649_local_search",
                "uiowa_rfq_18649_recommendation_register"):
    sys.path.insert(0, str(REVENUE / sibling))
import compiler
import evidence_search as search
import register
from search_provenance import verified_sources, git_blob, read_json

SCHEMA = "uiowa.discussion.v1"
NOTICE = ("SYNTHETIC PREPARATION / DRAFT_NON_AUTHORITATIVE. Integrity and search "
          "relevance do not establish evidence truth, current authority, approval, or University findings.")
LIMIT = 2 * 1024 * 1024


class DiscussionError(ValueError):
    pass


def read(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise DiscussionError(f"input exceeds {LIMIT} bytes: {path}")
    return raw


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def anchor(value):
    return "r-" + sha(value.encode())[:24]


def build(manifest, report_path, register_path):
    """Reuse canonical validators; retain their statuses instead of assigning ratings."""
    snapshots = {}
    bindings = {}

    def bind(key, raw, label):
        if key in snapshots:
            if snapshots[key] != raw:
                raise DiscussionError("colliding source snapshot: " + key)
            return
        if len(raw) > LIMIT:
            raise DiscussionError("source snapshot exceeds byte limit: " + key)
        snapshots[key] = raw
        bindings[key] = {"sha256": sha(raw), "git_blob_sha": git_blob(raw), "label": label}

    manifest = Path(manifest)
    bind("inputs/search/manifest.json", read(manifest), "Evidence search manifest")
    for source, raw, proof in verified_sources(manifest):
        bind("inputs/search/" + source["local_file"], raw, source["upstream_path"])
        if source.get("source_local_file"):
            name = source["source_local_file"]
            bind("inputs/search/" + name, read(manifest.parent / name), source["upstream_path"])
    records = search.load_manifest(manifest)
    if not all(row.get("synthetic") is True for row in records):
        raise DiscussionError("discussion preparation requires explicitly synthetic source records")
    evidence = {row["record_id"]: row for row in records}
    report_raw, register_raw = read(report_path), read(register_path)
    report = compiler.loads_strict(report_raw.decode("utf-8"))
    verification = compiler.verify_report_integrity(report)
    if report["mode"] != "UNTRUSTED_INSPECTION":
        raise DiscussionError("use the public compiler's UNTRUSTED_INSPECTION report")
    if not all(s["source_ref"].startswith("synthetic://") for s in report["evidence_authority"]["sources"]):
        raise DiscussionError("report source references must be explicitly synthetic")
    reg = register.normalize(register.loads(register_raw.decode("utf-8")))
    if reg["data_classification"] != "SYNTHETIC":
        raise DiscussionError("discussion preparation requires a SYNTHETIC recommendation register")
    bind("inputs/report.json", report_raw, "Workshare inspection report")
    bind("inputs/register.json", register_raw, "Recommendation register")
    citations, cards = {}, []

    def cite(identity, label, locator, source_key, excerpt, original, diagnostics=()):
        citations[identity] = dict(citation_id=identity, label=label, locator=locator,
            source_key=source_key, source_sha256=bindings[source_key]["sha256"],
            excerpt=excerpt, original=original, diagnostics=list(diagnostics))
        return identity

    def card(identity, question, state, leadership, practitioner, refs, related=(), diagnostics=()):
        cards.append(dict(card_id=identity, question=question, state=state,
            leadership_answer=leadership, practitioner_answer=practitioner,
            citation_ids=list(refs), related_card_ids=list(related), diagnostics=list(diagnostics)))

    manifest_data = read_json(snapshots["inputs/search/manifest.json"])
    source_by_path = {s["upstream_path"]: s for s in manifest_data["sources"]}
    for row in records:
        src = source_by_path[row["source_path"]]
        cite("evidence:" + row["record_id"], row.get("title") or row["record_id"],
             row.get("record_locator") or row["locator"], "inputs/search/" + src["local_file"],
             row.get("original_text", ""), row.get("original", {}), row.get("warnings", []))
    recs = {r["recommendation_id"]: r for r in reg["recommendations"]}
    findings = {f["finding_id"]: f for f in reg["findings"]}
    for row in records:
        if row["record_type"] != "finding":
            continue
        original, fid = row["original"], row["record_id"]
        missing = [link for link in row["linked_ids"] if link not in evidence]
        related = ["recommendation:" + r["recommendation_id"] for r in reg["recommendations"]
                   if fid in r["finding_ids"] and fid in findings
                   and findings[fid]["statement"] == original["statement"]]
        diagnostic = ["MISSING_EVIDENCE:" + x for x in missing]
        if not related:
            diagnostic.append("NO_EXACT_RECOMMENDATION_MAPPING")
        card("finding:" + fid, f"What {original.get('type', 'finding')} does {original['service']} show? {row['title']}",
             "MISSING_SUPPORT" if missing else "SOURCE_LINKED_DRAFT", original["statement"],
             original["limitation"] + " Recorded confidence: " + original["confidence"] + ". Not recalibrated by this kit.",
             ["evidence:" + fid] + ["evidence:" + x for x in row["linked_ids"] if x in evidence], related, diagnostic)

    authority = {s["source_id"]: s for s in report["evidence_authority"]["sources"]}
    for sid, source in authority.items():
        cite("authority:" + sid, sid, f"evidence_authority.sources[source_id={sid}]",
             "inputs/report.json", source["claim"], source)
    for cell in report["assessment_matrix"]:
        group, dimension, status = cell["group"], cell["dimension"], cell["status"]
        identity = f"cell:{group}:{dimension}"
        cite(identity, f"{group} {dimension} assessment", f"assessment_matrix[group={group},dimension={dimension}]",
             "inputs/report.json", "", cell)
        refs = [identity] + ["authority:" + sid for sid in cell["source_ids"]]
        diagnostics = list(cell["reason_codes"])
        for sid in cell["source_ids"]:
            if sid not in evidence:
                diagnostics.append("SOURCE_NOT_IN_SEARCH_PACKET:" + sid)
            elif evidence[sid].get("original") != authority[sid]:
                diagnostics.append("SEARCH_REPORT_SOURCE_VERSION_MISMATCH:" + sid)
        reasons = "; ".join(cell["reason_codes"]) or "No reason recorded"
        card(identity, f"What is the {group} {dimension} maturity, disagreement, and missing or stale evidence?",
             status, f"The supplied report records {status}. Maturity and confidence remain UNKNOWN in this public inspection.",
             f"Reasons: {reasons}. Evaluated at {report['evaluated_at']}; no current-time authority verification is performed. "
             "Inspect each cited source claim separately; differing source values are not averaged.", refs, diagnostics=diagnostics)

    for fid, finding in findings.items():
        identity = "register-finding:" + fid
        diagnostics = []
        refs = [cite(identity, fid, f"findings[finding_id={fid}]", "inputs/register.json", finding["statement"], finding)]
        for ref in finding["evidence_refs"]:
            if ref in evidence:
                refs.append("evidence:" + ref)
            else:
                diagnostics.append("UNRESOLVED_EVIDENCE_REF:" + ref)
        card(identity, f"What supports recommendation finding {fid} in {finding['group']}?", "ILLUSTRATIVE_DRAFT",
             finding["statement"], "These are register-native finding IDs. Similar scope or text does not create an evidence crosswalk.",
             refs, ["recommendation:" + rid for rid, r in recs.items() if fid in r["finding_ids"]], diagnostics)

    reviews = register.review_items(reg)
    roadmap = register.roadmap_view(reg)
    for rid, rec in recs.items():
        identity = "recommendation:" + rid
        refs = [cite(identity, rid, f"recommendations[recommendation_id={rid}]", "inputs/register.json", rec["practice_change"], rec)]
        related = ["register-finding:" + fid for fid in rec["finding_ids"] if fid in findings]
        related += ["recommendation:" + dep for dep in rec["dependencies"] if dep in recs]
        diagnostics = [x["code"] + ":" + x["detail"] for x in reviews if x["recommendation_id"] == rid]
        card(identity, f"What priority, effort, owner and roadmap implications does {rid} propose? {rec['practice_change']}",
             "PROPOSED_WITH_UNKNOWNS" if diagnostics else "PROPOSED", rec["practice_change"] + " " + rec["impact"],
             "Planning fields are preserved below, including null UNKNOWN values. Phase buckets are proposed horizons, "
             "not dates, priorities, an executable schedule or approved staffing. Dependencies link to their original recommendations.",
             refs, related, diagnostics)

    summary = register.summary(reg)
    cite("register:summary", "Effort accounting", "summary of distinct recommendations", "inputs/register.json", "", summary)
    total = summary["known_effort_subtotal"]
    card("planning:effort", "What effort is known, what is unknown, and which recommendations are priorities?",
         "PROPOSED" if summary["effort_total_complete"] else "UNKNOWN_TOTAL",
         f"Known effort subtotal is {total['low']}–{total['high']} person-days. Complete total: "
         + ("known as a scenario assumption." if summary["effort_total_complete"] else "UNKNOWN."),
         "Count each recommendation once, including actions serving several findings. Explicit zero is preserved separately from "
         "null. No priority ranking is inferred from proposed phases. Review prerequisites, unknown owners and estimates before planning.",
         ["register:summary"], ["recommendation:" + rid for rid in recs])

    cards.sort(key=lambda x: x["card_id"])
    indexed = []
    for row in cards:
        first = citations[row["citation_ids"][0]]
        indexed.append(dict(record_id=row["card_id"], record_type="discussion_card", title=row["question"],
            text=" ".join([row["leadership_answer"], row["practitioner_answer"], row["state"], dumps(row["diagnostics"]),
                            " ".join(dumps(citations[x]["original"]) for x in row["citation_ids"])]),
            source_path=first["source_key"], upstream_blob_sha=bindings[first["source_key"]]["git_blob_sha"],
            locator=first["locator"], source_url="synthetic://discussion/" + row["card_id"],
            linked_ids=row["related_card_ids"], metadata={"state": row["state"]}))
    payload = dict(schema=SCHEMA, notice=NOTICE, verification=verification, report_receipt=report["receipt_sha256"],
        report_evaluated_at=report["evaluated_at"], cards=cards, citations=citations, sources=bindings,
        roadmap=roadmap, search_index=search.build_index(indexed))
    if len(dumps(payload).encode("utf-8")) > LIMIT:
        raise DiscussionError("discussion exceeds the 2 MiB bundle limit")
    return payload, snapshots


def render_markdown(pack):
    out = ["# Evidence discussion kit", "", pack["notice"], "", "Use card IDs to follow local sources and recommendations.", ""]
    for card in pack["cards"]:
        out += [f"## {card['card_id']}", "", card["question"], "", f"State: **{card['state']}**", "",
                "Leadership: " + card["leadership_answer"], "", "Practitioner: " + card["practitioner_answer"], ""]
        for item in card["diagnostics"]:
            out.append("- " + item)
        out += ["", "Related: " + (", ".join(card["related_card_ids"]) or "NONE"), ""]
        for ref in card["citation_ids"]:
            cite = pack["citations"][ref]
            out += [f"### Source {ref}", "", f"{cite['source_key']} / {cite['locator']}",
                    "", "SHA-256: " + cite["source_sha256"], "", cite["excerpt"], "",
                    "```json", dumps(cite["original"]).rstrip(), "```", "", *cite["diagnostics"], ""]
    return "\n".join(out)


def render_html(pack):
    esc = html.escape
    out = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">',
        '<title>Evidence discussion kit</title><style>body{font:16px system-ui;max-width:76rem;margin:2rem auto;padding:0 1rem;line-height:1.5}section,article{border:1px solid #bac4ca;border-radius:.4rem;padding:1rem;margin:1rem 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f3f5;padding:1rem}label,input{display:block}input{font:inherit;padding:.5rem;width:95%}a{color:#075aa8}.state{font-weight:bold}small{overflow-wrap:anywhere}[hidden]{display:none}</style>',
        '<h1>Evidence discussion kit</h1><p>' + esc(pack["notice"]) + '</p>',
        '<label for="query">Search cards and quoted records (all words)</label><input id="query" type="search" placeholder="RIS security disagreement"><p id="count" role="status"></p><main>']
    for card in pack["cards"]:
        out += [f'<section class="card" id="{anchor(card["card_id"])}"><h2>{esc(card["card_id"])}</h2>',
                '<h3>' + esc(card["question"]) + '</h3><p class="state">' + esc(card["state"]) + '</p>',
                '<p><b>Leadership.</b> ' + esc(card["leadership_answer"]) + '</p>',
                '<p><b>Practitioner.</b> ' + esc(card["practitioner_answer"]) + '</p>',
                '<ul>' + ''.join('<li>' + esc(x) + '</li>' for x in card["diagnostics"]) + '</ul>',
                '<p>Related: ' + (', '.join(f'<a href="#{anchor(x)}">{esc(x)}</a>' for x in card["related_card_ids"]) or 'NONE') + '</p>']
        for ref in card["citation_ids"]:
            cite = pack["citations"][ref]
            out += ['<details><summary>Source: ' + esc(ref) + '</summary><p>' + esc(cite["locator"]) + '</p>',
                    f'<p><a href="{esc(cite["source_key"], quote=True)}">Local source snapshot</a></p>',
                    '<small>SHA-256: ' + esc(cite["source_sha256"]) + '</small><blockquote>' + esc(cite["excerpt"]) + '</blockquote>',
                    '<pre>' + esc(dumps(cite["original"])) + '</pre><p>' + esc('; '.join(cite["diagnostics"])) + '</p></details>']
        out.append('</section>')
    out += ['</main><script>const q=document.getElementById("query"), cards=[...document.querySelectorAll(".card")]; function filter(){const terms=q.value.toLowerCase().trim().split(/\\s+/).filter(Boolean);let n=0;for(const c of cards){c.hidden=!terms.every(t=>c.textContent.toLowerCase().includes(t));if(!c.hidden)n++;}document.getElementById("count").textContent=n+" of "+cards.length+" cards";}q.addEventListener("input",filter);document.addEventListener("click",e=>{const a=e.target.closest("a");if(a && a.getAttribute("href").startsWith("#")){q.value="";filter();}});filter();</script></html>']
    return "\n".join(out) + "\n"


def verify_bundle(root):
    root = Path(root)
    saved = read_json(read(root / "discussion.json"))
    rebuilt, _ = build(root / "inputs/search/manifest.json", root / "inputs/report.json", root / "inputs/register.json")
    if saved != rebuilt:
        raise DiscussionError("STALE_OR_CHANGED_BUNDLE: source bindings or derived discussion do not match")
    for name, expected in (("discussion.md", render_markdown(rebuilt)), ("discussion.html", render_html(rebuilt))):
        if (root / name).read_text(encoding="utf-8") != expected:
            raise DiscussionError("CHANGED_RENDERED_EXPORT:" + name)
    return rebuilt


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--report", type=Path, required=True)
    b.add_argument("--manifest", type=Path, default=REVENUE / "uiowa_rfq_18649_local_search/fixtures/manifest.json")
    b.add_argument("--register", type=Path, default=REVENUE / "uiowa_rfq_18649_recommendation_register/examples/synthetic_register.json")
    b.add_argument("--out", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("bundle", type=Path)
    q = sub.add_parser("query")
    q.add_argument("bundle", type=Path)
    q.add_argument("question")
    q.add_argument("--limit", type=int, default=5)
    by = sub.add_parser("show")
    by.add_argument("bundle", type=Path)
    by.add_argument("card_id")
    args = ap.parse_args()
    if args.command == "build":
        pack, snapshots = build(args.manifest, args.report, args.register)
        args.out.mkdir(parents=True, exist_ok=False)
        for name, raw in snapshots.items():
            dest = args.out / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("xb") as stream:
                stream.write(raw)
        for name, text in (("discussion.json", dumps(pack)), ("discussion.md", render_markdown(pack)), ("discussion.html", render_html(pack))):
            with (args.out / name).open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
        print(dumps(dict(status="EXPORTED_DRAFT", cards=len(pack["cards"]), citations=len(pack["citations"]), report_receipt=pack["report_receipt"])), end="")
        return 0
    pack = verify_bundle(args.bundle)
    if args.command == "verify":
        print(dumps(dict(status="INTEGRITY_ONLY", cards=len(pack["cards"]), current_authority_verified=False)), end="")
        return 0
    selected = {x["card_id"]: x for x in pack["cards"]}
    if args.command == "show":
        cards = [selected[args.card_id]] if args.card_id in selected else []
    else:
        cards = [selected[x["record_id"]] for x in search.search(pack["search_index"], args.question, args.limit)]
    refs = sorted({x for c in cards for x in c["citation_ids"]})
    print(dumps(dict(status="FOUND" if cards else "NO_SUPPORTED_CARD", notice=NOTICE, cards=cards,
                     citations={x: pack["citations"][x] for x in refs})), end="")
    return 0 if cards else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, UnicodeError, KeyError, TypeError, RecursionError) as exc:
        print(dumps(dict(status="ERROR", error=str(exc))), file=sys.stderr, end="")
        raise SystemExit(2)
