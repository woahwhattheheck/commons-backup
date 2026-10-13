import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import action_executor as ae
import action_land as al

PYTHON_SHELL = ("& " if sys.platform.startswith("win") else "") + f'"{sys.executable}"'


class ActionExecutorTests(unittest.TestCase):
    def init_repo(self, root):
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
        (root / "seed.txt").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "add", "seed.txt"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "seed"], cwd=root, check=True)

    def test_parse_action_record(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.md"
            p.write_text("from: SOL\nto: TOOLS\nid: sol-action-0001\nkind: ACTION\nact: MAKE IT SO\ntarget: out.txt\n\n---\n\nMAKE IT SO\ntarget: out.txt\n\nhello", encoding="utf-8")
            rec = ae.parse_record(p)
            self.assertEqual(rec["verb"], "MAKE IT SO")
            self.assertEqual(rec["target"], "out.txt")
            self.assertEqual(rec["payload"], "hello")

    def test_device_executor_import_does_not_load_repository_writer_graph(self):
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, action_executor; assert 'board_ingest' not in sys.modules",
            ],
            cwd=Path(__file__).parent,
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_empty_fire_action_is_recorded_noop(self):
        rec = {
            "meta": {"id": "action-empty-0001", "from": "UNSEATED"},
            "verb": "ACTION",
            "target": "",
            "payload": "possessing the link is authorization",
        }
        result = ae.execute(rec, "github")
        self.assertTrue(result["ok"])
        self.assertEqual(result["output"], "recorded; empty fire_action is an open-door no-op")
        self.assertEqual(result["changed"], [])

    def test_scope_selection(self):
        self.assertTrue(ae.is_device_target("bryce-pc"))
        self.assertTrue(ae.is_device_target("device:phone"))
        self.assertFalse(ae.is_device_target("repo"))
        self.assertTrue(ae.is_grok_com_target("GROK.COM"))
        self.assertTrue(ae.is_grok_com_target("https://grok.com/"))
        self.assertFalse(ae.is_grok_com_target("repo"))
        self.assertTrue(ae.is_grok_executor_target("GROK.EXECUTOR"))
        self.assertFalse(ae.is_grok_executor_target("GROK.COM"))

    def test_grok_com_build_queues_durable_browser_job_instead_of_shell(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            rec = {
                "meta": {"id": "codex-grok-task-0001", "from": "CODEX"},
                "verb": "BUILD",
                "target": "GROK.COM",
                "payload": "Review current main, build the requested change, and return receipts.",
            }
            with (
                mock.patch.object(ae, "ROOT", root),
                mock.patch.object(ae, "execute_shell_payload") as shell,
            ):
                result = ae.execute(rec, "github")
            shell.assert_not_called()
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["state"], "GROK_TASK_QUEUED")
            self.assertEqual(result["job_id"], "codex-grok-task-0001")
            job_path = root / "wake_jobs" / "codex-grok-task-0001.json"
            self.assertTrue(job_path.is_file())
            job = json.loads(job_path.read_text(encoding="utf-8"))
            self.assertEqual(job["harness"], ae.GROK_COM_HARNESS)
            self.assertEqual(job["checkpoint"]["task"], rec["payload"])
            self.assertEqual(job["checkpoint"]["schema"], "commons-grok-executor-job/v1")
            self.assertEqual(job["checkpoint"]["run_key"], "grok-action-codex-grok-task-0001")
            self.assertEqual(job["checkpoint"]["origin"]["requester"], "CODEX")
            self.assertEqual(job["checkpoint"]["execution"]["submission_state"], "NOT_SUBMITTED")
            self.assertTrue(
                job["checkpoint"]["receipt_contract"]["structural_start_before_submit"]
            )
            self.assertEqual(
                job["checkpoint"]["capture_start"]["tool"],
                "start_grok_capture",
            )
            self.assertEqual(
                job["checkpoint"]["receipt_contract"]["conversation_url_prefix"],
                "https://grok.com/c/",
            )
            self.assertEqual(result["queue_schema"], "commons-grok-executor-job/v1")
            self.assertEqual(job["completion_predicate"], {"type": "result_address_on_head"})
            self.assertEqual(result["changed"], ["wake_jobs/codex-grok-task-0001.json"])
            self.assertIn("wake_jobs/codex-grok-task-0001.json", result["action_outputs"])

    def test_grok_executor_claim_command_uses_public_serialized_action_road(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            submit = {
                "meta": {"id": "grok-command-job-0001", "from": "OPEN_CALLER"},
                "verb": "BUILD",
                "target": "GROK.COM",
                "payload": "exact prompt bytes",
            }
            command = {
                "schema": ae.GROK_COMMAND_SCHEMA,
                "operation": "CLAIM",
                "job_id": "grok-command-job-0001",
                "executor_id": "healthy-executor",
            }
            claim = {
                "meta": {"id": "grok-command-claim-0001", "act": "ACTION"},
                "verb": "ACTION",
                "target": "GROK.EXECUTOR",
                "payload": json.dumps(command, sort_keys=True),
            }
            with mock.patch.object(ae, "ROOT", root):
                queued = ae.execute(submit, "github")
                result = ae.execute(claim, "github")
            self.assertEqual(queued["state"], "GROK_TASK_QUEUED")
            self.assertEqual(result["state"], "CLAIMED")
            self.assertEqual(result["operation"], "CLAIM")
            self.assertEqual(
                result["queue_result"]["capture_start"]["tool"],
                "start_grok_capture",
            )
            job = json.loads(
                (root / "wake_jobs" / "grok-command-job-0001.json").read_text(encoding="utf-8")
            )
            self.assertEqual(job["checkpoint"]["execution"]["active_executor"], "healthy-executor")

    def test_device_pending_runs_in_bulk_and_can_optionally_filter_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            posts = root / "p"
            results = root / "actions" / "results"
            posts.mkdir(parents=True)
            with (
                mock.patch.object(ae, "ROOT", root),
                mock.patch.object(ae, "POSTS", posts),
                mock.patch.object(ae, "RESULTS", results),
            ):
                self.assertEqual(ae.pending("device"), [])
            for ident in ("sol-action-1001", "sol-action-1002"):
                (posts / (ident + ".md")).write_text(
                    "from: SOL\nto: TOOLS\nid: %s\nkind: ACTION\nact: RUN\ntarget: DEVICE\n\n---\n\necho open\n" % ident,
                    encoding="utf-8",
                )
            with (
                mock.patch.object(ae, "ROOT", root),
                mock.patch.object(ae, "POSTS", posts),
                mock.patch.object(ae, "RESULTS", results),
            ):
                self.assertEqual(
                    [row["meta"]["id"] for row in ae.pending("device")],
                    ["sol-action-1001", "sol-action-1002"],
                )
                rows = ae.pending("device", "sol-action-1002")
                self.assertEqual([row["meta"]["id"] for row in rows], ["sol-action-1002"])
                with self.assertRaisesRegex(ValueError, "exact"):
                    ae.pending("device", "../not-an-id")

    def test_github_push_creates_or_replaces_and_is_exactly_manifested(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            rec = {
                "meta": {"id": "sol-action-0002", "from": "SOL"},
                "verb": "PUSH", "target": "out/x.txt", "payload": "complete file\n",
            }
            with mock.patch.object(ae, "ROOT", root):
                result = ae.execute(rec, "github")
                self.assertTrue(result["ok"])
                self.assertEqual(result["changed"], ["out/x.txt"])
                self.assertEqual(
                    result["action_outputs"]["out/x.txt"],
                    hashlib.sha256((root / "out/x.txt").read_bytes()).hexdigest(),
                )
                rec["payload"] = "replacement\n"
                result = ae.execute(rec, "github")
                self.assertTrue(result["ok"])
                self.assertEqual((root / "out/x.txt").read_text(encoding="utf-8"), "replacement\n")

    def test_github_patch_is_an_open_hashed_write_verb(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            patch = """diff --git a/open.txt b/open.txt
new file mode 100644
--- /dev/null
+++ b/open.txt
@@ -0,0 +1 @@
+open door
"""
            rec = {"meta": {"id": "sol-action-0012", "from": "SOL"},
                   "verb": "PATCH", "target": "repo", "payload": patch}
            with mock.patch.object(ae, "ROOT", root):
                result = ae.execute(rec, "github")
            self.assertTrue(result["ok"])
            self.assertIn("open.txt", result["action_outputs"])

    def test_github_download_and_open_have_public_network_egress(self):
        class Response(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            download = {"meta": {"id": "sol-action-0015", "from": "SOL"},
                        "verb": "DOWNLOAD", "target": "downloads/data.bin",
                        "payload": "https://public.example/data"}
            opened = {"meta": {"id": "sol-action-0016", "from": "SOL"},
                      "verb": "OPEN", "target": "repo",
                      "payload": "https://public.example/status"}
            with mock.patch.object(ae, "ROOT", root), mock.patch.object(
                ae.urllib.request, "urlopen", side_effect=[Response(b"bytes"), Response(b"")]
            ) as fetch:
                result = ae.execute(download, "github")
                status = ae.execute(opened, "github")
            self.assertTrue(result["ok"])
            self.assertEqual((root / "downloads/data.bin").read_bytes(), b"bytes")
            self.assertEqual(status["output"], "opened https://public.example/status: HTTP 200")
            self.assertEqual(fetch.call_count, 2)

    def test_push_can_target_every_repository_path(self):
        for target in (
            "p/new.md", "conflicts/x.jsonl", "memory/KITE.json",
            "builds/records/x.json", "actions/results/old.json", "rejects.json",
            "tos_bans.json", "action.html",
        ):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                self.init_repo(root)
                rec = {"meta": {"id": "sol-action-0003", "from": "SOL"}, "verb": "PUSH", "target": target, "payload": "payload"}
                with mock.patch.object(ae, "ROOT", root):
                    result = ae.execute(rec, "github")
                self.assertTrue(result["ok"])
                self.assertEqual((root / target).read_text(encoding="utf-8"), "payload")
                self.assertIn(target, result["action_outputs"])

    def test_push_executes_dot_git_and_outside_checkout_targets_ephemerally(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside_td:
            root, outside = Path(td), Path(outside_td) / "outside.txt"
            self.init_repo(root)
            for target, expected in ((".git/open-door.txt", root / ".git/open-door.txt"),
                                     (str(outside), outside)):
                with self.subTest(target=target), mock.patch.object(ae, "ROOT", root):
                    result = ae.execute({
                        "meta": {"id": "sol-action-outside-0001"}, "verb": "PUSH",
                        "target": target, "payload": "executed",
                    }, "github")
                self.assertTrue(result["ok"])
                self.assertEqual(expected.read_text(encoding="utf-8"), "executed")
                self.assertEqual(result["changed"], [])

    def test_push_can_rewrite_action_pad_and_publisher_paths(self):
        for target in (
            "action_executor.py", "action_land.py", "board_ingest.py",
            "memory_board.py", "capability_declaration.py", ".capability-declaration-live",
            ".github/workflows/commons-action-executor.yml",
        ):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                self.init_repo(root)
                rec = {
                    "meta": {"id": "sol-action-0009", "from": "SOL"},
                    "verb": "PUSH", "target": target, "payload": "open door",
                }
                with mock.patch.object(ae, "ROOT", root):
                    result = ae.execute(rec, "github")
                self.assertTrue(result["ok"])
                self.assertEqual((root / target).read_text(encoding="utf-8"), "open door")

    def test_patch_can_target_post(self):
        patch = """diff --git a/p/new.md b/p/new.md
new file mode 100644
--- /dev/null
+++ b/p/new.md
@@ -0,0 +1 @@
+open
"""
        rec = {"meta": {"id": "sol-action-0004", "from": "SOL"}, "verb": "PATCH", "target": "repo", "payload": patch}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            with mock.patch.object(ae, "ROOT", root):
                result = ae.execute(rec, "github")
            self.assertTrue(result["ok"])
            self.assertEqual((root / "p" / "new.md").read_text(encoding="utf-8"), "open\n")
            self.assertIn("p/new.md", result["action_outputs"])

    def test_github_run_and_build_execute_payload_through_shell(self):
        for verb in ("RUN", "BUILD"):
            with self.subTest(verb=verb), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                self.init_repo(root)
                script = root / "make_output.py"
                script.write_text(
                    "from pathlib import Path\nimport sys\n"
                    "Path('built.txt').write_text('|'.join(sys.argv[1:]), encoding='utf-8')\n",
                    encoding="utf-8",
                )
                subprocess.run(["git", "add", "make_output.py"], cwd=root, check=True)
                subprocess.run(["git", "commit", "-qm", "script"], cwd=root, check=True)
                rec = {
                    "meta": {"id": "sol-action-0005", "from": "SOL"},
                    "verb": verb, "target": "repo",
                    "payload": f'{PYTHON_SHELL} make_output.py alpha "two words"',
                }
                with mock.patch.object(ae, "ROOT", root):
                    result = ae.execute(rec, "github")
                self.assertTrue(result["ok"])
                self.assertEqual((root / "built.txt").read_text(encoding="utf-8"), "alpha|two words")
                self.assertEqual(set(result["action_outputs"]), {"built.txt"})

    def test_github_run_allows_inline_commands_and_action_door_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            rec = {"meta": {"id": "sol-action-0013", "from": "SOL"},
                   "verb": "RUN", "target": "repo",
                   "payload": f'{PYTHON_SHELL} -c "from pathlib import Path; Path(\'inline.txt\').write_text(\'open\')"'}
            with mock.patch.object(ae, "ROOT", root):
                result = ae.execute(rec, "github")
            self.assertTrue(result["ok"])
            self.assertIn("inline.txt", result["action_outputs"])
            script = root / "touch_door.py"
            script.write_text("from pathlib import Path\nPath('action.html').write_text('no')\n", encoding="utf-8")
            subprocess.run(["git", "add", "touch_door.py"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "bad script"], cwd=root, check=True)
            rec = {"meta": {"id": "sol-action-0014", "from": "SOL"},
                   "verb": "RUN", "target": "repo", "payload": f'{PYTHON_SHELL} touch_door.py'}
            with mock.patch.object(ae, "ROOT", root):
                result = ae.execute(rec, "github")
            self.assertTrue(result["ok"])
            self.assertEqual((root / "action.html").read_text(encoding="utf-8"), "no")
            self.assertIn("action.html", result["action_outputs"])

    def test_github_run_carries_an_ordinary_deletion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            old = root / "ordinary-old.txt"
            old.write_text("old\n", encoding="utf-8")
            subprocess.run(["git", "add", "ordinary-old.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "ordinary"], cwd=root, check=True)
            rec = {"meta": {"id": "sol-action-0017", "from": "SOL"},
                   "verb": "RUN", "target": "repo",
                   "payload": f'{PYTHON_SHELL} -c "from pathlib import Path; Path(\'ordinary-old.txt\').unlink()"'}
            with mock.patch.object(ae, "ROOT", root):
                result = ae.execute(rec, "github")
            self.assertTrue(result["ok"])
            self.assertEqual(result["action_deletions"], ["ordinary-old.txt"])
            self.assertEqual(result["changed"], ["ordinary-old.txt"])

    def test_arbitrary_free_text_verb_executes_payload_without_preflight(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            rec = {
                "meta": {"id": "sol-action-0018"},
                "verb": "COMPUTE WHATEVER THE PAYLOAD SAYS",
                "target": "",
                "payload": f'{PYTHON_SHELL} -c "from pathlib import Path; Path(\'free-form.txt\').write_text(\'executed\')"',
            }
            with mock.patch.object(ae, "ROOT", root):
                result = ae.execute(rec, "github")
            self.assertTrue(result["ok"])
            self.assertEqual((root / "free-form.txt").read_text(encoding="utf-8"), "executed")
            self.assertIn("free-form.txt", result["action_outputs"])

    def test_post_runs_through_canonical_writer_and_hashes_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            posts = root / "p"
            posts.mkdir()
            results = root / "actions" / "results"
            rec = {
                "meta": {
                    "id": "sol-action-0006", "from": "SOL", "is_language_model": "YES",
                    "model": "model-x", "harness": "harness-y", "tools": "git, shell",
                    "resources": "Commons repo, workspace",
                    "reasoning_mode": "LATENT", "speech": "Run the request.",
                    "model_protocol": "CML/1", "model_codec": "json",
                    "model_packet": '{"k":"RESULT","ops":[],"v":1}',
                    "payload_kind": "action", "payload_sha256": "0" * 64,
                    "language_state": "LAYERED",
                },
                "verb": "POST", "target": "TABLE", "payload": "open",
            }

            def writer(src, dest, ident, body, **kwargs):
                text = "---\nfrom: %s\nto: %s\nid: %s\n---\n%s\n" % (src, dest, ident, body)
                (posts / (ident + ".md")).write_text(text, encoding="utf-8")
                (posts / (ident + ".html")).write_text("<p>open</p>\n", encoding="utf-8")
                return "wrote"

            with (
                mock.patch.object(ae, "ROOT", root),
                mock.patch.object(ae, "POSTS", posts),
                mock.patch.object(ae, "RESULTS", results),
                mock.patch.object(ae.board_ingest, "ROOT", str(root)),
                mock.patch.object(ae.board_ingest, "POSTS", str(posts)),
                mock.patch.object(ae.board_ingest, "write_post", side_effect=writer) as called,
            ):
                result = ae.execute(rec, "github")
            self.assertTrue(result["ok"])
            called.assert_called_once()
            sent_extra = called.call_args.kwargs["extra"]
            self.assertEqual(sent_extra["is_language_model"], "YES")
            self.assertEqual(sent_extra["tools"], "git, shell")
            self.assertEqual(sent_extra["resources"], "Commons repo, workspace")
            self.assertEqual(sent_extra["kind"], "ACTION")
            for key in (
                "reasoning_mode", "speech", "model_protocol", "model_codec",
                "model_packet", "payload_kind", "payload_sha256", "language_state",
            ):
                self.assertNotIn(key, sent_extra)
            self.assertEqual(set(result["changed"]), {"p/sol-action-0006-post.md", "p/sol-action-0006-post.html"})
            for name, digest in result["canonical_records"].items():
                self.assertEqual(digest, hashlib.sha256((root / name).read_bytes()).hexdigest())

    def test_post_real_writer_bypasses_declaration_and_memory_gates(self):
        """Action Pad POST output remains open even when chat gates are live."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            posts = root / "p"
            posts.mkdir()
            by = root / "by"
            to = root / "to"
            results = root / "actions" / "results"
            (root / ".capability-declaration-live").write_text("1\n", encoding="utf-8")

            yes = {
                "id": "sol-action-capability-yes", "from": "SOL",
                "is_language_model": "YES", "model": "model-x",
                "harness": "harness-y", "tools": "git, shell",
                "resources": "Commons repo, workspace",
            }
            no = {
                "id": "sol-action-capability-no", "from": "SOL",
                "is_language_model": "NO",
            }
            missing = {"id": "sol-action-capability-missing", "from": "SOL"}

            with (
                mock.patch.object(ae, "ROOT", root),
                mock.patch.object(ae, "POSTS", posts),
                mock.patch.object(ae, "RESULTS", results),
                mock.patch.object(ae.board_ingest, "ROOT", str(root)),
                mock.patch.object(ae.board_ingest, "POSTS", str(posts)),
                mock.patch.object(ae.board_ingest, "BY", str(by)),
                mock.patch.object(ae.board_ingest, "TO", str(to)),
            ):
                yes_result = ae.execute(
                    {"meta": yes, "verb": "POST", "target": "TABLE", "payload": "declared YES output"},
                    "github",
                )
                no_result = ae.execute(
                    {"meta": no, "verb": "POST", "target": "TABLE", "payload": "declared NO output"},
                    "github",
                )
                missing_result = ae.execute(
                    {"meta": missing, "verb": "POST", "target": "TABLE", "payload": "undeclared output"},
                    "github",
                )

            self.assertTrue(yes_result["ok"], yes_result)
            self.assertTrue(no_result["ok"], no_result)
            self.assertTrue(missing_result["ok"], missing_result)
            yes_meta, _ = ae.board_ingest.parse_post(
                (posts / "sol-action-capability-yes-post.md").read_text(encoding="utf-8")
            )
            no_meta, _ = ae.board_ingest.parse_post(
                (posts / "sol-action-capability-no-post.md").read_text(encoding="utf-8")
            )
            self.assertEqual(yes_meta["is_language_model"], "YES")
            self.assertEqual(yes_meta["resources"], "Commons repo, workspace")
            self.assertEqual(no_meta["is_language_model"], "NO")
            missing_meta, missing_body = ae.board_ingest.parse_post(
                (posts / "sol-action-capability-missing-post.md").read_text(encoding="utf-8")
            )
            self.assertEqual(missing_meta["from"], "SOL")
            self.assertEqual(missing_meta["kind"], "ACTION")
            self.assertEqual(missing_body, "undeclared output")

    def test_post_existing_exact_output_latches_without_conflict_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            posts = root / "p"
            posts.mkdir()
            results = root / "actions" / "results"
            existing = posts / "sol-action-replay-post.md"
            existing.write_text(
                "---\n"
                "from: SOL\n"
                "to: TABLE\n"
                "id: sol-action-replay-post\n"
                "subject: ACTION OUTPUT sol-action-replay\n"
                "kind: ACTION\n"
                "is_language_model: YES\n"
                "model: model-x\n"
                "harness: harness-y\n"
                "tools: git, shell\n"
                "resources: Commons repo, workspace\n"
                "---\n"
                "same output\n",
                encoding="utf-8",
            )
            rec = {
                "meta": {
                    "id": "sol-action-replay", "from": "SOL", "is_language_model": "YES",
                    "model": "model-x", "harness": "harness-y", "tools": "git, shell",
                    "resources": "Commons repo, workspace",
                },
                "verb": "POST", "target": "TABLE", "payload": "same output",
            }
            with (
                mock.patch.object(ae, "ROOT", root),
                mock.patch.object(ae, "POSTS", posts),
                mock.patch.object(ae, "RESULTS", results),
                mock.patch.object(ae.board_ingest, "ROOT", str(root)),
                mock.patch.object(ae.board_ingest, "POSTS", str(posts)),
                mock.patch.object(ae.board_ingest, "write_post") as writer,
            ):
                result = ae.execute(rec, "github")
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["write"], "exists")
            self.assertEqual(result["changed"], [])
            self.assertEqual(result["canonical_records"], {})
            writer.assert_not_called()
            self.assertFalse((root / "rejects.json").exists())
            self.assertFalse((root / "conflicts").exists())

    def test_main_recovers_missing_result_latch_from_exact_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            posts = root / "p"
            posts.mkdir()
            results = root / "actions" / "results"
            (posts / "sol-action-replay.md").write_text(
                "from: SOL\n"
                "to: TABLE\n"
                "id: sol-action-replay\n"
                "kind: ACTION\n"
                "act: POST\n"
                "target: TABLE\n"
                "is_language_model: YES\n"
                "model: model-x\n"
                "harness: harness-y\n"
                "tools: git, shell\n"
                "resources: Commons repo, workspace\n"
                "\n---\n\n"
                "same output\n",
                encoding="utf-8",
            )
            (posts / "sol-action-replay-post.md").write_text(
                "---\n"
                "from: SOL\n"
                "to: TABLE\n"
                "id: sol-action-replay-post\n"
                "subject: ACTION OUTPUT sol-action-replay\n"
                "kind: ACTION\n"
                "is_language_model: YES\n"
                "model: model-x\n"
                "harness: harness-y\n"
                "tools: git, shell\n"
                "resources: Commons repo, workspace\n"
                "---\n"
                "same output\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with (
                mock.patch.object(ae, "ROOT", root),
                mock.patch.object(ae, "POSTS", posts),
                mock.patch.object(ae, "RESULTS", results),
                mock.patch.object(ae.board_ingest, "ROOT", str(root)),
                mock.patch.object(ae.board_ingest, "POSTS", str(posts)),
                mock.patch.object(ae.board_ingest, "write_post") as writer,
                mock.patch("sys.argv", ["action_executor.py", "--scope", "github"]),
                mock.patch("sys.stdout", stdout),
            ):
                self.assertEqual(ae.main(), 0)
            writer.assert_not_called()
            latch = results / "sol-action-replay.json"
            self.assertTrue(latch.is_file())
            result = json.loads(latch.read_text(encoding="utf-8"))
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["write"], "exists")
            manifest = json.loads(stdout.getvalue())
            self.assertEqual(manifest["changed"], ["actions/results/sol-action-replay.json"])
            self.assertEqual(
                set(manifest["result_records"]),
                {"actions/results/sol-action-replay.json"},
            )
            self.assertFalse((root / "rejects.json").exists())
            self.assertFalse((root / "conflicts").exists())

    def test_post_defaults_optional_sender_and_target_without_declaration(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            posts = root / "p"
            posts.mkdir()

            def writer(src, dest, ident, body, **kwargs):
                text = "---\nfrom: %s\nto: %s\nid: %s\nkind: ACTION\n---\n%s\n" % (src, dest, ident, body)
                (posts / (ident + ".md")).write_text(text, encoding="utf-8")
                return "wrote"

            with (
                mock.patch.object(ae, "ROOT", root),
                mock.patch.object(ae, "POSTS", posts),
                mock.patch.object(ae.board_ingest, "ROOT", str(root)),
                mock.patch.object(ae.board_ingest, "POSTS", str(posts)),
                mock.patch.object(ae.board_ingest, "write_post", side_effect=writer) as called,
            ):
                result = ae.execute(
                    {"meta": {"id": "sol-action-0007"}, "verb": "POST", "target": "", "payload": "open"},
                    "github",
                )
            self.assertTrue(result["ok"])
            self.assertEqual(called.call_args.args[:2], ("UNSEATED", "TABLE"))
            self.assertEqual(called.call_args.kwargs["extra"]["kind"], "ACTION")
            self.assertTrue((posts / "sol-action-0007-post.md").exists())

    def test_action_land_requires_exact_hash_and_accepts_writer_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            post = root / "p" / "new-post.md"
            post.parent.mkdir()
            post.write_text("record\n", encoding="utf-8")
            digest = hashlib.sha256(post.read_bytes()).hexdigest()
            with mock.patch.object(al, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "path/hash mismatch"):
                    al.validate_manifest({"changed": ["p/new-post.md"]})
                paths = al.validate_manifest({
                    "changed": ["p/new-post.md"],
                    "canonical_records": {"p/new-post.md": digest},
                    "result_records": {},
                })
            self.assertEqual(paths, ["p/new-post.md"])

            projection = root / "players" / "new-post.html"
            projection.parent.mkdir()
            projection.write_text("projection\n", encoding="utf-8")
            projection_digest = hashlib.sha256(projection.read_bytes()).hexdigest()
            with mock.patch.object(al, "ROOT", root):
                self.assertEqual(al.validate_manifest({
                    "changed": ["players/new-post.html"],
                    "canonical_records": {"players/new-post.html": projection_digest},
                }), ["players/new-post.html"])

    def test_action_land_requires_hashed_result_latch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            result = root / "actions" / "results" / "sol-action-0008.json"
            result.parent.mkdir(parents=True)
            result.write_text(json.dumps({"ok": True}) + "\n", encoding="utf-8")
            digest = hashlib.sha256(result.read_bytes()).hexdigest()
            with mock.patch.object(al, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "path/hash mismatch"):
                    al.validate_manifest({"changed": ["actions/results/sol-action-0008.json"]})
                self.assertEqual(
                    al.validate_manifest({
                        "changed": ["actions/results/sol-action-0008.json"],
                        "result_records": {"actions/results/sol-action-0008.json": digest},
                    }),
                    ["actions/results/sol-action-0008.json"],
                )

    def test_action_land_rejects_every_unmanifested_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            output = root / "ordinary.txt"
            output.write_text("not a canonical producer\n", encoding="utf-8")
            with mock.patch.object(al, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "path/hash mismatch"):
                    al.validate_manifest({"changed": ["ordinary.txt"]})

    def test_action_land_accepts_exact_ordinary_and_action_door_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            ordinary = root / "ordinary.txt"
            ordinary.write_text("land me\n", encoding="utf-8")
            digest = hashlib.sha256(ordinary.read_bytes()).hexdigest()
            with mock.patch.object(al, "ROOT", root):
                self.assertEqual(
                    al.validate_manifest({
                        "changed": ["ordinary.txt"],
                        "action_outputs": {"ordinary.txt": digest},
                    }),
                    ["ordinary.txt"],
                )
                door = root / "action.html"
                door.write_text("replace door\n", encoding="utf-8")
                door_digest = hashlib.sha256(door.read_bytes()).hexdigest()
                self.assertEqual(
                    al.validate_manifest({
                        "changed": ["action.html"],
                        "action_outputs": {"action.html": door_digest},
                    }),
                    ["action.html"],
                )

    def test_action_land_carries_any_repository_deletion_exactly(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as sd:
            root, source = Path(td), Path(sd)
            self.init_repo(root)
            old = root / "action.html"
            old.write_text("remove me\n", encoding="utf-8")
            subprocess.run(["git", "add", "action.html"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "old"], cwd=root, check=True)
            manifest = {"changed": ["action.html"], "action_deletions": ["action.html"]}
            with mock.patch.object(al, "ROOT", root):
                paths = al.validate_manifest(manifest, source)
                al.materialize(source, paths, {"action.html"})
            self.assertFalse(old.exists())

    def test_action_land_keeps_unaddressable_and_nonfile_effects_as_receipts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.init_repo(root)
            directory = root / "ordinary-directory"
            directory.mkdir()
            metadata = root / ".git" / "config"
            metadata_digest = hashlib.sha256(metadata.read_bytes()).hexdigest()
            outside = str(root.parent / "outside-effect.txt").replace("\\", "/")
            manifest = {
                "changed": [outside, "../traversing-effect.txt", ".git/config", "ordinary-directory"],
                "action_outputs": {
                    outside: "0" * 64,
                    "../traversing-effect.txt": "1" * 64,
                    ".git/config": metadata_digest,
                    "ordinary-directory": "2" * 64,
                },
            }
            with mock.patch.object(al, "ROOT", root):
                paths = al.validate_manifest(manifest, root)
                landed = al.materialize(root, paths, set())
            self.assertEqual(paths, manifest["changed"])
            self.assertEqual(landed, [])

    def make_remote_pair(self, td):
        origin = Path(td) / "origin.git"
        work = Path(td) / "work"
        subprocess.run(["git", "init", "--bare", "-q", "-b", "main", str(origin)], check=True)
        subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
        subprocess.run(["git", "config", "user.email", "commons-action@users.noreply.github.com"], cwd=work, check=True)
        subprocess.run(["git", "config", "user.name", "commons-action"], cwd=work, check=True)
        (work / "seed.txt").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "add", "seed.txt"], cwd=work, check=True)
        subprocess.run(["git", "commit", "-qm", "seed"], cwd=work, check=True)
        subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work, check=True)
        return origin, work

    def write_action_source(self, source: Path, files: dict):
        records = {}
        changed = []
        for name, body in files.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
            records[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            changed.append(name)
        (source / ".action_changed.json").write_text(
            json.dumps({
                "changed": changed,
                "canonical_records": {},
                "action_outputs": {},
                "action_deletions": [],
                "result_records": records,
            }) + "\n",
            encoding="utf-8",
        )

    def origin_blob(self, origin: Path, name: str) -> str:
        shown = subprocess.run(
            ["git", "show", "main:%s" % name],
            cwd=origin,
            text=True,
            capture_output=True,
            check=True,
        )
        return shown.stdout

    def test_action_land_run_33223581414_dedupes_result_remints(self):
        """Run 33223581414 re-fired two already-latched result ids with later executed_at.

        Cite: woahwhattheheck/commons:commons-action-executor:05290b210bd7105e7c2a9970297776268a24d3ed:verify exact outputs on a fresh runner and land
        """
        ingress = "actions/results/grok-slack-immediate-ingress-repair-20260828-01.json"
        observe = "actions/results/grok-slack-observe-win-git-20260828-01.json"
        original_ingress = (
            '{\n  "id": "grok-slack-immediate-ingress-repair-20260828-01",\n'
            '  "ok": true,\n  "state": "DUPLICATE",\n'
            '  "executed_at": "2026-08-29T00:27:17Z"\n}\n'
        )
        remint_ingress = original_ingress.replace("2026-08-29T00:27:17Z", "2026-08-29T00:31:29Z")
        original_observe = (
            '{\n  "id": "grok-slack-observe-win-git-20260828-01",\n'
            '  "ok": false,\n  "executed_at": "2026-08-29T00:27:18.821158Z"\n}\n'
        )
        remint_observe = original_observe.replace(
            "2026-08-29T00:27:18.821158Z",
            "2026-08-29T00:31:30.625125Z",
        )
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as sd:
            origin, work = self.make_remote_pair(td)
            for name, body in ((ingress, original_ingress), (observe, original_observe)):
                path = work / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding="utf-8")
            subprocess.run(["git", "add", "--", ingress, observe], cwd=work, check=True)
            subprocess.run(["git", "commit", "-qm", "fire addressed Commons actions"], cwd=work, check=True)
            subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work, check=True)
            subprocess.run(["git", "reset", "--hard", "-q", "HEAD~1"], cwd=work, check=True)
            source = Path(sd)
            self.write_action_source(source, {ingress: remint_ingress, observe: remint_observe})
            with mock.patch.object(al, "ROOT", work), mock.patch.object(al.time, "sleep"):
                code = al.land_from_source(source)
            self.assertEqual(code, 0)
            self.assertEqual(self.origin_blob(origin, ingress), original_ingress)
            self.assertEqual(self.origin_blob(origin, observe), original_observe)
            self.assertNotIn("2026-08-29T00:31:29Z", self.origin_blob(origin, ingress))

    def test_action_land_lands_unique_result_and_drops_remint(self):
        remint_path = "actions/results/grok-slack-immediate-ingress-repair-20260828-01.json"
        unique_path = "actions/results/grok-slack-pending-shape-probe-20260828-01.json"
        original = (
            '{\n  "id": "grok-slack-immediate-ingress-repair-20260828-01",\n'
            '  "executed_at": "2026-08-29T00:27:17Z"\n}\n'
        )
        remint = original.replace("2026-08-29T00:27:17Z", "2026-08-29T00:31:29Z")
        unique = '{\n  "id": "grok-slack-pending-shape-probe-20260828-01",\n  "ok": true\n}\n'
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as sd:
            origin, work = self.make_remote_pair(td)
            path = work / remint_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(original, encoding="utf-8")
            subprocess.run(["git", "add", "--", remint_path], cwd=work, check=True)
            subprocess.run(["git", "commit", "-qm", "latch original"], cwd=work, check=True)
            subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work, check=True)
            subprocess.run(["git", "reset", "--hard", "-q", "HEAD~1"], cwd=work, check=True)
            source = Path(sd)
            self.write_action_source(source, {remint_path: remint, unique_path: unique})
            with mock.patch.object(al, "ROOT", work), mock.patch.object(al.time, "sleep"):
                code = al.land_from_source(source)
            self.assertEqual(code, 0)
            self.assertEqual(self.origin_blob(origin, remint_path), original)
            self.assertEqual(self.origin_blob(origin, unique_path), unique)

    def test_action_land_rebase_conflict_keeps_original_result_latch(self):
        name = "actions/results/grok-slack-immediate-ingress-repair-20260828-01.json"
        original = (
            '{\n  "id": "grok-slack-immediate-ingress-repair-20260828-01",\n'
            '  "executed_at": "2026-08-29T00:27:17Z"\n}\n'
        )
        remint = original.replace("2026-08-29T00:27:17Z", "2026-08-29T00:31:29Z")
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as sd:
            origin, work = self.make_remote_pair(td)
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(original, encoding="utf-8")
            subprocess.run(["git", "add", "--", name], cwd=work, check=True)
            subprocess.run(["git", "commit", "-qm", "latch original"], cwd=work, check=True)
            subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=work, check=True)
            subprocess.run(["git", "reset", "--hard", "-q", "HEAD~1"], cwd=work, check=True)
            source = Path(sd)
            self.write_action_source(source, {name: remint})

            def keep_remint(paths, deletions):
                del deletions
                return list(paths), []

            with (
                mock.patch.object(al, "ROOT", work),
                mock.patch.object(al.time, "sleep"),
                mock.patch.object(al, "drop_already_latched", side_effect=keep_remint),
            ):
                code = al.land_from_source(source)
            self.assertEqual(code, 0)
            self.assertEqual(self.origin_blob(origin, name), original)
            with self.assertRaisesRegex(RuntimeError, "force-push is forbidden"):
                al.git("push", "--force", "origin", "HEAD:main")

    def test_device_actions_reserve_automatically_without_a_reviewed_id(self):
        executor = Path(__file__).with_name("action_executor.py").read_text(encoding="utf-8")
        workflow = (Path(__file__).parent / ".github/workflows/commons-device-executor.yml").read_text(encoding="utf-8")
        self.assertNotIn("device execution requires --only-id", executor)
        self.assertNotIn("unsigned board actions", executor)
        self.assertNotIn("workflow_run:", workflow)
        self.assertIn("workflow_call:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("device_action_state.py preflight", workflow)
        self.assertIn("uses: ./.github/workflows/commons-device-cycle.yml", workflow)
        self.assertNotIn("reviewed Commons action id", workflow)
        self.assertNotIn("--only-id", workflow)
        self.assertIn("unbound device execution is disabled", executor)

    def test_parse_record_normalizes_windows_relative_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            action = root / "p" / "windows-device-action-0001.md"
            action.parent.mkdir()
            action.write_text(
                "from: GPT\nto: TOOLS\nid: windows-device-action-0001\n"
                "kind: ACTION\nact: RUN\ntarget: DEVICE\n\n---\n\n"
                "RUN\ntarget: DEVICE\n\necho safe\n",
                encoding="utf-8",
            )
            windows_rel = Path("p\\windows-device-action-0001.md")
            with (
                mock.patch.object(ae, "ROOT", root),
                mock.patch.object(type(action), "relative_to", return_value=windows_rel),
            ):
                rec = ae.parse_record(action)
            self.assertEqual(rec["path"], "p/windows-device-action-0001.md")

    def test_device_workflow_gates_the_self_hosted_runner_on_current_main_pending_work(self):
        workflow = (Path(__file__).parent / ".github/workflows/commons-device-executor.yml").read_text(encoding="utf-8")
        cycle_workflow = (Path(__file__).parent / ".github/workflows/commons-device-cycle.yml").read_text(encoding="utf-8")
        prefix, jobs = workflow.split("jobs:\n", 1)
        preflight, cycle = jobs.split("  cycle:\n", 1)

        self.assertNotIn("concurrency:", prefix)
        self.assertNotIn("workflow_run:", prefix)
        self.assertIn("workflow_call:", prefix)
        self.assertIn("workflow_dispatch:", prefix)
        self.assertIn("permissions:\n  contents: read", prefix)

        self.assertIn("  preflight:\n", "jobs:\n" + preflight)
        self.assertIn("runs-on: ubuntu-latest", preflight)
        self.assertNotIn("self-hosted", preflight)
        self.assertIn("device_action_state.py preflight", preflight)
        self.assertIn("has_pending: ${{ steps.pending.outputs.has_pending }}", preflight)
        self.assertIn('"$GITHUB_OUTPUT"', preflight)
        self.assertNotIn("github.event.workflow_run", preflight)

        self.assertIn("needs: preflight", cycle)
        self.assertIn("if: needs.preflight.outputs.has_pending == 'true'", cycle)
        self.assertIn("uses: ./.github/workflows/commons-device-cycle.yml", cycle)
        self.assertIn("concurrency:\n      group: commons-device-executor\n      cancel-in-progress: false\n      queue: single", cycle)
        self.assertNotIn("queue: max", cycle)
        self.assertNotIn("runs-on:", cycle)
        self.assertNotIn("secrets: inherit", cycle)
        self.assertEqual(workflow.count("ref: main"), 1)
        self.assertEqual(workflow.count("fetch-depth: 0"), 1)

        self.assertIn("on:\n  workflow_call:", cycle_workflow)
        self.assertEqual(cycle_workflow.count("runs-on: [self-hosted, commons-device]"), 1)
        self.assertIn("ref: ${{ needs.prepare.outputs.prepared_commit }}", cycle_workflow)
        self.assertIn("device_action_state.py execute-batch", cycle_workflow)
        self.assertNotIn("matrix:", cycle_workflow)
        self.assertNotIn("max-parallel:", cycle_workflow)
        execute_job = cycle_workflow.partition("\n  execute:\n")[2].partition("\n  finalize:\n")[0]
        self.assertEqual(execute_job.count("    timeout-minutes: 260\n"), 1)
        execute_step = cycle_workflow.partition("execute the prepared batch in sorted order")[2].partition("- uses: actions/upload-artifact")[0]
        self.assertNotIn("\\\n", execute_step)
        self.assertIn("run: >-", execute_step)
        self.assertNotIn("${{ github.workflow_ref }}", execute_step)
        self.assertNotIn("--workflow-ref", execute_step)
        self.assertIn("retention-days: 7", cycle_workflow)
        self.assertIn("name: commons-device-receipts-${{ github.run_id }}-${{ github.run_attempt }}", cycle_workflow)
        self.assertIn("path: ${{ runner.temp }}/device-receipts", cycle_workflow)
        upload_step = cycle_workflow.partition("- uses: actions/upload-artifact")[2].partition("\n\n  finalize:")[0]
        self.assertNotRegex(upload_step, r"(?m)^\s+if\s*:")
        finalize_job = cycle_workflow.partition("\n  finalize:\n")[2]
        self.assertEqual(
            finalize_job.count(
                "    if: ${{ always() && needs.prepare.result == 'success' && "
                "needs.execute.result == 'success' && "
                "needs.prepare.outputs.reservation_count != '0' }}\n"
            ),
            1,
        )
        self.assertNotIn("action_executor.py --scope device", cycle_workflow)
        self.assertIn("persist-credentials: false", cycle_workflow)
        self.assertIn("permissions:\n      contents: read", cycle_workflow)
        self.assertIn("permissions:\n      contents: write", cycle_workflow)
        self.assertIn("always() && needs.prepare.result == 'success'", cycle_workflow)
        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", cycle_workflow)
        self.assertIn("actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093", cycle_workflow)
        self.assertNotRegex(cycle_workflow, r"uses: actions/(?:checkout|upload-artifact|download-artifact)@v\d")
        self.assertNotIn("action_land.py", cycle_workflow)
        self.assertNotIn("secrets: inherit", cycle_workflow)

    def test_action_html_parses_and_one_click_author_fire_keeps_shared_link_explicit(self):
        html = Path(__file__).with_name("action.html").read_text(encoding="utf-8")
        script = html.partition("<script>")[2].partition("</script>")[0]
        proc = subprocess.run(
            ["node", "-e", "new Function(process.argv[1])", script],
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("fire.click()", script)
        self.assertIn("fireAction(a,document.getElementById", script)
        self.assertIn("GENERATE ADDRESS + FIRE", html)
        self.assertIn('<input id="verb" name="verb"', html)
        self.assertIn('name="verb" value="ACTION"', html)
        self.assertNotIn('name="verb" value="ACTION" placeholder="ACTION" required', html)
        self.assertIn('(form.elements.verb.value.trim()||"ACTION")', script)
        self.assertIn("if(!a.payload)", script)
        self.assertNotIn('<select id="verb"', html)
        self.assertIn('<input id="circuit" name="circuit"', html)
        self.assertNotIn('name="circuit" required', html)
        self.assertNotIn('id="circuit" name="circuit" required', html)
        self.assertIn("A circuit is additive", html)
        self.assertIn("---STEP---", html)
        self.assertIn("Any other nonblank verb runs this payload", html)
        self.assertIn("bryce-action-pad-open-door-directive-20260822-01", html)
        self.assertIn("Possessing the link is sufficient authorization", html)
        self.assertIn("THE LINK AUTHORIZES USE", html)
        self.assertNotIn('id="chat-declaration"', html)
        self.assertNotIn('id="from" name="from" maxlength="32" placeholder="CODEX_SOL" required', html)
        self.assertNotIn('id="target" name="target" placeholder="TABLE, parent-id, new/repo/file.txt, or repo" required', html)
        self.assertIn("ground/ACTION_DOOR.md", html)
        self.assertNotIn("Confirmation has already been received", html)
        self.assertNotIn("Bryce created or requested", html)

    def test_action_workflow_separates_unprivileged_execution_from_fresh_landing(self):
        workflow = (Path(__file__).parent / ".github/workflows/commons-action-executor.yml").read_text(encoding="utf-8")
        board = (Path(__file__).parent / ".github/workflows/commons-board.yml").read_text(encoding="utf-8")
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("permissions:\n      contents: read", workflow)
        self.assertIn("permissions:\n      contents: write", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("actions/download-artifact@v4", workflow)
        self.assertIn('action_land.py --source', workflow)
        self.assertIn("fire every nonblank Action Pad verb", workflow)
        self.assertIn(".action_receipt_only.json", workflow)
        self.assertIn("executed; no Git artifact address", workflow)
        self.assertNotIn("raise SystemExit", workflow)
        self.assertNotIn("unsafe manifest path", workflow)
        self.assertNotIn("manifest path escapes checkout", workflow)
        self.assertNotIn("manifest path is not a regular file", workflow)
        self.assertNotIn('muhlnickel_spec_guard.py', Path(__file__).with_name('action_land.py').read_text(encoding='utf-8'))
        self.assertNotIn("action_executor.py --scope github", board)
        self.assertIn("device_action_state.py preflight", board)
        self.assertIn("has_pending_device", board)
        self.assertNotIn("uses: ./.github/workflows/commons-device-executor.yml", board)
        self.assertIn("runs-on: ubuntu-24.04-arm", board)
        self.assertIn("does not allocate the owner's self-hosted laptop runner", board)
        self.assertIn("needs.ingest.outputs.has_pending_device == 'true'", board)


if __name__ == "__main__":
    unittest.main()
