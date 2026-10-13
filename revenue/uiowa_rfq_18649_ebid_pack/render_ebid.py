#!/usr/bin/env python3
"""UIOWA-001/UIOWA-131 offline eBid assembly and exact-field renderer.

Preparation only. Never logs in to eBid or submits a response.
"""
from __future__ import annotations
import argparse, csv, json, re, shutil, sys
from pathlib import Path

ATTACH_RE = re.compile(r"\[\[ATTACH:([a-z0-9_.-]+)\]\]")
TEXT_STATUSES = {"ready", "draft_requires_owner", "owner_required", "optional_blank"}
CHECKBOX_STATUSES = {"authorized", "owner_required"}

class PackError(ValueError):
    pass

def load_json(path: Path):
    with path.open("r", encoding="utf-8") as h:
        return json.load(h)

def char_metrics(text: str):
    return {
        "codepoints": len(text),
        "utf16_units": len(text.encode("utf-16-le")) // 2,
        "utf8_bytes": len(text.encode("utf-8")),
    }

def portal_count(text: str) -> int:
    m = char_metrics(text)
    return max(m["codepoints"], m["utf16_units"])

def validate_map(field_map: dict):
    errors = []
    attrs = field_map.get("attributes")
    if not isinstance(attrs, list):
        return ["field-map attributes must be a list"]
    ids = [a.get("attribute_id") for a in attrs if isinstance(a, dict)]
    if ids != list(range(1, 37)):
        errors.append("field-map must contain attributes 1..36 exactly once in order")
    seen = set()
    for a in attrs:
        if not isinstance(a, dict):
            errors.append("every attribute map entry must be an object")
            continue
        aid = a.get("attribute_id")
        expected = f"attribute_{aid:02d}" if isinstance(aid, int) else None
        if a.get("field_id") != expected:
            errors.append(f"attribute {aid}: field_id must be {expected}")
        if a.get("field_id") in seen:
            errors.append(f"duplicate field_id {a.get('field_id')}")
        seen.add(a.get("field_id"))
        typ = a.get("response_type")
        if typ not in {"text", "checkbox", "informational"}:
            errors.append(f"attribute {aid}: invalid response_type")
        limit = a.get("character_limit")
        if limit is not None and (not isinstance(limit, int) or limit <= 0):
            errors.append(f"attribute {aid}: invalid character_limit")
        if typ == "text" and limit is None:
            errors.append(f"attribute {aid}: text response missing character_limit")
        if typ != "text" and limit is not None:
            errors.append(f"attribute {aid}: non-text response has character_limit")
    return errors

def render_pack(field_map, answers, attachments, source_state, out_dir: Path):
    errors = validate_map(field_map)
    blockers = []
    rows = []
    attr_dir = out_dir / "attributes"
    attr_dir.mkdir(parents=True, exist_ok=True)
    amap = answers.get("attributes", {})
    attmap = attachments.get("attachments", {})
    if not isinstance(amap, dict):
        raise PackError("answers.attributes must be an object")
    if not isinstance(attmap, dict):
        raise PackError("attachments.attachments must be an object")

    valid_fids = {a["field_id"] for a in field_map.get("attributes", [])}
    unknown = sorted(set(amap) - valid_fids)
    if unknown:
        errors.append("unknown answer fields: " + ", ".join(unknown))

    preview = [
        "# RFQ 18649 eBid prepared-field preview", "",
        "**PREPARATION ONLY — NOT A SUBMISSION.**", "",
        f"Known current response deadline overlay: **{source_state.get('deadline_overlay', {}).get('value')}**.", "",
        "The original Bid Invitation used for field layout prints the superseded September 22 deadline. "
        "The controlling eBid solicitation/amendments must be refreshed before submission.", ""
    ]

    for a in field_map.get("attributes", []):
        aid, fid = a["attribute_id"], a["field_id"]
        typ, required, limit = a["response_type"], bool(a["required"]), a["character_limit"]
        entry = amap.get(fid)
        row = {
            "surface":"attribute","field_id":fid,"number":aid,"title":a["title"],
            "response_type":typ,"required":required,"character_limit":limit,
            "status":"informational" if typ=="informational" else None,
            "draft_location":"","owner_action":"","source_page":a["source_page"],
            "certification_or_agreement":bool(a.get("certification_or_agreement"))
        }
        preview += [f"## Attribute {aid} — {a['title']}", ""]

        if typ == "informational":
            if entry is not None:
                errors.append(f"{fid}: informational attribute must not have an answer record")
            preview += ["Portal response: **none (informational)**", ""]
            rows.append(row); continue

        if entry is None:
            errors.append(f"{fid}: missing answer/accounting record")
            row["status"] = "missing_record"
            preview += ["Status: **MISSING ACCOUNTING RECORD**", ""]
            rows.append(row); continue

        status = entry.get("status")
        row["status"] = status
        row["owner_action"] = entry.get("owner_action", "")

        if typ == "checkbox":
            if status not in CHECKBOX_STATUSES:
                errors.append(f"{fid}: invalid checkbox status {status!r}")
            if status == "authorized":
                if entry.get("authorized_value") != "checked" or not entry.get("authorization_ref"):
                    errors.append(f"{fid}: authorized checkbox requires checked value + authorization_ref")
                preview += ["Status: **AUTHORIZED MANUAL CHECKBOX**", "",
                            f"Authorization reference: \\{entry.get('authorization_ref')}\\", ""]
            else:
                blockers.append(f"{fid}: required agreement/certification needs authorized human disposition")
                preview += ["Status: **OWNER/AUTHORIZATION REQUIRED — DO NOT AUTO-CHECK**", "",
                            entry.get("owner_action", ""), ""]
            rows.append(row); continue

        if status not in TEXT_STATUSES:
            errors.append(f"{fid}: invalid text status {status!r}")
        text = entry.get("text")

        if status == "optional_blank":
            if required:
                errors.append(f"{fid}: required field cannot use optional_blank")
            if a.get("blank_has_certification_effect"):
                errors.append(f"{fid}: blank has certification effect and requires explicit authorization")
            preview += ["Status: **OPTIONAL — INTENTIONALLY UNPOPULATED IN PREPARATION PACK**", ""]
            rows.append(row); continue

        if not isinstance(text, str) or not text.strip():
            if required or a.get("blank_has_certification_effect"):
                blockers.append(f"{fid}: required/certification-sensitive text is unresolved")
            preview += [f"Status: **{str(status).upper()}**", "", entry.get("owner_action", ""), ""]
            rows.append(row); continue

        count, metrics = portal_count(text), char_metrics(text)
        if count > limit:
            errors.append(f"{fid}: {count} conservative characters exceeds limit {limit}")
        refs = ATTACH_RE.findall(text)
        missing_refs = [ref for ref in refs if ref not in attmap]
        if missing_refs:
            errors.append(f"{fid}: unknown attachment refs: {', '.join(missing_refs)}")

        rel = f"outputs/attributes/attr-{aid:02d}.txt"
        dest = attr_dir / f"attr-{aid:02d}.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        if dest.read_text(encoding="utf-8") != text:
            raise PackError(f"{fid}: rendered text did not round-trip")
        row["draft_location"] = rel

        if status != "ready":
            blockers.append(f"{fid}: drafted text requires authorized owner review")
        for ref in refs:
            if attmap.get(ref, {}).get("required") and attmap.get(ref, {}).get("status") != "final_ready":
                blockers.append(f"{fid}: attachment reference {ref} is not final_ready")

        preview += [
            f"Status: **{status.upper()}**", "",
            f"Character count: **{count}/{limit}** conservative "
            f"(code points {metrics['codepoints']}, UTF-16 units {metrics['utf16_units']}, UTF-8 bytes {metrics['utf8_bytes']})",
            "", "~~~text", text, "~~~", ""
        ]
        if entry.get("owner_action"):
            preview += ["Owner action:", entry["owner_action"], ""]
        rows.append(row)

    expected_atts = {x["attachment_id"] for x in field_map.get("requested_attachments", [])}
    for spec in field_map.get("requested_attachments", []):
        key = spec["attachment_id"]; entry = attmap.get(key)
        if entry is None:
            errors.append(f"attachment {key}: missing inventory record"); continue
        status = entry.get("status")
        if spec.get("required") and status != "final_ready":
            blockers.append(f"attachment {key}: required attachment is {status}, not final_ready")
        rows.append({
            "surface":"attachment","field_id":key,"number":"","title":spec["title"],
            "response_type":"file","required":bool(spec.get("required")),"character_limit":"",
            "status":status,"draft_location":entry.get("final_file") or " | ".join(entry.get("draft_sources", [])),
            "owner_action":entry.get("owner_action",""),"source_page":1,"certification_or_agreement":False
        })
    extra = sorted(set(attmap)-expected_atts)
    if extra:
        errors.append("unknown attachment inventory ids: "+", ".join(extra))

    fee = answers.get("bid_line",{}).get("fee_for_services")
    if not isinstance(fee, dict):
        errors.append("fee_for_services accounting record missing")
    else:
        ftext = fee.get("fee_details")
        if not isinstance(ftext,str) or not ftext.strip():
            errors.append("fee_for_services: fee_details text missing")
        else:
            lim = field_map["bid_lines"][0]["item_attributes"][0]["character_limit"]
            if portal_count(ftext) > lim:
                errors.append(f"fee_for_services fee details exceed {lim}")
            (out_dir/"fee-details.txt").write_text(ftext, encoding="utf-8")
        if fee.get("status") != "ready":
            blockers.append("fee_for_services: final inclusive Supplier price/fee details require authorized bidder approval")
        rows.append({
            "surface":"bid_line","field_id":"fee_for_services","number":1,"title":"Fee for Services / Fee Details",
            "response_type":"price+text","required":True,"character_limit":4000,"status":fee.get("status"),
            "draft_location":"outputs/fee-details.txt","owner_action":fee.get("owner_action",""),
            "source_page":15,"certification_or_agreement":False
        })

    supplier = answers.get("supplier_information")
    if not isinstance(supplier, dict):
        errors.append("supplier_information accounting record missing")
    else:
        if supplier.get("status") != "authorized":
            blockers.append("supplier_information: verified company/contact/signature authority required")
        elif not supplier.get("authorization_ref"):
            errors.append("supplier_information: authorized status requires authorization_ref")
        rows.append({
            "surface":"supplier_information","field_id":"supplier_information","number":"",
            "title":"Supplier Information / binding signature","response_type":"manual+signature",
            "required":True,"character_limit":"","status":supplier.get("status"),"draft_location":"",
            "owner_action":supplier.get("owner_action",""),"source_page":16,"certification_or_agreement":True
        })

    refresh = source_state.get("official_refresh", {})
    if refresh.get("required_before_submit") and not refresh.get("confirmed"):
        blockers.append("source_refresh: controlling official eBid solicitation/amendments not yet re-read for submission")

    cols=["surface","field_id","number","title","response_type","required","character_limit","status",
          "draft_location","owner_action","source_page","certification_or_agreement"]
    with (out_dir/"submission-index.csv").open("w",encoding="utf-8",newline="") as h:
        w=csv.DictWriter(h,fieldnames=cols); w.writeheader()
        for row in rows:
            w.writerow({
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in row.items()
            })
    (out_dir/"combined-preview.md").write_text("\n".join(preview),encoding="utf-8")
    report={
        "rfq_number":field_map.get("rfq_number"),"attribute_count":len(field_map.get("attributes",[])),
        "accounted_surfaces":len(rows),"errors":errors,"blockers":sorted(set(blockers)),
        "structurally_valid":not errors,"submission_ready":not errors and not blockers,
        "deadline_overlay":source_state.get("deadline_overlay"),"official_refresh":refresh
    }
    (out_dir/"validation-report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return report

def main(argv=None):
    p=argparse.ArgumentParser(); base=Path(__file__).resolve().parent
    p.add_argument("--field-map",type=Path,default=base/"field-map.json")
    p.add_argument("--answers",type=Path,default=base/"answers.json")
    p.add_argument("--attachments",type=Path,default=base/"attachments.json")
    p.add_argument("--source-state",type=Path,default=base/"source-state.json")
    p.add_argument("--out",type=Path,default=base/"outputs")
    p.add_argument("--mode",choices=["prepared","submit-ready"],default="prepared")
    args=p.parse_args(argv)
    try:
        if args.out.exists():
            for name in ("combined-preview.md","submission-index.csv","validation-report.json","fee-details.txt"):
                q=args.out/name
                if q.exists(): q.unlink()
            if (args.out/"attributes").exists(): shutil.rmtree(args.out/"attributes")
        report=render_pack(load_json(args.field_map),load_json(args.answers),load_json(args.attachments),load_json(args.source_state),args.out)
    except (PackError,OSError,json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr); return 2
    print(f"structurally_valid={str(report['structurally_valid']).lower()} submission_ready={str(report['submission_ready']).lower()} errors={len(report['errors'])} blockers={len(report['blockers'])}")
    if report["errors"]:
        for e in report["errors"]: print(f"ERROR: {e}",file=sys.stderr)
        return 2
    if args.mode=="submit-ready" and report["blockers"]:
        for b in report["blockers"]: print(f"BLOCKER: {b}",file=sys.stderr)
        return 3
    return 0

if __name__=="__main__":
    raise SystemExit(main())
