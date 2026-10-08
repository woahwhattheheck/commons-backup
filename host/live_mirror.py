#!/usr/bin/env python3
"""GITHUB_TOKEN-safe live mirror of canonical main onto commons-backup.

Same-account GitHub copy at woahwhattheheck/commons-backup. The scheduled
workflow on the backup `ops` branch force-pushes canonical commons `main`
onto backup `main`. GitHub Apps (including Actions GITHUB_TOKEN) cannot
create or update `.github/workflows/*` without the `workflows` permission.

This is not a Commons lock and not a reason to add a PAT. Exact SHA push
is attempted first when backup main is already contained in source main.
On the measured GitHub App workflows rejection - and whenever backup main
has moved off the recorded tip, via an earlier graft or a direct commit -
dest `.github/workflows` is grafted onto the source tree and that previous
backup tip is kept as the graft commit's second parent, so backup main
stays append-only and no pushed commit is orphaned. Source SHA is
recorded at refs/backup/source-main.
When that ref itself is rejected because the source commit introduces a
workflow file, a workflow-free receipt commit stores the SHA instead.
Tag namespace updates use the same classifier: tags GitHub refuses for
workflow files are skipped; other tag errors stay fail-closed.
GitHub also times out that same App-scope check; that wording is
classified identically so the existing fallbacks still run.

Does not remint host/repo_backup.py or host/moving_main_mirror.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any


SCHEMA_VERSION = "commons-live-mirror/v1"
SOURCE_REF = "refs/backup/source-main"
DEST_REF = "refs/backup/dest-main"
SOURCE_RECEIPT_NAME = "SOURCE_SHA"
WORKFLOWS_DIR = ".github/workflows"
WORKFLOWS_PERMISSION_RE = re.compile(
    r"create or update workflow|"
    r"workflow can be created or updated|"
    r"without [`']workflows[`'] permission|"
    r"[`']workflows[`'] scope may be required",
    re.IGNORECASE,
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class MirrorError(RuntimeError):
    """A live-mirror plan, graft, or push failed its measured contract."""


def _run(
    args: list[str],
    *,
    git_dir: str | None = None,
    check: bool = True,
    input_bytes: bytes | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    cmd = ["git"]
    if git_dir:
        cmd.extend(["--git-dir", git_dir])
    cmd.extend(args)
    completed = subprocess.run(
        cmd,
        input=input_bytes,
        capture_output=True,
        check=False,
        env=env,
    )
    if check and completed.returncode:
        detail = (completed.stderr or completed.stdout).decode("utf-8", "replace").strip()
        raise MirrorError(f"git {' '.join(args)} failed: {detail}")
    return completed


def classify_push_error(stderr: str) -> str:
    """Return WORKFLOWS_PERMISSION or OTHER for a git-push rejection."""
    text = str(stderr or "")
    if WORKFLOWS_PERMISSION_RE.search(text):
        return "WORKFLOWS_PERMISSION"
    return "OTHER"


def plan(src_sha: str, dst_sha: str, mirrored_sha: str | None = None) -> dict[str, Any]:
    """Decide whether backup main already carries this source SHA."""
    if not SHA_RE.fullmatch(src_sha or ""):
        raise MirrorError("src_sha is not a full object id")
    if dst_sha and not SHA_RE.fullmatch(dst_sha):
        raise MirrorError("dst_sha is not a full object id")
    if mirrored_sha and not SHA_RE.fullmatch(mirrored_sha):
        raise MirrorError("mirrored_sha is not a full object id")
    if src_sha == dst_sha:
        return {"action": "already_in_sync", "reason": "exact_sha", "src_sha": src_sha, "dst_sha": dst_sha}
    if mirrored_sha and src_sha == mirrored_sha:
        return {
            "action": "already_in_sync",
            "reason": "recorded_source",
            "src_sha": src_sha,
            "dst_sha": dst_sha,
            "mirrored_sha": mirrored_sha,
        }
    return {"action": "push", "src_sha": src_sha, "dst_sha": dst_sha, "mirrored_sha": mirrored_sha}


def _ls_tree(git_dir: str, tree: str) -> list[tuple[str, str, str, str]]:
    completed = _run(["ls-tree", "-z", tree], git_dir=git_dir)
    rows: list[tuple[str, str, str, str]] = []
    for entry in completed.stdout.split(b"\0"):
        if not entry:
            continue
        meta, name = entry.split(b"\t", 1)
        mode, typ, sha = meta.decode("ascii").split(" ")
        rows.append((mode, typ, sha, name.decode("utf-8")))
    return rows


def _mktree(git_dir: str, rows: list[tuple[str, str, str, str]]) -> str:
    payload = b"".join(
        f"{mode} {typ} {sha}\t{name}\0".encode("utf-8")
        for mode, typ, sha, name in sorted(rows, key=lambda row: row[3].encode("utf-8"))
    )
    completed = _run(["mktree", "-z"], git_dir=git_dir, input_bytes=payload)
    tree = completed.stdout.decode("ascii").strip()
    if not SHA_RE.fullmatch(tree):
        raise MirrorError("mktree did not return a tree id")
    return tree


def _replace_entry(
    git_dir: str,
    tree: str,
    name: str,
    new_mode: str | None,
    new_type: str | None,
    new_sha: str | None,
) -> str:
    rows = []
    found = False
    for mode, typ, sha, fname in _ls_tree(git_dir, tree):
        if fname == name:
            found = True
            if new_sha is not None:
                rows.append((new_mode or mode, new_type or typ, new_sha, fname))
            continue
        rows.append((mode, typ, sha, fname))
    if not found and new_sha is not None:
        rows.append((new_mode or "040000", new_type or "tree", new_sha, name))
    return _mktree(git_dir, rows)


def _path_tree(git_dir: str, commit: str, path: str) -> str | None:
    completed = _run(["rev-parse", "--verify", f"{commit}:{path}"], git_dir=git_dir, check=False)
    if completed.returncode:
        return None
    sha = completed.stdout.decode("ascii").strip()
    return sha if SHA_RE.fullmatch(sha) else None


def graft_dest_workflows(git_dir: str, src_commit: str, dst_commit: str | None) -> dict[str, Any]:
    """Replace source `.github/workflows` with dest's so GITHUB_TOKEN can push.

    Dest workflow blobs are kept byte-identical. New source workflow files are
    omitted. Dest workflow files missing from source are kept. Non-workflow
    paths stay on the source tree.
    """
    src_tree = _run(["rev-parse", f"{src_commit}^{{tree}}"], git_dir=git_dir).stdout.decode("ascii").strip()
    dst_wf = _path_tree(git_dir, dst_commit, WORKFLOWS_DIR) if dst_commit else None
    src_wf = _path_tree(git_dir, src_commit, WORKFLOWS_DIR)
    src_github = _path_tree(git_dir, src_commit, ".github")

    if dst_wf is None:
        if src_wf is None:
            return {
                "schema_version": SCHEMA_VERSION,
                "state": "UNCHANGED",
                "src_tree": src_tree,
                "grafted_tree": src_tree,
                "workflows_frozen": False,
                "workflows_omitted": False,
            }
        if src_github is None:
            raise MirrorError("source has workflows but no .github tree")
        github_rows = [row for row in _ls_tree(git_dir, src_github) if row[3] != "workflows"]
        if github_rows:
            new_github = _mktree(git_dir, github_rows)
            grafted = _replace_entry(git_dir, src_tree, ".github", "040000", "tree", new_github)
        else:
            grafted = _replace_entry(git_dir, src_tree, ".github", None, None, None)
        return {
            "schema_version": SCHEMA_VERSION,
            "state": "OMITTED",
            "src_tree": src_tree,
            "grafted_tree": grafted,
            "workflows_frozen": False,
            "workflows_omitted": True,
        }

    if src_github is None:
        new_github = _mktree(git_dir, [("040000", "tree", dst_wf, "workflows")])
    else:
        new_github = _replace_entry(git_dir, src_github, "workflows", "040000", "tree", dst_wf)
    grafted = _replace_entry(git_dir, src_tree, ".github", "040000", "tree", new_github)
    frozen = src_wf != dst_wf
    return {
        "schema_version": SCHEMA_VERSION,
        "state": "FROZEN" if frozen else "UNCHANGED",
        "src_tree": src_tree,
        "grafted_tree": grafted,
        "src_workflows": src_wf,
        "dst_workflows": dst_wf,
        "workflows_frozen": frozen,
        "workflows_omitted": False,
    }


def _bot_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "github-actions[bot]")
    env.setdefault("GIT_AUTHOR_EMAIL", "41898282+github-actions[bot]@users.noreply.github.com")
    env.setdefault("GIT_COMMITTER_NAME", "github-actions[bot]")
    env.setdefault("GIT_COMMITTER_EMAIL", "41898282+github-actions[bot]@users.noreply.github.com")
    return env


def commit_graft(
    git_dir: str,
    src_commit: str,
    grafted_tree: str,
    message: str | None = None,
    extra_parents: list[str] | None = None,
) -> str:
    src_commit = _run(["rev-parse", src_commit], git_dir=git_dir).stdout.decode("ascii").strip()
    parents = [src_commit] + list(extra_parents or [])
    body = message or (
        f"live-mirror: commons {src_commit} with dest workflow files preserved\n"
        "\n"
        "GITHUB_TOKEN cannot create or update .github/workflows without workflows "
        "permission. Non-workflow paths stay on the source tree. Source SHA is "
        f"recorded at {SOURCE_REF}.\n"
    )
    if len(parents) > 1:
        body += (
            "\n"
            f"Previous backup main {parents[1]} is kept as a second parent so "
            "earlier grafts and direct commits stay reachable in history.\n"
        )
    args = ["commit-tree", grafted_tree]
    for parent in parents:
        args.extend(["-p", parent])
    sha = _run(
        [*args, "-m", body],
        git_dir=git_dir,
        env=_bot_env(),
    ).stdout.decode("ascii").strip()
    if not SHA_RE.fullmatch(sha):
        raise MirrorError("commit-tree did not return a commit id")
    return sha


def _force_refspec(refspec: str) -> str:
    """Force-update dest refs. Grafted backup main is not an ancestor of later source SHAs."""
    return refspec if refspec.startswith("+") else f"+{refspec}"


def _push(git_dir: str, dest_url: str, refspec: str) -> subprocess.CompletedProcess[bytes]:
    # Same contract as the measured live-mirror job: `git push --force`.
    return _run(["push", dest_url, _force_refspec(refspec)], git_dir=git_dir, check=False)


def _push_main(git_dir: str, dest_url: str, refspec: str, expected: str | None) -> subprocess.CompletedProcess[bytes]:
    # Lease on the fetched backup main: a remote update that lands mid-run
    # fails this push instead of being silently overwritten; the next run
    # then keeps the newer tip as a graft parent. Zero sha means "must not
    # exist yet".
    lease = f"--force-with-lease=refs/heads/main:{expected or '0' * 40}"
    return _run(["push", lease, dest_url, refspec.lstrip("+")], git_dir=git_dir, check=False)


def _is_ancestor(git_dir: str, old: str, new: str) -> bool:
    return _run(["merge-base", "--is-ancestor", old, new], git_dir=git_dir, check=False).returncode == 0


def _last_error_line(stderr: str) -> str:
    text = stderr.strip()
    if not text:
        return "workflows permission"
    return text.splitlines()[-1]


def read_source_receipt(git_dir: str, ref: str = SOURCE_REF) -> str | None:
    """Return the recorded source SHA from SOURCE_REF.

    Legacy tips are the source commit itself. After a workflows rejection the
    ref points at a workflow-free commit whose SOURCE_SHA blob holds the hex.
    """
    tip = _run(["rev-parse", "--verify", ref], git_dir=git_dir, check=False)
    if tip.returncode:
        return None
    tip_sha = tip.stdout.decode("ascii").strip()
    blob = _run(
        ["rev-parse", "--verify", f"{ref}:{SOURCE_RECEIPT_NAME}"],
        git_dir=git_dir,
        check=False,
    )
    if blob.returncode == 0:
        text = _run(
            ["cat-file", "-p", blob.stdout.decode("ascii").strip()],
            git_dir=git_dir,
        ).stdout.decode("ascii").strip()
        if not SHA_RE.fullmatch(text):
            raise MirrorError(f"source receipt blob is not a full object id: {text!r}")
        return text
    if SHA_RE.fullmatch(tip_sha):
        return tip_sha
    return None


def commit_source_receipt(git_dir: str, src_sha: str) -> str:
    """Commit containing only SOURCE_SHA so GITHUB_TOKEN can update SOURCE_REF."""
    if not SHA_RE.fullmatch(src_sha or ""):
        raise MirrorError("src_sha is not a full object id")
    blob = _run(
        ["hash-object", "-w", "--stdin"],
        git_dir=git_dir,
        input_bytes=f"{src_sha}\n".encode("ascii"),
    ).stdout.decode("ascii").strip()
    if not SHA_RE.fullmatch(blob):
        raise MirrorError("hash-object did not return a blob id")
    tree = _mktree(git_dir, [("100644", "blob", blob, SOURCE_RECEIPT_NAME)])
    if _path_tree(git_dir, tree, WORKFLOWS_DIR) is not None:
        raise MirrorError("source receipt tree must not contain .github/workflows")
    body = (
        f"live-mirror source receipt {src_sha}\n"
        "\n"
        "GITHUB_TOKEN cannot create or update .github/workflows without workflows "
        f"permission. {SOURCE_REF} therefore records the source SHA in a "
        "workflow-free tree instead of pointing at the source commit.\n"
    )
    sha = _run(
        ["commit-tree", tree, "-m", body],
        git_dir=git_dir,
        env=_bot_env(),
    ).stdout.decode("ascii").strip()
    if not SHA_RE.fullmatch(sha):
        raise MirrorError("commit-tree did not return a commit id")
    return sha


def push_source_receipt(git_dir: str, dest_url: str, src_sha: str) -> dict[str, Any]:
    """Point SOURCE_REF at src_sha, or at a workflow-free receipt of that SHA."""
    if not SHA_RE.fullmatch(src_sha or ""):
        raise MirrorError("src_sha is not a full object id")
    current = read_source_receipt(git_dir, SOURCE_REF)
    if current == src_sha:
        tip = _run(["rev-parse", "--verify", SOURCE_REF], git_dir=git_dir, check=False)
        ref_sha = tip.stdout.decode("ascii").strip() if tip.returncode == 0 else src_sha
        return {
            "schema_version": SCHEMA_VERSION,
            "state": "ALREADY_RECORDED",
            "src_sha": src_sha,
            "ref_sha": ref_sha,
        }
    exact = _push(git_dir, dest_url, f"{src_sha}:{SOURCE_REF}")
    if exact.returncode == 0:
        _run(["update-ref", SOURCE_REF, src_sha], git_dir=git_dir)
        return {
            "schema_version": SCHEMA_VERSION,
            "state": "EXACT_REF",
            "src_sha": src_sha,
            "ref_sha": src_sha,
        }
    stderr = (exact.stderr or exact.stdout).decode("utf-8", "replace")
    if classify_push_error(stderr) != "WORKFLOWS_PERMISSION":
        raise MirrorError(f"source receipt exact push failed: {stderr.strip()}")
    receipt = commit_source_receipt(git_dir, src_sha)
    pushed = _push(git_dir, dest_url, f"{receipt}:{SOURCE_REF}")
    if pushed.returncode:
        detail = (pushed.stderr or pushed.stdout).decode("utf-8", "replace").strip()
        raise MirrorError(f"source receipt fallback push failed: {detail}")
    _run(["update-ref", SOURCE_REF, receipt], git_dir=git_dir)
    return {
        "schema_version": SCHEMA_VERSION,
        "state": "RECEIPT_REF",
        "src_sha": src_sha,
        "ref_sha": receipt,
        "first_error": _last_error_line(stderr),
    }


def push_dest_receipt(git_dir: str, dest_url: str, dst_sha: str) -> None:
    if not SHA_RE.fullmatch(dst_sha or ""):
        raise MirrorError("dst_sha is not a full object id")
    pushed = _push(git_dir, dest_url, f"{dst_sha}:{DEST_REF}")
    if pushed.returncode:
        detail = (pushed.stderr or pushed.stdout).decode("utf-8", "replace").strip()
        raise MirrorError(f"dest receipt push failed: {detail}")


def record_receipts(git_dir: str, dest_url: str, src_sha: str, dst_sha: str) -> dict[str, Any]:
    """Refresh source and destination receipts after sync or a successful push."""
    source = push_source_receipt(git_dir, dest_url, src_sha)
    push_dest_receipt(git_dir, dest_url, dst_sha)
    return {
        "schema_version": SCHEMA_VERSION,
        "src_sha": src_sha,
        "dst_sha": dst_sha,
        "source_ref_state": source["state"],
        "source_ref_sha": source["ref_sha"],
        "dest_ref": DEST_REF,
    }


def push_mirror(
    git_dir: str,
    src_ref: str,
    dest_url: str,
    dst_ref: str | None = None,
) -> dict[str, Any]:
    """Exact-push source main; on workflows rejection, graft dest workflows and push."""
    src_sha = _run(["rev-parse", src_ref], git_dir=git_dir).stdout.decode("ascii").strip()
    dst_sha = None
    if dst_ref:
        completed = _run(["rev-parse", "--verify", dst_ref], git_dir=git_dir, check=False)
        if completed.returncode == 0:
            dst_sha = completed.stdout.decode("ascii").strip()

    # A backup tip that source history does not yet contain (an earlier graft
    # or a direct commit) must stay reachable: graft it in as a second parent
    # instead of force-pushing over it.
    preserve_dst = bool(dst_sha) and not _is_ancestor(git_dir, dst_sha, src_sha)
    stderr = ""
    if not preserve_dst:
        exact = _push_main(git_dir, dest_url, f"{src_sha}:refs/heads/main", dst_sha)
        if exact.returncode == 0:
            receipts = record_receipts(git_dir, dest_url, src_sha, src_sha)
            return {
                "schema_version": SCHEMA_VERSION,
                "state": "EXACT",
                "src_sha": src_sha,
                "pushed_sha": src_sha,
                "workflows_frozen": False,
                "source_ref_state": receipts["source_ref_state"],
                "source_ref_sha": receipts["source_ref_sha"],
            }

        stderr = (exact.stderr or exact.stdout).decode("utf-8", "replace")
        kind = classify_push_error(stderr)
        if kind != "WORKFLOWS_PERMISSION":
            raise MirrorError(f"exact push failed: {stderr.strip()}")

    graft = graft_dest_workflows(git_dir, src_sha, dst_sha)
    if graft["grafted_tree"] == graft["src_tree"] and not preserve_dst:
        raise MirrorError(
            "workflows permission rejected an exact push but grafted tree equals source tree: "
            + stderr.strip()
        )
    grafted_commit = commit_graft(
        git_dir,
        src_sha,
        graft["grafted_tree"],
        extra_parents=[dst_sha] if preserve_dst else None,
    )
    grafted = _push_main(git_dir, dest_url, f"{grafted_commit}:refs/heads/main", dst_sha)
    if grafted.returncode:
        detail = (grafted.stderr or grafted.stdout).decode("utf-8", "replace").strip()
        raise MirrorError(f"grafted push failed: {detail}")
    receipts = record_receipts(git_dir, dest_url, src_sha, grafted_commit)
    return {
        "schema_version": SCHEMA_VERSION,
        "state": "GRAFTED",
        "src_sha": src_sha,
        "pushed_sha": grafted_commit,
        "grafted_tree": graft["grafted_tree"],
        "workflows_frozen": True,
        "preserved_dst": dst_sha if preserve_dst else None,
        "first_error": _last_error_line(stderr) if stderr else None,
        "source_ref_state": receipts["source_ref_state"],
        "source_ref_sha": receipts["source_ref_sha"],
    }


def _list_tag_refs(git_dir: str) -> list[str]:
    completed = _run(["for-each-ref", "--format=%(refname)", "refs/tags"], git_dir=git_dir)
    return [
        line.strip()
        for line in completed.stdout.decode("ascii").splitlines()
        if line.strip().startswith("refs/tags/")
    ]


def _remote_tag_refs(dest_url: str) -> list[str]:
    completed = _run(["ls-remote", dest_url, "refs/tags/*"], check=False)
    refs: list[str] = []
    for line in completed.stdout.decode("ascii").splitlines():
        if not line.strip():
            continue
        _sha, ref = line.split("\t", 1)
        refs.append(ref.strip())
    return refs


def _push_tag_namespace(git_dir: str, dest_url: str) -> subprocess.CompletedProcess[bytes]:
    return _run(
        ["push", "--force", "--prune", dest_url, "refs/tags/*:refs/tags/*"],
        git_dir=git_dir,
        check=False,
    )


def push_tags(git_dir: str, dest_url: str) -> dict[str, Any]:
    """Mirror refs/tags/*. On workflows rejection, push remaining tags one by one."""
    combined = _push_tag_namespace(git_dir, dest_url)
    if combined.returncode == 0:
        return {"schema_version": SCHEMA_VERSION, "state": "EXACT_TAGS", "skipped": []}
    stderr = (combined.stderr or combined.stdout).decode("utf-8", "replace")
    if classify_push_error(stderr) != "WORKFLOWS_PERMISSION":
        raise MirrorError(f"tag namespace push failed: {stderr.strip()}")
    skipped: list[dict[str, str]] = []
    pushed: list[str] = []
    for ref in _list_tag_refs(git_dir):
        one = _push(git_dir, dest_url, f"{ref}:{ref}")
        if one.returncode == 0:
            pushed.append(ref)
            continue
        err = (one.stderr or one.stdout).decode("utf-8", "replace")
        if classify_push_error(err) == "WORKFLOWS_PERMISSION":
            skipped.append({"ref": ref, "error": _last_error_line(err)})
            continue
        raise MirrorError(f"tag push {ref} failed: {err.strip()}")
    local = set(_list_tag_refs(git_dir))
    for remote in _remote_tag_refs(dest_url):
        if remote in local:
            continue
        deleted = _run(["push", dest_url, f":{remote}"], git_dir=git_dir, check=False)
        if deleted.returncode:
            detail = (deleted.stderr or deleted.stdout).decode("utf-8", "replace").strip()
            raise MirrorError(f"tag prune {remote} failed: {detail}")
    return {
        "schema_version": SCHEMA_VERSION,
        "state": "TAGS_WORKFLOWS_SKIPPED" if skipped else "EXACT_TAGS",
        "pushed": pushed,
        "skipped": skipped,
        "first_error": _last_error_line(stderr),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    classify = commands.add_parser("classify-error")
    classify.add_argument("--stderr", default="")
    classify.add_argument("--stderr-file", default=None)

    planned = commands.add_parser("plan")
    planned.add_argument("--src", required=True)
    planned.add_argument("--dst", required=True)
    planned.add_argument("--mirrored", default=None)

    graft = commands.add_parser("graft")
    graft.add_argument("--git-dir", required=True)
    graft.add_argument("--src-ref", required=True)
    graft.add_argument("--dst-ref", default=None)

    push = commands.add_parser("push")
    push.add_argument("--git-dir", required=True)
    push.add_argument("--src-ref", required=True)
    push.add_argument("--dst-ref", default=None)
    push.add_argument("--dest-url", required=True)

    read_src = commands.add_parser("read-source")
    read_src.add_argument("--git-dir", required=True)
    read_src.add_argument("--ref", default=SOURCE_REF)

    record = commands.add_parser("record-receipts")
    record.add_argument("--git-dir", required=True)
    record.add_argument("--src", required=True)
    record.add_argument("--dst", required=True)
    record.add_argument("--dest-url", required=True)

    tags = commands.add_parser("push-tags")
    tags.add_argument("--git-dir", required=True)
    tags.add_argument("--dest-url", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "classify-error":
            text = args.stderr
            if args.stderr_file:
                text = open(args.stderr_file, encoding="utf-8", errors="replace").read()
            payload = {"kind": classify_push_error(text)}
        elif args.command == "plan":
            payload = plan(args.src, args.dst, args.mirrored)
        elif args.command == "graft":
            payload = graft_dest_workflows(args.git_dir, args.src_ref, args.dst_ref)
        elif args.command == "read-source":
            payload = {"src_sha": read_source_receipt(args.git_dir, args.ref)}
        elif args.command == "record-receipts":
            payload = record_receipts(args.git_dir, args.dest_url, args.src, args.dst)
        elif args.command == "push-tags":
            payload = push_tags(args.git_dir, args.dest_url)
        else:
            payload = push_mirror(args.git_dir, args.src_ref, args.dest_url, args.dst_ref)
        print(json.dumps(payload, sort_keys=True))
        return 0
    except MirrorError as error:
        print(f"LIVE_MIRROR_ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
