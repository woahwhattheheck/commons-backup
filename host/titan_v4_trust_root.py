#!/usr/bin/env python3
"""Pin Titan V4 candidate workflow bytes as Git data only.

Never checks out, imports, sources, or executes candidate content. Reads
``git ls-tree`` entries for HEAD and BASE and pins any present workflow blob
to the approved digest.

Pre-plumbing V4 candidates are lawful: if the canonical BASE tree does not
carry the frozen plumbing workflow, HEAD may also omit it. Introducing the
file is allowed only as the exact approved blob. Once BASE has the file,
HEAD must keep that exact ordinary 100644 blob.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

APPROVED_WORKFLOW_BLOB = "2a1800c02d2a4c11293bdccc7914ab8f6fd93321"
WORKFLOW = ".github/workflows/titan-v4-plumbing.yml"


def _fail(message: str) -> None:
    raise SystemExit(message)


def ls_tree(commit: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "ls-tree", commit, "--", path],
        text=True,
    ).rstrip("\n")


def parse_entry(entry: str) -> tuple[str, str, str, str]:
    parts = entry.split(None, 3)
    if len(parts) != 4:
        _fail("candidate workflow must be one ordinary 100644 Git blob")
    return parts[0], parts[1], parts[2], parts[3]


def pin_candidate_workflow(
    *,
    head_sha: str,
    base_sha: str,
    workflow: str = WORKFLOW,
    approved: str = APPROVED_WORKFLOW_BLOB,
) -> str:
    head_entry = ls_tree(head_sha, workflow)
    base_entry = ls_tree(base_sha, workflow)
    if not head_entry:
        if not base_entry:
            return (
                f"TITAN V4 TRUST ROOT OK head={head_sha} "
                "workflow=absent-on-canonical-and-candidate"
            )
        _fail(f"candidate dropped {workflow}")
    mode, typ, obj, path = parse_entry(head_entry)
    if mode != "100644" or typ != "blob" or path != workflow or not obj:
        _fail(
            "candidate workflow must be one ordinary 100644 Git blob\n"
            f"mode={mode!r} type={typ!r} object={obj!r} path={path!r}"
        )
    if obj != approved:
        _fail(
            "candidate changed frozen Titan-V4 workflow authority\n"
            f"expected_blob={approved} observed_blob={obj}"
        )
    return f"TITAN V4 TRUST ROOT OK head={head_sha} workflow_blob={obj}"


def _expect_ok(head: str, base: str, approved: str, workflow: str, needle: str) -> None:
    msg = pin_candidate_workflow(head_sha=head, base_sha=base, approved=approved, workflow=workflow)
    if needle not in msg:
        raise SystemExit(f"expected {needle!r} in {msg!r}")


def _expect_fail(head: str, base: str, approved: str, workflow: str, needle: str) -> None:
    try:
        msg = pin_candidate_workflow(head_sha=head, base_sha=base, approved=approved, workflow=workflow)
    except SystemExit as exc:
        text = str(exc)
        if needle not in text:
            raise SystemExit(f"expected {needle!r} in fail {text!r}") from None
        return
    raise SystemExit(f"expected failure containing {needle!r}, got {msg!r}")


def _run(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=merged,
    )
    return result.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "trust-root-test",
        "GIT_AUTHOR_EMAIL": "trust-root-test@example.invalid",
        "GIT_COMMITTER_NAME": "trust-root-test",
        "GIT_COMMITTER_EMAIL": "trust-root-test@example.invalid",
        "GIT_AUTHOR_DATE": "2026-09-12T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-09-12T00:00:00+00:00",
    }
    _run(repo, "add", "-A", env=env)
    _run(repo, "commit", "--allow-empty", "-m", message, env=env)
    return _run(repo, "rev-parse", "HEAD")


def self_test() -> None:
    workflow = WORKFLOW
    approved_text = "name: titan-v4-plumbing\napproved: true\n"
    other_text = "name: titan-v4-plumbing\napproved: false\n"
    with tempfile.TemporaryDirectory(prefix="titan-v4-trust-root-") as raw:
        repo = Path(raw)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        _run(repo, "config", "user.email", "trust-root-test@example.invalid")
        _run(repo, "config", "user.name", "trust-root-test")
        old = os.getcwd()
        os.chdir(repo)
        try:
            (repo / "README").write_text("canonical\n", encoding="utf-8")
            base_missing = _commit(repo, "canonical without plumbing")
            (repo / "overlay").mkdir()
            (repo / "overlay" / "feature.py").write_text("print(1)\n", encoding="utf-8")
            head_missing = _commit(repo, "candidate without plumbing")
            _expect_ok(
                head_missing, base_missing, "unused", workflow,
                "absent-on-canonical-and-candidate",
            )

            dest = repo / workflow
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(approved_text, encoding="utf-8")
            head_intro = _commit(repo, "introduce approved plumbing")
            intro_blob = ls_tree(head_intro, workflow).split()[2]
            _expect_ok(head_intro, base_missing, intro_blob, workflow, f"workflow_blob={intro_blob}")

            dest.write_text(other_text, encoding="utf-8")
            head_wrong = _commit(repo, "wrong plumbing blob")
            _expect_fail(
                head_wrong, base_missing, intro_blob, workflow,
                "changed frozen Titan-V4 workflow authority",
            )

            dest.write_text(approved_text, encoding="utf-8")
            base_present = _commit(repo, "canonical with plumbing")
            (repo / "overlay" / "more.py").write_text("print(2)\n", encoding="utf-8")
            head_keep = _commit(repo, "keep frozen plumbing")
            _expect_ok(head_keep, base_present, intro_blob, workflow, f"workflow_blob={intro_blob}")

            dest.unlink()
            head_drop = _commit(repo, "drop plumbing")
            _expect_fail(head_drop, base_present, intro_blob, workflow, f"candidate dropped {workflow}")

            os.symlink("elsewhere.yml", dest)
            head_link = _commit(repo, "symlink plumbing")
            _expect_fail(head_link, base_present, intro_blob, workflow, "ordinary 100644 Git blob")
        finally:
            os.chdir(old)
    print("TITAN V4 TRUST ROOT SELF-TEST OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--head-sha", default=os.environ.get("HEAD_SHA", ""))
    parser.add_argument("--base-sha", default=os.environ.get("BASE_SHA", ""))
    parser.add_argument("--workflow", default=os.environ.get("WORKFLOW", WORKFLOW))
    parser.add_argument("--approved", default=os.environ.get("APPROVED_WORKFLOW_BLOB", APPROVED_WORKFLOW_BLOB))
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if not args.head_sha or not args.base_sha:
        _fail("HEAD_SHA and BASE_SHA are required")
    print(pin_candidate_workflow(
        head_sha=args.head_sha,
        base_sha=args.base_sha,
        workflow=args.workflow,
        approved=args.approved,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
