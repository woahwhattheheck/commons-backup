#!/usr/bin/env python3
"""Component implementation and operation."""
from __future__ import annotations

import argparse
from bisect import bisect_left
import json
import os
import re
import subprocess
import sys

try:
    from host.git_source_capsules import _git_env
except ModuleNotFoundError:
    from git_source_capsules import _git_env


SCHEMA = "commons-open-work-v1"
CLASSES = ("OPEN", "LANDED", "DEAD_CLAIM", "SALON", "NOISE")
DEFAULT_ROOT = "."
HUMAN_REL = os.path.join("ground", "open-work-structured-ids-on-current-main.md")
MACHINE_REL = os.path.join("ground", "open-work-structured-ids-on-current-main.json")
POINTER_HUMAN_REL = os.path.join("ground", "OPEN_WORK.md")
POINTER_MACHINE_REL = os.path.join("ground", "OPEN_WORK.json")
LISTING_REL = os.path.join("ground", "open-work-listing")
ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# A quoted marker is literal. For an unquoted marker, extract_work_ids strips
# prose-final periods while preserving periods inside the identifier. The
# marker must start at a word boundary so a suffix inside words like
# "paperwork order" cannot fire it. A space-separated all-lowercase marker
# ("work order some-id") is prose; lowercase forms count only when the id is
# backtick-quoted or a ":"/"=" separator is present. Mixed/uppercase markers
# accept quoted and plain ids either way.
WORK_MARK_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<marker>WORK[ \t]+ORDER|OWNER[ \t]+LAND[ \t]+ORDER)\s*(?P<sep>[:=])?\s*"
    r"(?:`(?P<quoted>[A-Za-z0-9._-]{8,80})`|(?P<plain>[A-Za-z0-9._-]{8,80}))"
    r"(?![A-Za-z0-9._-])",
    re.I,
)
SENT_USING_RE = re.compile(r"\*Sent using\*", re.I)
HELLO_RE = re.compile(
    r"^(?:hello(?:\s+table)?|hi(?:\s+table)?|hey(?:\s+table)?|"
    r"just arriving|good (?:morning|evening|night)|chorus)\b",
    re.I,
)
KIND_ACTION_RE = re.compile(r"^kind\s*:\s*ACTION\s*$", re.I)
HEADER_ID_RE = re.compile(r"^id\s*:\s*`?([A-Za-z0-9._-]{8,80})`?\s*$", re.I)
FROM_RE = re.compile(r"^from\s*:\s*(\S+)\s*$", re.I)
LM_RE = re.compile(r"^is_language_model\s*:\s*(\S+)\s*$", re.I)
CLAIMED_STATES = frozenset({"CLAIMED", "COMPLETE", "COMPLETED", "DONE", "SUCCESS"})
SLACK_TS_RE = re.compile(r"^\d{10,}\.\d+$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
OPAQUE_ACTION_RE = re.compile(r"^action-\d{8,}-[0-9a-f]{8,}$", re.I)
PREFIX_BYTES = 8192
BODY_STRUCTURE_LINES = 16


def _read(root, rel, max_bytes=None):
    path = os.path.join(root, rel)
    try:
        with open(path, "rb") as handle:
            raw = handle.read() if max_bytes is None else handle.read(max_bytes)
    except OSError:
        return ""
    return raw.decode("utf-8", errors="replace")


def resolve_main_sha(root, explicit=""):
    text = str(explicit or "").strip().lower()
    if text:
        return text if SHA_RE.fullmatch(text) else ""
    # An arbitrary feature-branch HEAD is not official-main evidence. Offline
    # copies without origin/main can supply an observed official SHA explicitly.
    for args in (
        ["git", "rev-parse", "--verify", "refs/remotes/origin/main^{commit}"],
    ):
        try:
            out = subprocess.check_output(
                args,
                cwd=root,
                text=True,
                stderr=subprocess.DEVNULL,
                env=_git_env(),
            ).strip().lower()
        except (OSError, subprocess.CalledProcessError):
            continue
        if SHA_RE.match(out):
            return out
    return ""


def receipt_path(ident):
    return "p/%s.md" % ident


def _git_object_exists(root, spec):
    try:
        subprocess.check_call(
            ["git", "cat-file", "-e", spec],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=_git_env(),
        )
    except OSError:
        return None
    except subprocess.CalledProcessError:
        return False
    return True


def _prefix_receipt_names(ident):
    """Long-slug companions share p/{id}--*.md when the short id has no exact file."""
    return "%s--" % str(ident or "")


def _fs_prefix_receipt(root, ident):
    folder = os.path.join(root, "p")
    prefix = _prefix_receipt_names(ident)
    if not prefix or not os.path.isdir(folder):
        return None
    for name in sorted(os.listdir(folder)):
        if name.startswith(prefix) and name.endswith(".md"):
            return "p/%s" % name
    return None


def _git_prefix_receipt(root, sha, ident):
    prefix = "p/%s" % _prefix_receipt_names(ident)
    if prefix == "p/":
        return None
    try:
        out = subprocess.check_output(
            ["git", "ls-tree", "--name-only", sha, "p/"],
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
            env=_git_env(),
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    for line in out.splitlines():
        rel = line.strip()
        if rel.startswith(prefix) and rel.endswith(".md"):
            return rel
    return None



def _git_receipt_index(root, sha):
    """Read one immutable p/ tree for a projection, not one Git process per ID."""
    try:
        output = subprocess.check_output(
            ["git", "ls-tree", "-z", "--name-only", sha, "p/"],
            cwd=root, stderr=subprocess.DEVNULL,
            env=_git_env(),
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return sorted(
        name.decode("utf-8", "surrogateescape")
        for name in output.split(b"\0")
        if name.startswith(b"p/") and name.endswith(b".md")
    )


class CandidateSourceError(RuntimeError):
    def __init__(self, path, detail):
        super().__init__(detail)
        self.path = path


def _git_candidate_records(root, sha):
    """Stream committed source through one size-framed Git batch reader."""
    try:
        output = subprocess.check_output(
            ["git", "ls-tree", "-z", sha, "--", "p/", "wake_jobs/"],
            cwd=root, stderr=subprocess.DEVNULL, env=_git_env(),
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CandidateSourceError("", "candidate tree could not be read") from exc
    entries = []
    for entry in output.split(b"\0"):
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        _mode, kind, oid = metadata.split()
        # Match the existing flat source directories; nested files and the
        # watchdog's underscore-prefixed tick files are not candidate records.
        if kind != b"blob" or path.count(b"/") != 1:
            continue
        folder, name = path.split(b"/", 1)
        post = folder == b"p" and name.endswith(b".md")
        wake = folder == b"wake_jobs" and name.endswith(b".json") and not name.startswith(b"_")
        if post or wake:
            entries.append((path.decode("utf-8", "surrogateescape"), oid, post))
    if not entries:
        return
    try:
        process = subprocess.Popen(
            ["git", "cat-file", "--batch"], cwd=root,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=_git_env(),
        )
    except OSError as exc:
        raise CandidateSourceError("", "candidate blob reader could not start") from exc
    path = ""
    try:
        for path, oid, post in entries:
            process.stdin.write(oid + b"\n")
            process.stdin.flush()
            header = process.stdout.readline().split()
            if len(header) != 3 or header[:2] != [oid, b"blob"]:
                raise CandidateSourceError(path, "committed candidate blob is unavailable; fetch source blobs")
            size = int(header[2])
            keep = min(size, PREFIX_BYTES) if post else size
            raw = process.stdout.read(keep)
            if len(raw) != keep:
                raise CandidateSourceError(path, "committed candidate blob was truncated")
            remaining = size - keep
            while remaining:
                chunk = process.stdout.read(min(remaining, 65536))
                if not chunk:
                    raise CandidateSourceError(path, "committed candidate blob was truncated")
                remaining -= len(chunk)
            if process.stdout.read(1) != b"\n":
                raise CandidateSourceError(path, "candidate blob framing is incomplete")
            yield path, raw.decode("utf-8", errors="replace")
        process.stdin.close()
        if process.wait() != 0:
            raise CandidateSourceError(path, "candidate blob reader failed")
    except (OSError, ValueError) as exc:
        raise CandidateSourceError(path, "candidate blob could not be read: %s" % exc) from exc
    finally:
        if not process.stdin.closed:
            process.stdin.close()
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
            process.wait()


def _indexed_receipt(names, ident):
    """Exact receipt wins; otherwise use the first sorted long-slug companion."""
    rel = receipt_path(ident).replace(os.sep, "/")
    index = bisect_left(names, rel)
    if index < len(names) and names[index] == rel:
        return rel
    prefix = "p/" + _prefix_receipt_names(ident)
    index = bisect_left(names, prefix)
    if index < len(names) and names[index].startswith(prefix):
        return names[index]
    return None


def resolve_receipt(root, ident, main_sha=""):
    """Exact p/{id}.md first; else first landed p/{id}--*.md companion."""
    rel = receipt_path(ident).replace(os.sep, "/")
    sha = str(main_sha or "").strip().lower()
    if SHA_RE.match(sha):
        commit_exists = _git_object_exists(root, "%s^{commit}" % sha)
        if commit_exists is not True:
            return None
        if _git_object_exists(root, "%s:%s" % (sha, rel)) is True:
            return rel
        return _git_prefix_receipt(root, sha, ident)
    if os.path.isfile(os.path.join(root, rel)):
        return rel
    return _fs_prefix_receipt(root, ident)


def receipt_exists(root, ident, main_sha=""):
    return resolve_receipt(root, ident, main_sha) is not None


def is_work_id(ident):
    text = str(ident or "")
    if not ID_RE.match(text):
        return False
    if text.startswith("grkrev-") or text.startswith("Ev0"):
        return False
    if SLACK_TS_RE.match(text) or UUID_RE.match(text):
        return False
    return True


def is_title_filename(ident):
    """True when a peer can read the work from the filename itself."""
    text = str(ident or "")
    if not is_work_id(text):
        return False
    if OPAQUE_ACTION_RE.match(text):
        return False
    tokens = [part for part in re.split(r"[._-]+", text) if part]
    words = [part for part in tokens if re.search(r"[A-Za-z]{3,}", part)]
    return len(words) >= 2


def listing_filename(ident, klass):
    """Readable title first. Class slug goes last so a truncated file list still reads."""
    title = str(ident or "")
    klass = str(klass or "open").lower()
    stem = "%s-%s" % (title, klass)
    # The 80-character bound belongs to work IDs, not derived filenames.
    # Retain the complete ID so distinct suffixes cannot overwrite one listing.
    if ID_RE.fullmatch(title) and klass.upper() in CLASSES:
        return "%s.md" % stem
    if len(stem) > 80:
        keep = 80 - (len(klass) + 1)
        if keep >= 8:
            stem = "%s-%s" % (title[:keep].rstrip("._-"), klass)
        else:
            stem = title[:80].rstrip("._-")
    if not ID_RE.match(stem):
        stem = re.sub(r"[^A-Za-z0-9._-]", "-", stem)[:80].strip("._-")
    return "%s.md" % stem


def extract_work_ids(text):
    found = []
    seen = set()
    for match in WORK_MARK_RE.finditer(str(text or "")):
        quoted = match.group("quoted")
        if (
            quoted is None
            and match.group("sep") is None
            and match.group("marker").islower()
        ):
            continue
        ident = quoted if quoted is not None else match.group("plain").rstrip(".")
        if ident not in seen and is_work_id(ident):
            seen.add(ident)
            found.append(ident)
    return found


def _split_headers(text):
    lines = str(text or "").replace("\r\n", "\n").split("\n")
    if lines and lines[0].strip() == "---":
        lines = lines[1:]
    headers = []
    body = []
    in_headers = True
    for line in lines:
        if in_headers and line.strip() == "---":
            in_headers = False
            continue
        if in_headers:
            headers.append(line)
        else:
            body.append(line)
    if in_headers:
        return headers, []
    return headers, body


def parse_structured_record(text):
    headers, body = _split_headers(text)
    header_text = "\n".join(headers)
    structure = body[:BODY_STRUCTURE_LINES]
    structure_text = "\n".join(structure)
    ident = ""
    src = ""
    language_model = ""
    kind = ""
    for line in headers:
        mid = HEADER_ID_RE.match(line.strip())
        if mid and not ident:
            ident = mid.group(1)
        mfrom = FROM_RE.match(line.strip())
        if mfrom:
            src = mfrom.group(1)
        mlm = LM_RE.match(line.strip())
        if mlm:
            language_model = mlm.group(1)
        if KIND_ACTION_RE.match(line.strip()):
            kind = "ACTION"
    work_ids = extract_work_ids(header_text + "\n" + "\n".join(body))
    owner = src.upper() == "BRYCE" or language_model.upper() == "NO"
    action = kind == "ACTION"
    sent_using = bool(SENT_USING_RE.search(structure_text)) or bool(
        SENT_USING_RE.search(header_text)
    )
    hello = False
    for line in structure:
        stripped = line.strip()
        if not stripped:
            continue
        if HELLO_RE.match(stripped) or SENT_USING_RE.search(stripped):
            hello = True
        break
    salon = sent_using and hello and not work_ids and not action and not owner
    return {
        "id": ident,
        "from": src,
        "is_language_model": language_model,
        "kind": kind,
        "work_ids": work_ids,
        "owner_directive": owner,
        "action": action,
        "salon": salon,
        "sent_using": sent_using,
    }


def classify_record(record, exists, slack_claimed=False):
    """Classify one structured record / work id."""
    record = record if isinstance(record, dict) else {}
    if record.get("salon") and not record.get("work_ids") and not record.get("action"):
        return "SALON"
    if slack_claimed and not exists:
        return "DEAD_CLAIM"
    work = bool(
        record.get("work_ids")
        or record.get("action")
        or record.get("owner_directive")
        or record.get("work")
    )
    if work and exists:
        return "LANDED"
    if work and not exists:
        return "OPEN"
    if slack_claimed and exists:
        return "LANDED"
    return "NOISE"


def classify_id(ident, root, extra=None, record=None, main_sha=""):
    extra = extra if isinstance(extra, dict) else {}
    claimed = set(extra.get("slack_claimed") or [])
    sha = resolve_main_sha(root, main_sha)
    measured = bool(SHA_RE.match(sha)) and _git_object_exists(
        root, "%s^{commit}" % sha
    ) is True
    resolved = resolve_receipt(root, ident, sha) if measured else None
    exists = resolved is not None
    row_record = dict(record or {})
    row_record.setdefault("work", True)
    klass = classify_record(row_record, exists, slack_claimed=ident in claimed)
    errors = []
    if not measured:
        errors.append({"code": "MAIN_SHA_UNMEASURED", "main_sha": sha})
    return {
        "id": ident,
        "class": klass,
        "receipt": resolved if exists else "404",
        "last_sha": sha,
        "errors": errors,
    }


def _walk_strings(value, out):
    if isinstance(value, str):
        out.append(value)
        return
    if isinstance(value, dict):
        for item in value.values():
            _walk_strings(item, out)
        return
    if isinstance(value, list):
        for item in value:
            _walk_strings(item, out)


def collect_wake_jobs(root, committed=None):
    rows = []
    records = dict(committed or {})
    folder = os.path.join(root, "wake_jobs")
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".json") or name.startswith("_"):
                continue
            rel = "wake_jobs/" + name
            # This store is live working state. A newer local transition wins
            # for the same job, while jobs omitted by sparse checkout survive.
            records[rel] = _read(root, rel)
    for rel in sorted(records):
        try:
            data = json.loads(records[rel] or "{}")
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        strings = []
        _walk_strings(data, strings)
        work_ids = []
        seen = set()
        for blob in strings:
            for ident in extract_work_ids(blob):
                if ident not in seen:
                    seen.add(ident)
                    work_ids.append(ident)
        for key in ("result_address",):
            ident = str(data.get(key) or "").strip()
            ident = ident[2:] if ident.startswith("p/") and ident.endswith(".md") else ident
            ident = ident[:-3] if ident.endswith(".md") else ident
            if is_work_id(ident) and ident not in seen:
                seen.add(ident)
                work_ids.append(ident)
        status = str(data.get("status") or "").strip().upper()
        for ident in work_ids:
            rows.append(
                {
                    "id": ident,
                    "work": True,
                    "work_ids": [ident],
                    "wake_status": status,
                    "slack_claimed": status in CLAIMED_STATES,
                }
            )
    return rows


def _post_candidates(text, include_salon=False):
    rows = []
    parsed = parse_structured_record(text)
    if parsed["salon"]:
        if include_salon and parsed["id"]:
            rows.append(parsed)
        return rows
    if parsed["action"] and parsed["id"]:
        rows.append(
            {
                "id": parsed["id"],
                "work": True,
                "action": True,
                "work_ids": list(parsed["work_ids"]),
                "owner_directive": parsed["owner_directive"],
            }
        )
    for ident in parsed["work_ids"]:
        rows.append(
            {
                "id": ident,
                "work": True,
                "work_ids": [ident],
                "owner_directive": parsed["owner_directive"],
                "action": parsed["action"],
            }
        )
    if (
        parsed["owner_directive"]
        and parsed["id"]
        and (parsed["action"] or parsed["work_ids"])
    ):
        rows.append(
            {
                "id": parsed["id"],
                "work": True,
                "owner_directive": True,
                "work_ids": list(parsed["work_ids"]),
                "action": parsed["action"],
            }
        )
    return rows


def collect_posts(root, include_salon=False):
    rows = []
    folder = os.path.join(root, "p")
    if not os.path.isdir(folder):
        return rows
    for name in sorted(os.listdir(folder)):
        if name.endswith(".md"):
            rel = os.path.join("p", name)
            rows.extend(_post_candidates(_read(root, rel, max_bytes=PREFIX_BYTES), include_salon))
    return rows


def merge_candidates(rows, extra=None):
    extra = extra if isinstance(extra, dict) else {}
    by_id = {}
    for row in rows:
        ident = str(row.get("id") or "")
        if not is_work_id(ident) and not row.get("salon"):
            continue
        if not ident:
            continue
        prior = by_id.get(ident) or {"id": ident}
        if row.get("salon"):
            prior["salon"] = True
        if row.get("work") or row.get("work_ids") or row.get("action") or row.get("owner_directive"):
            prior["work"] = True
        if row.get("action"):
            prior["action"] = True
        if row.get("owner_directive"):
            prior["owner_directive"] = True
        if row.get("slack_claimed"):
            prior["slack_claimed"] = True
        ids = list(prior.get("work_ids") or [])
        for item in row.get("work_ids") or []:
            if item not in ids:
                ids.append(item)
        prior["work_ids"] = ids
        by_id[ident] = prior
    for ident in extra.get("slack_claimed") or []:
        if not is_work_id(ident):
            continue
        prior = by_id.get(ident) or {"id": ident, "work": True}
        prior["slack_claimed"] = True
        prior["work"] = True
        by_id[ident] = prior
    for ident in extra.get("work_ids") or []:
        if not is_work_id(ident):
            continue
        prior = by_id.get(ident) or {"id": ident, "work": True}
        prior["work"] = True
        by_id[ident] = prior
    return by_id


def project(root, main_sha="", extra=None, include_salon=False):
    sha = resolve_main_sha(root, main_sha)
    measured = bool(SHA_RE.match(sha)) and _git_object_exists(
        root, "%s^{commit}" % sha
    ) is True
    errors = []
    if not measured:
        errors.append({"code": "MAIN_SHA_UNMEASURED", "main_sha": sha})
    receipts = _git_receipt_index(root, sha) if measured else None
    if measured and receipts is None:
        errors.append({"code": "MAIN_TREE_UNMEASURED", "main_sha": sha})
    extra = extra if isinstance(extra, dict) else {}
    rows = []
    wake_records = {}
    if measured:
        try:
            for rel, text in _git_candidate_records(root, sha):
                if rel.startswith("p/"):
                    rows.extend(_post_candidates(text, include_salon))
                else:
                    wake_records[rel] = text
        except CandidateSourceError as exc:
            errors.append({
                "code": "MAIN_SOURCE_UNMEASURED", "main_sha": sha,
                "path": exc.path, "detail": str(exc),
            })
    rows.extend(collect_posts(root, include_salon=include_salon))
    rows.extend(collect_wake_jobs(root, committed=wake_records))
    by_id = merge_candidates(rows, extra)
    items = []
    for ident in sorted(by_id):
        record = by_id[ident]
        resolved = _indexed_receipt(receipts, ident) if receipts is not None else None
        exists = resolved is not None
        slack_claimed = bool(record.get("slack_claimed")) or ident in set(
            extra.get("slack_claimed") or []
        )
        klass = classify_record(record, exists, slack_claimed=slack_claimed)
        titled = is_title_filename(ident)
        items.append(
            {
                "id": ident,
                "class": klass,
                "receipt": resolved if exists else "404",
                "last_sha": sha,
                "title_filename": listing_filename(ident, klass) if titled else "",
            }
        )
    counts = {name: 0 for name in CLASSES}
    for item in items:
        counts[item["class"]] = counts.get(item["class"], 0) + 1
    return {
        "schema": SCHEMA,
        "main_sha": sha,
        "errors": errors,
        "items": items,
        "counts": counts,
        "human": HUMAN_REL,
        "machine": MACHINE_REL,
        "listing": LISTING_REL,
        "pointer_human": POINTER_HUMAN_REL,
        "pointer_machine": POINTER_MACHINE_REL,
    }


def render_human(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    sha = snapshot.get("main_sha") or ""
    counts = snapshot.get("counts") or {}
    lines = [
        "# Open work",
        "",
        "Sibling projector of structured work-order ids on this board. Not a second queue. Not a Slack dump-scan.",
        "",
        "LANDED only when `p/{id}.md` exists at the official current main SHA. Slack CLAIMED, pulse, Pages, and ntfy 200 are not a land.",
        "",
        "Instrument: [`host/open_work.py`](../host/open_work.py). Machine: [`open-work-structured-ids-on-current-main.json`](./open-work-structured-ids-on-current-main.json). Listing dir: [`open-work-listing/`](./open-work-listing/). Pointer: [`OPEN_WORK.md`](./OPEN_WORK.md).",
        "",
        "New projector outputs use title-filenames with useful words first. Existing `p/{id}.md` slugs are not renamed.",
        "",
        "Checked SHA: `%s`" % (sha or "UNKNOWN"),
        "",
    ]
    for klass in ("OPEN", "LANDED", "DEAD_CLAIM"):
        rows = [
            item
            for item in snapshot.get("items") or []
            if item.get("class") == klass and item.get("title_filename")
        ]
        lines.append("## %s" % klass)
        lines.append("")
        if not rows:
            lines.append("None this SHA.")
            lines.append("")
            continue
        lines.append("| title filename | id | receipt | last SHA |")
        lines.append("| --- | --- | --- | --- |")
        for item in rows:
            lines.append(
                "| `%s` | `%s` | `%s` | `%s` |"
                % (
                    item.get("title_filename"),
                    item.get("id"),
                    item.get("receipt"),
                    item.get("last_sha") or "",
                )
            )
        lines.append("")
    lines.extend(
        [
            "## Counts",
            "",
            "- OPEN: %s" % counts.get("OPEN", 0),
            "- LANDED: %s" % counts.get("LANDED", 0),
            "- DEAD_CLAIM: %s" % counts.get("DEAD_CLAIM", 0),
            "- SALON: %s" % counts.get("SALON", 0),
            "- NOISE: %s" % counts.get("NOISE", 0),
            "",
            "SALON hellos and chorus marks (`*Sent using*`) are not ingested as work.",
            "",
            "## Live cash",
            "",
            "Verified product pages only — no invented Stripe links.",
            "",
            "- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)",
            "- [$199 referral diagnostic](../referral-intake-completeness.html)",
            "- [$199 repair diagnostic](../repair-booking-preflight.html)",
            "- [$199 plant diagnostic](../plant-downtime-handoff.html)",
            "",
            "Larger fixed engagements (separate product pages; checkout/intent stays there): [GGUF diagnostic · $12,000 / 10 days](../diagnostic.html) · [White Box pilot · $30,000 / 30 days](../commercial.html). Not remints of tip SKUs.",
            "",
            "Shelf: [tools-cash.html](../tools-cash.html). Catalog: [commerce.html](../commerce.html). Cite spy-ground-batch-live-cash-20260909-24 — do not remint.",
            "",
            "## Contest product (titanmcp)",
            "",
            "Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.",
            "",
        ]
    )
    return "\n".join(lines)


def render_pointer(snapshot):
    sha = (snapshot or {}).get("main_sha") or "UNKNOWN"
    return "\n".join(
        [
            "# Open work",
            "",
            "Pointer only. Canonical title-filename listing:",
            "",
            "- human: [`open-work-structured-ids-on-current-main.md`](./open-work-structured-ids-on-current-main.md)",
            "- machine: [`open-work-structured-ids-on-current-main.json`](./open-work-structured-ids-on-current-main.json)",
            "- ls listing: [`open-work-listing/`](./open-work-listing/)",
            "",
            "Existing `p/{id}.md` slugs are not renamed. This path stays so older links still resolve.",
            "",
            "Checked SHA: `%s`" % sha,
            "",
            "## Live cash",
            "",
            "Verified product pages only — no invented Stripe links.",
            "",
            "- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)",
            "- [$199 referral diagnostic](../referral-intake-completeness.html)",
            "- [$199 repair diagnostic](../repair-booking-preflight.html)",
            "- [$199 plant diagnostic](../plant-downtime-handoff.html)",
            "",
            "Larger fixed engagements (separate product pages; checkout/intent stays there): [GGUF diagnostic · $12,000 / 10 days](../diagnostic.html) · [White Box pilot · $30,000 / 30 days](../commercial.html). Not remints of tip SKUs.",
            "",
            "Shelf: [tools-cash.html](../tools-cash.html). Catalog: [commerce.html](../commerce.html). Cite spy-ground-batch-live-cash-20260905-19 — do not remint.",
            "",
            "## Contest product (titanmcp)",
            "",
            "Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.",
            "",
        ]
    )


def write_listing(root, snapshot):
    folder = os.path.join(root, LISTING_REL)
    os.makedirs(folder, exist_ok=True)
    keep = set()
    for item in snapshot.get("items") or []:
        if item.get("class") not in ("OPEN", "DEAD_CLAIM"):
            continue
        name = item.get("title_filename") or ""
        if not name.endswith(".md"):
            continue
        keep.add(name)
        path = os.path.join(folder, name)
        body = "\n".join(
            [
                "# %s" % item.get("id"),
                "",
                "- class: `%s`" % item.get("class"),
                "- receipt: `%s`" % item.get("receipt"),
                "- last_sha: `%s`" % (item.get("last_sha") or ""),
                "- title_filename: `%s`" % name,
                "",
                "Projection of the existing board. Not a second queue. Not a remint of `p/{id}.md`.",
                "",
            ]
        )
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if name.endswith(".md") and name not in keep:
                try:
                    os.remove(os.path.join(folder, name))
                except OSError:
                    pass
    return folder


def write_snapshot(root, snapshot):
    # Preserve the last measured projection when a checkout or Git observation
    # is unavailable. Diagnostics belong in the CLI result, not a replacement
    # document that silently discards them and looks like an empty work queue.
    if snapshot.get("errors"):
        raise ValueError("cannot write an unmeasured main snapshot")
    human = render_human(snapshot)
    machine = {
        "schema": snapshot.get("schema"),
        "main_sha": snapshot.get("main_sha"),
        "counts": snapshot.get("counts"),
        "items": snapshot.get("items"),
        "human": HUMAN_REL,
        "machine": MACHINE_REL,
        "listing": LISTING_REL,
    }
    human_path = os.path.join(root, HUMAN_REL)
    machine_path = os.path.join(root, MACHINE_REL)
    os.makedirs(os.path.dirname(human_path), exist_ok=True)
    with open(human_path, "w", encoding="utf-8") as handle:
        handle.write(human)
        if not human.endswith("\n"):
            handle.write("\n")
    with open(machine_path, "w", encoding="utf-8") as handle:
        json.dump(machine, handle, indent=2, sort_keys=True)
        handle.write("\n")
    pointer_human = os.path.join(root, POINTER_HUMAN_REL)
    pointer_machine = os.path.join(root, POINTER_MACHINE_REL)
    with open(pointer_human, "w", encoding="utf-8") as handle:
        handle.write(render_pointer(snapshot))
    with open(pointer_machine, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "schema": SCHEMA,
                "canonical_human": HUMAN_REL,
                "canonical_machine": MACHINE_REL,
                "listing": LISTING_REL,
                "main_sha": snapshot.get("main_sha"),
            },
            handle,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")
    write_listing(root, snapshot)
    return human_path, machine_path


def self_test():
    salon = parse_structured_record(
        "from: PEER\nid: salon-hello-fixture-20260829-01\n\n---\n\nhello table\n\n*Sent using* Cursor\n"
    )
    assert salon["salon"] is True
    assert classify_record(salon, True) == "SALON"
    work = parse_structured_record(
        "from: BRYCE\nis_language_model: NO\nid: owner-land-order-fixture-01\nkind: ACTION\n\n---\n\nWORK ORDER missing-work-fixture-20260829-01\n"
    )
    assert work["action"] is True
    assert work["owner_directive"] is True
    assert "missing-work-fixture-20260829-01" in work["work_ids"]
    assert extract_work_ids("WORK ORDER sentence-final-work-20260830-01. Done") == [
        "sentence-final-work-20260830-01"
    ]
    assert extract_work_ids("WORK ORDER dotted.namespace-work-20260830-01") == [
        "dotted.namespace-work-20260830-01"
    ]
    assert extract_work_ids("WORK ORDER `literal-terminal-dot-20260830-01.`") == [
        "literal-terminal-dot-20260830-01."
    ]
    assert extract_work_ids("OWNER LAND ORDER missing-work-fixture-20260829-01") == [
        "missing-work-fixture-20260829-01"
    ]
    assert extract_work_ids("the purchasing-paperwork order unclaimed; current-main") == []
    assert extract_work_ids(
        "search for `estimate approval invoice contractor work order change-order`"
    ) == []
    assert extract_work_ids("work order change-order") == []
    assert extract_work_ids("Work order open-door-main-push-report-20260830-01.") == [
        "open-door-main-push-report-20260830-01"
    ]
    assert extract_work_ids("work order `kimi-continuity-kit-20260829-01` is CLOSED") == [
        "kimi-continuity-kit-20260829-01"
    ]
    assert extract_work_ids("work\torder: lowercase-sep-work-20260830-01") == [
        "lowercase-sep-work-20260830-01"
    ]
    assert extract_work_ids("owner land order= lowercase-eq-work-20260830-01") == [
        "lowercase-eq-work-20260830-01"
    ]
    assert classify_record({"work": True}, True) == "LANDED"
    assert classify_record({"work": True}, False) == "OPEN"
    assert classify_record({"work": True}, False, slack_claimed=True) == "DEAD_CLAIM"
    assert classify_record({"work": True}, True, slack_claimed=True) == "LANDED"
    assert is_title_filename("kimi-pages-speed-20260829-01")
    assert is_title_filename("commons-peers-telegram-20260829-01")
    assert is_title_filename("open-work-projector-20260829-01")
    assert not is_title_filename("action-20260828163033-89fe29a5e062")
    assert listing_filename("kimi-continuity-kit-20260829-01", "OPEN") == (
        "kimi-continuity-kit-20260829-01-open.md"
    )
    assert listing_filename("kimi-continuity-kit-20260829-01", "OPEN").startswith(
        "kimi-continuity-kit"
    )
    print("self-test ok")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Structured open-work projector")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument(
        "--main-sha", default="",
        help="official commit for candidate sources and receipts (default: origin/main); source blobs must be local",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--include-salon", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--slack-claimed",
        action="append",
        default=[],
        help="id that Slack marked CLAIMED; without p/ this is DEAD_CLAIM",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    extra = {"slack_claimed": list(args.slack_claimed or [])}
    snapshot = project(
        args.root,
        args.main_sha,
        extra=extra,
        include_salon=args.include_salon,
    )
    if args.write and not snapshot.get("errors"):
        write_snapshot(args.root, snapshot)
    json.dump(snapshot, sys.stdout, indent=2)
    sys.stdout.write("\n")
    if snapshot.get("errors"):
        sys.stderr.write("Official main or candidate source was not measured; existing projection files were preserved.\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
