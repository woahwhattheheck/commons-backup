"""Offline UIOWA-135 DRAFT/SYNTHETIC packet assembly; never a payment authority."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
from typing import Any

VERSION = 1
MAX_BYTES = 5_000_000
ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,79}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
EXHIBIT = {
    "repository": "woahwhattheheck/commons",
    "commit": "6caf6adf010111feacffb1a5a57fbdc4526b7366",
    "path": "revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_EXHIBIT.md",
    "git_blob": "48465060fff1402af966871352e894686fffe05e",
    "status": "PROPOSED_NOT_ACCEPTED",
}
MILESTONES = {
    "kickoff": (960000, "WRITTEN_AUTHORIZATION", "Written authorization / kickoff", "5.1"),
    "draft": (960000, "DRAFT_DELIVERY", "Delivery of the draft technical work package", "5.2"),
    "final": (480000, "FINAL_ACCEPTANCE", "Acceptance of the final technical work package", "5.3"),
}
# Concise criterion paraphrases; numbering is the actual proposed exhibit numbering.
CRITERIA = {
    "kickoff": [
        "Scope covers ESS, RIS and IAM across all four technical dimensions.",
        "Requested source classes map to assessment cells.",
        "Source schema identifies source, custodian, evidence reference, authorization, currentness and digest.",
        "Unavailable evidence stays a gap/HOLD, not a fabricated observation.",
        "Prime-owned and University-owned dependencies are distinguished.",
    ],
    "draft": [
        "Every populated technical conclusion traces to delivered source IDs.",
        "The full twelve-cell frame is covered, with explicit HOLD for unsupported cells.",
        "Missing, stale, conflicting and untrusted evidence remains visibly bounded.",
        "Currentness and deterministic recompilation are supplied, or their exact blocker is recorded.",
        "Findings and roadmap remain in scope without unsupported authority or vendor recommendations.",
        "Received comments are incorporated for genuine nonconformance or retained as bounded open decisions.",
    ],
    "final": [
        "Register, matrix, findings, roadmap, limitations, change log and verification identify a coherent generation.",
        "Supported conclusions remain traceable to the delivered evidence universe.",
        "Unresolved evidence stays explicit rather than becoming verified evidence.",
        "Genuine nonconformance corrections are applied or the exact unresolved blocker is documented.",
        "No unsupported University acceptance, executed subcontract, payment or revenue representation is made.",
        "The prime can identify complete/held work, changes from draft and prime-owned decisions.",
    ],
}
NOTICE = ("DRAFT / SYNTHETIC DEMONSTRATION — not University evidence, a qualifying live "
          "delivery, authorization, acceptance, issued invoice, payment request or payment record.")


class PacketError(ValueError):
    """Malformed or unsafe packet input; no output should be published."""


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n").encode()


def integrity_index(files: dict[str, bytes]) -> bytes:
    return canonical({"schema_version": VERSION, "algorithm": "sha256", "files": {
        name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}})


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    out = {}
    for key, value in pairs:
        if key in out:
            raise PacketError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load(path: Path) -> dict:
    if path.stat().st_size > MAX_BYTES:
        raise PacketError("input exceeds size limit")
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(PacketError(f"invalid JSON {x}")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PacketError(f"invalid JSON: {exc}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PacketError(message)


def text(value: Any, name: str) -> str:
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= 12000, f"invalid {name}")
    return value


def identifier(value: Any, name: str) -> str:
    require(isinstance(value, str) and ID.fullmatch(value) is not None, f"invalid {name}")
    return value


def relative(value: Any) -> str:
    text(value, "relative path")
    require("\\" not in value and "\0" not in value and ":" not in value, "invalid path characters")
    require(not PurePosixPath(value).is_absolute() and all(x not in ("", ".", "..") for x in value.split("/")), "path must be canonical and relative")
    return value


def file_bytes(root: Path, rel: str) -> bytes:
    """Read only regular files, without following any input-tree symlink."""
    relative(rel)
    current = root
    for component in rel.split("/"):
        current = current / component
        info = current.lstat()
        require(not stat.S_ISLNK(info.st_mode), f"symlink rejected: {rel}")
    info = current.stat()
    require(stat.S_ISREG(info.st_mode), f"not a regular file: {rel}")
    require(info.st_size <= MAX_BYTES, f"artifact too large: {rel}")
    with current.open("rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    require(len(data) <= MAX_BYTES, f"artifact too large: {rel}")
    return data


def _keys(obj: Any, required: set[str], optional: set[str] | None = None) -> None:
    require(isinstance(obj, dict), "expected object")
    require(required <= obj.keys(), f"missing keys: {sorted(required - obj.keys())}")
    require(obj.keys() <= required | (optional or set()), f"unknown keys: {sorted(obj.keys() - required - (optional or set()))}")


def validate(plan: Any) -> None:
    _keys(plan, {"schema_version", "mode", "generation", "currency", "base_cents", "option_cents", "artifacts", "milestones"})
    require(type(plan["schema_version"]) is int and plan["schema_version"] == VERSION, "unsupported schema")
    require(plan["mode"] == "SYNTHETIC_DRAFT", "this public demonstration assembler accepts SYNTHETIC_DRAFT only")
    identifier(plan["generation"], "generation")
    require(plan["currency"] == "USD", "currency must be USD")
    for key, amount in [("base_cents", 2400000), ("option_cents", 400000)]:
        require(type(plan[key]) is int and plan[key] == amount, f"{key} must match proposed baseline")
    artifacts = plan["artifacts"]
    require(isinstance(artifacts, list) and 1 <= len(artifacts) <= 100, "expected 1–100 artifacts")
    ids = set()
    for item in artifacts:
        _keys(item, {"id", "path", "git_blob", "generation", "kind", "description", "origin"})
        key = identifier(item["id"], "artifact ID")
        require(key not in ids, f"duplicate artifact: {key}")
        ids.add(key)
        relative(item["path"])
        require(isinstance(item["git_blob"], str) and HEX40.fullmatch(item["git_blob"]) is not None, "expected exact artifact blob")
        require(item["generation"] == plan["generation"], f"generation mismatch: {key}")
        require(item["kind"] in ("SYNTHETIC", "PROPOSED_REFERENCE"), "only explicit synthetic/public proposed-reference artifacts allowed")
        text(item["description"], "description")
        origin = item["origin"]
        _keys(origin, {"type", "locator"}, {"repository", "commit", "path", "git_blob"})
        text(origin["locator"], "source locator")
        require(origin["type"] in ("UPSTREAM_GIT", "AUTHORED_SYNTHETIC"), "unknown origin type")
        if origin["type"] == "UPSTREAM_GIT":
            require(set(origin) == {"type", "locator", "repository", "commit", "path", "git_blob"}, "incomplete upstream identity")
            require(origin["repository"] == "woahwhattheheck/commons", "unexpected upstream repository")
            require(isinstance(origin["commit"], str) and HEX40.fullmatch(origin["commit"]) is not None, "unversioned upstream source")
            relative(origin["path"])
            require(origin["git_blob"] == item["git_blob"], "source byte identity mismatch")
        else:
            require(set(origin) == {"type", "locator"}, "synthetic origin must not imply a verified source commit")
    milestones = plan["milestones"]
    require(isinstance(milestones, list) and len(milestones) == 3, "all three milestones required")
    kinds = set()
    for item in milestones:
        _keys(item, {"id", "amount_cents", "trigger", "artifact_ids", "criteria", "dependencies", "scenario_receipt"})
        kind = item["id"]
        require(isinstance(kind, str) and kind in MILESTONES and kind not in kinds, "duplicate or unknown milestone")
        kinds.add(kind)
        amount, trigger, _, section = MILESTONES[kind]
        require(type(item["amount_cents"]) is int and item["amount_cents"] == amount, "milestone amount differs from proposed baseline")
        require(item["trigger"] == trigger, f"{kind} trigger must remain {trigger}")
        refs = item["artifact_ids"]
        require(isinstance(refs, list) and bool(refs) and all(isinstance(r, str) for r in refs), "invalid artifact references")
        require(len(refs) == len(set(refs)) and set(refs) <= ids, "duplicate or dangling artifact references")
        criteria = item["criteria"]
        require(isinstance(criteria, list) and len(criteria) == len(CRITERIA[kind]), "all proposed criteria must be accounted for")
        expected = {f"{section}.{n}" for n in range(1, len(criteria) + 1)}
        seen = set()
        for criterion in criteria:
            _keys(criterion, {"id", "artifact_ids", "unresolved"})
            require(criterion["id"] in expected and criterion["id"] not in seen, "duplicate or unknown criterion")
            seen.add(criterion["id"])
            links = criterion["artifact_ids"]
            require(isinstance(links, list) and all(isinstance(r, str) for r in links), "invalid criterion artifacts")
            require(len(links) == len(set(links)) and set(links) <= set(refs), "criterion references an artifact outside its packet")
            text(criterion["unresolved"], "criterion unresolved/human-review statement")
        deps = item["dependencies"]
        require(isinstance(deps, list) and bool(deps), "dependencies must remain explicit")
        for dep in deps:
            _keys(dep, {"owner_role", "input", "effect"})
            require(dep["owner_role"] in ("PRIME", "UNIVERSITY", "TJLabs"), "dependency owner must be a role")
            text(dep["input"], "dependency input")
            text(dep["effect"], "dependency effect")
        receipt = item["scenario_receipt"]
        _keys(receipt, {"kind", "state", "artifact_id", "note"})
        require(receipt["kind"] == trigger, "receipt concerns a different milestone event")
        require(receipt["state"] in ("SYNTHETIC", "NOT_SUPPLIED"), "sample receipt cannot establish real commercial authority")
        require(receipt["artifact_id"] in refs or receipt["artifact_id"] is None, "receipt references unlisted artifact")
        require(receipt["state"] != "SYNTHETIC" or receipt["artifact_id"] in refs, "synthetic receipt needs an actual sample artifact")
        text(receipt["note"], "receipt note")
    require(sum(m["amount_cents"] for m in milestones) == plan["base_cents"], "base reconciliation failed")


def source_url(origin: dict) -> str | None:
    if origin["type"] != "UPSTREAM_GIT":
        return None
    return f"https://github.com/{origin['repository']}/blob/{origin['commit']}/{origin['path']}"


def money(cents: int) -> str:
    return f"${cents // 100:,}.{cents % 100:02d}"


def cell(value: Any) -> str:
    # Preserve text literally in Markdown cells; prevent accidental links/markup.
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;").replace("[", "&#91;").replace("]", "&#93;").replace("`", "&#96;").replace("\r", "").replace("\n", "<br>")


def packet_markdown(packet: dict) -> str:
    rows = [f"# {packet['id'].title()} milestone packet", "", NOTICE, "",
            f"Generation: `{packet['generation']}`. Packaging: **{packet['packaging_status']}**. "
            "Artifact conformance: **NOT ASSESSED**. Real commercial event: **NOT ESTABLISHED**.", "",
            "## Proposed commercial description", "",
            f"Base milestone: **{money(packet['amount_cents'])} USD**. Trigger: **{packet['trigger']}**. "
            "The separately proposed $4,000 option is excluded.", "",
            "Written authorization triggers kickoff; qualifying draft delivery triggers draft; final acceptance triggers final. "
            "File completeness, test results, pending inputs and review comments do not create additional payment conditions.", "",
            "## Delivered-file index", "", "| ID | Local file | Bytes | SHA-256 |", "|---|---|---:|---|"]
    for artifact in packet["artifacts"]:
        link = f"[open]({artifact['packet_path']})" if artifact["status"] == "BOUND" else "NOT SUPPLIED / CHANGED"
        rows.append(f"| {artifact['id']} | {link} | {artifact.get('bytes', 'UNKNOWN')} | {artifact.get('sha256', 'UNKNOWN')} |")
    rows += ["", "Version and original ID/locator metadata for every entry are retained in `packet.json`. "
             "Copied upstream evidence is byte-identical; hashing proves bytes, not truth or independent authorization.", "",
             "Keep `packet-integrity.json` with this folder. With the assembler available, run "
             "`python packets.py verify /path/to/this-packet` to check this packet without sibling milestones. "
             "A matching digest index establishes file consistency only.", "",
             "## Applicable criteria and remaining work", "",
             "These are paraphrases of the **proposed** exhibit, not findings of conformance. "
             "A linked example is not proof that the full engagement criterion is satisfied.", "",
             "| Clause | Artifact references | Unresolved / human review |", "|---|---|---|"]
    for criterion in packet["criteria"]:
        rows.append(f"| [{criterion['id']}]({criterion['source_url']}) {cell(criterion['text'])} | "
                    f"{cell(', '.join(criterion['artifact_ids']) or 'NOT SUPPLIED')} | {cell(criterion['unresolved'])} |")
    rows += ["", "## Open dependencies", "", "| Proposed owner role | Input | Effect on work |", "|---|---|---|"]
    rows += [f"| {d['owner_role']} | {cell(d['input'])} | {cell(d['effect'])} |" for d in packet["dependencies"]]
    rows += ["", "## Transmittal draft — not sent", "", packet["transmittal_draft"], "",
             "## Invoice-description draft — not an invoice or a payment request", "", packet["invoice_description_draft"], "",
             "No invoice number, issue date, payment instructions, due date, purchase order or actual recipient is assigned.", "",
             "## Scenario event and authority limit", "", f"Sample event: **{packet['scenario_receipt']['state']}** / "
             f"{packet['scenario_receipt']['kind']}. {cell(packet['scenario_receipt']['note'])}", "",
             "There is no real authorization, delivery acknowledgment or final acceptance receipt in this demonstration. "
             "Inspect the applicable agreement and actual event record separately in authorized private custody.", ""]
    return "\n".join(rows)


def construct(plan: dict, source_root: Path) -> tuple[dict[str, bytes], dict]:
    validate(plan)
    root = source_root.resolve(strict=True)
    require(root.is_dir(), "source root must be a directory")
    blobs, records, diagnostics = {}, {}, []
    for item in plan["artifacts"]:
        record = dict(item)
        try:
            data = file_bytes(root, item["path"])
        except FileNotFoundError:
            record["status"] = "MISSING"
        else:
            actual = git_blob(data)
            if actual != item["git_blob"]:
                record.update(status="CHANGED", actual_git_blob=actual)
            else:
                record.update(status="BOUND", sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
                blobs[item["id"]] = data
        if record["status"] != "BOUND":
            diagnostics.append({"artifact_id": item["id"], "status": record["status"], "source_path": item["path"]})
        record["source_url"] = source_url(item["origin"])
        records[item["id"]] = record
    output, packets = {}, []
    by_kind = {m["id"]: m for m in plan["milestones"]}
    for kind, (_, trigger, label, section) in MILESTONES.items():
        item = by_kind[kind]
        packet_artifacts = []
        for ref in item["artifact_ids"]:
            artifact = dict(records[ref])
            artifact["packet_path"] = f"artifacts/{ref}{PurePosixPath(artifact['path']).suffix}"
            packet_artifacts.append(artifact)
            if ref in blobs:
                output[f"{kind}/{artifact['packet_path']}"] = blobs[ref]
        criteria = []
        for criterion in sorted(item["criteria"], key=lambda c: c["id"]):
            n = int(criterion["id"].split(".")[-1])
            criteria.append({**criterion, "text": CRITERIA[kind][n-1], "conformance": "NOT_ASSESSED",
                "source_url": f"https://github.com/{EXHIBIT['repository']}/blob/{EXHIBIT['commit']}/{EXHIBIT['path']}#"
                              + {"kickoff": "51-kickoff--evidence-plan-acceptance", "draft": "52-draft-technical-package-acceptance", "final": "53-final-technical-package-acceptance"}[kind]})
        packet = {
            "schema_version": VERSION, "id": kind, "mode": plan["mode"], "generation": plan["generation"],
            "amount_cents": item["amount_cents"], "currency": "USD", "trigger": trigger,
            "packaging_status": "COMPLETE" if all(a["status"] == "BOUND" for a in packet_artifacts) else "INCOMPLETE",
            "artifact_conformance": "NOT_ASSESSED", "real_commercial_event": "NOT_ESTABLISHED",
            "exhibit_reference": EXHIBIT, "artifacts": packet_artifacts, "criteria": criteria,
            "dependencies": item["dependencies"], "scenario_receipt": item["scenario_receipt"],
            "transmittal_draft": f"Prepared for prospective prime review: {label.lower()}, generation {plan['generation']}. "
                "The attached file index identifies exact versions and remaining work. This is a synthetic rehearsal; "
                "no real delivery or receipt is asserted. Please distinguish factual correction, judgment, additional evidence and scope change when adapting this draft.",
            "invoice_description_draft": f"Proposed description only: TJLabs bounded technical assessment base workshare — "
                f"{label}; {money(item['amount_cents'])} USD ({item['amount_cents'] * 100 // plan['base_cents']}% of proposed $24,000 base). "
                f"Applicable event: {trigger}. No assertion that this event occurred; option and travel excluded.",
        }
        output[f"{kind}/packet.json"] = canonical(packet)
        output[f"{kind}/README.md"] = packet_markdown(packet).encode()
        prefix = f"{kind}/"
        output[f"{kind}/packet-integrity.json"] = integrity_index({
            name[len(prefix):]: data for name, data in output.items() if name.startswith(prefix)})
        packets.append({k: packet[k] for k in ("id", "amount_cents", "trigger", "packaging_status", "artifact_conformance", "real_commercial_event")})
    report = {"schema_version": VERSION, "notice": NOTICE, "generation": plan["generation"],
              "base_cents": plan["base_cents"], "milestone_sum_cents": sum(m["amount_cents"] for m in packets),
              "separate_option_cents": plan["option_cents"], "currency": "USD", "packets": packets,
              "bound_source_artifacts": len(blobs), "source_artifacts": len(records), "diagnostics": diagnostics,
              "plan_sha256": hashlib.sha256(canonical(plan)).hexdigest(),
              "status": "COMPLETE" if not diagnostics else "INCOMPLETE"}
    output["completeness.json"] = canonical(report)
    output["README.md"] = ("# Three milestone delivery packets\n\n" + NOTICE + "\n\n" +
        "Packaging checks cover exact artifact bytes and links, not conformance or commercial authority.\n\n" +
        "| Packet | Proposed amount | Event | Packaging |\n|---|---:|---|---|\n" +
        "\n".join(f"| [{m['id']}]({m['id']}/README.md) | {money(m['amount_cents'])} | {m['trigger']} | {m['packaging_status']} |" for m in packets) +
        "\n\n**Base total: $24,000.00 USD. Optional readout: $4,000.00 separately proposed, not included.**\n\n" +
        "Each folder is portable on its own: open README.md, packet.json and artifacts/. No source checkout is needed to read it. "
        "Retain bundle-integrity.json to verify the whole bundle, or packet-integrity.json to verify a copied milestone. "
        "Every criterion remains NOT_ASSESSED; every real commercial event remains NOT_ESTABLISHED. "
        "Read each criterion's unresolved statement before adapting this demonstration to a live engagement.\n").encode()
    output["bundle-integrity.json"] = integrity_index(output)
    return output, report


def verify(directory: Path) -> dict:
    root = directory.resolve(strict=True)
    index_name = "bundle-integrity.json" if os.path.lexists(root / "bundle-integrity.json") else "packet-integrity.json"
    index = load(root / index_name)
    _keys(index, {"schema_version", "algorithm", "files"})
    require(index["schema_version"] == VERSION and index["algorithm"] == "sha256", "unsupported integrity index")
    require(isinstance(index["files"], dict) and bool(index["files"]), "empty integrity index")
    require(len(index["files"]) <= 1000, "too many bundle files")
    errors = []
    for rel, digest in sorted(index["files"].items()):
        relative(rel)
        require(isinstance(digest, str) and re.fullmatch("[0-9a-f]{64}", digest) is not None, "invalid integrity digest")
        try:
            data = file_bytes(root, rel)
        except FileNotFoundError:
            errors.append({"path": rel, "status": "MISSING"})
        else:
            if hashlib.sha256(data).hexdigest() != digest:
                errors.append({"path": rel, "status": "CHANGED"})
    actual = set()
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            require(not (Path(current) / name).is_symlink(), "symlink in bundle")
        actual.update((Path(current) / name).relative_to(root).as_posix() for name in files)
    extra = actual - set(index["files"]) - {index_name}
    errors += [{"path": name, "status": "UNINDEXED"} for name in sorted(extra)]
    return {"status": "PASS" if not errors else "FAIL", "files_checked": len(index["files"]), "errors": errors,
            "integrity_scope": "bundle" if index_name == "bundle-integrity.json" else "packet",
            "integrity_index": index_name,
            "authority_limit": "Self-contained integrity only; replacing files and the index together is not independently detectable."}


def assemble(plan_path: Path, source_root: Path, output: Path) -> dict:
    output = output.absolute()
    require(not os.path.lexists(output), "output already exists; nothing overwritten")
    require(output.parent.is_dir(), "output parent must already exist")
    files, report = construct(load(plan_path), source_root)
    # Write to an isolated staging directory and reread every generated artifact before publication.
    with tempfile.TemporaryDirectory(prefix=".milestone-", dir=output.parent) as tmp:
        stage = Path(tmp)
        for rel, data in files.items():
            dest = stage / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        require(verify(stage)["status"] == "PASS", "generated bundle verification failed")
        output.mkdir()  # exclusive: never replace an existing file or directory
        try:
            for child in stage.iterdir():
                shutil.move(str(child), str(output / child.name))
        except BaseException:
            shutil.rmtree(output)
            raise
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    a = commands.add_parser("assemble")
    a.add_argument("plan", type=Path)
    a.add_argument("--root", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    v = commands.add_parser("verify", help="Verify a complete bundle or one copied milestone packet.")
    v.add_argument("directory", type=Path, help="Directory containing bundle-integrity.json or packet-integrity.json.")
    args = parser.parse_args(argv)
    try:
        report = assemble(args.plan, args.root, args.output) if args.command == "assemble" else verify(args.directory)
        print(canonical(report).decode(), end="")
        return 0 if report["status"] in ("COMPLETE", "PASS") else 1
    except (PacketError, OSError, KeyError, TypeError) as exc:
        print(f"packet error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
