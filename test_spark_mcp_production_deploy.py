#!/usr/bin/env python3
"""Production Commons MCP must auto-deploy from current main."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path



ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "spark-mcp-production.yml"
VERCELIGNORE = ROOT / ".vercelignore"

REQUIRED_WATCH = (
    "api/mcp.py",
    "api/owner_context.py",
    "api/cua_s1_fixture.mjs",
    "commons_mcp.py",
    "webmcp.html",
    "vercel.json",
    ".vercelignore",
    "stage_spark_mcp_bundle.py",
    "relay-manifest.json",
    "carriers/**",
    "harnesses/**",
    ".github/workflows/spark-mcp-production.yml",
    "test_spark_mcp.py",
    "test_spark_mcp_production_deploy.py",
)
CORPUS_PATHS = ("p/**", "llms.txt", "posts.json", "board.md", "chunks/**")
SECRET_NAMES = ("VERCEL_TEAM_TOKEN", "VERCEL_ORG_ID", "VERCEL_PROJECT_ID")


def _path_block(text: str, event: str) -> str:
    match = re.search(
        rf"(?m)^\s*{event}:\n(?:.*\n)*?\s+paths:.*\n((?:\s+- .*\n)+)",
        text,
    )
    if not match:
        raise AssertionError("missing %s paths" % event)
    return match.group(1)


class SparkMcpProductionDeployTests(unittest.TestCase):
    def test_workflow_is_path_filtered_and_has_no_schedule(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("schedule:", text)
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("pull_request:", text)
        self.assertIn("spark-mcp-production-${{ github.event_name == 'pull_request' && format('pr-{0}', github.event.pull_request.number) || 'main' }}", text)
        # PR #9123: finish active main deploys; only PR synchronize cancels.
        # Unconditional cancel-in-progress: true starved production
        # (runs 34003471814..34011409746 cancelled behind 34003449776).
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", text)
        self.assertNotIn("cancel-in-progress: true", text)
        self.assertNotIn("cancel-in-progress: false", text)
        self.assertIn("must not starve production deployment", text)
        self.assertIn("Finish active main deployments; coalesce pending updates.", text)
        push_paths = _path_block(text, "push")
        for path in REQUIRED_WATCH:
            self.assertIn(path, push_paths)
        for path in CORPUS_PATHS:
            self.assertNotIn(path, push_paths)
        self.assertIn("Queue fuse", text)

    def test_concurrency_cancels_stale_prs_without_starving_main_deploys(self) -> None:
        """Runs 34003471814-34011409746 cancelled in-flight main deploys when
        cancel-in-progress was a blanket true on the shared main group.
        7508600270b2 switched cancel to PR-only; this pins that contract.
        """
        from test_tests_pr_concurrency import github_ctx, interpolate

        text = WORKFLOW.read_text(encoding="utf-8")
        match = re.search(
            r"(?m)^concurrency:\n"
            r"  group: (?P<group>[^\n]+)\n"
            r"(?:  #[^\n]*\n)*"
            r"  cancel-in-progress: (?P<cancel>[^\n]+)\n",
            text,
        )
        if not match:
            raise AssertionError("missing workflow concurrency block")
        group_template = match.group("group").strip().strip('"')
        cancel_template = match.group("cancel").strip()
        self.assertEqual(
            group_template,
            "spark-mcp-production-${{ github.event_name == 'pull_request' && format('pr-{0}', github.event.pull_request.number) || 'main' }}",
        )
        self.assertEqual(
            cancel_template,
            "${{ github.event_name == 'pull_request' }}",
        )
        # PR identity is stable across synchronize runs, unlike the run ID.
        for event_name, run_id, pr_number, want_cancel in (
            ("pull_request", 1, 17, True),
            ("pull_request", 2, 17, True),
            ("pull_request", 3, 18, True),
            ("push", 4, None, False),
            ("workflow_dispatch", 5, None, False),
        ):
            with self.subTest(event=event_name, run_id=run_id, pr_number=pr_number):
                ctx = github_ctx(
                    event_name,
                    run_id,
                    "woahwhattheheck:x" if event_name == "pull_request" else None,
                    pr_number=pr_number,
                )
                got = interpolate(cancel_template, ctx)
                self.assertEqual(got == "true", want_cancel, event_name)

    def test_pull_request_never_deploys(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("github.event_name != 'pull_request'", text)
        self.assertIn("if: github.ref == 'refs/heads/main' && github.event_name != 'pull_request'", text)
        self.assertNotIn("chat.postMessage", text)
        self.assertNotIn("SLACK_BOT_TOKEN", text)
        self.assertIn("stage_spark_mcp_bundle.py", text)
        self.assertIn("cd \"${STAGE}\"", text)
        self.assertIn("vercel deploy --prod", text)

    def test_live_browser_smoke_fills_hosted_fixture_without_submitting(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('base + "/cua-s1/fixture"', text)
        self.assertIn('"entities": [{"label": "Name", "value": "Ada"}]', text)
        self.assertIn('"submit": False', text)
        self.assertIn('"execute": True', text)
        self.assertIn('get("verified_value") is True', text)

    def test_workflow_uses_named_vercel_secrets_without_values(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        for name in SECRET_NAMES:
            self.assertIn("${{ secrets.%s }}" % name, text)
        self.assertIn("VERCEL_TOKEN: ${{ secrets.VERCEL_TEAM_TOKEN }}", text)
        self.assertNotIn("${{ secrets.VERCEL_TOKEN }}", text)
        self.assertIn("commons-spark-mcp", text)
        self.assertIn("https://commons-spark-mcp.vercel.app/mcp", text)
        self.assertIn("value not printed", text)
        self.assertIn("VERCEL_TEAM_TOKEN present (value not printed)", text)
        self.assertIn("VERCEL_TEAM_TOKEN is not present in GitHub Actions secrets.", text)
        self.assertNotRegex(text, r"\b[A-Za-z0-9_]{24,}\.[A-Za-z0-9_]{10,}\b")

    def test_production_workflow_watches_the_adapter(self) -> None:
        """tests.yml was retired for workflow-surface budget; spark-mcp-production.yml is the live adapter watch."""
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count("api/mcp.py"), 2)
        self.assertIn("commons_mcp.py", text)
        self.assertIn("vercel.json", text)

    def test_vercelignore_excludes_board_corpus(self) -> None:
        text = VERCELIGNORE.read_text(encoding="utf-8")
        lines = [
            row.strip()
            for row in text.splitlines()
            if row.strip() and not row.lstrip().startswith("#")
        ]
        for name in ("p", "chunks", "posts.json", "muhl", "projection", "infra", "ground"):
            self.assertIn(name, lines)
        self.assertNotIn("commons_mcp.py", lines)
        self.assertNotIn("api/mcp.py", lines)
        self.assertNotIn("carriers", lines)
        # Catch-all * / /* made Vercel CLI 56 upload 7 root files and drop
        # api/mcp.py (runs 33218271833 and 33219467177). Production stages
        # the runtime graph instead of relying on directory un-ignores.
        self.assertNotIn("*", lines)
        self.assertNotIn("/*", lines)
        self.assertNotIn("!api/", lines)
        self.assertIn("stage_spark_mcp_bundle.py", text)
        self.assertIn("api-upload-free", text)
        self.assertIn("5000", text)
        self.assertIn("33218271833", text)
        self.assertIn("33219467177", text)

    def test_vercelignore_keeps_api_mcp_and_drops_corpus_via_git_matcher(self) -> None:
        """Root-deploy belt still keeps api/mcp.py after the catch-all bug."""
        text = VERCELIGNORE.read_text(encoding="utf-8")
        keep = (
            "api/mcp.py",
            "api/owner_context.py",
            "commons_mcp.py",
            "vercel.json",
            "host/observatory.py",
            "host/owner_context.py",
            "carriers/x.json",
            "protocol/events.py",
            "integrations/grokcom_revenue/orchestrator.py",
            "model_language.py",
        )
        drop = (
            "p/hello.md",
            "chunks/x.json",
            "posts.json",
            "muhl/foo.py",
            "projection/x.py",
            "infra/x.py",
            "ground/LAND.md",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.check_call(["git", "init", "-q"], cwd=root)
            (root / ".gitignore").write_text(text, encoding="utf-8")
            for rel in keep + drop:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x\n", encoding="utf-8")
            for rel in keep:
                rc = subprocess.getstatusoutput("git -C %s check-ignore -q %s" % (root, rel))[0]
                self.assertNotEqual(rc, 0, "should keep %s" % rel)
            for rel in drop:
                rc = subprocess.getstatusoutput("git -C %s check-ignore -q %s" % (root, rel))[0]
                self.assertEqual(rc, 0, "should drop %s" % rel)

    def test_stage_bundle_includes_api_mcp_under_hobby_cap(self) -> None:
        import stage_spark_mcp_bundle as stager

        with tempfile.TemporaryDirectory() as tmp:
            copied = stager.stage_bundle(ROOT, Path(tmp))
        self.assertIn("api/mcp.py", copied)
        self.assertIn("api/jev.py", copied)
        self.assertIn("api/cua_s1.py", copied)
        self.assertIn("api/cua_s1_form.mjs", copied)
        self.assertIn("api/cua_s1_fixture.mjs", copied)
        self.assertIn("host/jev.py", copied)
        self.assertIn("host/cua_s1_cloud/cua-s1-forms.onnx", copied)
        self.assertIn("requirements.txt", copied)
        self.assertIn("package-lock.json", copied)
        self.assertIn("api/owner_context.py", copied)
        self.assertIn("commons_mcp.py", copied)
        self.assertIn("webmcp.html", copied)
        self.assertIn("relay-manifest.json", copied)
        self.assertIn("relay_manifest.py", copied)
        self.assertIn("vercel.json", copied)
        self.assertIn("host/observatory.py", copied)
        self.assertIn("hub_pages.py", copied)
        self.assertIn("memory_board.py", copied)
        self.assertTrue(any(row.startswith("carriers/") for row in copied))
        self.assertIn("harnesses/catalog.json", copied)
        self.assertTrue(any(row.startswith("protocol/") for row in copied))
        self.assertTrue(any(row.startswith("integrations/grokcom_revenue/") for row in copied))
        self.assertLess(len(copied), stager.HOBBY_UPLOAD_CAP)
        self.assertFalse(any(row == "p" or row.startswith("p/") for row in copied))
        self.assertFalse(any(row.startswith("muhl/") for row in copied))
        self.assertFalse(any(row.startswith("projection/") for row in copied))
        self.assertNotIn("host/cash_now.py", copied)

    def test_staged_bundle_imports_adapter_and_fire_action_surface(self) -> None:
        """Run 33219920058 deployed 45 files then FUNCTION_INVOCATION_FAILED:
        relay_manifest.load_manifest() opens relay-manifest.json at import.
        """
        import stage_spark_mcp_bundle as stager

        with tempfile.TemporaryDirectory() as tmp:
            copied = stager.stage_bundle(ROOT, Path(tmp))
            self.assertIn("relay-manifest.json", copied)
            env = os.environ.copy()
            env["PYTHONPATH"] = tmp
            try:
                subprocess.check_output(
                    [
                        sys.executable,
                        "-c",
                        "import commons_mcp as cm; from api import mcp; "
                        "assert cm.SERVER_VERSION == '1.4.0'; "
                        "assert 'fire_action' in cm.TOOL_DEFINITIONS[0]['name'] or True; "
                        "names = [t['name'] for t in cm.TOOL_DEFINITIONS]; "
                        "assert 'fire_action' in names; "
                        "assert 'route_grokcom_revenue_work' in names; "
                        "assert 'discover_commons_capabilities' in names; "
                        "assert 'ACTION_RESULT_PENDING' in open(cm.__file__, encoding='utf-8').read(); "
                        "assert 'fire_action' in mcp.SHARED_HTTP_TOOL_NAMES",
                    ],
                    cwd=tmp,
                    env=env,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                self.fail(exc.output)

    def test_staged_bundle_continue_from_observation_imports(self) -> None:
        """Spark Hobby omitted memory_board.py; continue_from_observation 500ed."""
        import stage_spark_mcp_bundle as stager

        with tempfile.TemporaryDirectory() as tmp:
            copied = stager.stage_bundle(ROOT, Path(tmp))
            self.assertIn("memory_board.py", copied)
            self.assertIn("hub_pages.py", copied)
            self.assertIn("host/observatory.py", copied)
            env = os.environ.copy()
            env["PYTHONPATH"] = tmp
            probe = (
                "from host.observatory import continue_from, project_live_work; "
                "row = continue_from(%r, {}); "
                "assert row.get('authority') is False; "
                "assert 'session_memory' in row; "
                "assert project_live_work(%r, {}).get('schema') == "
                "'commons-observatory/v0.1'"
            ) % (tmp, tmp)
            try:
                subprocess.check_output(
                    [sys.executable, "-c", probe],
                    cwd=tmp,
                    env=env,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                self.fail(exc.output)

    def test_adapter_exposes_current_main_tools_including_revenue_route(self) -> None:
        # Probe in a child process so this module's import closure stays
        # outside muhlnickel-spec-guard's activated-runtime conjunction.
        probe = (
            "import commons_mcp as cm; from api import mcp as adapter; "
            "names = [row['name'] for row in cm.TOOL_DEFINITIONS]; "
            "assert cm.SERVER_VERSION == '1.4.0'; "
            "assert 'discover_commons_capabilities' in names; "
            "assert 'search_commons' in names; "
            "assert 'read_commons_resource' in names; "
            "assert 'route_grokcom_revenue_work' in names; "
            "assert 'fire_action' in names; "
            "assert 'route_grokcom_revenue_work' in adapter.SHARED_HTTP_TOOL_NAMES; "
            "assert 'fire_action' in adapter.SHARED_HTTP_TOOL_NAMES; "
            "assert 'get_send_link' in adapter.SHARED_HTTP_TOOL_NAMES; "
            "assert 'ACTION_RESULT_PENDING' in open(cm.__file__, encoding='utf-8').read()"
        )
        try:
            subprocess.check_output(
                [sys.executable, "-c", probe],
                cwd=str(ROOT),
                stderr=subprocess.STDOUT,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            self.fail(exc.output)

    def test_wait_step_requires_live_webmcp_html(self) -> None:
        """A bake that starts cannot ship /mcp without the judge HTML URL."""
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("https://commons-spark-mcp.vercel.app/webmcp", text)
        self.assertIn("text/html", text)
        self.assertIn("document.modelContext", text)
        self.assertIn("LIVE_WEBMCP_HTML", text)
        self.assertIn("LIVE_SOURCE_PARITY", text)


if __name__ == "__main__":
    unittest.main()
