from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from host.commons_android.lan_client import LanAndroidServer
from host.titan_hands.lanes import LinuxPendingServer
from host.titan_hands.linux_atspi import LinuxHandsServer
from host.titan_hands.one_tool import TitanHandsOne, contains_pixel_payload, default_factories


class DummyBroker:
    def handle(self, request):
        return {"ok": True, "kind": "capabilities", "platform": "dummy"}

    def close(self):
        return None


class LanAndroidTests(unittest.TestCase):
    def test_offline_capabilities_and_typed_observe(self):
        server = LanAndroidServer(base_url="")
        caps = server.handle({"op": "capabilities"})
        self.assertTrue(caps["ok"])
        self.assertFalse(caps["online"])
        self.assertEqual(caps["transport"], "lan")
        self.assertEqual(caps["pairing"], "none")
        observed = server.handle({"op": "observe"})
        self.assertEqual(observed["failure_reason"], "HOST_OFFLINE")
        self.assertFalse(contains_pixel_payload(observed))

    def test_lan_url_without_pairing_is_open(self):
        posted = []

        def post(url, request):
            posted.append((url, dict(request)))
            return {
                "ok": True,
                "kind": "observation_delta",
                "added": [{"id": "a_1", "role": "Button", "name": "Send"}],
                "pixels": "not-captured",
            }

        server = LanAndroidServer(
            base_url="http://192.168.1.20:8745",
            pairing="",
            post=post,
        )
        caps = server.handle({"op": "capabilities"})
        self.assertTrue(caps["ok"])
        observed = server.handle({"op": "observe"})
        self.assertTrue(observed["ok"])
        self.assertEqual(observed["kind"], "observation_delta")
        self.assertFalse(contains_pixel_payload(observed))
        self.assertEqual(posted[0][0], "http://192.168.1.20:8745")
        self.assertNotIn("failure_reason", observed)

    def test_forward_observe_without_pixels_and_capture_to_file(self):
        tmp = Path(tempfile.mkdtemp())
        posted = []

        def post(url, request):
            posted.append((url, dict(request)))
            op = request["op"]
            if op == "observe":
                return {
                    "ok": True,
                    "kind": "observation_delta",
                    "added": [{"id": "a_1", "role": "Button", "name": "Send"}],
                    "pixels": "not-captured",
                }
            if op == "capture":
                return {
                    "ok": True,
                    "kind": "pixel_capture",
                    "image_png_b64": "iVBORw0KGgo=",
                    "platform": "android",
                }
            return {"ok": True, "kind": "capabilities", "pixels": "on-demand-only"}

        server = LanAndroidServer(base_url="http://192.168.1.20:8745", post=post)
        router = TitanHandsOne(factories={"android-lan": lambda: server, "linux": LinuxPendingServer})
        self.addCleanup(router.close)
        observed = router.handle({"op": "observe", "target": "android-lan"})
        self.assertTrue(observed["ok"])
        self.assertFalse(contains_pixel_payload(observed))
        captured = router.handle(
            {"op": "capture", "target": "android-lan", "path": str(tmp / "phone.png")},
        )
        self.assertEqual(captured["kind"], "pixel_capture")
        self.assertTrue(contains_pixel_payload(captured))
        self.assertNotIn("image_png_b64", captured)
        self.assertTrue(Path(captured["pixel_ref"]).is_file())
        self.assertEqual(posted[0][0], "http://192.168.1.20:8745")

    def test_default_factories_include_lan_without_reminting_linux(self):
        names = sorted(default_factories(DummyBroker()).keys())
        self.assertIn("android-lan", names)
        self.assertIn("android", names)
        self.assertIn("windows", names)
        self.assertIn("linux", names)
        factories = default_factories(DummyBroker())
        self.assertIs(factories["android-lan"], LanAndroidServer)
        self.assertIs(factories["linux"], LinuxHandsServer)


if __name__ == "__main__":
    unittest.main()
