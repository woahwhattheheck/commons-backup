"""Fail-closed solicitation/amendment ingest.

Converts buyer-official solicitation + amendment captures into:
- an active requirement set
- a selector compatible with procurement-response-modules/solicitation/v1
- a deadline/readiness record
- a human evidence-gap worklist

Secondary sources never create or supersede requirements. Unknown target,
same/later-sequence supersession, duplicate/cyclic lineage, or two active
values for one lineage fail closed. Zero or multiple active submission
deadlines HOLD. OCR/table guesses are never buyer truth.

This layer never authorizes proposal, submission, buyer/prime contact,
portal action, signature, certification, pricing, award, payment, or revenue.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACK = "procurement-solicitation-ingest/pack/v1"
ACTIVE = "procurement-solicitation-ingest/active-set/v1"
GAPS = "procurement-solicitation-ingest/gaps/v1"
READY = "procurement-solicitation-ingest/readiness/v1"
REC = "procurement-solicitation-ingest/receipt/v1"
SOL = "procurement-response-modules/solicitation/v1"
BOUNDARY = "INTERNAL_OWNER_REVIEW_ONLY"
SRC_CLASS = {"BUYER_OFFICIAL", "SECONDARY"}
DOC_KIND = {"SOLICITATION", "AMENDMENT"}
REQ_KIND = {"MANDATORY", "SCORED", "INFORMATIONAL"}
TOK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(Z|[+-]\d{2}:\d{2})$")
HOSTILE_KEYS = {
    "ocr",
    "ocr_guess",
    "table_guess",
    "inferred",
    "guess",
    "promoted_from",
    "derived",
    "extracted_guess",
}


class Error(ValueError):
    pass


@dataclass(frozen=True)
class Output:
    selector: bytes
    active: bytes
    gaps: bytes
    markdown: bytes
    readiness: bytes
    receipt: bytes
    status: str


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise Error(f"duplicate JSON key: {k}")
        out[k] = v
    return out


def _bad(v):
    raise Error(f"non-integer JSON number forbidden: {v}")


def load(raw: bytes, label="input"):
    if not isinstance(raw, (bytes, bytearray)):
        raise Error(f"{label}: bytes required")
    raw = bytes(raw)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise Error(f"{label}: BOM forbidden")
    try:
        v = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_float=_bad,
            parse_constant=_bad,
        )
    except Error:
        raise
    except Exception as e:
        raise Error(f"{label}: invalid JSON/UTF-8") from e
    if not isinstance(v, dict):
        raise Error(f"{label}: object required")
    return v


def canon(v):
    return (json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def digest(b):
    return hashlib.sha256(b).hexdigest()


def keys(v, want, where):
    if not isinstance(v, dict):
        raise Error(f"{where}: object required")
    extra = set(v) - set(want)
    missing = set(want) - set(v)
    if extra or missing:
        raise Error(f"{where}: keys mismatch")
    hostile = extra & HOSTILE_KEYS
    if hostile:
        raise Error(f"{where}: OCR/table guess keys forbidden")
    return v


def s(v, w, token=False, limit=4096):
    if not isinstance(v, str) or not v or len(v) > limit or any(ord(c) < 32 and c not in "\n\t" for c in v):
        raise Error(f"{w}: invalid string")
    if token and not TOK.fullmatch(v):
        raise Error(f"{w}: invalid token")
    return v


def i(v, w, lo=0, hi=10**9):
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise Error(f"{w}: integer required")
    return v


def b(v, w):
    if not isinstance(v, bool):
        raise Error(f"{w}: boolean required")
    return v


def sh(v, w):
    v = s(v, w, limit=64)
    if not SHA.fullmatch(v):
        raise Error(f"{w}: sha256 required")
    return v


def parse_offset_dt(v, w):
    v = s(v, w, limit=32)
    if not TS.fullmatch(v):
        raise Error(f"{w}: RFC3339-with-offset timestamp required")
    try:
        if v.endswith("Z"):
            dt = datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(v)
            if dt.tzinfo is None:
                raise ValueError
    except ValueError as e:
        raise Error(f"{w}: RFC3339-with-offset timestamp required") from e
    return v, dt.astimezone(timezone.utc)


def to_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def toks(v, w, minn=0, maxn=64):
    if not isinstance(v, list) or not minn <= len(v) <= maxn:
        raise Error(f"{w}: invalid list")
    out = [s(x, f"{w}[{n}]", True, 128) for n, x in enumerate(v)]
    if len(out) != len(set(out)):
        raise Error(f"{w}: duplicate item")
    return out


def authority():
    return {
        k: False
        for k in [
            "proposal_authorized",
            "submission_authorized",
            "buyer_contact_authorized",
            "prime_contact_authorized",
            "portal_action_authorized",
            "signature_authorized",
            "certification_authorized",
            "price_commitment_authorized",
            "payment_authorized",
            "award_or_revenue_recognized",
        ]
    }


def _norm_req(x, w):
    keys(x, ["lineage_id", "section_id", "kind", "family", "tags", "text"], w)
    kind = s(x["kind"], w + ".kind", True, 32)
    if kind not in REQ_KIND:
        raise Error(w + ": bad kind")
    return {
        "lineage_id": s(x["lineage_id"], w + ".lineage_id", True),
        "section_id": s(x["section_id"], w + ".section_id", True),
        "kind": kind,
        "family": s(x["family"], w + ".family", True),
        "tags": toks(x["tags"], w + ".tags"),
        "text": s(x["text"], w + ".text"),
    }


def _norm_deadline(x, w):
    if x is None:
        return None
    keys(x, ["value", "supersedes_deadline"], w)
    value, dt = parse_offset_dt(x["value"], w + ".value")
    return {"value": value, "utc": to_z(dt), "dt": dt, "supersedes_deadline": b(x["supersedes_deadline"], w + ".supersedes_deadline")}


def _norm_att(x, w):
    keys(x, ["attachment_id", "sha256", "ref"], w)
    return {
        "attachment_id": s(x["attachment_id"], w + ".attachment_id", True),
        "sha256": sh(x["sha256"], w + ".sha256"),
        "ref": s(x["ref"], w + ".ref", limit=2048),
    }


def _norm_source(x, n, eval_dt, maxage):
    w = f"sources[{n}]"
    keys(
        x,
        [
            "source_id",
            "source_class",
            "kind",
            "identity",
            "ref",
            "sha256",
            "captured_at",
            "sequence",
            "supersedes_sources",
            "supersedes_lineages",
            "requirements",
            "deadline",
            "attachments",
        ],
        w,
    )
    klass = s(x["source_class"], w + ".source_class", True, 32)
    if klass not in SRC_CLASS:
        raise Error(w + ": bad source_class")
    kind = s(x["kind"], w + ".kind", True, 32)
    if kind not in DOC_KIND:
        raise Error(w + ": bad kind")
    cap_raw, cap_dt = parse_offset_dt(x["captured_at"], w + ".captured_at")
    age = int((eval_dt - cap_dt).total_seconds())
    if age < 0:
        raise Error(w + ": future source")
    if age > maxage:
        raise Error(w + ": stale source")
    if not isinstance(x["requirements"], list):
        raise Error(w + ": requirements list required")
    reqs = [_norm_req(r, f"{w}.requirements[{q}]") for q, r in enumerate(x["requirements"])]
    lids = [r["lineage_id"] for r in reqs]
    if len(lids) != len(set(lids)):
        raise Error(w + ": duplicate lineage_id")
    if not isinstance(x["attachments"], list):
        raise Error(w + ": attachments list required")
    atts = [_norm_att(a, f"{w}.attachments[{q}]") for q, a in enumerate(x["attachments"])]
    aids = [a["attachment_id"] for a in atts]
    if len(aids) != len(set(aids)):
        raise Error(w + ": duplicate attachment_id")
    src = {
        "source_id": s(x["source_id"], w + ".source_id", True),
        "source_class": klass,
        "kind": kind,
        "identity": s(x["identity"], w + ".identity", True, 256),
        "ref": s(x["ref"], w + ".ref", limit=2048),
        "sha256": sh(x["sha256"], w + ".sha256"),
        "captured_at": cap_raw,
        "captured_at_utc": to_z(cap_dt),
        "captured_dt": cap_dt,
        "sequence": i(x["sequence"], w + ".sequence", 1, 10**6),
        "supersedes_sources": toks(x["supersedes_sources"], w + ".supersedes_sources"),
        "supersedes_lineages": toks(x["supersedes_lineages"], w + ".supersedes_lineages"),
        "requirements": reqs,
        "deadline": _norm_deadline(x["deadline"], w + ".deadline"),
        "attachments": atts,
    }
    if klass == "BUYER_OFFICIAL" and kind == "AMENDMENT":
        if not src["supersedes_sources"] and not src["supersedes_lineages"] and not (
            src["deadline"] and src["deadline"]["supersedes_deadline"]
        ):
            raise Error(w + ": amendment must explicitly supersede a source, lineage, or deadline")
    return src


def _cycle(edges: dict[str, list[str]]):
    seen = set()
    stack = set()

    def walk(n):
        if n in stack:
            return True
        if n in seen:
            return False
        stack.add(n)
        for m in edges.get(n, []):
            if walk(m):
                return True
        stack.remove(n)
        seen.add(n)
        return False

    return any(walk(n) for n in edges)


def _norm_pack(v):
    keys(v, ["schema", "pack_id", "evaluated_at", "source_max_age_seconds", "truth_boundary", "sources"], "pack")
    if v["schema"] != PACK or v["truth_boundary"] != BOUNDARY:
        raise Error("pack: unsupported schema/boundary")
    eval_raw, eval_dt = parse_offset_dt(v["evaluated_at"], "pack.evaluated_at")
    maxage = i(v["source_max_age_seconds"], "pack.source_max_age_seconds", 1, 31536000)
    if not isinstance(v["sources"], list) or not v["sources"]:
        raise Error("pack: sources required")
    sources = [_norm_source(x, n, eval_dt, maxage) for n, x in enumerate(v["sources"])]
    ids = [x["source_id"] for x in sources]
    if len(ids) != len(set(ids)):
        raise Error("pack: duplicate source_id")
    return {
        "pack_id": s(v["pack_id"], "pack.pack_id", True),
        "evaluated_at": eval_raw,
        "evaluated_at_utc": to_z(eval_dt),
        "evaluated_dt": eval_dt,
        "source_max_age_seconds": maxage,
        "sources": sources,
    }


def compile_ingest(raw: bytes) -> Output:
    pack = _norm_pack(load(raw, "pack"))
    official = [x for x in pack["sources"] if x["source_class"] == "BUYER_OFFICIAL"]
    secondary = [x for x in pack["sources"] if x["source_class"] == "SECONDARY"]
    if not official:
        raise Error("pack: BUYER_OFFICIAL source required")
    seqs = [x["sequence"] for x in official]
    if len(seqs) != len(set(seqs)):
        raise Error("pack: duplicate official sequence")
    official_ids = {x["source_id"] for x in official}
    by_id = {x["source_id"]: x for x in official}

    edges = {x["source_id"]: list(x["supersedes_sources"]) for x in official}
    for src in official:
        for t in src["supersedes_sources"]:
            if t not in official_ids:
                raise Error(f"{src['source_id']}: unknown supersession target {t}")
            target = by_id[t]
            if src["sequence"] <= target["sequence"]:
                raise Error(f"{src['source_id']}: same/later-sequence supersession of {t}")
    if _cycle(edges):
        raise Error("pack: cyclic lineage")

    official_sorted = sorted(official, key=lambda x: (x["sequence"], x["source_id"]))
    active_req: dict[str, dict[str, Any]] = {}
    origin: dict[str, str] = {}
    active_deadlines: list[dict[str, Any]] = []
    killed_sources: set[str] = set()

    def kill_source(sid: str):
        killed_sources.add(sid)
        dead = [lid for lid, s in origin.items() if s == sid]
        for lid in dead:
            active_req.pop(lid, None)
            origin.pop(lid, None)
        active_deadlines[:] = [d for d in active_deadlines if d["source_id"] != sid]
        for child in list(official_ids):
            if sid in by_id[child]["supersedes_sources"] and child not in killed_sources:
                # only kill descendants already applied; later sources handled in-order
                pass

    for src in official_sorted:
        for t in src["supersedes_sources"]:
            kill_source(t)
        for lid in src["supersedes_lineages"]:
            if lid not in origin and lid not in {r["lineage_id"] for r in src["requirements"]}:
                raise Error(f"{src['source_id']}: unknown supersession target {lid}")
            active_req.pop(lid, None)
            origin.pop(lid, None)
        if src["deadline"] and src["deadline"]["supersedes_deadline"]:
            active_deadlines.clear()
        for req in src["requirements"]:
            lid = req["lineage_id"]
            if lid in active_req:
                raise Error(f"{src['source_id']}: two active values for lineage {lid}")
            row = {
                **req,
                "source_id": src["source_id"],
                "source_identity": src["identity"],
                "source_ref": src["ref"],
                "source_sha256": src["sha256"],
                "source_captured_at": src["captured_at"],
                "sequence": src["sequence"],
            }
            active_req[lid] = row
            origin[lid] = src["source_id"]
        if src["deadline"]:
            if not src["deadline"]["supersedes_deadline"] and active_deadlines:
                # two active deadlines unless this is the first
                active_deadlines.append(
                    {
                        "source_id": src["source_id"],
                        "value": src["deadline"]["value"],
                        "utc": src["deadline"]["utc"],
                        "identity": src["identity"],
                        "ref": src["ref"],
                        "sha256": src["sha256"],
                    }
                )
            else:
                active_deadlines.append(
                    {
                        "source_id": src["source_id"],
                        "value": src["deadline"]["value"],
                        "utc": src["deadline"]["utc"],
                        "identity": src["identity"],
                        "ref": src["ref"],
                        "sha256": src["sha256"],
                    }
                )

    gaps = []
    for sec in secondary:
        if sec["requirements"] or (sec["deadline"] is not None) or sec["supersedes_sources"] or sec["supersedes_lineages"]:
            gaps.append(
                {
                    "gap_id": f"secondary-rejected:{sec['source_id']}",
                    "severity": "INFORMATIONAL",
                    "blocking": False,
                    "reason": "SECONDARY_SOURCE_CANNOT_CREATE_OR_SUPERSEDE",
                    "detail": f"Secondary source `{sec['source_id']}` was ignored for requirement and deadline authority.",
                    "source_id": sec["source_id"],
                    "source_ref": sec["ref"],
                    "source_sha256": sec["sha256"],
                }
            )

    holds = []
    if len(active_deadlines) != 1:
        holds.append("ZERO_OR_MULTIPLE_ACTIVE_SUBMISSION_DEADLINES")
        gaps.append(
            {
                "gap_id": "deadline-active-count",
                "severity": "HOLD",
                "blocking": True,
                "reason": "ZERO_OR_MULTIPLE_ACTIVE_SUBMISSION_DEADLINES",
                "detail": f"Active submission deadline count is {len(active_deadlines)}; exactly one source-bound deadline is required.",
                "source_id": None,
                "source_ref": None,
                "source_sha256": None,
            }
        )

    for lid, req in sorted(active_req.items()):
        blocking = req["kind"] in {"MANDATORY", "SCORED"}
        if blocking:
            gaps.append(
                {
                    "gap_id": f"human-evidence:{lid}",
                    "severity": "HOLD" if req["kind"] == "MANDATORY" else "SCORED",
                    "blocking": True,
                    "reason": "BLOCKING_REQUIREMENT_NEEDS_OWNER_EVIDENCE",
                    "detail": req["text"],
                    "source_id": req["source_id"],
                    "source_ref": req["source_ref"],
                    "source_sha256": req["source_sha256"],
                    "lineage_id": lid,
                    "kind": req["kind"],
                    "family": req["family"],
                    "section_id": req["section_id"],
                }
            )
        else:
            gaps.append(
                {
                    "gap_id": f"informational:{lid}",
                    "severity": "INFORMATIONAL",
                    "blocking": False,
                    "reason": "INFORMATIONAL_NOT_BLOCKING",
                    "detail": req["text"],
                    "source_id": req["source_id"],
                    "source_ref": req["source_ref"],
                    "source_sha256": req["source_sha256"],
                    "lineage_id": lid,
                    "kind": req["kind"],
                    "family": req["family"],
                    "section_id": req["section_id"],
                }
            )

    attachments = []
    for src in official_sorted:
        if src["source_id"] in killed_sources:
            continue
        for a in src["attachments"]:
            attachments.append(
                {
                    **a,
                    "source_id": src["source_id"],
                    "source_identity": src["identity"],
                    "source_ref": src["ref"],
                    "source_sha256": src["sha256"],
                }
            )

    current_src = official_sorted[-1]
    for src in reversed(official_sorted):
        if src["source_id"] not in killed_sources:
            current_src = src
            break

    selector_reqs = []
    for req in sorted(active_req.values(), key=lambda r: r["section_id"]):
        selector_reqs.append(
            {
                "section_id": req["section_id"],
                "family": req["family"],
                "required_tags": sorted(req["tags"]),
                "required": req["kind"] in {"MANDATORY", "SCORED"},
            }
        )
    if not selector_reqs:
        holds.append("NO_ACTIVE_REQUIREMENTS")
        gaps.append(
            {
                "gap_id": "no-active-requirements",
                "severity": "HOLD",
                "blocking": True,
                "reason": "NO_ACTIVE_REQUIREMENTS",
                "detail": "No active buyer-official requirements remained after supersession.",
                "source_id": None,
                "source_ref": None,
                "source_sha256": None,
            }
        )

    observed = min(x["captured_dt"] for x in official)
    selector = {
        "schema": SOL,
        "solicitation_id": pack["pack_id"],
        "source_ref": current_src["ref"],
        "source_sha256": current_src["sha256"],
        "observed_at": to_z(observed),
        "generated_at": pack["evaluated_at_utc"],
        "source_max_age_seconds": pack["source_max_age_seconds"],
        "requirements": selector_reqs,
    }

    active_set = {
        "schema": ACTIVE,
        "truth_boundary": BOUNDARY,
        "pack_id": pack["pack_id"],
        "evaluated_at": pack["evaluated_at"],
        "current_source": {
            "source_id": current_src["source_id"],
            "identity": current_src["identity"],
            "ref": current_src["ref"],
            "sha256": current_src["sha256"],
            "captured_at": current_src["captured_at"],
            "sequence": current_src["sequence"],
        },
        "deadline": None
        if len(active_deadlines) != 1
        else {
            "value": active_deadlines[0]["value"],
            "utc": active_deadlines[0]["utc"],
            "source_id": active_deadlines[0]["source_id"],
            "identity": active_deadlines[0]["identity"],
            "ref": active_deadlines[0]["ref"],
            "sha256": active_deadlines[0]["sha256"],
        },
        "requirements": [active_req[k] for k in sorted(active_req)],
        "attachments": attachments,
        "killed_sources": sorted(killed_sources),
        "authority": authority(),
    }
    # strip non-serializable
    for r in active_set["requirements"]:
        r.pop("captured_dt", None)

    status = "HOLD" if holds else "OWNER_REVIEW_READY"
    gap_obj = {
        "schema": GAPS,
        "truth_boundary": BOUNDARY,
        "pack_id": pack["pack_id"],
        "status": status,
        "hold_reasons": sorted(set(holds)),
        "gaps": sorted(gaps, key=lambda g: g["gap_id"]),
        "authority": authority(),
    }

    ready = {
        "schema": READY,
        "truth_boundary": BOUNDARY,
        "pack_id": pack["pack_id"],
        "status": status,
        "evaluated_at": pack["evaluated_at"],
        "active_deadline": active_set["deadline"],
        "blocking_requirement_count": sum(1 for r in active_req.values() if r["kind"] in {"MANDATORY", "SCORED"}),
        "informational_requirement_count": sum(1 for r in active_req.values() if r["kind"] == "INFORMATIONAL"),
        "gap_count": len(gap_obj["gaps"]),
        "hold_reasons": sorted(set(holds)),
        "authority": authority(),
    }

    md = _markdown(pack["pack_id"], status, active_set, gap_obj, selector)
    sb = canon(selector)
    ab = canon(active_set)
    gb = canon(gap_obj)
    rb = canon(ready)
    rec = {
        "schema": REC,
        "truth_boundary": BOUNDARY,
        "status": status,
        "pack_id": pack["pack_id"],
        "pack_sha256": digest(raw),
        "selector_sha256": digest(sb),
        "active_set_sha256": digest(ab),
        "gaps_sha256": digest(gb),
        "markdown_sha256": digest(md),
        "readiness_sha256": digest(rb),
        "authority": authority(),
    }
    return Output(sb, ab, gb, md, rb, canon(rec), status)


def _markdown(pack_id, status, active, gaps, selector):
    lines = [
        "# Solicitation ingest evidence-gap worklist",
        "",
        f"- Pack: `{pack_id}`",
        f"- Status: **{status}**",
        "- Authority: **internal owner review only; every external/commercial authority flag is false**",
        f"- Selector schema: `{selector['schema']}`",
        f"- Current official source: `{active['current_source']['identity']}` / `{active['current_source']['sha256']}`",
        "",
        "## Deadline",
        "",
    ]
    if active["deadline"] is None:
        lines.append("No unique source-bound submission deadline is active. This is HOLD.")
    else:
        d = active["deadline"]
        lines.append(f"- Value: `{d['value']}` (UTC `{d['utc']}`)")
        lines.append(f"- Source: `{d['source_id']}` / `{d['sha256']}`")
    lines += ["", "## Active requirements", "", "| Lineage | Kind | Family | Section | Source SHA |", "| --- | --- | --- | --- | --- |"]
    for r in active["requirements"]:
        lines.append(
            f"| `{r['lineage_id']}` | **{r['kind']}** | `{r['family']}` | `{r['section_id']}` | `{r['source_sha256']}` |"
        )
    lines += ["", "## Attachments retained", ""]
    if not active["attachments"]:
        lines.append("None.")
    else:
        for a in active["attachments"]:
            lines.append(f"- `{a['attachment_id']}` `{a['sha256']}` from `{a['source_id']}` (`{a['ref']}`)")
    lines += ["", "## Evidence gaps", ""]
    for g in gaps["gaps"]:
        lines.append(f"- `{g['gap_id']}` · **{g['severity']}** · {g['reason']}: {g['detail']}")
    return ("\n".join(lines).rstrip() + "\n").encode()


def verify(pack: bytes, selector: bytes, active: bytes, gaps: bytes, markdown: bytes, readiness: bytes, receipt: bytes):
    exp = compile_ingest(pack)
    for label, got, want in [
        ("selector", selector, exp.selector),
        ("active_set", active, exp.active),
        ("gaps", gaps, exp.gaps),
        ("markdown", markdown, exp.markdown),
        ("readiness", readiness, exp.readiness),
        ("receipt", receipt, exp.receipt),
    ]:
        if label != "markdown":
            parsed = load(got, label)
            if canon(parsed) != got:
                raise Error(f"{label} non-canonical")
        if got != want:
            raise Error(f"{label} mismatch")
    return {"verified": True, "status": exp.status, "selector_sha256": digest(exp.selector), "receipt_sha256": digest(exp.receipt)}


def _open_regular(path, write=False, exclusive=False):
    flags = os.O_RDONLY
    if write:
        flags = os.O_WRONLY | os.O_CREAT
        if exclusive:
            flags |= os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o644 if write else 0)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise Error(f"{path}: not a regular file")
        if hasattr(os, "O_NONBLOCK"):
            import fcntl

            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl & ~os.O_NONBLOCK)
        return fd
    except Exception:
        os.close(fd)
        raise


def read_bytes(path):
    fd = _open_regular(path)
    try:
        chunks = []
        while True:
            bts = os.read(fd, 1024 * 1024)
            if not bts:
                break
            chunks.append(bts)
        return b"".join(chunks)
    finally:
        os.close(fd)


def write_exclusive(path, data: bytes):
    fd = _open_regular(path, write=True, exclusive=True)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("compile")
    c.add_argument("--pack", required=True)
    c.add_argument("--out-dir", required=True)
    v = sp.add_parser("verify")
    for x in ["--pack", "--selector", "--active-set", "--gaps", "--markdown", "--readiness", "--receipt"]:
        v.add_argument(x, required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "compile":
            o = compile_ingest(read_bytes(a.pack))
            out = Path(a.out_dir)
            out.mkdir(parents=True, exist_ok=True)
            mapping = {
                "selector.json": o.selector,
                "active_set.json": o.active,
                "gaps.json": o.gaps,
                "gaps.md": o.markdown,
                "readiness.json": o.readiness,
                "receipt.json": o.receipt,
            }
            for name, data in mapping.items():
                write_exclusive(str(out / name), data)
            print(json.dumps({"status": o.status, "selector_sha256": digest(o.selector)}, sort_keys=True))
        else:
            print(
                json.dumps(
                    verify(
                        read_bytes(a.pack),
                        read_bytes(a.selector),
                        read_bytes(a.active_set),
                        read_bytes(a.gaps),
                        read_bytes(a.markdown),
                        read_bytes(a.readiness),
                        read_bytes(a.receipt),
                    ),
                    sort_keys=True,
                )
            )
        return 0
    except (Error, OSError, FileExistsError) as e:
        print(f"HOLD: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
