from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from host.titan_hands.linux_atspi import (
    LinuxBackendError,
    LinuxHandsServer,
    UnconfiguredAtspi,
    compositor_capture,
    measure_atspi_transport,
    node_id,
    state_names,
)
from host.titan_hands.mcp_one import TOOL, dispatch
from host.titan_hands.one_tool import TitanHandsOne, contains_pixel_payload
from host.titan_hands_windows.protocol import PROTOCOL_VERSION


class FakeAtspi:
    def __init__(self) -> None:
        self.name = "Idle"
        self.closed = False
        self.acts: list[dict] = []

    def capabilities(self):
        return {
            "ok": True,
            "kind": "capabilities",
            "platform": "linux",
            "adapter": "at-spi",
            "status": "live",
            "online": True,
            "pixels": "on-demand-only",
            "observation": "at-spi-semantic-delta",
            "actions": ["invoke", "click", "type_text"],
        }

    def snapshot(self, *, max_nodes: int, max_depth: int, include_offscreen: bool):
        del max_nodes, max_depth, include_offscreen
        return {
            "ok": True,
            "kind": "semantic_snapshot",
            "platform": "linux",
            "adapter": "at-spi",
            "pixels": "not-captured",
            "nodes": [
                {
                    "id": "l_button",
                    "parent": "",
                    "role": "Button",
                    "name": self.name,
                    "states": ["enabled", "showing", "visible"],
                    "actions": ["invoke", "click"],
                }
            ],
        }

    def act(self, action):
        self.acts.append(dict(action))
        action_type = str(action.get("type") or "")
        if action_type == "mystery":
            raise LinuxBackendError("UNKNOWN_OPERATION", "linux adapter has no handler for mystery")
        if action_type == "invoke":
            self.name = "Done"
        return {
            "ok": True,
            "kind": "action_outcome",
            "platform": "linux",
            "action": action_type,
            "id": action.get("id"),
        }

    def capture(self, request):
        return {
            "ok": True,
            "kind": "pixel_capture",
            "platform": "linux",
            "pixel_ref": str(request.get("path") or "linux.png"),
            "method": "fake",
        }

    def close(self):
        self.closed = True


class LinuxAtspiTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeAtspi()
        self.server = LinuxHandsServer(backend=self.backend)

    def tearDown(self):
        self.server.close()

    def test_observe_act_capture_and_capabilities(self):
        caps = self.server.handle({"op": "capabilities"})
        self.assertTrue(caps["ok"])
        self.assertEqual(caps["adapter"], "at-spi")
        self.assertEqual(caps["status"], "live")
        self.assertEqual(caps["pixels"], "on-demand-only")
        observed = self.server.handle({"op": "observe"})
        self.assertTrue(observed["ok"])
        self.assertEqual(observed["kind"], "observation_delta")
        self.assertEqual(observed["added"][0]["name"], "Idle")
        self.assertFalse(contains_pixel_payload(observed))
        acted = self.server.handle({"op": "act", "action": {"type": "invoke", "id": "l_button"}})
        self.assertTrue(acted["ok"])
        self.assertEqual(acted["observation"]["updated"][0]["name"], "Done")
        self.assertFalse(contains_pixel_payload(acted))
        captured = self.server.handle({"op": "capture", "path": "shot.png"})
        self.assertEqual(captured["kind"], "pixel_capture")
        self.assertEqual(captured["pixel_ref"], "shot.png")
        self.assertTrue(contains_pixel_payload(captured))

    def test_unknown_operation_and_missing_action_are_typed(self):
        self.assertEqual(self.server.handle({"op": "mystery"})["failure_reason"], "UNKNOWN_OPERATION")
        missing = self.server.handle({"op": "act"})
        self.assertEqual(missing["failure_reason"], "INVALID_REQUEST")
        unknown_act = self.server.handle({"op": "act", "action": {"type": "mystery", "id": "l_button"}})
        self.assertEqual(unknown_act["failure_reason"], "UNKNOWN_OPERATION")

    def test_unconfigured_bus_is_transport_failure_not_a_fake_desktop(self):
        error = LinuxBackendError(
            "TRANSPORT_UNCONFIGURED",
            "AT-SPI bus is not usable: no session bus",
            dbus_python=True,
            session_bus=False,
            a11y_address="",
        )
        server = LinuxHandsServer(backend=UnconfiguredAtspi(error, capture=self._unsupported_capture))
        self.addCleanup(server.close)
        caps = server.handle({"op": "capabilities"})
        self.assertTrue(caps["ok"])
        self.assertEqual(caps["adapter"], "at-spi")
        self.assertEqual(caps["status"], "transport-unconfigured")
        self.assertFalse(caps["online"])
        observed = server.handle({"op": "observe"})
        self.assertEqual(observed["failure_reason"], "TRANSPORT_UNCONFIGURED")
        self.assertIn("session_bus", observed["evidence"])
        acted = server.handle({"op": "act", "action": {"type": "invoke", "id": "x"}})
        self.assertEqual(acted["failure_reason"], "TRANSPORT_UNCONFIGURED")
        captured = server.handle({"op": "capture"})
        self.assertEqual(captured["failure_reason"], "PIXEL_UNSUPPORTED")

    def test_connect_error_becomes_unconfigured_backend(self):
        error = LinuxBackendError(
            "TRANSPORT_UNCONFIGURED",
            "dbus-python is not importable",
            dbus_python=False,
            pyatspi=False,
            gi_atspi=False,
        )

        def connect():
            raise error

        server = LinuxHandsServer(connect=connect, capture=self._unsupported_capture)
        self.addCleanup(server.close)
        observed = server.handle({"op": "observe"})
        self.assertEqual(observed["failure_reason"], "TRANSPORT_UNCONFIGURED")
        self.assertFalse(observed["evidence"]["dbus_python"])

    def test_one_tool_still_lists_only_hands(self):
        router = TitanHandsOne(factories={"linux": lambda: self.server})
        self.addCleanup(router.close)
        listed = dispatch(router, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual([tool["name"] for tool in listed["result"]["tools"]], ["hands"])
        self.assertEqual(TOOL["name"], "hands")
        observed = router.handle({"op": "observe", "target": "linux"})
        self.assertTrue(observed["ok"])
        self.assertFalse(contains_pixel_payload(observed))
        leaked = dict(observed)
        leaked["pixel_ref"] = "nope.png"
        self.assertTrue(contains_pixel_payload(leaked))

    def test_state_names_and_node_ids(self):
        names = state_names([1 << 8 | 1 << 12, 0])
        self.assertIn("enabled", names)
        self.assertIn("focused", names)
        self.assertEqual(node_id(":1.4", "/org/a11y/atspi/accessible/1"), node_id(":1.4", "/org/a11y/atspi/accessible/1"))
        self.assertNotEqual(node_id(":1.4", "/org/a11y/atspi/accessible/1"), node_id(":1.5", "/org/a11y/atspi/accessible/1"))

    def test_compositor_capture_uses_injected_ffmpeg(self):
        tmp = Path(tempfile.mkdtemp()) / "cap.png"

        def which(name):
            return "/bin/ffmpeg" if name == "ffmpeg" else None

        def run(command, **kwargs):
            del kwargs
            tmp.write_bytes(_TINY_PNG)
            return _Completed(0, "", "")

        result = compositor_capture(tmp, which=which, run=run, environ={"DISPLAY": ":1"})
        self.assertEqual(result["kind"], "pixel_capture")
        self.assertEqual(result["method"], "ffmpeg-x11grab")
        self.assertEqual(result["sha256"], hashlib.sha256(_TINY_PNG).hexdigest())

    def test_live_bus_is_measured_not_faked(self):
        probe = measure_atspi_transport()
        server = LinuxHandsServer()
        self.addCleanup(server.close)
        caps = server.handle({"op": "capabilities"})
        self.assertEqual(caps["adapter"], "at-spi")
        self.assertEqual(caps["protocol"], PROTOCOL_VERSION)
        observed = server.handle({"op": "observe"})
        if caps.get("online") and probe.get("registry"):
            self.assertTrue(observed["ok"], msg=observed)
            self.assertEqual(observed["kind"], "observation_delta")
            self.assertGreater(observed["node_count"], 0)
            self.assertFalse(contains_pixel_payload(observed))
            self.assertNotEqual(observed.get("kind"), "pixel_capture")
            meta = observed.get("meta") or {}
            self.assertEqual(meta.get("pixels") or observed.get("pixels"), "not-captured")
            shot = Path(tempfile.mkdtemp()) / "linux-live.png"
            captured = server.handle({"op": "capture", "path": str(shot)})
            if captured.get("ok"):
                self.assertEqual(captured["kind"], "pixel_capture")
                self.assertTrue(contains_pixel_payload(captured))
                self.assertTrue(Path(captured["pixel_ref"]).is_file())
            else:
                self.assertEqual(captured["failure_reason"], "PIXEL_UNSUPPORTED")
        else:
            self.assertEqual(observed["failure_reason"], "TRANSPORT_UNCONFIGURED")
            self.assertIn("evidence", observed)

    def _unsupported_capture(self, path, bounds):
        del bounds
        raise LinuxBackendError("PIXEL_UNSUPPORTED", "no compositor in this test", path=str(path), probes=["grim=missing"])


class _Completed:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# 1x1 transparent PNG
_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


if __name__ == "__main__":
    unittest.main()
