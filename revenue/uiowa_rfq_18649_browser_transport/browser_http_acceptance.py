#!/usr/bin/env python3
"""Independent workbench intake acceptance; synthetic data, explicit transport mode.

Native mode navigates real Chromium to the unchanged loopback workbench server.
Split mode executes the same assets in memory, captures the browser's request,
then replays its body through Python HTTP. Split mode is NOT native network proof.
No automatic fallback, downloads, installs, policy changes or external services.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import http.client
import importlib.util
import io
import json
import os
import platform
import re
import shutil
import sys
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

MIB = 1024 * 1024
FLAGS = (
    "buyer_approved", "prime_approved", "current_evidence_review_authority",
    "submission_authorized", "signature_authorized", "invoice_or_payment_authorized",
    "recognized_revenue",
)


def fingerprint(data: bytes) -> dict:
    return {
        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "git_blob_sha1": hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest(),
    }


def source_files(root: Path) -> list[Path]:
    """Only explicit local assets in the selected workbench, never directory scans."""
    html = (root / "index.html").read_text(encoding="utf-8")
    paths = {root / n for n in ("server.py", "index.html", "style.css", "app.js")}
    for name in re.findall(r'<script\b[^>]*\bsrc=[\"\']([^\"\']+)', html):
        relative = name.lstrip("/")
        if ":" in name or "/" in relative or relative in {"", ".", ".."}:
            raise ValueError("only explicit workbench-local script filenames are supported")
        paths.add(root / relative)
    return sorted(paths)


def snapshot(root: Path) -> dict:
    result = {}
    for path in source_files(root):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"source must be a regular, nonsymlink file: {path.name}")
        result[path.name] = fingerprint(path.read_bytes())
    return result


def synthetic_report() -> dict:
    return {
        "schema": "BASALT_R7Q_SYNTHETIC_RECORDING_ADAPTER_NOT_COMPILER_OUTPUT",
        "synthetic_demo": True, "mode": "UNTRUSTED_INSPECTION",
        "receipt_sha256": "a" * 64, "aggregate_state": "HOLD_TRUSTED_AUTHORITY_REQUIRED",
        "trust": {"current_evidence_review_authority": False,
                  "authority_root_supplied_out_of_band": False},
        "commercial_terms": {"status": "PROPOSED_NOT_ACCEPTED"},
        "assessment_matrix": [
            {"group": g, "dimension": d, "status": "UNTRUSTED_EVIDENCE_CONSISTENT",
             "maturity": None, "confidence_bp": None, "source_ids": [f"FICTION-{g}-{d}"],
             "source_record_sha256s": ["0" * 64], "reason_codes": ["SYNTHETIC_ADAPTER_ONLY"]}
            for g in ("ESS", "RIS", "IAM")
            for d in ("software_development", "security", "deployment", "ai_readiness")
        ],
    }


class RecordingAdapter:
    def __init__(self, error_type):
        self.error_type = error_type
        self.calls: list[tuple[dict, dict]] = []
        self.reject = False
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def inspect(self, candidate, authority):
        self.calls.append((copy.deepcopy(candidate), copy.deepcopy(authority)))
        self.entered.set()
        if not self.release.wait(10):
            raise self.error_type("Synthetic test adapter release timed out")
        if self.reject:
            raise self.error_type("Synthetic adapter rejected the supplied test case")
        return synthetic_report()


class Runtime:
    def __init__(self, root: Path, mode: str, executable: str | None):
        from playwright.sync_api import sync_playwright
        self.root, self.mode = root, mode
        self.before = snapshot(root)
        self.wire_observations: list[dict] = []
        spec = importlib.util.spec_from_file_location("_basalt_r7q_workbench_server", root / "server.py")
        if spec is None or spec.loader is None:
            raise ValueError("could not load the selected server source")
        self.module = importlib.util.module_from_spec(spec)
        # Do not emit __pycache__ into a reviewed source tree.
        old_flag = sys.dont_write_bytecode
        try:
            sys.dont_write_bytecode = True
            spec.loader.exec_module(self.module)
        finally:
            sys.dont_write_bytecode = old_flag
        self.adapter = RecordingAdapter(self.module.WorkbenchError)
        self.server = self.module.create_server(port=0, adapter=self.adapter, static_root=root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"
        self.playwright = None
        self.browser = None
        try:
            self.playwright = sync_playwright().start()
            options = {"headless": True}
            if executable:
                options["executable_path"] = executable
            self.browser = self.playwright.chromium.launch(**options)
            self.browser_version = self.browser.version
            # Stop native mode immediately on policy/navigation failure. Never
            # relabel split-stage execution as a successful native fallback.
            if mode == "native":
                probe = self.browser.new_page()
                try:
                    response = probe.goto(self.origin + "/", timeout=8000)
                    if response is None or response.status != 200:
                        raise RuntimeError("native workbench document did not return HTTP 200")
                finally:
                    probe.close()
        except Exception:
            self.close()
            raise

    def close(self):
        self.adapter.release.set()
        if self.browser is not None:
            self.browser.close()
        if self.playwright is not None:
            self.playwright.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError("test HTTP server did not stop")

    def page(self):
        self.adapter.calls.clear()
        self.adapter.reject = False
        self.adapter.entered.clear()
        self.adapter.release.set()
        context = self.browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(3000)
        errors, blocked = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        # Prevent external resources in either mode. No changes to admin policy.
        def route(request_route):
            parsed = urlsplit(request_route.request.url)
            if parsed.scheme in {"http", "https"} and (
                parsed.hostname != "127.0.0.1" or parsed.port != self.server.server_port
            ):
                blocked.append(request_route.request.url)
                request_route.abort()
            else:
                request_route.continue_()
        context.route("**/*", route)
        if self.mode == "native":
            page.goto(self.origin + "/")
        else:
            html = (self.root / "index.html").read_text(encoding="utf-8")
            scripts = re.findall(r'<script\b[^>]*\bsrc=[\"\']([^\"\']+)', html)
            html = re.sub(r'<script\b[^>]*>.*?</script>', "", html, flags=re.S)
            html = re.sub(r'<link\b[^>]*>', "", html)
            page.set_content(html)
            page.add_style_tag(content=(self.root / "style.css").read_text(encoding="utf-8"))
            for script in scripts:
                page.add_script_tag(content=(self.root / script.lstrip("/")).read_text(encoding="utf-8"))
            # Deliberate test double. It performs no browser HTTP request. The
            # Python driver replays its captured body to the actual server later.
            page.evaluate("""() => {
                window.__r7qPending = [];
                window.fetch = (url, options) => new Promise(resolve => {
                    window.__r7qPending.push({url, options, resolve});
                });
            }""")
        page.wait_for_function("typeof inspectFiles === 'function'")
        return context, page, errors, blocked

    def replay(self, page) -> tuple[int, bytes]:
        pending = page.evaluate("""() => {
            const p = window.__r7qPending[0];
            return {url: p.url, method: p.options.method, body: p.options.body,
                    headers: p.options.headers};
        }""")
        if pending["url"] != "/api/inspect" or pending["method"] != "POST":
            raise AssertionError("application emitted an unexpected transport request")
        body = pending["body"].encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            conn.request("POST", "/api/inspect", body=body,
                         headers={**pending["headers"], "Origin": self.origin})
            response = conn.getresponse()
            code, raw = response.status, response.read()
        finally:
            conn.close()
        page.evaluate("""payload => {
            const p = window.__r7qPending.shift();
            p.resolve({ok: payload.code >= 200 && payload.code < 300, status: payload.code,
                       json: async () => JSON.parse(payload.text)});
        }""", {"code": code, "text": raw.decode("utf-8")})
        return code, body


class IntakeAcceptance(unittest.TestCase):
    runtime: Runtime

    def setUp(self):
        self.rt = type(self).runtime
        self.context, self.page, self.script_errors, self.external_requests = self.rt.page()
        self.addCleanup(self.context.close)
        self.requests = []
        self.page.on("request", lambda request: self.requests.append(request)
                     if request.method == "POST" else None)

    def tearDown(self):
        self.assertEqual(self.script_errors, [], "uncaught JavaScript error")
        self.assertEqual(self.external_requests, [], "page attempted an external request")

    def upload(self, candidate=b"{}", authority=b"{}"):
        for selector, name, raw in (("#candidateFile", "candidate.json", candidate),
                                     ("#authorityFile", "authority.json", authority)):
            if isinstance(raw, str):
                raw = raw.encode("utf-8")
            self.page.locator(selector).set_input_files({
                "name": name, "mimeType": "application/json", "buffer": raw,
            })

    def submit(self, candidate=b"{}", authority=b"{}", *, local_error=False):
        from playwright.sync_api import expect
        self.upload(candidate, authority)
        count = len(self.rt.adapter.calls)
        if local_error:
            self.page.locator("#inspectBtn").click()
            if self.rt.mode == "split":
                self.page.wait_for_function("document.querySelector('#error').textContent || window.__r7qPending.length")
                pending_count = self.page.evaluate("window.__r7qPending.length")
                if pending_count:
                    # Release an unexpected mocked request before failing this
                    # subcase, so it cannot leave the next subcase's button busy.
                    self.page.evaluate("""() => {
                        for (const p of window.__r7qPending.splice(0)) {
                            p.resolve({ok: false, status: 599,
                                json: async () => ({error: 'Harness cleanup of unexpected capture'})});
                        }
                    }""")
                    expect(self.page.locator("#inspectBtn")).to_be_enabled()
                self.assertEqual(pending_count, 0,
                                 "invalid file reached the mocked request boundary")
            else:
                self.page.wait_for_function("document.querySelector('#error').textContent || !document.querySelector('#inspectBtn').disabled")
            self.assertEqual(len(self.requests), 0, "invalid file emitted browser HTTP")
            expect(self.page.locator("#error")).not_to_be_empty()
            self.assertEqual(len(self.requests), 0, "invalid file emitted browser HTTP")
            self.assertEqual(len(self.rt.adapter.calls), count)
            return None, None
        if self.rt.mode == "split":
            self.page.locator("#inspectBtn").click()
            self.page.wait_for_function("window.__r7qPending.length || document.querySelector('#error').textContent")
            self.assertEqual(self.page.evaluate("window.__r7qPending.length"), 1,
                             self.page.locator("#error").inner_text())
            code, body = self.rt.replay(self.page)
        else:
            with self.page.expect_response(lambda r: r.url == self.rt.origin + "/api/inspect") as response:
                self.page.locator("#inspectBtn").click()
            code, body = response.value.status, response.value.request.post_data_buffer
        if code == 200:
            expect(self.page.locator("#matrix")).to_have_attribute("data-rendered-cells", "12")
        else:
            expect(self.page.locator("#error")).not_to_be_empty()
        self.rt.wire_observations.append({"test": self.id(), "http_status": code,
                                         "body": fingerprint(body), "adapter_calls": len(self.rt.adapter.calls) - count})
        return code, body

    def check_wire(self, actual: bytes, candidate: str, authority: str):
        expected = ('{"candidate":' + candidate + ',"authority":' + authority + '}').encode("utf-8")
        self.assertEqual(fingerprint(actual), fingerprint(expected), "original JSON fragments changed")

    def check_cleared(self):
        from playwright.sync_api import expect
        expect(self.page.locator("#matrix")).to_have_attribute("data-rendered-cells", "0")
        expect(self.page.locator("#note")).to_have_value("")
        expect(self.page.locator("#exportBtn")).to_be_disabled()

    def test_01_original_fragments_and_unicode(self):
        c = ' \n{ "integer": 9007199254740993, "text": "café 観察 📝", "escaped": "\\u0061" }\n'
        a = '{"order":2, "first":1,"spelling":1.2500e+2}\t'
        code, body = self.submit(c, a)
        self.assertEqual(code, 200)
        self.check_wire(body, c, a)
        self.assertEqual(self.rt.adapter.calls[-1][0]["integer"], 9007199254740993)
        self.assertEqual(self.rt.adapter.calls[-1][0]["escaped"], "a")

    def test_02_large_integer_in_both_documents(self):
        c, a = '{"n":9007199254740993}', '{"n":-9007199254740993}'
        code, body = self.submit(c, a)
        self.assertEqual(code, 200)
        self.check_wire(body, c, a)
        self.assertEqual([d["n"] for d in self.rt.adapter.calls[-1]], [9007199254740993, -9007199254740993])

    def test_03_finite_zero_decimal_and_literal_text(self):
        c, a = '{"zero":-0,"fraction":0.125,"literal":"1e400 is text"}', '{"yes":true,"missing":null}'
        code, body = self.submit(c, a)
        self.assertEqual(code, 200)
        self.check_wire(body, c, a)
        self.assertEqual(self.rt.adapter.calls[-1][0]["fraction"], 0.125)
        self.assertIsNone(self.rt.adapter.calls[-1][1]["missing"])

    def duplicate_cases(self, side):
        for raw in ('{"same":1,"same":2}', '{"nested":{"x":1,"x":2}}',
                    '{"array":[{"x":1,"\\u0078":2}]}'):
            with self.subTest(document=side, raw=raw):
                before = len(self.rt.adapter.calls)
                c, a = (raw, "{}") if side == "candidate" else ("{}", raw)
                code, body = self.submit(c, a)
                self.assertEqual(code, 400)
                self.check_wire(body, c, a)
                self.assertEqual(len(self.rt.adapter.calls), before)
                self.assertIn("duplicate JSON key", self.page.locator("#error").inner_text())
                self.check_cleared()

    def test_04_candidate_duplicates_reach_strict_server(self):
        self.duplicate_cases("candidate")

    def test_05_authority_duplicates_reach_strict_server(self):
        self.duplicate_cases("authority")

    def test_06_invalid_utf8_candidate(self):
        self.submit(b'{"text":"\xff"}', local_error=True)
        self.assertIn("Candidate", self.page.locator("#error").inner_text())
        self.check_cleared()

    def test_07_invalid_utf8_authority(self):
        self.submit(authority=b'{"text":"\xc3("}', local_error=True)
        self.assertIn("Authority", self.page.locator("#error").inner_text())
        self.check_cleared()

    def test_08_bom_is_not_silently_removed(self):
        for side in ("candidate", "authority"):
            with self.subTest(side=side):
                self.submit(**{side: b'\xef\xbb\xbf{}'}, local_error=True)

    def test_09_nonobjects_and_trailing_input(self):
        for raw in ('[]', 'null', 'true', '"text"', '{}{}', '{"x":', '{"x":01}'):
            with self.subTest(raw=raw):
                self.submit(raw, local_error=True)
                self.check_cleared()

    def test_10_individual_file_limit(self):
        large = b' ' * MIB + b'{}'
        for side in ("candidate", "authority"):
            with self.subTest(side=side):
                self.submit(**{side: large}, local_error=True)
                self.assertIn("1 MiB", self.page.locator("#error").inner_text())

    def test_11_exact_combined_body_limit(self):
        overhead = len('{"candidate":,"authority":}')
        c = '{"x":"' + 'x' * (MIB - 8) + '"}'
        a = '{"x":"' + 'y' * (MIB - 8 - overhead) + '"}'
        self.assertEqual(len(c), MIB)
        code, body = self.submit(c, a)
        self.assertEqual(code, 200)
        self.assertEqual(len(body), 2 * MIB)
        self.check_wire(body, c, a)

    def test_12_combined_overhead_is_counted(self):
        overhead = len('{"candidate":,"authority":}')
        c = '{"x":"' + 'x' * (MIB - 8) + '"}'
        a = '{"x":"' + 'y' * (MIB - 8 - overhead + 1) + '"}'
        self.submit(c, a, local_error=True)
        self.assertIn("2 MiB", self.page.locator("#error").inner_text())

    def test_13_adapter_error_is_visible_and_nonexportable(self):
        self.rt.adapter.reject = True
        code, _ = self.submit('{"synthetic":true}')
        self.assertEqual(code, 400)
        self.assertIn("Synthetic adapter rejected", self.page.locator("#error").inner_text())
        self.check_cleared()

    def test_14_failed_replacement_clears_prior_notes(self):
        self.submit()
        self.page.locator(".cell").first.click()
        self.page.locator("#note").fill("Synthetic previous-generation note")
        self.requests.clear()
        self.submit('{bad', local_error=True)
        self.check_cleared()

    def test_15_server_rejection_clears_prior_notes(self):
        self.submit()
        self.page.locator(".cell").first.click()
        self.page.locator("#note").fill("Synthetic prior note")
        code, _ = self.submit('{"x":1,"x":2}')
        self.assertEqual(code, 400)
        self.check_cleared()

    def test_16_download_retains_false_flags(self):
        self.submit()
        self.page.locator(".cell").first.click()
        note = "Synthetic café / 観察\nNo University findings."
        self.page.locator("#note").fill(note)
        with self.page.expect_download() as pending:
            self.page.locator("#exportBtn").click()
        path = pending.value.path()
        self.assertIsNotNone(path)
        draft = json.loads(Path(path).read_bytes())
        self.assertEqual(draft["status"], "DRAFT_NON_AUTHORITATIVE")
        self.assertEqual(draft["report_receipt_sha256"], "a" * 64)
        self.assertEqual(len(draft["cell_notes"]), 12)
        self.assertEqual(draft["cell_notes"][0]["analyst_note"], note)
        self.assertEqual(set(draft["authority"]), set(FLAGS))
        for flag in FLAGS:
            self.assertIs(draft["authority"][flag], False)


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.cases.append({"test": test.id(), "result": "PASS"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.cases.append({"test": test.id(), "result": "FAIL"})

    def addError(self, test, err):
        super().addError(test, err)
        self.cases.append({"test": test.id(), "result": "ERROR"})

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            kind = "FAIL" if issubclass(err[0], test.failureException) else "ERROR"
            self.cases.append({"test": subtest.id(), "result": kind})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="trusted workbench checkout directory")
    parser.add_argument("--mode", choices=("native", "split"), default="native")
    parser.add_argument("--out", required=True, type=Path, help="new output directory; never overwritten")
    parser.add_argument("--chromium", default=os.environ.get("CHROMIUM_EXECUTABLE") or shutil.which("chromium"))
    args = parser.parse_args(argv)
    root = args.source.resolve(strict=True)
    # Read and bind source before making any output directory.
    before = snapshot(root)
    out = args.out.absolute()
    if out == root or root in out.resolve().parents:
        parser.error("output directory must be outside the source checkout")
    out.mkdir(parents=False, exist_ok=False)
    receipt = {
        "schema": "uiowa-browser-http-acceptance/v1",
        "operation": "uiowa-browser-http-acceptance-basalt42r7q-20260919",
        "provenance": "Synthetic inputs and recording-adapter reports; actual test measurements.",
        "mode": args.mode, "started_at": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": sys.version, "platform": platform.platform(), "optimized": not __debug__},
        "source_before": before, "status": "BLOCKED", "tests_run": 0,
        "native_browser_http_verified": False, "parent_compiler_verified": False,
        "hosted_ci_verified": False, "cases": [], "wire_observations": [],
    }
    runtime = None
    log = io.StringIO()
    code = 2
    try:
        runtime = Runtime(root, args.mode, args.chromium)
        receipt["environment"]["chromium"] = runtime.browser_version
        IntakeAcceptance.runtime = runtime
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(IntakeAcceptance)
        result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=RecordedResult).run(suite)
        receipt.update(tests_run=result.testsRun, cases=result.cases,
                       failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
                       wire_observations=runtime.wire_observations)
        receipt["status"] = "PASS" if result.wasSuccessful() and result.testsRun == 16 and not result.skipped else "FAIL"
        receipt["native_browser_http_verified"] = args.mode == "native" and receipt["status"] == "PASS"
        code = 0 if receipt["status"] == "PASS" else 1
    except Exception as exc:
        receipt["blocked_reason"] = f"{type(exc).__name__}: {exc}"
        log.write(receipt["blocked_reason"] + "\n")
    finally:
        if runtime is not None:
            try:
                runtime.close()
            except Exception as exc:
                receipt["cleanup_error"] = str(exc)
                receipt["status"] = "FAIL"
                code = 2
        try:
            receipt["source_after"] = snapshot(root)
            receipt["source_unchanged"] = receipt["source_after"] == before
            if not receipt["source_unchanged"]:
                receipt["status"] = "FAIL"
                code = 1
        except Exception as exc:
            receipt["source_readback_error"] = str(exc)
            receipt["status"] = "FAIL"
            code = 2
        if receipt["status"] != "PASS":
            receipt["native_browser_http_verified"] = False
        (out / "receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        (out / "test-output.txt").write_text(log.getvalue(), encoding="utf-8")
    print(log.getvalue(), end="")
    print(json.dumps({k: receipt[k] for k in ("mode", "status", "tests_run", "native_browser_http_verified", "parent_compiler_verified")}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
