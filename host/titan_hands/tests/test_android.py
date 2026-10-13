from __future__ import annotations

import base64
import os
import tempfile
import unittest
from pathlib import Path

from host.titan_hands.android import AndroidHandsServer, parse_uiautomator_xml


XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="android" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[0,0][1080,1920]">
    <node index="0" text="Hello" resource-id="com.example:id/input" class="android.widget.EditText" package="com.example" content-desc="Greeting" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="true" scrollable="false" long-clickable="true" password="false" selected="false" bounds="[20,100][500,180]" />
  </node>
</hierarchy>"""


class FakeAdb:
    serial = "emulator-5554"

    def __init__(self):
        self.calls = []
        self.xml = XML

    def devices(self):
        return [{"serial": self.serial, "state": "device", "model": "headless"}]

    def resolve_serial(self):
        return self.serial

    def shell(self, *args, timeout=30):
        self.calls.append(("shell", args))
        return "UI hierchary dumped"

    def exec_out(self, *args, timeout=30):
        self.calls.append(("exec_out", args))
        if args[0] == "cat":
            return self.xml.encode()
        return b"PNG"


class FlakyAdb(FakeAdb):
    def __init__(self):
        super().__init__()
        self.reads = 0

    def exec_out(self, *args, timeout=30):
        if args[0] == "cat":
            self.reads += 1
            if self.reads == 1:
                return b"UI hierarchy unavailable"
        return super().exec_out(*args, timeout=timeout)


class PhysicalOnlyAdb(FakeAdb):
    serial = None

    def devices(self):
        return [{"serial": "PHONE123", "state": "device", "model": "personal"}]

    def resolve_serial(self):
        from host.titan_hands.android import AndroidBackendError

        raise AndroidBackendError("DEVICE_MISS", "no online Android emulator")


MARKED_JPEG = b"LDA-SET-OF-MARKS-JPEG"


class FakeLdaBridge:
    def __init__(self):
        self.actions = []
        self.captures = 0

    def available(self):
        return True

    def observe(self):
        return {
            "ok": True,
            "implementation": "lda-kotlin",
            "snapshot": '[0] "Untitled" field [focused]\nTEXT ON SCREEN: Untitled',
        }

    def act(self, action):
        self.actions.append(action)
        return {
            "ok": True,
            "implementation": "lda-kotlin",
            "result": "CONTINUE",
            "summary": "typed it",
        }

    def capture(self):
        self.captures += 1
        return {
            "ok": True,
            "implementation": "lda-kotlin",
            "visual": "set-of-marks",
            "mime": "image/jpeg",
            "source": "ActionAccessibilityService.captureScreenshot",
            "marks_source": "ActionAccessibilityService.currentMarks",
            "image_b64": base64.b64encode(MARKED_JPEG).decode("ascii"),
            "mark_ids": [0],
            "snapshot": '[0] "Untitled" field [focused]',
        }


class UnknownCaptureLda(FakeLdaBridge):
    def capture(self):
        self.captures += 1
        return {
            "ok": False,
            "failure_reason": "UNKNOWN_OPERATION",
            "message": "op must be capabilities, observe, or act",
        }


class AndroidHandsTests(unittest.TestCase):
    def test_parser_produces_semantic_edit_node(self):
        nodes = parse_uiautomator_xml(XML, "emulator-5554")
        edit = next(node for node in nodes if node["role"] == "TextBox")
        self.assertEqual(edit["name"], "Hello")
        self.assertIn("set_value", edit["actions"])
        self.assertEqual(edit["bounds"]["width"], 480)

    def test_observe_then_click_returns_delta(self):
        adb = FakeAdb()
        server = AndroidHandsServer(adb)
        first = server.handle({"op": "observe"})
        target = next(node for node in first["added"] if node["role"] == "TextBox")
        result = server.handle({"op": "act", "action": {"type": "click", "id": target["id"]}})
        self.assertTrue(result["ok"])
        self.assertIn(("shell", ("input", "tap", "260", "140")), adb.calls)
        self.assertFalse(result["observation"]["full"])

    def test_capabilities_do_not_require_live_observation(self):
        result = AndroidHandsServer(FakeAdb()).handle({"op": "capabilities"})
        self.assertTrue(result["online"])
        self.assertEqual(result["observation"], "uiautomator-semantic-delta")

    def test_observation_retries_transient_uiautomator_failure(self):
        adb = FlakyAdb()
        result = AndroidHandsServer(adb).handle({"op": "observe"})
        self.assertTrue(result["ok"])
        self.assertEqual(adb.reads, 2)

    def test_physical_only_backend_is_not_reported_as_default_online_target(self):
        result = AndroidHandsServer(PhysicalOnlyAdb()).handle({"op": "capabilities"})
        self.assertFalse(result["online"])
        self.assertEqual(result["devices"][0]["serial"], "PHONE123")

    def test_lda_kotlin_is_preferred_and_receives_native_set_text(self):
        lda = FakeLdaBridge()
        server = AndroidHandsServer(FakeAdb(), lda_bridge=lda)
        observed = server.handle({"op": "observe"})
        field = next(node for node in observed["added"] if node["id"] == "lda:0")
        self.assertEqual(observed["meta"]["implementation"], "lda-kotlin")
        result = server.handle(
            {
                "op": "act",
                "action": {"type": "type_text", "id": field["id"], "text": "owner build"},
                "observe_after": False,
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(
            lda.actions[-1], {"id": 0, "text": "owner build", "action": "set_text"}
        )

    def test_capture_without_lda_uses_adb_framebuffer(self):
        adb = FakeAdb()
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "raw.png")
            result = AndroidHandsServer(adb).handle({"op": "capture", "path": path})
            self.assertTrue(result["ok"])
            self.assertEqual(result["visual"], "adb-framebuffer")
            self.assertEqual(result["mime"], "image/png")
            self.assertIn(("exec_out", ("screencap", "-p")), adb.calls)
            self.assertEqual(Path(result["pixel_ref"]).read_bytes(), b"PNG")

    def test_lda_capture_returns_set_of_marks_not_adb_framebuffer(self):
        adb = FakeAdb()
        lda = FakeLdaBridge()
        server = AndroidHandsServer(adb, lda_bridge=lda)
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "marks.jpg")
            result = server.handle({"op": "capture", "path": path})
            self.assertTrue(result["ok"])
            self.assertEqual(result["visual"], "set-of-marks")
            self.assertEqual(result["implementation"], "lda-kotlin")
            self.assertEqual(result["mime"], "image/jpeg")
            self.assertEqual(result["mark_ids"], [0])
            self.assertEqual(lda.captures, 1)
            self.assertNotIn("image_b64", result)
            self.assertNotIn("snapshot", result)
            self.assertEqual(Path(result["pixel_ref"]).read_bytes(), MARKED_JPEG)
        self.assertFalse(any(call[0] == "exec_out" and call[1][:1] == ("screencap",) for call in adb.calls))

    def test_default_lda_capture_path_matches_jpeg_mime(self):
        previous_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                result = AndroidHandsServer(FakeAdb(), lda_bridge=FakeLdaBridge()).handle(
                    {"op": "capture"}
                )
            finally:
                os.chdir(previous_cwd)
            self.assertTrue(result["ok"])
            self.assertEqual(result["mime"], "image/jpeg")
            self.assertEqual(Path(result["pixel_ref"]).suffix, ".jpg")
            self.assertEqual(Path(result["pixel_ref"]).read_bytes(), MARKED_JPEG)

    def test_default_old_receiver_fallback_path_matches_png_bytes(self):
        previous_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                result = AndroidHandsServer(FakeAdb(), lda_bridge=UnknownCaptureLda()).handle(
                    {"op": "capture"}
                )
            finally:
                os.chdir(previous_cwd)
            self.assertTrue(result["ok"])
            self.assertEqual(result["fallback"], "adb-screencap")
            self.assertEqual(result["mime"], "image/png")
            self.assertEqual(Path(result["pixel_ref"]).suffix, ".png")
            self.assertEqual(Path(result["pixel_ref"]).read_bytes(), b"PNG")

    def test_lda_capabilities_advertise_set_of_marks_capture(self):
        result = AndroidHandsServer(FakeAdb(), lda_bridge=FakeLdaBridge()).handle({"op": "capabilities"})
        self.assertEqual(result["implementation"], "lda-kotlin")
        self.assertEqual(result["pixels"], "lda-set-of-marks-on-demand")

    def test_old_receiver_without_capture_falls_back_to_adb(self):
        adb = FakeAdb()
        lda = UnknownCaptureLda()
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "fallback.png")
            result = AndroidHandsServer(adb, lda_bridge=lda).handle({"op": "capture", "path": path})
            self.assertTrue(result["ok"])
            self.assertEqual(result["visual"], "adb-framebuffer")
            self.assertEqual(result["fallback"], "adb-screencap")
            self.assertEqual(Path(result["pixel_ref"]).read_bytes(), b"PNG")

    def test_lda_forced_mode_does_not_fallback_unknown_capture(self):
        lda = UnknownCaptureLda()
        server = AndroidHandsServer(FakeAdb(), lda_bridge=lda)
        server._lda_mode = "lda"
        with tempfile.TemporaryDirectory() as tmp:
            result = server.handle({"op": "capture", "path": str(Path(tmp) / "nope.jpg")})
        self.assertFalse(result["ok"])
        self.assertEqual(result["failure_reason"], "UNKNOWN_OPERATION")


if __name__ == "__main__":
    unittest.main()
