#!/usr/bin/env python3
"""Restore a verified JEV snapshot from the existing private Commons Git repo.

Only private data and status receipts are written under --output-dir. No message
body or credential is printed. Requires GH_TOKEN_PRIMARY or authenticated gh.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = "woahwhattheheck/commons-ship-enforcer"
MANIFEST = re.compile(r"^history-review/\d{4}-\d{2}-\d{2}/private-bundles/"
                      r"((?:gmail|slack)-[a-f0-9]{16})/manifest\.json$")
BASE = "https://api.github.com/repos/" + REPO


def token():
    value = os.environ.get("GH_TOKEN_SECONDARY")
    if value:
        return value
    try:
        run = subprocess.run(["gh", "auth", "token", "--hostname", "github.com",
                              "--user", "tokenjunkielabs"], capture_output=True,
                             text=True, check=True, timeout=25)
        if run.stdout.strip():
            return run.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    value = os.environ.get("GH_TOKEN_PRIMARY") or os.environ.get("GH_TOKEN")
    if value:
        return value
    try:
        run = subprocess.run(["gh", "auth", "token", "--hostname", "github.com"],
                             capture_output=True, text=True, check=True, timeout=25)
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise RuntimeError("github_credential_unavailable") from None
    if not run.stdout.strip():
        raise RuntimeError("github_credential_unavailable")
    return run.stdout.strip()


def get_json(path, credential):
    request = urllib.request.Request(BASE + path, headers={
        "Authorization": "Bearer " + credential,
        "Accept": "application/vnd.github+json",
        "User-Agent": "TJLabs-Jev-Private-Transfer/1.0"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=50) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            retryable = error.code in (429, 500, 502, 503, 504) or (
                error.code == 403 and (error.headers.get("Retry-After") or
                                       error.headers.get("X-RateLimit-Remaining") == "0"))
            if not retryable or attempt == 5:
                raise RuntimeError("private_provider_read_failed_" + str(error.code)) from None
            try:
                delay = float(error.headers.get("Retry-After") or 0)
            except ValueError:
                delay = 0
            if not delay and error.headers.get("X-RateLimit-Remaining") == "0":
                try:
                    delay = int(error.headers.get("X-RateLimit-Reset") or 0) - time.time()
                except ValueError:
                    delay = 0
            time.sleep(max(1, min(delay or 2 ** attempt, 60)))
        except (urllib.error.URLError, TimeoutError):
            if attempt == 5:
                raise RuntimeError("private_provider_read_failed_transport") from None
            time.sleep(min(2 ** attempt, 30))


def verify_checkout(repo_root):
    root = Path(repo_root).expanduser().resolve()
    if not root.is_dir():
        raise RuntimeError("private_checkout_invalid")
    try:
        result = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                                capture_output=True, text=True, check=True, timeout=15)
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise RuntimeError("private_checkout_invalid") from None
    remote = result.stdout.strip()
    if remote.startswith("git@github.com:"):
        remote_path = remote[len("git@github.com:"):]
    else:
        parsed = urllib.parse.urlparse(remote)
        if parsed.scheme not in ("https", "ssh") or parsed.hostname != "github.com":
            raise RuntimeError("private_checkout_invalid")
        remote_path = parsed.path.lstrip("/")
    if remote_path.removesuffix(".git").rstrip("/").lower() != REPO:
        raise RuntimeError("private_checkout_invalid")
    return root


def content(path, credential, repo_root=None):
    if repo_root is not None:
        target = (repo_root / path).resolve()
        if not target.is_relative_to(repo_root) or not target.is_file():
            raise RuntimeError("private_content_invalid")
        return target.read_bytes()
    item = get_json("/contents/" + path + "?ref=main", credential)
    if item.get("type") != "file" or item.get("encoding") != "base64":
        raise RuntimeError("private_content_invalid")
    try:
        return base64.b64decode(item["content"], validate=False)
    except (KeyError, ValueError):
        raise RuntimeError("private_content_invalid") from None


def restore(manifest_path, output_dir, repo_root=None):
    matched = MANIFEST.fullmatch(manifest_path)
    if not matched:
        raise RuntimeError("manifest_path_invalid")
    if repo_root is not None:
        repo_root = verify_checkout(repo_root)
        credential = None
    else:
        credential = token()
        repository = get_json("", credential)
        if (repository.get("full_name", "").lower() != REPO or
                repository.get("private") is not True or repository.get("visibility") != "private"):
            raise RuntimeError("private_destination_unverified")
    manifest = json.loads(content(manifest_path, credential, repo_root))
    name = matched[1]
    expected = manifest.get("archive_sha256")
    count = manifest.get("chunk_count")
    expected_bytes = manifest.get("archive_bytes")
    if (manifest.get("archive") != name or manifest.get("privacy") != "private_repo_only" or
            not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected) or
            not isinstance(count, int) or not 1 <= count <= 10000 or
            not isinstance(expected_bytes, int) or not 1 <= expected_bytes <= 2_000_000_000):
        raise RuntimeError("private_manifest_invalid")
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / name
    marker = destination / ".archive-sha256"
    if destination.exists():
        if marker.is_file() and marker.read_text(encoding="ascii").strip() == expected:
            return {"archive": name, "state": "already_verified", "files": manifest.get("selected_file_count")}
        raise RuntimeError("restore_destination_conflict")
    with tempfile.TemporaryDirectory(dir=output_dir, prefix=name + "-transfer-") as temporary:
        temp = Path(temporary)
        compressed = temp / "archive.tar.gz"
        digest = hashlib.sha256()
        length = 0
        with compressed.open("wb") as target:
            for index in range(count):
                chunk_path = manifest_path.rsplit("/", 1)[0] + f"/chunk-{index:04d}.json"
                envelope = json.loads(content(chunk_path, credential, repo_root))
                if (envelope.get("version") != 1 or envelope.get("archive") != name or
                        envelope.get("index") != index or
                        not isinstance(envelope.get("sha256"), str) or
                        not re.fullmatch(r"[a-f0-9]{64}", envelope["sha256"])):
                    raise RuntimeError("private_chunk_invalid")
                try:
                    part = base64.b64decode(envelope["data"], validate=True)
                except (KeyError, ValueError):
                    raise RuntimeError("private_chunk_invalid") from None
                if (not part or len(part) > 220 * 1024 or
                        hashlib.sha256(part).hexdigest() != envelope["sha256"]):
                    raise RuntimeError("private_chunk_hash_mismatch")
                target.write(part)
                digest.update(part)
                length += len(part)
        if length != expected_bytes or digest.hexdigest() != expected:
            raise RuntimeError("private_archive_hash_mismatch")
        expanded = temp / "expanded"
        expanded.mkdir()
        files = 0
        with tarfile.open(compressed, "r:gz") as archive:
            for member in archive:
                relative = PurePosixPath(member.name)
                if (not member.isfile() or relative.is_absolute() or
                        any(part in ("", ".", "..") for part in relative.parts)):
                    raise RuntimeError("private_archive_member_invalid")
                target = expanded.joinpath(*relative.parts)
                if not target.resolve().is_relative_to(expanded.resolve()):
                    raise RuntimeError("private_archive_member_invalid")
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise RuntimeError("private_archive_member_invalid")
                with target.open("xb") as output:
                    while data := source.read(1024 * 1024):
                        output.write(data)
                files += 1
        if files != manifest.get("selected_file_count"):
            raise RuntimeError("private_archive_file_count_mismatch")
        (expanded / ".archive-sha256").write_text(expected + "\n", encoding="ascii")
        os.replace(expanded, destination)
    return {"archive": name, "state": "restored_verified", "files": files,
            "archive_bytes": length, "archive_sha256": expected}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest_path")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repo-root", help="Existing checkout of the private repository; avoids REST reads")
    args = parser.parse_args()
    try:
        print(json.dumps(restore(args.manifest_path, args.output_dir, args.repo_root)))
        return 0
    except Exception as error:
        code = str(error)
        if not code.startswith(("private_", "manifest_", "restore_")):
            code = "restore_failed"
        print(json.dumps({"restored": False, "error": code}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
