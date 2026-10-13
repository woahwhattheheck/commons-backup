from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
WORKFLOW = ROOT / ".github" / "workflows" / "titan-w10-exact-head-gate.yml"
VALID_SHA = "c179ca54ef38534ea801698aa15d5fbc3f59250f"
VALID_HEAD = "sol/verdant-w10-realized-fertilizer-certificate-20260909-03"
VALID_BASE = "main"
VALID_REPO = "woahwhattheheck/commons"
VALID_ITEM = {
    "number": 11699,
    "url": "https://github.com/woahwhattheheck/commons/pull/11699",
    "baseRefName": VALID_BASE,
    "headRefName": VALID_HEAD,
    "headRefOid": VALID_SHA,
    "isCrossRepository": False,
    "headRepositoryOwner": {"login": "woahwhattheheck"},
}


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _heredoc_before(marker: str) -> str:
    text = _workflow_text()
    marker_at = text.find(marker)
    if marker_at < 0:
        raise AssertionError(f"workflow marker is missing: {marker!r}")
    start = text.rfind("<<'PY'\n", 0, marker_at)
    if start < 0:
        raise AssertionError(f"heredoc before marker is missing: {marker!r}")
    start = text.find("\n", start) + 1
    end = text.find("\n          PY\n", start)
    if end < 0:
        raise AssertionError(f"heredoc terminator is missing: {marker!r}")
    return textwrap.dedent(text[start:end] + "\n")


def _context_guard_source() -> str:
    return _heredoc_before(
        "repository, ref_type, ref, ref_name, expected_repository, expected_head = "
        "sys.argv[1:]"
    )


def _verifier_source() -> str:
    return _heredoc_before("expected_owner = repo_parts[0]")


def _run_context_guard(
    repository: str = VALID_REPO,
    ref_type: str = "branch",
    ref: str = f"refs/heads/{VALID_HEAD}",
    ref_name: str = VALID_HEAD,
    expected_repository: str = VALID_REPO,
    expected_head: str = VALID_HEAD,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-",
            repository,
            ref_type,
            ref,
            ref_name,
            expected_repository,
            expected_head,
        ],
        input=_context_guard_source(),
        text=True,
        capture_output=True,
        check=False,
    )


def _run_verifier(snapshot: bytes, *argv: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as tmp:
        snap_path = Path(tmp) / "w10-open-prs.json"
        out_path = Path(tmp) / "github-output.txt"
        snap_path.write_bytes(snapshot)
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                "-",
                *argv,
                str(out_path),
                str(snap_path),
            ],
            input=_verifier_source(),
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        output = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
        completed.output_file = output  # type: ignore[attr-defined]
        return completed


class ExactHeadPrVerifierTests(unittest.TestCase):
    def test_manual_dispatch_is_removed_and_owner_context_precedes_checkout(self) -> None:
        text = _workflow_text()
        self.assertNotIn("workflow_dispatch", text)
        guard_at = text.index("- name: Bind the run to the frozen W10 owner branch")
        checkout_at = text.index("- name: Check out the pushed head")
        self.assertLess(guard_at, checkout_at)
        self.assertIn("EXPECTED_REPOSITORY: woahwhattheheck/commons", text)
        self.assertIn(f"EXPECTED_HEAD_REF: {VALID_HEAD}", text)
        self.assertIn("EXPECTED_BASE_REF: main", text)

    def test_owner_context_accepts_only_the_frozen_branch(self) -> None:
        completed = _run_context_guard()
        self.assertEqual(completed.returncode, 0, completed.stderr)

        cases = [
            {"ref": "refs/heads/sol-prism/foreign-dispatch",
             "ref_name": "sol-prism/foreign-dispatch"},
            {"repository": "other/commons"},
            {"ref_type": "tag", "ref": "refs/tags/v1", "ref_name": "v1"},
            {"ref": f"refs/tags/{VALID_HEAD}"},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                rejected = _run_context_guard(**kwargs)
                self.assertNotEqual(rejected.returncode, 0)
                self.assertIn("refuse unbound W10 run", rejected.stderr)

    def test_workflow_snapshots_inventory_and_does_not_share_stdin(self) -> None:
        text = _workflow_text()
        self.assertIn('printf \'%s\\n\' "$prs" > /tmp/w10-open-prs.json', text)
        self.assertIn("/tmp/w10-open-prs.json <<'PY'", text)
        self.assertNotIn("<<'PY' <<<", text)
        self.assertIn('"$GITHUB_SHA"', text)
        self.assertIn('"$head"', text)
        self.assertIn('"$base"', text)
        self.assertIn('"$repo"', text)
        self.assertIn('"$GITHUB_OUTPUT"', text)
        self.assertIn(
            "--json number,url,baseRefName,headRefName,headRefOid,"
            "isCrossRepository,headRepositoryOwner",
            text,
        )

    def test_valid_tuple_writes_github_output(self) -> None:
        completed = _run_verifier(
            json.dumps([VALID_ITEM]).encode("utf-8"),
            VALID_SHA,
            VALID_HEAD,
            VALID_BASE,
            VALID_REPO,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.output_file,  # type: ignore[attr-defined]
            "\n".join(
                [
                    "number=11699",
                    "url=https://github.com/woahwhattheheck/commons/pull/11699",
                    f"head_sha={VALID_SHA}",
                    "",
                ]
            ),
        )

    def test_empty_inventory_fails_closed(self) -> None:
        completed = _run_verifier(
            b"[]", VALID_SHA, VALID_HEAD, VALID_BASE, VALID_REPO
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn(
            "expected exactly one open PR inventory item, found 0",
            completed.stderr,
        )
        self.assertEqual(completed.output_file, "")  # type: ignore[attr-defined]

    def test_duplicate_json_key_fails_closed(self) -> None:
        raw = (
            b'[{"number":11699,"number":1,'
            b'"url":"https://github.com/woahwhattheheck/commons/pull/11699",'
            b'"baseRefName":"main",'
            b'"headRefName":"sol/verdant-w10-realized-fertilizer-certificate-20260909-03",'
            b'"headRefOid":"c179ca54ef38534ea801698aa15d5fbc3f59250f",'
            b'"isCrossRepository":false,'
            b'"headRepositoryOwner":{"login":"woahwhattheheck"}}]'
        )
        completed = _run_verifier(
            raw, VALID_SHA, VALID_HEAD, VALID_BASE, VALID_REPO
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("duplicate JSON key: number", completed.stderr)
        self.assertEqual(completed.output_file, "")  # type: ignore[attr-defined]

    def test_malformed_json_fails_closed(self) -> None:
        completed = _run_verifier(
            b"{", VALID_SHA, VALID_HEAD, VALID_BASE, VALID_REPO
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("unable to parse open PR inventory", completed.stderr)
        self.assertEqual(completed.output_file, "")  # type: ignore[attr-defined]

    def test_invalid_utf8_fails_closed(self) -> None:
        completed = _run_verifier(
            b"\xff\xfe", VALID_SHA, VALID_HEAD, VALID_BASE, VALID_REPO
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("unable to parse open PR inventory", completed.stderr)
        self.assertEqual(completed.output_file, "")  # type: ignore[attr-defined]

    def test_wrong_base_ref_fails_closed(self) -> None:
        item = dict(VALID_ITEM)
        item["baseRefName"] = "release"
        completed = _run_verifier(
            json.dumps([item]).encode("utf-8"),
            VALID_SHA,
            VALID_HEAD,
            VALID_BASE,
            VALID_REPO,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("does not equal expected base", completed.stderr)
        self.assertEqual(completed.output_file, "")  # type: ignore[attr-defined]

    def test_wrong_head_ref_fails_closed(self) -> None:
        item = dict(VALID_ITEM)
        item["headRefName"] = "other-branch"
        completed = _run_verifier(
            json.dumps([item]).encode("utf-8"),
            VALID_SHA,
            VALID_HEAD,
            VALID_BASE,
            VALID_REPO,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("does not equal expected ref", completed.stderr)
        self.assertEqual(completed.output_file, "")  # type: ignore[attr-defined]

    def test_wrong_head_sha_fails_closed(self) -> None:
        item = dict(VALID_ITEM)
        item["headRefOid"] = "a" * 40
        completed = _run_verifier(
            json.dumps([item]).encode("utf-8"),
            VALID_SHA,
            VALID_HEAD,
            VALID_BASE,
            VALID_REPO,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("does not equal pushed SHA", completed.stderr)
        self.assertEqual(completed.output_file, "")  # type: ignore[attr-defined]

    def test_cross_repository_or_nonboolean_identity_fails_closed(self) -> None:
        for value in (True, 0, None, "false"):
            item = dict(VALID_ITEM)
            item["isCrossRepository"] = value
            completed = _run_verifier(
                json.dumps([item]).encode("utf-8"),
                VALID_SHA,
                VALID_HEAD,
                VALID_BASE,
                VALID_REPO,
            )
            with self.subTest(value=value):
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("must use a same-repository head", completed.stderr)
                self.assertEqual(
                    completed.output_file, ""  # type: ignore[attr-defined]
                )

    def test_wrong_or_malformed_head_owner_fails_closed(self) -> None:
        for value in (
            {"login": "attacker"},
            {"name": "woahwhattheheck"},
            "woahwhattheheck",
            None,
        ):
            item = dict(VALID_ITEM)
            item["headRepositoryOwner"] = value
            completed = _run_verifier(
                json.dumps([item]).encode("utf-8"),
                VALID_SHA,
                VALID_HEAD,
                VALID_BASE,
                VALID_REPO,
            )
            with self.subTest(value=value):
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("PR head owner", completed.stderr)
                self.assertEqual(
                    completed.output_file, ""  # type: ignore[attr-defined]
                )


if __name__ == "__main__":
    unittest.main()
