#!/usr/bin/env python3
"""Continue complete private-history JEV review on a public, free hosted runner.

Source, model results, and publication payloads remain in the private runner
workspace and private Commons repository. Stdout contains counts and hashes only.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

from private_restore import restore

PREFIX = "history-review/2026-09-20/private-bundles/"
BUNDLES = (
    "gmail-22c9f0fdb65dfa26", "gmail-697def44bad3e0a6",
    "gmail-4bd0f2015e505a2a", "gmail-0e39e388e4c62168",
    "slack-0fe40cc968538301", "slack-52471f496d4115d3",
)
PUBLISHER = "https://account-publisher.tjlabs-publisher.workers.dev/v1/publish"
PRIVATE_API = "https://api.github.com/repos/woahwhattheheck/commons-ship-enforcer/contents/"
CHUNK_BYTES = 220 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def http_json(url, token, payload=None):
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(url, data=body, headers={
        "Authorization": "Bearer " + token, "Accept": "application/json",
        "Content-Type": "application/json", "User-Agent": "Commons-JEV-Hosted/1.0",
    }, method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        try:
            response = json.load(error)
        except Exception:
            response = {}
        return error.code, response


def private_read(path, token):
    code, item = http_json(PRIVATE_API + path + "?ref=main", token)
    if code == 404:
        return None
    if code != 200 or item.get("type") != "file":
        raise RuntimeError("private_readback_failed_" + str(code))
    return base64.b64decode(item["content"])


def private_put(path, raw, token):
    prior = private_read(path, token)
    if prior is not None:
        if prior != raw:
            raise RuntimeError("immutable_private_path_conflict")
        return
    operation = "jev-hosted-" + digest(path.encode() + b"\n" + raw)[:48]
    payload = {"operation_id": operation, "operation": "file.put", "args": {
        "owner": "woahwhattheheck", "repo": "commons-ship-enforcer",
        "path": path, "message": ("Store private JEV history bundle chunk"
                            if Path(path).name.startswith("chunk-") else "Store private JEV history receipt manifest"),
        "content": base64.b64encode(raw).decode(),
    }}
    for attempt in range(8):
        code, reply = http_json(PUBLISHER, token, payload)
        if code == 409 and reply.get("error") == "RESOURCE_BUSY":
            time.sleep(min(2 ** attempt, 30))
            continue
        break
    if code not in (200, 201) or reply.get("allow") is not True or not reply.get("receipt", {}).get("commit", {}).get("oid"):
        raise RuntimeError("private_publication_rejected_" + str(reply.get("error") or code))
    if private_read(path, token) != raw:
        raise RuntimeError("private_readback_mismatch")


def source_stats(source):
    records = json.loads(source.read_text(encoding="utf-8"))["records"]
    return len(records), sum(len(str(record.get("body") or record.get("text") or "")) for record in records)


def process(corpus, pattern, source_dir):
    sources = sorted(source_dir.glob(pattern))
    pending = [source for source in sources if not (source.parent / "jev-results" / (source.stem + "-complete.json")).exists()]
    if pending:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("process_collected.py")),
                                 str(source_dir), "--pattern", pattern, "--workers", "4"],
                                capture_output=True, text=True, timeout=5 * 60 * 60)
        if result.returncode:
            tail = result.stdout.strip().splitlines()[-1:] or ['']
            try:
                failed = json.loads(tail[0])
            except ValueError:
                failed = {}
            diagnostic = failed.get('stderr_tail', '')
            known = re.search(r'(?:JevError: (HTTP_\d+|TRANSPORT|BAD_REPLY|NO_KEY|STATE_TOO_LARGE|BAD_QUESTIONS)|'
                              r'(incomplete_jev_answers|invalid_jev_choice|missing completion receipt))', diagnostic)
            code = known.group(1) or known.group(2) if known else 'UNCLASSIFIED'
            source = failed.get('source_file', '')
            if not isinstance(source, str) or not re.fullmatch(r'(?:mail|batch)-[A-Za-z0-9_-]{1,100}\.json', source):
                source = 'unknown'
            raise RuntimeError('jev_process_failed_' + ('gmail' if source_dir == corpus else 'slack')
                               + ':' + source + ':' + code)
    total_messages = total_chars = 0
    for source in sources:
        receipt = source.parent / "jev-results" / (source.stem + "-complete.json")
        if not receipt.is_file():
            raise RuntimeError("completion_receipt_missing")
        count, chars = source_stats(source)
        done = json.loads(receipt.read_text(encoding="utf-8"))
        if done.get("messages") != count or done.get("body_chars_read") != chars:
            raise RuntimeError("completion_receipt_count_mismatch")
        total_messages += count
        total_chars += chars
    return {"source_files": len(sources), "previously_complete": len(sources) - len(pending),
            "newly_complete": len(pending), "messages": total_messages, "body_chars": total_chars}


def receipt_paths(corpus):
    return {p.relative_to(corpus).as_posix(): p for p in corpus.rglob("jev-results/*.json") if p.is_file()}


def publish_receipts(corpus, new_paths, token):
    if not new_paths:
        return {"new_receipt_files": 0}
    packed = io.BytesIO()
    with tarfile.open(fileobj=packed, mode="w:gz") as archive:
        for relative in sorted(new_paths):
            archive.add(corpus / relative, arcname=relative, recursive=False)
    raw = packed.getvalue()
    archive_hash = digest(raw)
    name = "slack-" + archive_hash[:16]
    chunks = [raw[i:i + CHUNK_BYTES] for i in range(0, len(raw), CHUNK_BYTES)]
    base = PREFIX + name + "/"
    for index, chunk in enumerate(chunks):
        envelope = {"version": 1, "archive": name, "index": index,
                    "sha256": digest(chunk), "data": base64.b64encode(chunk).decode()}
        private_put(base + f"chunk-{index:04d}.json",
                    (json.dumps(envelope, separators=(",", ":")) + "\n").encode(), token)
    manifest = {"version": 1, "privacy": "private_repo_only", "bundle": "slack",
                "archive": name, "archive_sha256": archive_hash, "archive_bytes": len(raw),
                "chunk_bytes": CHUNK_BYTES, "chunk_count": len(chunks),
                "selected_file_count": len(new_paths)}
    private_put(base + "manifest.json", (json.dumps(manifest, separators=(",", ":")) + "\n").encode(), token)
    return {"new_receipt_files": len(new_paths), "receipt_archive_sha256": archive_hash,
            "receipt_manifest": base + "manifest.json", "chunks": len(chunks)}


def main():
    token = os.environ.get("COMMONS_GITHUB_TOKEN")
    if not token or not os.environ.get("TYPESAFE_API_KEY"):
        raise RuntimeError("hosted_credential_unbound")
    repo_root = Path(os.environ["PRIVATE_HISTORY_CHECKOUT"]).resolve()
    with tempfile.TemporaryDirectory(prefix="commons-jev-hosted-") as temporary:
        work = Path(temporary)
        restored = work / "restored"
        corpus = work / "corpus"
        corpus.mkdir()
        for name in BUNDLES:
            restore(PREFIX + name + "/manifest.json", restored, repo_root=repo_root)
            for source in (restored / name).rglob("*"):
                if not source.is_file() or source.name == ".archive-sha256":
                    continue
                target = corpus / source.relative_to(restored / name)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        before = set(receipt_paths(corpus))
        gmail = process(corpus, "mail-*.json", corpus)
        slack = process(corpus, "batch-*.json", corpus / "slack" / "batches")
        new = set(receipt_paths(corpus)) - before
        publication = publish_receipts(corpus, new, token)
        print(json.dumps({"status": "complete_for_restored_snapshot", "bundles": len(BUNDLES),
                          "gmail": gmail, "slack": slack, **publication}, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        code = str(error)
        if not code.startswith(("hosted_", "private_", "completion_", "jev_process_", "immutable_")):
            code = "hosted_jev_failed"
        print(json.dumps({"status": "failed", "error": code}))
        raise SystemExit(1)
