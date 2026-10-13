from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from host.titan_hands.broker import TitanHandsBroker
from host.titan_hands.linux_atspi import LinuxBackendError, LinuxHandsServer, UnconfiguredAtspi
from host.titan_hands.mcp_one import dispatch as dispatch_one
from host.titan_hands.one_tool import TitanHandsOne
from host.titan_hands.routes import HandsRoutes
from host.titan_hands.runtime import TitanHandsRuntime
from host.titan_hands.tests.test_linux_atspi import FakeAtspi


class FakeServer:
    def __init__(self, platform):
        self.platform = platform
        self.closed = False
        self.calls = []

    def handle(self, request):
        self.calls.append(dict(request))
        if request.get("op") == "capabilities":
            return {"ok": True, "kind": "capabilities", "platform": self.platform}
        if request.get("op") == "observe":
            return {"ok": True, "kind": "observation_delta", "platform": self.platform, "full": True}
        if request.get("op") == "act":
            return {
                "ok": True,
                "kind": "action_outcome",
                "platform": self.platform,
                "action": request["action"]["type"],
            }
        if request.get("op") == "capture":
            return {"ok": True, "kind": "pixel_capture", "platform": self.platform, "pixel_ref": "shot.png"}
        return {"ok": True, "kind": request["op"], "platform": self.platform}

    def close(self):
        self.closed = True


class FakeHttp:
    def __init__(self):
        self.calls = []
        self.response = {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"ok": True, "ts": "111.222", "messages": []}).encode("utf-8"),
            "error": "",
        }

    def __call__(self, method, url, headers=None, body=None, timeout=30):
        self.calls.append(
            {"method": method, "url": url, "headers": dict(headers or {}), "body": body, "timeout": timeout}
        )
        return dict(self.response)


def init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "hands@example.test"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Titan Hands"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=path, check=True, capture_output=True)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        init_repo(self.root)
        self.windows = FakeServer("windows")
        self.android = FakeServer("android")
        self.http = FakeHttp()
        self.runtime = TitanHandsRuntime(
            broker=TitanHandsBroker(
                factories={"windows": lambda: self.windows, "android": lambda: self.android}
            ),
            routes=HandsRoutes(repo_root=self.root, http=self.http, environ={}),
            linux=LinuxHandsServer(backend=FakeAtspi()),
        )

    def tearDown(self):
        self.runtime.close()
        self.tmp.cleanup()

    def test_primary_tool_is_hands_and_titan_hands_alias_still_calls(self):
        router = TitanHandsOne(factories={"windows": lambda: self.windows})
        self.addCleanup(router.close)
        listed = dispatch_one(router, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [tool["name"] for tool in listed["result"]["tools"]]
        self.assertEqual(names, ["hands"])
        called = dispatch_one(
            router,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "titan_hands", "arguments": {"op": "observe", "target": "windows"}},
            },
        )
        payload = json.loads(called["result"]["content"][0]["text"])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["platform"], "windows")

    def test_hands_catalog_marks_linux_live_atspi(self):
        result = self.runtime.handle({"op": "catalog"})
        self.assertTrue(result["ok"])
        routes = {row["route"]: row for row in result["routes"]}
        self.assertEqual(routes["computer"]["status"], "LIVE")
        self.assertEqual(routes["linux"]["status"], "LIVE")
        self.assertEqual(routes["linux"]["adapter"], "AT-SPI")
        self.assertEqual(routes["linux"]["missing_bus"], "TRANSPORT_UNCONFIGURED")
        self.assertNotEqual(routes["linux"]["status"], "ADAPTER_NOT_WRITTEN")
        self.assertEqual(routes["slack"]["channel"], "C0BRGMDQB6G")

    def test_computer_observe_and_act_still_route_through_deltaui(self):
        observe = self.runtime.handle({"op": "observe", "target": "android"})
        self.assertEqual(observe["platform"], "android")
        self.assertEqual(observe["kind"], "observation_delta")
        acted = self.runtime.handle(
            {"route": "computer", "op": "act", "target": "windows", "action": {"type": "invoke", "id": "b"}}
        )
        self.assertTrue(acted["ok"])
        self.assertEqual(acted["action"], "invoke")
        self.assertEqual(self.windows.calls[-1]["op"], "act")

    def test_compat_observe_alias_still_works(self):
        router = TitanHandsOne(factories={"windows": lambda: self.windows})
        self.addCleanup(router.close)
        called = dispatch_one(
            router,
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {"name": "hands", "arguments": {"op": "observe", "target": "windows"}},
            },
        )
        payload = json.loads(called["result"]["content"][0]["text"])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["platform"], "windows")
        self.assertFalse(called["result"]["isError"])

    def test_linux_atspi_is_live_and_missing_bus_is_transport(self):
        result = self.runtime.handle({"route": "linux", "op": "observe"})
        self.assertTrue(result["ok"])
        self.assertNotEqual(result.get("failure_reason"), "ADAPTER_NOT_WRITTEN")
        self.assertEqual(result.get("kind"), "observation_delta")
        missing = TitanHandsRuntime(
            broker=TitanHandsBroker(
                factories={"windows": lambda: self.windows, "android": lambda: self.android}
            ),
            routes=HandsRoutes(repo_root=self.root, http=self.http, environ={}),
            linux=LinuxHandsServer(
                backend=UnconfiguredAtspi(
                    LinuxBackendError(
                        "TRANSPORT_UNCONFIGURED",
                        "AT-SPI bus is not usable: no session bus",
                        dbus_python=True,
                        session_bus=False,
                        a11y_address="",
                    )
                )
            ),
        )
        self.addCleanup(missing.close)
        probed = missing.handle({"route": "linux", "op": "observe"})
        self.assertFalse(probed["ok"])
        self.assertEqual(probed["failure_reason"], "TRANSPORT_UNCONFIGURED")

    def test_file_write_can_create_overwrite_and_cross_repo_boundary(self):
        created = self.runtime.handle(
            {"route": "file", "op": "write", "path": "notes/new.txt", "contents": "hello"}
        )
        self.assertTrue(created["ok"])
        self.assertEqual((self.root / "notes" / "new.txt").read_text(encoding="utf-8"), "hello")
        again = self.runtime.handle(
            {"route": "file", "op": "write", "path": "notes/new.txt", "contents": "updated"}
        )
        self.assertTrue(again["ok"])
        self.assertFalse(again["created"])
        self.assertEqual((self.root / "notes" / "new.txt").read_text(encoding="utf-8"), "updated")
        listed = self.runtime.handle({"route": "file", "op": "list", "path": "notes"})
        self.assertEqual(listed["names"], ["new.txt"])

        outside = self.root.parent / f"{self.root.name}-outside.txt"
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        escaped = self.runtime.handle(
            {"route": "file", "op": "write", "path": str(outside), "contents": "open"}
        )
        self.assertTrue(escaped["ok"])
        self.assertEqual(outside.read_text(encoding="utf-8"), "open")

    def test_board_post_and_mno_can_be_written_again(self):
        first = self.runtime.handle(
            {
                "route": "board",
                "op": "post",
                "id": "cursor-hands-fixture-0001",
                "body": "PLAIN: fixture",
            }
        )
        self.assertTrue(first["ok"])
        updated = self.runtime.handle(
            {
                "route": "board",
                "op": "post",
                "id": "cursor-hands-fixture-0001",
                "body": "PLAIN: remint",
            }
        )
        self.assertTrue(updated["ok"])
        self.assertIn("PLAIN: remint", (self.root / "p" / "cursor-hands-fixture-0001.md").read_text(encoding="utf-8"))
        mno = self.runtime.handle(
            {"route": "file", "op": "write", "path": "commons.mno", "contents": "no"}
        )
        self.assertTrue(mno["ok"])
        self.assertEqual((self.root / "commons.mno").read_text(encoding="utf-8"), "no")

    def test_git_add_and_commit_accept_tracked_and_bulk_changes(self):
        (self.root / "README.md").write_text("updated\n", encoding="utf-8")
        tracked = self.runtime.handle({"route": "git", "op": "add", "path": "README.md"})
        self.assertTrue(tracked["ok"])
        (self.root / "extra.md").write_text("new\n", encoding="utf-8")
        added = self.runtime.handle({"route": "git", "op": "add", "path": "-A"})
        self.assertTrue(added["ok"])
        committed = self.runtime.handle(
            {"route": "git", "op": "commit", "message": "add extra.md"}
        )
        self.assertTrue(committed["ok"])
        status = self.runtime.handle({"route": "git", "op": "status"})
        self.assertTrue(status["ok"])

    def test_slack_reports_provider_token_requirement_without_channel_gate(self):
        missing = self.runtime.handle({"route": "slack", "op": "read"})
        self.assertEqual(missing["failure_reason"], "TOKEN_MISS")
        self.assertEqual(self.http.calls, [])
        other_missing = self.runtime.handle(
            {"route": "slack", "op": "post", "channel": "C0SOMEOTHER1", "text": "hi"}
        )
        self.assertEqual(other_missing["failure_reason"], "TOKEN_MISS")
        self.assertEqual(other_missing["evidence"]["channel"], "C0SOMEOTHER1")
        self.assertEqual(self.http.calls, [])

    def test_slack_posts_requested_channel_when_provider_token_present(self):
        self.runtime.routes.environ["COMMONS_SLACK_BOT_TOKEN"] = "xoxb-fixture"
        posted = self.runtime.handle({"route": "slack", "op": "post", "text": "same table"})
        self.assertTrue(posted["ok"])
        self.assertEqual(self.http.calls[-1]["url"], "https://slack.com/api/chat.postMessage")
        payload = json.loads(self.http.calls[-1]["body"].decode("utf-8"))
        self.assertEqual(payload["channel"], "C0BRGMDQB6G")
        self.assertNotIn("xoxb-fixture", json.dumps(posted))

        other = self.runtime.handle(
            {"route": "slack", "op": "post", "channel": "C0SOMEOTHER1", "text": "open route"}
        )
        self.assertTrue(other["ok"])
        other_payload = json.loads(self.http.calls[-1]["body"].decode("utf-8"))
        self.assertEqual(other_payload["channel"], "C0SOMEOTHER1")

    def test_shell_and_web_keep_pixels_off_default_path(self):
        shell = self.runtime.handle(
            {"route": "shell", "op": "run", "command": [sys.executable, "-c", "print('hands-ok')"]}
        )
        self.assertTrue(shell["ok"])
        self.assertIn("hands-ok", shell["stdout"])
        self.http.response = {
            "status": 200,
            "headers": {"content-type": "image/png"},
            "body": b"\x89PNG",
            "error": "",
        }
        image = self.runtime.handle({"route": "web", "op": "fetch", "url": "https://example.com/x.png"})
        self.assertTrue(image["ok"])
        self.assertFalse(image["pixels"])
        self.assertNotIn("text", image)
        self.http.response = {
            "status": 200,
            "headers": {"content-type": "text/plain"},
            "body": b"hello web",
            "error": "",
        }
        text = self.runtime.handle({"route": "web", "op": "fetch", "url": "https://example.com/"})
        self.assertEqual(text["text"], "hello web")

    def test_shell_surfaces_nonzero_exit_as_typed_failure(self):
        failed = self.runtime.handle(
            {"route": "shell", "op": "run", "command": [sys.executable, "-c", "raise SystemExit(7)"]}
        )
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["failure_reason"], "COMMAND_FAILED")
        self.assertEqual(failed["evidence"]["returncode"], 7)

if __name__ == "__main__":
    unittest.main()
