from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import os
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from . import cli
from .proof import (
    CAPTURE_SCHEMA, REQUIRED_FAMILIES, SchemaError, canonical_bytes,
    classify_exchange, compile_proof, loads_strict, normalize_bundle, verify_proof,
)


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def jr_result(i: int = 9, text: str = "ok") -> bytes:
    return canonical_bytes({"jsonrpc":"2.0","id":i,"result":{"isError":False,"content":[{"type":"text","text":text}]}})


def case(case_id: str, family: str, status: int, ctype: str, body: bytes, disp: str, expected_id: int = 9) -> dict:
    return {
        "id": case_id, "family": family, "status": status, "content_type": ctype,
        "body_base64": b64(body), "expected_jsonrpc_id": expected_id,
        "observed_client_disposition": disp,
        "client_event_sha256": h("client:"+case_id), "source_sha256": h("source:"+case_id),
    }


def complete_bundle(vulnerable: bool = True) -> dict:
    html = b"<!doctype html><html><body>landing</body></html>"
    login = b"<html><body><form><input type='password'>Log in</form></body></html>"
    mislabeled = b"<html><body>proxy error</body></html>"
    rpc_error = canonical_bytes({"jsonrpc":"2.0","id":9,"error":{"code":-32000,"message":"boom"}})
    tool_error = canonical_bytes({"jsonrpc":"2.0","id":9,"result":{"isError":True,"content":[{"type":"text","text":"tool failed"}]}})
    wrapped = jr_result(text="Upstream response:\n<html><body><form>Log in</form></body></html>")
    malformed = b'{"jsonrpc":"2.0","id":9,'
    valid = jr_result()
    rows = [
        case("html", "HTTP_200_HTML", 200, "text/html", html, "SUCCESS" if vulnerable else "ERROR"),
        case("login", "HTTP_200_LOGIN_HTML", 200, "text/html", login, "ERROR"),
        case("mislabeled", "HTTP_200_MISLABELED_HTML", 200, "application/json", mislabeled, "ERROR"),
        case("non2xx", "HTTP_NON_2XX", 503, "application/json", b'{}', "ERROR"),
        case("rpc-error", "JSON_RPC_ERROR", 200, "application/json", rpc_error, "ERROR"),
        case("tool-error", "MCP_TOOL_ERROR", 200, "application/json", tool_error, "ERROR"),
        case("wrapped", "MCP_WRAPPED_HTML", 200, "application/json", wrapped, "ERROR"),
        case("malformed", "MALFORMED_JSON", 200, "application/json", malformed, "ERROR"),
        case("control", "VALID_CONTROL", 200, "application/json", valid, "SUCCESS"),
    ]
    return {"schema":CAPTURE_SCHEMA,"client":{"name":"synthetic-client","version":"1.0"},"captured_at":"2026-09-14T00:00:00Z","cases":rows}


class ProofTests(unittest.TestCase):
    def test_complete_vulnerable_detects_false_success(self):
        self.assertEqual(compile_proof(complete_bundle(True))["proof"]["decision"], "FALSE_SUCCESS_DETECTED")

    def test_complete_safe_survives(self):
        self.assertEqual(compile_proof(complete_bundle(False))["proof"]["decision"], "SURVIVED")

    def test_deterministic(self):
        a = compile_proof(complete_bundle()); b = compile_proof(complete_bundle())
        self.assertEqual(canonical_bytes(a), canonical_bytes(b))

    def test_verify_tamper_fails(self):
        b = complete_bundle(); p = compile_proof(b); p["proof"]["decision"] = "SURVIVED"
        self.assertFalse(verify_proof(b, p))

    def test_receipt_contains_no_raw_body(self):
        raw = "Upstream response:"
        self.assertNotIn(raw, canonical_bytes(compile_proof(complete_bundle())).decode())

    def test_commitments_truth_labeled(self):
        p = compile_proof(complete_bundle())
        self.assertEqual(p["proof"]["commitment_authority"], "CALLER_PROVIDED_UNVERIFIED")
        self.assertTrue(all(f["commitment_authentication"] == "CALLER_PROVIDED_UNVERIFIED" for f in p["proof"]["findings"]))

    def test_unknown_content_type_rejected(self):
        body = canonical_bytes({"jsonrpc":"2.0","id":9,"result":{"isError":False,"content":[{"type":"bogus"}]}})
        c = classify_exchange(200,"application/json",body,9)
        self.assertEqual(c.decision,"REJECT"); self.assertIn("MCP_CONTENT_TYPE_UNSUPPORTED",c.reasons)

    def test_image_without_payload_rejected(self):
        for typ in ("image","audio","resource"):
            body = canonical_bytes({"jsonrpc":"2.0","id":9,"result":{"isError":False,"content":[{"type":typ}]}})
            c = classify_exchange(200,"application/json",body,9)
            self.assertEqual(c.decision,"REJECT")

    def test_text_extra_keys_rejected(self):
        body = canonical_bytes({"jsonrpc":"2.0","id":9,"result":{"isError":False,"content":[{"type":"text","text":"ok","x":1}]}})
        self.assertIn("MCP_CONTENT_ITEM_KEYS_INVALID", classify_exchange(200,"application/json",body,9).reasons)

    def test_result_extra_keys_rejected(self):
        body = canonical_bytes({"jsonrpc":"2.0","id":9,"result":{"isError":False,"content":[{"type":"text","text":"ok"}],"x":1}})
        self.assertIn("MCP_RESULT_KEYS_INVALID", classify_exchange(200,"application/json",body,9).reasons)

    def test_empty_content_rejected(self):
        body = canonical_bytes({"jsonrpc":"2.0","id":9,"result":{"isError":False,"content":[]}})
        self.assertIn("MCP_CONTENT_EMPTY", classify_exchange(200,"application/json",body,9).reasons)

    def test_prefixed_html_rejected(self):
        for text in ("Upstream response:\n<html><body>login</body></html>", "Error page follows: <!doctype html><html></html>"):
            c = classify_exchange(200,"application/json",jr_result(text=text),9)
            self.assertIn("MCP_WRAPPED_HTML", c.reasons)

    def test_plain_prose_html_word_not_overmatched(self):
        c = classify_exchange(200,"application/json",jr_result(text="Documentation says the HTML format is supported."),9)
        self.assertEqual(c.decision,"ACCEPT")

    def test_json_wrong_id_rejected(self):
        c = classify_exchange(200,"application/json",jr_result(i=10),9)
        self.assertIn("JSON_RPC_RESPONSE_ID_MISMATCH",c.reasons)

    def test_json_missing_id_rejected(self):
        body = canonical_bytes({"jsonrpc":"2.0","result":{"isError":False,"content":[{"type":"text","text":"ok"}]}})
        self.assertIn("JSON_RPC_RESPONSE_ID_MISSING", classify_exchange(200,"application/json",body,9).reasons)

    def test_sse_cross_id_error_then_success_rejected(self):
        a = json.dumps({"jsonrpc":"2.0","id":1,"error":{"code":-1,"message":"boom"}},separators=(",",":"))
        b = json.dumps({"jsonrpc":"2.0","id":2,"result":{"isError":False,"content":[{"type":"text","text":"ok"}]}},separators=(",",":"))
        body = f"data: {a}\n\ndata: {b}\n\n".encode()
        c = classify_exchange(200,"text/event-stream",body,1)
        self.assertEqual(c.decision,"REJECT"); self.assertIn("JSON_RPC_CROSS_ID_RESPONSE",c.reasons)

    def test_sse_notification_then_correlated_success_accepts(self):
        a = json.dumps({"jsonrpc":"2.0","method":"progress","params":{}},separators=(",",":"))
        b = jr_result(i=9).decode()
        body = f"data: {a}\n\ndata: {b}\n\n".encode()
        self.assertEqual(classify_exchange(200,"text/event-stream",body,9).decision,"ACCEPT")

    def test_sse_duplicate_correlated_rejected(self):
        b = jr_result(i=9).decode(); body = f"data: {b}\n\ndata: {b}\n\n".encode()
        self.assertIn("JSON_RPC_CORRELATED_RESPONSE_DUPLICATE", classify_exchange(200,"text/event-stream",body,9).reasons)

    def test_source_commitment_contradictory_reuse_rejected(self):
        b = complete_bundle(False); b["cases"][1]["source_sha256"] = b["cases"][0]["source_sha256"]
        with self.assertRaisesRegex(SchemaError,"source_sha256"):
            normalize_bundle(b)

    def test_client_commitment_contradictory_reuse_rejected(self):
        b = complete_bundle(False); b["cases"][1]["client_event_sha256"] = b["cases"][0]["client_event_sha256"]
        with self.assertRaisesRegex(SchemaError,"client_event_sha256"):
            normalize_bundle(b)

    def test_same_source_commitment_same_generation_allowed(self):
        b = complete_bundle(False)
        clone = copy.deepcopy(b["cases"][0]); clone["id"]="html2"; clone["family"]="HTTP_200_HTML"; clone["client_event_sha256"] = h("client:html2")
        b["cases"].append(clone)
        normalize_bundle(b)

    def test_high_surrogate_rejected(self):
        b = complete_bundle(False); b["client"]["name"] = loads_strict(r'"\ud800"')
        with self.assertRaises(SchemaError): compile_proof(b)

    def test_low_surrogate_rejected(self):
        b = complete_bundle(False); b["client"]["version"] = loads_strict(r'"\udfff"')
        with self.assertRaises(SchemaError): compile_proof(b)

    def test_surrogate_in_mcp_text_rejected(self):
        bad = loads_strict(r'"\ud800"')
        body = canonical_bytes({"jsonrpc":"2.0","id":9,"result":{"isError":False,"content":[{"type":"text","text":"ok"}]}})
        obj = loads_strict(body); obj["result"]["content"][0]["text"] = bad
        raw = json.dumps(obj, ensure_ascii=True, separators=(",",":")).encode()
        self.assertIn("MCP_TEXT_CONTENT_INVALID", classify_exchange(200,"application/json",raw,9).reasons)

    def test_duplicate_case_id_rejected(self):
        b=complete_bundle(False); b["cases"][1]["id"] = b["cases"][0]["id"]
        with self.assertRaises(SchemaError): normalize_bundle(b)

    def test_bool_status_rejected(self):
        b=complete_bundle(False); b["cases"][0]["status"] = True
        with self.assertRaises(SchemaError): normalize_bundle(b)

    def test_bool_expected_id_rejected(self):
        b=complete_bundle(False); b["cases"][0]["expected_jsonrpc_id"] = True
        with self.assertRaises(SchemaError): normalize_bundle(b)

    def test_unknown_bundle_key_rejected(self):
        b=complete_bundle(False); b["extra"] = 1
        with self.assertRaises(SchemaError): normalize_bundle(b)

    def test_bad_base64_rejected(self):
        b=complete_bundle(False); b["cases"][0]["body_base64"]="***"
        with self.assertRaises(SchemaError): normalize_bundle(b)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(SchemaError): loads_strict('{"a":1,"a":2}')

    def test_nonfinite_rejected(self):
        with self.assertRaises(SchemaError): loads_strict('{"a":NaN}')

    def test_invalid_utf8_rejected(self):
        with self.assertRaises(SchemaError): loads_strict(b'\xff')

    def test_non2xx_is_reject(self):
        c=classify_exchange(503,"application/json",b'{}',9)
        self.assertIn("HTTP_STATUS_NOT_SUCCESS",c.reasons)

    def test_unsupported_success_media_rejected(self):
        c=classify_exchange(200,"text/plain",b'ok',9)
        self.assertIn("UNSUPPORTED_SUCCESS_MEDIA_TYPE",c.reasons)

    def test_raw_html_json_tagged_mislabeled(self):
        c=classify_exchange(200,"application/json",b'<html>x</html>',9)
        self.assertIn("HTTP_200_MISLABELED_HTML",c.tags)

    def test_missing_family_holds(self):
        b=complete_bundle(False); b["cases"] = b["cases"][:-1]
        self.assertEqual(compile_proof(b)["proof"]["decision"],"HOLD_INCOMPLETE_MATRIX")

    def test_required_family_count(self):
        self.assertEqual(len(REQUIRED_FAMILIES),9)


class CliTests(unittest.TestCase):
    def _write_bundle(self, td: str, bundle: dict | None = None) -> str:
        p=os.path.join(td,"bundle.json")
        with open(p,"wb") as f: f.write(canonical_bytes(bundle or complete_bundle(False)))
        return p

    def test_cli_compile_verify(self):
        with tempfile.TemporaryDirectory() as td:
            src=self._write_bundle(td); out=os.path.join(td,"proof.json")
            with redirect_stdout(io.StringIO()): self.assertEqual(cli.main(["compile",src,"--out",out]),0)
            with redirect_stdout(io.StringIO()): self.assertEqual(cli.main(["verify",src,out]),0)

    def test_cli_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            src=self._write_bundle(td); out=os.path.join(td,"proof.json"); open(out,"wb").close()
            with redirect_stderr(io.StringIO()): self.assertEqual(cli.main(["compile",src,"--out",out]),2)

    def test_read_regular_detects_same_size_generation_change(self):
        with tempfile.TemporaryDirectory() as td:
            p=os.path.join(td,"x")
            with open(p,"wb") as f: f.write(b"abcd")
            real_fstat=os.fstat
            fd_holder={"n":0}
            def fake_fstat(fd):
                st=real_fstat(fd); fd_holder["n"]+=1
                if fd_holder["n"] == 2:
                    return types.SimpleNamespace(st_dev=st.st_dev,st_ino=st.st_ino,st_mode=st.st_mode,st_nlink=st.st_nlink,st_size=st.st_size,st_mtime_ns=st.st_mtime_ns+1,st_ctime_ns=st.st_ctime_ns+1)
                return st
            with mock.patch.object(cli.os,"fstat",side_effect=fake_fstat):
                with self.assertRaisesRegex(Exception,"generation changed while reading"): cli._read_regular(p)

    def test_read_regular_detects_path_rebind(self):
        with tempfile.TemporaryDirectory() as td:
            p=os.path.join(td,"x")
            with open(p,"wb") as f: f.write(b"abcd")
            real_lstat=os.lstat; calls={"n":0}
            def fake_lstat(path):
                st=real_lstat(path); calls["n"]+=1
                if calls["n"] == 2:
                    return types.SimpleNamespace(st_dev=st.st_dev,st_ino=st.st_ino+1,st_mode=st.st_mode,st_nlink=st.st_nlink,st_size=st.st_size,st_mtime_ns=st.st_mtime_ns,st_ctime_ns=st.st_ctime_ns)
                return st
            with mock.patch.object(cli.os,"lstat",side_effect=fake_lstat):
                with self.assertRaisesRegex(Exception,"no longer names retained generation"): cli._read_regular(p)

    def test_cli_surrogate_is_structured_error(self):
        with tempfile.TemporaryDirectory() as td:
            raw=canonical_bytes(complete_bundle(False)).decode()
            obj=json.loads(raw); obj["client"]["name"]="\ud800"
            p=os.path.join(td,"bad.json")
            with open(p,"w",encoding="utf-8") as f: json.dump(obj,f,ensure_ascii=True,separators=(",",":"))
            err=io.StringIO()
            with redirect_stderr(err): rc=cli.main(["demo",p])
            self.assertEqual(rc,2); self.assertIn('"ok":false',err.getvalue()); self.assertNotIn("Traceback",err.getvalue())


if __name__ == "__main__":
    unittest.main()
