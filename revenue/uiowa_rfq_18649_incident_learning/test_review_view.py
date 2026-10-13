"""Stdlib regression coverage for the read-only incident review presentation."""
from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

if __package__:
    from . import review_view as view
    from .analyze import analyze
    from .fixture import sample
else:
    import review_view as view
    from analyze import analyze
    from fixture import sample


def raw_packet(data=None):
    return (json.dumps(sample() if data is None else data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def embedded(page):
    encoded = re.search(r'<div id="payload" hidden>([A-Za-z0-9+/=]+)</div>', page).group(1)
    return json.loads(base64.b64decode(encoded))


class PayloadTests(unittest.TestCase):
    def test_exact_canonical_report_not_a_second_assessor(self):
        data = sample()
        self.assertEqual(view.make_payload(raw_packet(data))["report"], analyze(data))

    def test_snapshot_digest_byte_count_and_original_preserved(self):
        raw = raw_packet() + b" \n"
        payload = view.make_payload(raw)
        self.assertEqual(base64.b64decode(payload["original_packet_base64"]), raw)
        self.assertEqual(payload["input_bytes"], len(raw))
        self.assertEqual(payload["input_sha256"], hashlib.sha256(raw).hexdigest())

    def test_canonical_report_digest_reproducible(self):
        p = view.make_payload(raw_packet())
        body = json.dumps(p["report"], ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("ascii")
        self.assertEqual(p["report_sha256"], hashlib.sha256(body).hexdigest())

    def test_whitespace_changes_input_not_report_identity(self):
        a = view.make_payload(raw_packet())
        b = view.make_payload(raw_packet() + b" ")
        self.assertNotEqual(a["input_sha256"], b["input_sha256"])
        self.assertEqual(a["report_sha256"], b["report_sha256"])

    def test_unknown_durations_stay_null(self):
        incidents = {i["id"]: i for i in view.make_payload(raw_packet())["report"]["incidents"]}
        self.assertIsNone(incidents["INC-RIS-1"]["minutes"]["restoration_to_verification"])
        self.assertIsNone(incidents["INC-IAM-1"]["minutes"]["impact_to_restoration"])
        self.assertEqual(incidents["INC-ESS-1"]["minutes"]["impact_to_restoration"], 60)

    def test_shared_action_not_duplicated(self):
        actions = view.make_payload(raw_packet())["report"]["actions"]
        self.assertEqual(len(actions), 6)
        shared = [a for a in actions if a["id"] == "ACT-02"]
        self.assertEqual(len(shared), 1)
        self.assertEqual(len(shared[0]["incident_ids"]), 2)

    def test_replacement_does_not_close_successor(self):
        actions = {a["id"]: a for a in view.make_payload(raw_packet())["report"]["actions"]}
        self.assertEqual(actions["ACT-04"]["evidence_state"], "replacement_documented")
        self.assertEqual(actions["ACT-05"]["evidence_state"], "open_work")
        self.assertTrue(actions["ACT-05"]["overdue_unresolved"])

    def test_engagement_classification_not_relabeled(self):
        data = sample(); data["classification"] = "engagement"
        self.assertEqual(view.make_payload(raw_packet(data))["report"]["classification"], "engagement")

    def test_timeline_orders_real_instants_not_input_order(self):
        data = sample()
        row = data["incidents"][0]
        row["events"].reverse()
        # 04:05-05:00 is 09:05Z. Lexical timestamp order is not chronology.
        next(e for e in row["events"] if e["kind"] == "detected")["at"] = "2026-09-01T04:05:00-05:00"
        p = view.make_payload(raw_packet(data))
        self.assertEqual(p["presentation"]["timeline_order"]["INC-ESS-1"][:3], ["impact_start", "detected", "coordinated"])
        self.assertEqual(p["report"]["incidents"][0]["events"], row["events"])

    def test_empty_record_set_is_supported(self):
        data = sample()
        for key in ("incidents", "actions", "conditions", "sources"): data[key] = []
        self.assertEqual(view.make_payload(raw_packet(data))["report"]["summary"]["actions"], 0)

    def test_duplicate_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            view.read_packet(b'{"x":{"y":1,"y":2}}')

    def test_invalid_utf8_and_surrogate_rejected(self):
        for raw in (b'{"x":"\xff"}', b'{"x":"\\ud800"}'):
            with self.subTest(raw=raw), self.assertRaises(UnicodeError): view.read_packet(raw)

    def test_nonfinite_and_overflow_rejected(self):
        for token in (b"NaN", b"Infinity", b"-Infinity", b"1e500"):
            with self.subTest(token=token), self.assertRaises(ValueError): view.read_packet(b'{"x":'+token+b'}')

    def test_empty_oversized_and_wrong_type_rejected(self):
        for raw in (b"", b" " * (view.MAX_INPUT_BYTES+1), "{}", bytearray(b"{}")):
            with self.subTest(kind=type(raw)), self.assertRaises(ValueError): view.read_packet(raw)

    def test_structural_limits(self):
        with self.assertRaisesRegex(ValueError, "structure"):
            view.read_packet(b'{"x":' + b'[' * 62 + b'0' + b']' * 62 + b'}')
        with mock.patch.object(view, 'MAX_NODES', 3), self.assertRaisesRegex(ValueError, "structure"):
            view.read_packet(b'{"x":[1,2,3,4]}')

    def test_parent_contract_errors_not_ignored(self):
        data = sample(); data["actions"][0]["implementation_evidence_ids"] = ["MISSING"]
        with self.assertRaisesRegex(ValueError, "unresolved"): view.make_payload(raw_packet(data))

    def test_analyzed_report_not_silently_accepted_as_raw_packet(self):
        with self.assertRaises(ValueError): view.make_payload(raw_packet(analyze(sample())))


class PageTests(unittest.TestCase):
    def test_deterministic_page_and_exact_embedded_data(self):
        raw = raw_packet()
        page = view.render_packet(raw)
        self.assertEqual(page, view.render_packet(raw))
        self.assertEqual(embedded(page), view.make_payload(raw))
        self.assertNotIn('__PAYLOAD__', page)

    def test_user_content_never_becomes_markup(self):
        data = sample(); marker = '</script><img src="https://example.invalid/" onerror="window.probe=1">'
        data["sources"][0]["excerpt"] = marker
        page = view.render_packet(raw_packet(data))
        self.assertNotIn(marker, page)
        self.assertEqual(next(s for s in embedded(page)["report"]["sources"] if s["id"] == 'EV-QUEUE')["excerpt"], marker)

    def test_script_style_hashes_match_exact_embedded_bytes(self):
        page = view.render_packet(raw_packet())
        for tag in ("script", "style"):
            value = re.search('<'+tag+'>(.*?)</'+tag+'>', page, re.S).group(1)
            expected = base64.b64encode(hashlib.sha256(value.encode()).digest()).decode()
            self.assertIn("'sha256-"+expected+"'", page)
        self.assertIn("connect-src 'none'", page)
        self.assertNotRegex(page, r'<script\s+src=|<link\s+[^>]*href=')

    def test_controls_and_no_script_limitation_are_present(self):
        page = view.render_packet(raw_packet())
        for name in ('group', 'state', 'query', 'export-json', 'export-text', 'export-input', 'print'):
            self.assertIn('id="'+name+'"', page)
        self.assertIn('<noscript>', page)
        self.assertIn('aria-live="polite"', page)

    def test_existing_output_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'review.html'; path.write_bytes(b'KEEP')
            with self.assertRaises(FileExistsError): view.publish_new(path, 'REPLACE')
            self.assertEqual(path.read_bytes(), b'KEEP')

    def test_symlink_and_hardlink_outputs_are_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'source'; source.write_bytes(b'KEEP')
            for name, create in [('sym', lambda p: p.symlink_to(source)), ('hard', lambda p: os.link(source,p))]:
                target=Path(directory)/name; create(target)
                with self.assertRaises(FileExistsError): view.publish_new(target, 'REPLACE')
                self.assertEqual(source.read_bytes(), b'KEEP')

    def test_successful_exclusive_output_has_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'review.html'; view.publish_new(path, 'Unicode: é\n')
            self.assertEqual(path.read_bytes(), 'Unicode: é\n'.encode())

    def test_write_failure_removes_only_created_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'review.html'
            with mock.patch.object(view.os, 'fsync', side_effect=OSError('injected flush failure')):
                with self.assertRaises(OSError): view.publish_new(path, 'x')
            self.assertFalse(path.exists())

    def test_write_failure_preserves_foreign_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'review.html'; held=Path(directory)/'held'
            def replace(_fd):
                path.rename(held); path.write_bytes(b'FOREIGN'); raise OSError('injected replacement')
            with mock.patch.object(view.os, 'fsync', side_effect=replace):
                with self.assertRaises(OSError): view.publish_new(path, 'x')
            self.assertEqual(path.read_bytes(), b'FOREIGN')

    def test_real_cli_render_and_repeated_output_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'review.html'
            command=[sys.executable, str(view.ROOT/'review_view.py'), '--demo', '--out', str(out)]
            success=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(success.returncode,0,success.stderr)
            first=out.read_bytes()
            second=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(second.returncode,2)
            self.assertEqual(out.read_bytes(),first)

    def test_cli_input_equal_output_and_invalid_input_preserve_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'packet.json'; raw=raw_packet(); path.write_bytes(raw)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(view.main(['--input',str(path),'--out',str(path)]),2)
            self.assertEqual(path.read_bytes(),raw)
            path.write_bytes(b'not JSON'); out=Path(directory)/'missing.html'
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(view.main(['--input',str(path),'--out',str(out)]),2)
            self.assertFalse(out.exists())

    def test_real_cli_reads_original_input_once(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'packet.json'; source.write_bytes(raw_packet()); out=Path(directory)/'review.html'
            process=subprocess.run([sys.executable,str(view.ROOT/'review_view.py'),'--input',str(source),'--out',str(out)],capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertEqual(base64.b64decode(embedded(out.read_text())["original_packet_base64"]),source.read_bytes())


if __name__ == '__main__':
    unittest.main()
