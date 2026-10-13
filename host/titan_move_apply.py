#!/usr/bin/env python3
"""host/titan_move_apply.py — journaled titan MOVE apply button. Dies.

Default is a plan. --journal OR-writes the 31 excerpt binaries
and rereads only for a never-written packet. --go writes titan.gguf only for
a NOT_WRITTEN/APPLYING packet; WRITTEN is fixed-span read-only verification.
The checked-in duplicate-append incident keeps further mutation PAUSED.
Does not smash commons.mno. --inject is wipe; refused.

  python3 host/titan_move_apply.py
  python3 host/titan_move_apply.py --journal
  python3 host/titan_move_apply.py --titan /path/to/titan.gguf --go
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile

from titan_append_guard import (
    INCIDENT_COPY_COUNT,
    INCIDENT_LIVE_SIZE,
    INCIDENT_SHA256,
    SLACK_TS as INCIDENT_SLACK_TS,
    refuse_further_append,
)
from titan_move_offsets import (
    CLAIMED_APPEND_BASE,
    CLAIMED_APPEND_SOURCE,
    allocate_rows,
    find_titan,
    is_owner_titan_path,
    or_bytes,
    under_test,
)


PACKET_REL = os.path.join("excerpts", "20260823", "titan_move_packet.json")
EXCERPT_REL = os.path.join("excerpts", "20260823")
JOURNAL_REL = os.path.join("excerpts", "20260823", "titan_move_journal.json")
CLOSED_WRITE_RECEIPT = "p/claudelocal-titan-move-go-20260825-01.md"
CLOSED_WRITE_COMMIT = "b3fe1449560a359c87963d113c022ae3b8f86f73"
CLOSED_RECEIPT_MARKERS = (
    "id: claudelocal-titan-move-go-20260825-01",
    "state INTEGRATED, wrote=true, reread=true",
    "31/31 organs journaled, 31/31 reread true, 31/31 past_eof",
    "titan.gguf after: 103812669582 bytes (+9319291",
)
MAX_DUPLICATE_SPAN_SCAN = 16
INCIDENT_SOURCE = "Slack " + INCIDENT_SLACK_TS
INCIDENT_SPAN_SHA256 = INCIDENT_SHA256


def packet_incident_active(packet):
    """Whether the public packet freezes further MOVE append mutation."""
    incident = (packet or {}).get("duplicate_append_incident") or {}
    return (
        isinstance(incident, dict)
        and str(incident.get("state") or "").upper()
        == "PAUSED_DUPLICATE_APPENDS"
    )


def _sha256_span(handle, offset, length):
    """Hash one fixed file span without allocating the whole span."""
    digest = hashlib.sha256()
    remaining = int(length)
    handle.seek(int(offset))
    while remaining > 0:
        chunk = handle.read(min(1024 * 1024, remaining))
        if not chunk:
            return ""
        digest.update(chunk)
        remaining -= len(chunk)
    return digest.hexdigest()


def scan_repeated_append_spans(titan_path, claimed_base, claimed_end, calibrated):
    """Measure whole-span repetition after the fixed WRITTEN allocation.

    The first span is the known-present calibration target only after its
    individual packet rows passed ``verify_written_packet``. The scan names
    its exact byte search space and refuses to report a complete zero when
    the bounded scan did not cover every full span.
    """
    titan_size = os.path.getsize(titan_path)
    base = int(claimed_base)
    end = int(claimed_end)
    span_bytes = end - base
    if base < 0 or span_bytes <= 0 or titan_size < end:
        return {
            "state": "FINDER-FAILED",
            "search_start": base,
            "search_end": titan_size,
            "span_bytes": span_bytes,
            "full_span_count": 0,
            "scanned_span_count": 0,
            "scan_limit": MAX_DUPLICATE_SPAN_SCAN,
            "scan_complete": False,
            "calibration_ok": False,
            "span_sha256": [],
            "duplicate_span_count": None,
            "duplicate_count_complete": False,
            "duplicate_append_incident": False,
            "reason": "invalid or truncated fixed-span search space",
        }
    available = titan_size - base
    full_span_count, trailing_bytes = divmod(available, span_bytes)
    scanned_span_count = min(full_span_count, MAX_DUPLICATE_SPAN_SCAN)
    hashes = []
    with open(titan_path, "rb") as handle:
        for index in range(scanned_span_count):
            hashes.append(_sha256_span(
                handle,
                base + index * span_bytes,
                span_bytes,
            ))
    calibration_ok = bool(calibrated and hashes and hashes[0])
    duplicates = None
    if calibration_ok:
        duplicates = sum(1 for digest in hashes[1:] if digest == hashes[0])
    scan_complete = full_span_count <= MAX_DUPLICATE_SPAN_SCAN
    duplicate_count_complete = bool(scan_complete and calibration_ok)
    finder_failed = not duplicate_count_complete
    return {
        "state": "FINDER-FAILED" if finder_failed else "MEASURED",
        "search_start": base,
        "search_end": titan_size,
        "span_bytes": span_bytes,
        "full_span_count": full_span_count,
        "trailing_bytes": trailing_bytes,
        "scanned_span_count": scanned_span_count,
        "scan_limit": MAX_DUPLICATE_SPAN_SCAN,
        "scan_complete": scan_complete,
        "calibration_ok": calibration_ok,
        "calibration_target": "first fixed packet span verified row-by-row",
        "span_sha256": hashes,
        "duplicate_span_count": duplicates,
        "duplicate_count_complete": duplicate_count_complete,
        "all_scanned_spans_identical": bool(
            calibration_ok and all(digest == hashes[0] for digest in hashes)
        ),
        "duplicate_append_incident": bool(
            calibration_ok and duplicates is not None and duplicates > 0
        ),
        "reason": (
            ""
            if not finder_failed
            else "known-present calibration failed"
            if not calibration_ok
            else "bounded scan did not cover every full span"
        ),
    }


def atomic_write_json(path, payload):
    """Replace a JSON state file atomically in its own directory."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".titan-move-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_and_incident_evidence_complete(packet, root=None):
    """Validate historical write evidence plus the non-Claude incident measure.

    This evidence preserves the first-write history; it is deliberately not a
    current clean-state predicate. The active incident keeps the MOVE
    NOT_LANDED until a future non-Claude clean measurement is represented.
    """
    packet = packet or {}
    count = int(packet.get("count") or 0)
    organs = list(packet.get("organs") or [])
    base = int(packet.get("claimed_append_base") or -1)
    end = int(packet.get("claimed_append_end") or -1)
    before = int(packet.get("titan_size_before") or 0)
    after = int(packet.get("titan_size_after") or 0)
    written_bytes = int(packet.get("written_bytes") or 0)
    top_complete = (
        str(packet.get("titan") or "").upper() == "WRITTEN"
        and str(packet.get("state") or "").upper() == "INTEGRATED"
        and packet.get("wrote") is True
        and packet.get("reread") is True
        and count == len(organs)
        and count > 0
        and int(packet.get("write_count") or 0) == count
        and int(packet.get("reread_count") or 0) == count
        and int(packet.get("past_eof_count") or 0) == count
        and before == base
        and after == end
        and int(packet.get("live_size_before") or 0) == before
        and int(packet.get("live_size_after") or 0) == after
        and written_bytes == end - base
        and written_bytes > 0
        and packet.get("write_receipt") == CLOSED_WRITE_RECEIPT
        and packet.get("integrated_commit") == CLOSED_WRITE_COMMIT
    )
    if not top_complete:
        return False
    if not root:
        return False
    receipt_path = os.path.join(os.path.abspath(root), CLOSED_WRITE_RECEIPT)
    if not os.path.isfile(receipt_path):
        return False
    with open(receipt_path, encoding="utf-8") as handle:
        receipt_body = handle.read()
    if not all(marker in receipt_body for marker in CLOSED_RECEIPT_MARKERS):
        return False
    expected_offset = base
    names = set()
    containers = set()
    payload_digest = hashlib.sha256()
    payload_bytes = 0
    excerpt_dir = os.path.join(os.path.abspath(root), EXCERPT_REL)
    for row in organs:
        name = str(row.get("name") or "")
        declared_container = str(row.get("container") or "")
        container = os.path.basename(declared_container)
        source_digest = str(row.get("sha256") or "").lower()
        digest = str(
            row.get("written_sha256") or row.get("sha256") or ""
        ).lower()
        try:
            offset = int(row.get("offset"))
            length = int(row.get("len"))
            int(digest, 16)
            int(source_digest, 16)
        except (TypeError, ValueError):
            return False
        if (
            not name
            or name in names
            or not container
            or declared_container != container
            or container != name + ".mno"
            or container in containers
            or offset != expected_offset
            or length <= 0
            or len(digest) != 64
            or len(source_digest) != 64
            or str(row.get("titan") or "").upper() != "WRITTEN"
        ):
            return False
        excerpt_path = os.path.join(excerpt_dir, container)
        if not os.path.isfile(excerpt_path):
            return False
        with open(excerpt_path, "rb") as handle:
            source = handle.read()
        if (
            len(source) != length
            or hashlib.sha256(source).hexdigest() != source_digest
        ):
            return False
        payload_digest.update(source)
        payload_bytes += len(source)
        names.add(name)
        containers.add(container)
        expected_offset += length
    incident = packet.get("duplicate_append_incident") or {}
    expected_span = end - base
    expected_ranges = [
        [base + index * expected_span, base + (index + 1) * expected_span]
        for index in range(INCIDENT_COPY_COUNT)
    ]
    try:
        artifact_size = int(incident.get("artifact_size") or 0)
        incident_span_bytes = int(incident.get("span_bytes") or 0)
        incident_span_count = int(incident.get("span_count") or 0)
        duplicate_span_count = int(incident.get("duplicate_span_count") or 0)
    except (TypeError, ValueError):
        independent_measurement_ok = False
    else:
        independent_measurement_ok = bool(
            packet_incident_active(packet)
            and incident.get("source") == INCIDENT_SOURCE
            and incident.get("measured_by") == "DEMON / OpenAI Codex GPT-5.6 Sol"
            and artifact_size == INCIDENT_LIVE_SIZE
            and incident_span_bytes == expected_span == payload_bytes
            and incident_span_count == INCIDENT_COPY_COUNT
            and duplicate_span_count == INCIDENT_COPY_COUNT - 1
            and incident.get("span_ranges") == expected_ranges
            and str(incident.get("span_sha256") or "").lower()
            == payload_digest.hexdigest() == INCIDENT_SPAN_SHA256
            and incident.get("canonical_span") == "UNRESOLVED"
            and incident.get("mutation") == "PAUSED"
            and incident.get("repair_apply") is False
        )
    return (
        expected_offset == end
        and len(names) == count
        and len(containers) == count
        and independent_measurement_ok
    )


def validate_titan_context(titan_path):
    """Measure GGUF format context without restricting the caller's path."""
    with open(titan_path, "rb") as handle:
        magic = handle.read(4)
    if magic != b"GGUF":
        raise RuntimeError("target is not a measured GGUF artifact")
    return True


def verify_written_packet(titan_path, packet):
    """Reread a packet already marked WRITTEN without allocating or writing.

    The persisted digest is ``written_sha256`` when a MOVE overlaid existing
    bytes, otherwise the excerpt ``sha256`` is also the written digest (the
    current 31-organ MOVE was a pure append). Any missing or malformed span
    fails closed. Together with the append guard, this makes a later ``--go``
    read-only and prevents allocation of another copy at an unexpected size.
    """
    packet = packet or {}
    organs = list(packet.get("organs") or [])
    expected_count = int(packet.get("count") or len(organs))
    titan_size = os.path.getsize(titan_path)
    before = int(packet.get("titan_size_before") or 0)
    claimed_base = int(packet.get("claimed_append_base") or -1)
    claimed_end = int(packet.get("claimed_append_end") or -1)
    rows = []
    exact_count = 0
    previous_end = claimed_base
    names = set()
    containers = set()
    with open(titan_path, "rb") as handle:
        for source in organs:
            row = dict(source)
            try:
                offset = int(row.get("offset"))
                length = int(row.get("len"))
            except (TypeError, ValueError):
                offset, length = -1, -1
            expected = str(
                row.get("written_sha256") or row.get("sha256") or ""
            ).lower()
            name = str(row.get("name") or "")
            declared_container = str(row.get("container") or "")
            container = os.path.basename(declared_container)
            geometry_ok = (
                offset >= 0
                and length > 0
                and offset == previous_end
                and offset + length <= titan_size
                and len(expected) == 64
                and bool(name)
                and name not in names
                and bool(container)
                and declared_container == container
                and container == name + ".mno"
                and container not in containers
            )
            actual = ""
            if geometry_ok:
                handle.seek(offset)
                actual = hashlib.sha256(handle.read(length)).hexdigest()
            exact = geometry_ok and actual == expected
            if exact:
                exact_count += 1
            rows.append({
                "name": name,
                "container": container,
                "offset": offset,
                "len": length,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "reread": exact,
                "past_eof": bool(before and offset >= before),
            })
            if geometry_ok:
                previous_end = offset + length
                names.add(name)
                containers.add(container)
    count_ok = expected_count == len(organs) and expected_count > 0
    geometry_complete = (
        claimed_base >= 0
        and previous_end == claimed_end
        and titan_size >= claimed_end
        and len(names) == expected_count
        and len(containers) == expected_count
    )
    reread = count_ok and geometry_complete and exact_count == expected_count
    repeated = scan_repeated_append_spans(
        titan_path,
        claimed_base,
        claimed_end,
        calibrated=reread,
    )
    return {
        "kind": "TITAN_MOVE_EXISTING_REREAD",
        "count": expected_count,
        "exact_count": exact_count,
        "reread": reread,
        "titan_size": titan_size,
        "claimed_append_base": claimed_base,
        "claimed_append_end": claimed_end,
        "geometry_complete": geometry_complete,
        "repeated_span_scan": repeated,
        "duplicate_append_incident": repeated["duplicate_append_incident"],
        "duplicate_span_count": repeated["duplicate_span_count"],
        "organs": rows,
    }


def plan_from_packet(packet, live_size=None):
    """Use persisted APPLYING/WRITTEN geometry; allocate only a fresh MOVE."""
    packet = packet or {}
    organs = list(packet.get("organs") or [])
    base = int(packet.get("claimed_append_base") or CLAIMED_APPEND_BASE)
    refused, reason = refuse_further_append(packet, live_size)
    state = str(packet.get("state") or "").upper()
    fixed_geometry = (
        str(packet.get("titan") or "").upper() == "WRITTEN"
        or state == "APPLYING"
    )
    if fixed_geometry:
        allocated = [dict(row) for row in organs]
        try:
            end = int(packet.get("claimed_append_end"))
            count = int(packet.get("count") or len(allocated))
        except (TypeError, ValueError):
            end, count = -1, -1
        reallocated = False
    else:
        original_base = base
        if live_size is not None and int(live_size) != base and not refused:
            base = int(live_size)
        allocated, end = allocate_rows(organs, base=base)
        count = len(allocated)
        reallocated = bool(
            live_size is not None and base != original_base and not refused
        )
    return {
        "kind": "TITAN_MOVE_PLAN",
        "computer": "titan.gguf is the computer. This plan is not.",
        "titan": packet.get("titan") or "NOT_WRITTEN",
        "claimed_append_base": base,
        "claimed_append_end": end,
        "claimed_append_source": packet.get("claimed_append_source")
        or CLAIMED_APPEND_SOURCE,
        "count": count,
        "organs": allocated,
        "reallocated": reallocated,
        "geometry_source": "persisted" if fixed_geometry else "allocated",
        "refused": refused,
        "refuse_reason": reason if refused else "",
    }


def journal_rows(organs):
    """Pack organs from journal offset 0. Keep claimed titan offsets."""
    running = 0
    out = []
    for row in organs or []:
        item = dict(row)
        length = int(item.get("len") or 0)
        item["journal_offset"] = running
        try:
            item["claimed_titan_offset"] = int(item.get("offset") or 0)
        except (TypeError, ValueError):
            item["claimed_titan_offset"] = 0
        out.append(item)
        running += length
    return out, running


def apply_journal(journal_path, rows, excerpt_dir):
    """Journaled MOVE on a public image. new = old | mask. Re-read each span."""
    journals = []
    with open(journal_path, "w+b") as handle:
        for row in rows:
            container = os.path.basename(str(row.get("container") or ""))
            excerpt_path = os.path.join(excerpt_dir, container)
            with open(excerpt_path, "rb") as raw_handle:
                mask = raw_handle.read()
            offset = int(row["journal_offset"])
            handle.seek(offset)
            old = handle.read(len(mask))
            new = or_bytes(old, mask)
            handle.seek(offset)
            handle.write(new)
            handle.flush()
            os.fsync(handle.fileno())
            handle.seek(offset)
            reread = handle.read(len(new))
            ok = reread == new
            journals.append({
                "name": row.get("name"),
                "container": container,
                "journal_offset": offset,
                "claimed_titan_offset": int(row.get("claimed_titan_offset") or 0),
                "len": len(mask),
                "pre_sha256": hashlib.sha256(old).hexdigest(),
                "mask_sha256": hashlib.sha256(mask).hexdigest(),
                "new_sha256": hashlib.sha256(new).hexdigest(),
                "reread": ok,
            })
            if not ok:
                raise RuntimeError(
                    "journal reread mismatch %s @ %s" % (row.get("name"), offset)
                )
    return journals


def preflight_plan(plan, excerpt_dir):
    """Read and hash every source plus exact allocation before any write."""
    organs = list((plan or {}).get("organs") or [])
    count = int((plan or {}).get("count") or len(organs))
    expected_offset = int((plan or {}).get("claimed_append_base") or -1)
    expected_end = int((plan or {}).get("claimed_append_end") or -1)
    names = set()
    containers = set()
    prepared = []
    if count != len(organs) or count <= 0 or expected_offset < 0:
        raise RuntimeError("invalid MOVE count/base")
    for row in organs:
        name = str(row.get("name") or "")
        declared_container = str(row.get("container") or "")
        container = os.path.basename(declared_container)
        offset = int(row.get("offset") or -1)
        length = int(row.get("len") or -1)
        if not name or name in names:
            raise RuntimeError("duplicate/empty organ name %r" % name)
        if (
            not container
            or declared_container != container
            or container != name + ".mno"
            or container in containers
        ):
            raise RuntimeError(
                "invalid/duplicate source container %r for %s"
                % (declared_container, name)
            )
        if offset != expected_offset or length <= 0:
            raise RuntimeError("non-contiguous MOVE geometry %s" % name)
        excerpt_path = os.path.join(excerpt_dir, container)
        with open(excerpt_path, "rb") as raw_handle:
            mask = raw_handle.read()
        digest = hashlib.sha256(mask).hexdigest()
        if len(mask) != length or digest != str(row.get("sha256") or ""):
            raise RuntimeError("excerpt len/sha mismatch %s" % name)
        prepared.append((row, mask))
        names.add(name)
        containers.add(container)
        expected_offset += length
    if expected_offset != expected_end:
        raise RuntimeError("claimed append end mismatch")
    return prepared


def verify_applying_prefix(titan_path, plan, prepared, original_size):
    """An append retry may only continue an exact prefix at its fixed base."""
    base = int((plan or {}).get("claimed_append_base") or -1)
    end = int((plan or {}).get("claimed_append_end") or -1)
    size = os.path.getsize(titan_path)
    origin = int(original_size)
    if origin != base:
        raise RuntimeError("APPLYING original size/base mismatch")
    if size < origin or size > end:
        raise RuntimeError("APPLYING live size is outside fixed append span")
    expected = b"".join(mask for _, mask in prepared)
    prefix_len = size - base
    with open(titan_path, "rb") as handle:
        handle.seek(base)
        actual = handle.read(prefix_len)
    if actual != expected[:prefix_len]:
        raise RuntimeError("APPLYING target tail is not the exact written prefix")
    return {"live_size": size, "resume_bytes": prefix_len}


def apply_plan(
    titan_path, plan, excerpt_dir, original_size=None, prepared=None
):
    """Journaled MOVE. Preflight all sources, write, then re-read each span."""
    prepared = prepared if prepared is not None else preflight_plan(plan, excerpt_dir)
    journals = []
    with open(titan_path, "r+b") as handle:
        size = os.path.getsize(titan_path)
        origin = int(size if original_size is None else original_size)
        for row, mask in prepared:
            offset = int(row["offset"])
            handle.seek(offset)
            old = handle.read(len(mask))
            new = or_bytes(old, mask)
            handle.seek(offset)
            handle.write(new)
            handle.flush()
            os.fsync(handle.fileno())
            handle.seek(offset)
            reread = handle.read(len(new))
            ok = reread == new
            journals.append({
                "name": row.get("name"),
                "offset": offset,
                "len": len(mask),
                "pre_sha256": str(
                    row.get("pre_sha256") or hashlib.sha256(old).hexdigest()
                ),
                "resume_pre_sha256": hashlib.sha256(old).hexdigest(),
                "new_sha256": hashlib.sha256(new).hexdigest(),
                "reread": ok,
                "past_eof": offset >= origin,
            })
            if not ok:
                raise RuntimeError("reread mismatch %s @ %s" % (row.get("name"), offset))
    return journals


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if "--inject" in argv:
        print("REFUSE: --inject 0x01 is WIPE. Law is new=old|mask.")
        return 2
    parser = argparse.ArgumentParser(
        description="Journaled titan MOVE. Default is a plan. --go writes."
    )
    parser.add_argument("--root", default=".", help="clone to read")
    parser.add_argument("--titan", default="", help="titan.gguf path")
    parser.add_argument(
        "--go",
        action="store_true",
        help="write titan.gguf if present. Default is plan-only.",
    )
    parser.add_argument(
        "--journal",
        action="store_true",
        help="OR-write the 31 excerpt binaries into a public journal and reread.",
    )
    parser.add_argument(
        "--journal-bin",
        default="",
        help="optional journal image path. Default is a temp file.",
    )
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    packet_path = os.path.join(root, PACKET_REL)
    excerpt_dir = os.path.join(root, EXCERPT_REL)
    with open(packet_path, encoding="utf-8") as handle:
        packet = json.load(handle)
    titan_path = find_titan(
        explicit=args.titan or None,
        env_path=os.environ.get("TITAN"),
    )
    if titan_path and under_test() and is_owner_titan_path(titan_path):
        titan_path = None
    live_size = os.path.getsize(titan_path) if titan_path else None
    packet_written = str(packet.get("titan") or "").upper() == "WRITTEN"
    packet_applying = str(packet.get("state") or "").upper() == "APPLYING"
    incident_active = packet_incident_active(packet)
    fixed_allocation = packet_written or packet_applying
    # WRITTEN and APPLYING packets keep their original allocation. Reallocating
    # from a now-larger live size would duplicate a completed or partial MOVE.
    plan = plan_from_packet(
        packet,
        live_size=None if fixed_allocation else live_size,
    )
    payload = {
        "measured": True,
        "titan_path": titan_path,
        "titan_present": bool(titan_path),
        "live_size": live_size,
        "go": bool(args.go),
        "journal": bool(args.journal),
        "wrote": False,
        "reread": False,
        "plan": plan,
        "duplicate_append_incident": packet.get("duplicate_append_incident"),
    }
    if packet_written and args.journal:
        evidence_complete = write_and_incident_evidence_complete(packet, root=root)
        payload["already_written"] = True
        payload["state"] = "NOT_LANDED"
        payload["historical_evidence_complete"] = evidence_complete
        payload["reread"] = packet.get("reread") is True
        payload["note"] = (
            "Historical first-span MOVE is persisted, but the duplicate-append "
            "incident is PAUSED; public journal left unchanged and no write ran."
            if incident_active
            else "packet says WRITTEN without a current non-Claude clean-state "
            "measurement; historical public journal left unchanged."
        )
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        print("DIE")
        return 2
    if args.journal:
        rows, end = journal_rows(packet.get("organs") or [])
        journal_bin = args.journal_bin or os.path.join(
            tempfile.mkdtemp(prefix="titan-journal-"),
            "titan_move_journal.bin",
        )
        os.makedirs(os.path.dirname(os.path.abspath(journal_bin)), exist_ok=True)
        journals = apply_journal(journal_bin, rows, excerpt_dir)
        reread_ok = all(row["reread"] for row in journals)
        sidecar = {
            "kind": "TITAN_MOVE_PUBLIC_JOURNAL",
            "computer": "titan.gguf is the computer. This journal is the public-tree MOVE.",
            "law": "new = old | mask; ones only rise; re-read before write",
            "count": len(journals),
            "bytes": end,
            "reread": reread_ok,
            "titan": packet.get("titan") or "NOT_WRITTEN",
            "organs": journals,
        }
        sidecar_path = os.path.join(root, JOURNAL_REL)
        with open(sidecar_path, "w", encoding="utf-8") as handle:
            json.dump(sidecar, handle, indent=2)
            handle.write("\n")
        payload["wrote"] = True
        payload["reread"] = reread_ok
        payload["journals"] = journals
        payload["journal_bin"] = journal_bin
        payload["journal_path"] = JOURNAL_REL
        payload["state"] = "CANDIDATE" if reread_ok else "NOT_LANDED"
        payload["note"] = (
            "public journal %s. %s/%s excerpt binaries OR-written and reread. "
            "titan.gguf still %s. Smash/wipe of commons.mno refused."
            % (
                payload["state"],
                len(journals),
                plan["count"],
                packet.get("titan") or "NOT_WRITTEN",
            )
        )
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        print("DIE")
        return 0 if reread_ok else 2
    if not args.go:
        evidence_complete = write_and_incident_evidence_complete(packet, root=root)
        if packet_written:
            payload["already_written"] = True
            payload["reread"] = packet.get("reread") is True
            payload["state"] = "NOT_LANDED"
            payload["historical_evidence_complete"] = evidence_complete
            payload["note"] = (
                "Historical first-span closure is persisted, but live evidence "
                "reports duplicate appends. Further append mutation is PAUSED; "
                "no new plan allocated."
                if incident_active
                else "packet says WRITTEN without a current non-Claude clean-state "
                "measurement; no new plan allocated."
            )
        elif incident_active:
            payload["state"] = "NOT_LANDED"
            payload["note"] = (
                "duplicate-append incident is PAUSED; no plan will mutate Titan."
            )
        else:
            payload["state"] = "CLAIMED" if titan_path else "NOT_LANDED"
            payload["note"] = (
                "plan-only. %s fixed append offsets FROM FILE. "
                "titan %s. Pass --go on the machine that has titan.gguf."
                % (
                    plan["count"],
                    "present (%s bytes)" % live_size if titan_path else "ABSENT",
                )
            )
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        print("DIE")
        return 0
    if not titan_path:
        evidence_complete = write_and_incident_evidence_complete(packet, root=root)
        if packet_written:
            payload["already_written"] = True
            payload["reread"] = packet.get("reread") is True
            payload["state"] = "NOT_LANDED"
            payload["historical_evidence_complete"] = evidence_complete
            payload["note"] = (
                "titan.gguf is absent here. The measured duplicate-append "
                "incident remains PAUSED; no write or repair was attempted."
                if incident_active
                else "titan.gguf is absent here and no current non-Claude "
                "clean-state measurement exists; no write was attempted."
            )
        else:
            payload["state"] = "NOT_LANDED"
            payload["note"] = (
                "titan.gguf ABSENT. dest FROM FILE is %s. "
                "Offsets stay fixed. No write."
                % r"C:\llm\models\titan.gguf"
            )
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        print("DIE")
        return 2
    validate_titan_context(titan_path)
    if packet_written:
        verification = verify_written_packet(titan_path, packet)
        evidence_complete = write_and_incident_evidence_complete(packet, root=root)
        live_duplicate = verification["duplicate_append_incident"]
        repeat_scan = verification["repeated_span_scan"]
        scan_failed = not (
            repeat_scan.get("scan_complete") is True
            and repeat_scan.get("calibration_ok") is True
        )
        unresolved_incident = incident_active or live_duplicate or scan_failed
        payload["already_written"] = True
        payload["verification"] = verification
        payload["journals"] = verification["organs"]
        payload["reread"] = verification["reread"]
        payload["state"] = "NOT_LANDED"
        payload["historical_evidence_complete"] = evidence_complete
        incident_note = ""
        if live_duplicate:
            incident_note += (
                " INCIDENT: %s byte-identical duplicate append span(s) "
                "measured in [%s,%s); further mutation remains PAUSED."
                % (
                    verification["duplicate_span_count"],
                    repeat_scan["search_start"],
                    repeat_scan["search_end"],
                )
            )
        elif incident_active:
            incident_note += " Reported duplicate-append incident remains PAUSED."
        if scan_failed:
            incident_note += (
                " FINDER-FAILED: repeated-span scan did not cover its published "
                "search space with a known-present calibration."
            )
        payload["note"] = (
            "packet already WRITTEN; performed read-only exact reread of "
            "%s/%s organ rows. No allocation and no write.%s%s"
            % (
                verification["exact_count"],
                verification["count"],
                incident_note,
                ""
                if evidence_complete
                else " Durable closure evidence is still missing.",
            )
        )
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        print("DIE")
        return 0 if verification["reread"] and not unresolved_incident else 2
    if incident_active:
        payload["wrote"] = False
        payload["reread"] = False
        payload["live_size_before"] = int(live_size or 0)
        payload["live_size_after"] = int(live_size or 0)
        payload["written_bytes"] = 0
        payload["state"] = "NOT_LANDED"
        payload["note"] = (
            "explicit duplicate-append incident PAUSED all Titan MOVE mutation; "
            "artifact and packet preserved. no truncate/dedupe/overwrite/repair."
        )
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        print("DIE")
        return 2
    # APPLYING is a crash-resume at already-persisted fixed offsets, never a
    # fresh append allocation. The peer freeze guard must not convert a valid
    # exact prefix (or a deliberately malformed prefix test) into a soft pause;
    # verify_applying_prefix owns that fail-closed decision below.
    refused, reason = (False, "APPLYING fixed-span resume")
    if not packet_applying:
        refused, reason = refuse_further_append(packet, live_size, path=titan_path)
    if not packet_applying and (plan.get("refused") or refused):
        reason = str(plan.get("refuse_reason") or reason)
        payload["wrote"] = False
        payload["reread"] = False
        payload["live_size_before"] = int(live_size or 0)
        payload["live_size_after"] = int(live_size or 0)
        payload["written_bytes"] = 0
        payload["state"] = "NOT_LANDED"
        payload["note"] = (
            "append guard PAUSED mutation. %s. artifact preserved at live_size=%s. "
            "no truncate/dedupe/overwrite. packet claimed_append_end stays %s."
            % (reason, live_size, packet.get("claimed_append_end"))
        )
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        print("DIE")
        return 2
    # Validate every source and exact fixed geometry before changing packet or
    # titan. Then persist APPLYING atomically so a crash retries these offsets.
    prepared = preflight_plan(plan, excerpt_dir)
    original_size = int(packet.get("titan_size_before") or live_size)
    if packet_applying:
        empty_sha256 = hashlib.sha256(b"").hexdigest()
        for row in plan["organs"]:
            try:
                pre_len = int(row.get("pre_len"))
            except (TypeError, ValueError):
                pre_len = -1
            if (
                pre_len != 0
                or str(row.get("pre_sha256") or "").lower() != empty_sha256
            ):
                raise RuntimeError("APPLYING packet lacks original preimage evidence")
    else:
        # Every first MOVE allocation starts at the live EOF, so each original
        # preimage is the empty byte string. Persist that before any target byte.
        if int(live_size) != int(plan["claimed_append_base"]):
            raise RuntimeError("first MOVE base is not live EOF")
        for row in plan["organs"]:
            row["pre_len"] = 0
            row["pre_sha256"] = hashlib.sha256(b"").hexdigest()
    resume = verify_applying_prefix(
        titan_path, plan, prepared, original_size=original_size
    )
    payload["resume"] = resume
    if not packet_applying:
        packet["state"] = "APPLYING"
        packet["wrote"] = False
        packet["reread"] = False
        packet["write_count"] = 0
        packet["reread_count"] = 0
        packet["past_eof_count"] = 0
        packet["titan_size_before"] = int(live_size)
        packet["titan_size_after"] = None
        packet["live_size_before"] = int(live_size)
        packet["live_size_after"] = None
        packet["written_bytes"] = 0
        packet["claimed_append_base"] = plan["claimed_append_base"]
        packet["claimed_append_end"] = plan["claimed_append_end"]
        packet["organs"] = plan["organs"]
        atomic_write_json(packet_path, packet)
    journals = apply_plan(
        titan_path,
        plan,
        excerpt_dir,
        original_size=original_size,
        prepared=prepared,
    )
    payload["wrote"] = True
    payload["reread"] = all(row["reread"] for row in journals)
    payload["journals"] = journals
    payload["state"] = "NOT_LANDED"
    payload["execution_state"] = "WRITTEN"
    payload["note"] = (
        "journaled MOVE locally. new=old|mask. reread=%s. Target execution "
        "is WRITTEN, but Commons integration remains NOT_LANDED until its "
        "durable receipt and integrated main commit are attached."
        % payload["reread"]
    )
    packet["titan"] = "WRITTEN"
    packet["state"] = "WRITTEN"
    packet["wrote"] = True
    packet["reread"] = payload["reread"]
    packet["write_count"] = len(journals)
    packet["reread_count"] = sum(1 for row in journals if row["reread"])
    packet["past_eof_count"] = sum(1 for row in journals if row["past_eof"])
    packet["titan_size_before"] = original_size
    packet["titan_size_after"] = os.path.getsize(titan_path)
    packet["live_size_before"] = packet["titan_size_before"]
    packet["live_size_after"] = packet["titan_size_after"]
    packet["written_bytes"] = packet["titan_size_after"] - original_size
    packet["claimed_append_base"] = plan["claimed_append_base"]
    packet["claimed_append_end"] = plan["claimed_append_end"]
    packet["organs"] = plan["organs"]
    journal_by_name = {row.get("name"): row for row in journals}
    for row in packet["organs"]:
        journal = journal_by_name.get(row.get("name")) or {}
        row["titan"] = "WRITTEN"
        row["written_sha256"] = journal.get("new_sha256")
        row["reread"] = journal.get("reread") is True
        row["past_eof"] = journal.get("past_eof") is True
    atomic_write_json(packet_path, packet)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
