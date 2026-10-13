from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from host.titan_hands.lda_bridge import LdaBridge, LdaBridgeError, write_marked_image


def broadcast_data(payload: dict) -> str:
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return f'Broadcast completed: result=-1, data="{encoded}"'


class CaptureAdb:
    serial = "emulator-5554"

    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = []

    def resolve_serial(self):
        return self.serial

    def shell(self, *args, timeout=30):
        self.calls.append((args, timeout))
        return broadcast_data(self.payload)


class LdaBridgeCaptureTests(unittest.TestCase):
    def test_capture_sends_receiver_op_and_returns_marks_payload(self):
        payload = {
            "ok": True,
            "implementation": "lda-kotlin",
            "visual": "set-of-marks",
            "image_b64": base64.b64encode(b"MARKED").decode("ascii"),
            "mark_ids": [3, 7],
        }
        adb = CaptureAdb(payload)
        result = LdaBridge(adb).capture()
        self.assertTrue(result["ok"])
        self.assertEqual(result["visual"], "set-of-marks")
        args, timeout = adb.calls[-1]
        self.assertEqual(args[:8], ("am", "broadcast", "-W", "-a", "com.local.deviceagent.TITAN_HANDS", "-n", "com.local.deviceagent/.TitanHandsReceiver", "--es"))
        self.assertEqual(args[8:10], ("op", "capture"))
        self.assertEqual(timeout, 45)

    def test_write_marked_image_strips_wire_bytes_and_keeps_mark_ids(self):
        jpeg = b"LDA-SET-OF-MARKS-JPEG"
        result = {
            "ok": True,
            "implementation": "lda-kotlin",
            "visual": "set-of-marks",
            "image_b64": base64.b64encode(jpeg).decode("ascii"),
            "mark_ids": [0],
            "snapshot": "[0] field",
        }
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "marks.jpg"
            normalized = write_marked_image(result, output)
            self.assertEqual(output.read_bytes(), jpeg)
            self.assertEqual(normalized["pixel_ref"], str(output))
            self.assertEqual(normalized["bytes"], len(jpeg))
            self.assertEqual(normalized["mark_ids"], [0])
            self.assertNotIn("image_b64", normalized)
            self.assertNotIn("snapshot", normalized)

    def test_write_marked_image_rejects_missing_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(LdaBridgeError):
                write_marked_image({"ok": True, "visual": "set-of-marks"}, Path(tmp) / "x.jpg")


if __name__ == "__main__":
    unittest.main()
