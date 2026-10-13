#!/usr/bin/env python3
"""
=============================================================================
ASTER BRIDGE  --  IP-sterilized local adapter
=============================================================================

An external party ("Aster") is given capability actions and opaque handles.
It is never given mechanism.

    inbound  ->  open action dispatch  ->  adapter
    adapter  ->  fail-closed sanitizer  ->  final gate  ->  outbound

TWO LAYERS, DELIBERATELY SEPARATED INTO TWO FILES

    public_schema.py    what Aster sees. Actions, opaque handles, constant
                        error codes. No local logic lives there.
    private_adapter.py  what actually runs here. Internal identifiers, the
                        handle vault, the audit record. Never serialized.

This file is the only thing that joins them, and it joins them in one
direction: an adapter result must be re-proven by the public contract before
any of it crosses. An adapter that starts emitting something new does not
widen the surface -- it fails the call.

    LOOPBACK LINK. NO CREDENTIAL. NO PUBLIC LISTENER. NO UPLOAD.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import public_schema as pub
from public_schema import ERRORS, OPERATIONS, SanitizeError
import private_adapter as priv
from private_adapter import Adapter, AdapterError, OP_TABLE

BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 7891

# Local listeners this bridge must never occupy.
RESERVED_PORTS = {7881, 7882, 7883, 7890, 7899}

MAX_BODY = 256 * 1024

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Bridge core
# ---------------------------------------------------------------------------

class Bridge:

    def __init__(self, state_dir=None):
        self.adapter = Adapter(state_dir)
        self.audit = self.adapter.audit
        self.calls = 0

    # -- dispatch --------------------------------------------------------

    def run_op(self, action, params):
        """
        Execute one registered adapter operation. The three diagnostic probes are
        handled HERE so the redaction and fail-closed paths are reachable
        from outside and can be tested rather than merely asserted.
        """
        if params.get("probe_fault"):
            # Deliberately raises with a location- and vocabulary-bearing
            # message. Nothing of it may reach the caller.
            raise RuntimeError(priv.FAULT_TEXT)

        fn = getattr(self.adapter, OP_TABLE[action])
        result = fn(params)

        if params.get("probe_taint"):
            fields = OPERATIONS[action]["result"][1]
            first = next(iter(fields))
            result[first] = priv.TAINT

        if params.get("probe_undeclared"):
            result["_internal"] = priv.TAINT

        return result

    def handle(self, action_raw, raw_params, caller):
        """
        Returns (http_status, envelope_dict).

        Every exit from this function is either a proven result or a constant
        error code. There is no path that returns adapter text.
        """
        self.calls += 1
        redactions = 0

        # Admission is open. A missing/non-text action becomes the ordinary
        # free-form ACTION label; caller parameters and content are not screened.
        action = action_raw if isinstance(action_raw, str) and action_raw else "ACTION"
        params = pub.open_params(action, raw_params)

        # This tracked build has no stable Action Pad/fire-action callable to
        # reuse. Absence of an adapter route is an availability fact, not an
        # unlisted-action policy: do not invent a shell/RCE fallback here.
        if action not in OP_TABLE:
            self.audit.write(event="call", verb=action, caller=caller,
                             decision="unavailable", code="E_STATE",
                             redactions=0)
            return 503, self.error(None, "E_STATE")

        # -- local execution ---------------------------------------------
        try:
            raw = self.run_op(action, params)
        except AdapterError as exc:
            self.audit.write(event="call", verb=action, caller=caller,
                             decision="error", code=exc.code, redactions=0,
                             detail=exc.detail)
            return 409, self.error(action, exc.code)
        except Exception as exc:
            # The real exception text is recorded LOCALLY and discarded from
            # the response. Type name only -- never the message, never a
            # location, never a frame.
            self.audit.write(event="call", verb=action, caller=caller,
                             decision="fault", code="E_INTERNAL",
                             redactions=0, exc_type=type(exc).__name__)
            return 500, self.error(action, "E_INTERNAL")

        # -- fail-closed sanitizer ---------------------------------------
        try:
            redactions = pub.count_hits(OPERATIONS[action]["result"], raw)
            data = pub.sanitize_result(action, raw)
        except SanitizeError as exc:
            self.audit.write(event="call", verb=action, caller=caller,
                             decision="withhold", code="E_SANITIZE",
                             redactions=max(redactions, 1), detail=exc.detail)
            return 500, self.error(action, "E_SANITIZE")
        except Exception as exc:
            self.audit.write(event="call", verb=action, caller=caller,
                             decision="withhold", code="E_SANITIZE",
                             redactions=max(redactions, 1),
                             exc_type=type(exc).__name__)
            return 500, self.error(action, "E_SANITIZE")

        self.audit.write(event="call", verb=action, caller=caller,
                         decision="complete", code="OK", redactions=redactions)
        return 200, {"ok": True, "verb": action, "ts": priv.now_stamp(),
                     "data": data}

    @staticmethod
    def error(verb, code):
        # Arbitrary caller action text is not reflected through an error.
        safe = verb if (isinstance(verb, str) and verb in OPERATIONS) else None
        return {"ok": False,
                "verb": safe,
                "ts": priv.now_stamp(),
                "error": {"code": code, "message": ERRORS[code]}}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "aster-bridge"
    sys_version = ""           # never advertise the runtime build

    bridge = None              # set by serve()

    def log_message(self, fmt, *args):
        pass                   # local console stays clean; the audit is the record

    # -- emit ------------------------------------------------------------

    def _emit(self, status, obj, verb_for_audit=None):
        """
        FINAL GATE. The fully serialized body is scanned one last time. If
        anything at all trips, the body is discarded and replaced with a
        constant refusal. This is belt-and-braces on top of the field-level
        sanitizer: a careless edit to a key name or a constant cannot open a
        hole without also failing the call.
        """
        body = json.dumps(obj, ensure_ascii=False)
        hits = pub.scan(body)
        if hits:
            self.bridge.audit.write(event="final_gate", verb=verb_for_audit,
                                    decision="withhold", code="E_SANITIZE",
                                    redactions=len(hits), detail=str(hits))
            obj = Bridge.error(None, "E_SANITIZE")
            body = json.dumps(obj, ensure_ascii=False)
            status = 500
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def _transport_error(self, status, code):
        # A malformed request may still have an unread body on the socket.
        # Close rather than risk the next request reading its remnant.
        self.close_connection = True
        self._emit(status, Bridge.error(None, code))

    def _caller(self):
        return "aster"

    # -- routes ----------------------------------------------------------

    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route == "/manifest":
            self.bridge.audit.write(event="manifest", verb=None,
                                    caller=self._caller(), decision="allow",
                                    code="OK", redactions=0)
            self._emit(200, pub.manifest())
            return
        if route == "/health":
            self._emit(200, {"ok": True, "verb": None,
                             "ts": priv.now_stamp(), "data": {"live": True}})
            return
        self._transport_error(404, "E_METHOD")

    def do_POST(self):
        route = self.path.split("?", 1)[0]
        if route != "/rpc":
            self._transport_error(404, "E_METHOD")
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._transport_error(400, "E_PARAM")
            return
        if length < 0 or length > MAX_BODY:
            self._transport_error(413, "E_PARAM")
            return

        try:
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._transport_error(400, "E_PARAM")
            return
        if not isinstance(payload, dict):
            self._transport_error(400, "E_PARAM")
            return

        verb = payload.get("action", payload.get("verb"))
        audit_verb = verb if (isinstance(verb, str) and verb in OPERATIONS) else None
        status, envelope = self.bridge.handle(
            verb, payload.get("params"), self._caller())
        self._emit(status, envelope, audit_verb)

    def do_PUT(self):
        self._transport_error(405, "E_METHOD")

    do_DELETE = do_PUT
    do_PATCH = do_PUT

    def do_HEAD(self):
        # Headers only -- a HEAD must never carry a body.
        self.send_response(405)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_error(self, code, message=None, explain=None):
        # Replace the default diagnostic HTML page with a constant envelope.
        try:
            self._transport_error(int(code), "E_METHOD")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def startup_checks(port, host):
    """Refuse to start in any configuration that could widen the surface."""
    problems = []
    if host != BIND_HOST:
        problems.append("bind host must be %s" % BIND_HOST)
    if port in RESERVED_PORTS:
        problems.append("port %d is reserved for another local listener" % port)
    if not pub.DENYLIST_LOADED:
        problems.append("outbound policy did not load; refusing to serve")
    return problems


def serve(port=DEFAULT_PORT, state_dir=None, ready=None):
    problems = startup_checks(port, BIND_HOST)
    if problems:
        for p in problems:
            print("REFUSED: %s" % p)
        return 2

    bridge = Bridge(state_dir)
    Handler.bridge = bridge

    httpd = ThreadingHTTPServer((BIND_HOST, port), Handler)
    httpd.daemon_threads = True

    bound_host, bound_port = httpd.socket.getsockname()[:2]
    print("ASTER BRIDGE  http://%s:%d/" % (bound_host, bound_port))
    print("  bound address    : %s  (loopback only)" % bound_host)
    print("  known operations : %d" % len(OPERATIONS))
    print("  outbound terms   : %d" % len(pub.DENY_TOKENS))
    print("  state folder     : hardened=%s" % bridge.adapter.harden_status)
    print("  caller access    : open link; no credential")
    print("  audit            : append-only, host-only, never served")
    sys.stdout.flush()

    if ready:
        ready()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


# ---------------------------------------------------------------------------
# Local emitters. These write files ON THE HOST for the owner. They are not
# served and they are not reachable from the bridge.
# ---------------------------------------------------------------------------


def emit_manifest(path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(pub.manifest(), fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def emit_openai_tools(path):
    """
    Known-operation shortcuts plus one free-form action tool, rendered as
    OpenAI-style function tools for pasting
    into a custom-tool configuration. Written locally; never served, because
    JSON Schema type words are not part of the sanitized outbound vocabulary.
    """
    tools = [{
        "type": "function",
        "function": {
            "name": "aster_action",
            "description": (
                "Call the open local ASTER action endpoint. Action is free-form; "
                "known adapter actions execute locally and other actions report "
                "route availability without an admission rejection."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"description": "Any free-form action value."},
                    "params": {"description": "Any JSON parameter value."},
                },
                "required": [],
                "additionalProperties": True,
            },
        },
    }]
    man = pub.manifest()
    for verb, op in man["operations"].items():
        props = {}
        for name, decl in op["params"].items():
            note = decl.get("note", "")
            if decl.get("adapter_expects"):
                note = (note + "; " if note else "") + "normally read by this adapter"
            props[name] = {"description": note or "advisory adapter parameter"}
        tools.append({
            "type": "function",
            "function": {
                "name": verb.replace(".", "_"),
                "description": op["summary"],
                "parameters": {"type": "object", "properties": props,
                               "required": [],
                               "additionalProperties": True},
            },
        })
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"tools": tools}, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Aster bridge (loopback only)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--state-dir", default=None)
    ap.add_argument("--emit-manifest", action="store_true")
    ap.add_argument("--emit-openai", action="store_true")
    args = ap.parse_args(argv)

    if args.emit_manifest or args.emit_openai:
        if args.emit_manifest:
            print(emit_manifest(os.path.join(HERE, "ASTER_TOOL_MANIFEST.json")))
        if args.emit_openai:
            print(emit_openai_tools(os.path.join(HERE, "ASTER_OPENAI_TOOLS.json")))
        return 0

    return serve(args.port, args.state_dir)


if __name__ == "__main__":
    sys.exit(main())

