#!/usr/bin/env python3
"""
LOOM SURFACE SERVER -- read-only surfacing of a Muhlnickel container.

HOST BOUNDARY: this process performs exactly one kind of I/O: bounded READS of
container bytes ("rb" only) so the surface can display them. It never writes to
any .mno, never touches titan.gguf, never touches any registry, never evaluates
a gate, never advances state. It is SURFACING ONLY.

Port 7890. Binds 127.0.0.1 only.
"""

import os
import sys
import time
import json
import zlib
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = 7890
HOST = "127.0.0.1"

HERE = os.path.dirname(os.path.abspath(__file__))

# Allowlisted roots. ?file= may only resolve inside one of these.
ALLOW_ROOTS = [
    os.path.normcase(os.path.abspath(r"C:\Users\lucys\Desktop\MUHLNICKEL_LOOM")),
    os.path.normcase(os.path.abspath(r"C:\Users\lucys\TITAN_CUTOVER\loomtest")),
]

DEFAULT_FILE = os.path.join(ALLOW_ROOTS[0], "loom.mno")

# Names this server refuses to open under any circumstance.
FORBIDDEN_BASENAMES = {"titan.gguf"}

MAX_SNAPSHOT_ATTEMPTS = 8
RETRY_SLEEP = 0.004

# ---------------------------------------------------------------------------
# Snapshot engine: double-buffered coherent whole-file reads.
# ---------------------------------------------------------------------------


class Snapshot:
    __slots__ = ("path", "size", "mtime_ns", "crc", "gen", "data",
                 "chunk_size", "chunk_crcs", "read_ms", "attempts",
                 "consistent", "stamp")

    def __init__(self):
        self.path = None
        self.size = 0
        self.mtime_ns = 0
        self.crc = 0
        self.gen = ""
        self.data = b""
        self.chunk_size = 0
        self.chunk_crcs = []
        self.read_ms = 0.0
        self.attempts = 0
        self.consistent = False
        self.stamp = 0.0


_lock = threading.Lock()
# path -> Snapshot  (the FRONT buffer: last read proven internally coherent)
_front = {}


def _chunk_size_for(size):
    # aim for <= 4096 chunks, never smaller than 4 KiB
    cs = 4096
    while size // cs > 4096:
        cs *= 2
    return cs


def _chunk_crcs(data, cs):
    out = []
    n = len(data)
    i = 0
    while i < n:
        out.append(zlib.crc32(data[i:i + cs]) & 0xFFFFFFFF)
        i += cs
    return out


def read_coherent(path):
    """
    BACK BUFFER read. Verifies size + mtime marker BEFORE and AFTER a complete
    read of the file, and that the number of bytes actually returned equals the
    stated size. Retries on any inconsistency (the file is live and may mutate
    mid-read). Returns (Snapshot, err_string_or_None).

    A torn read is never promoted to the front buffer.
    """
    t0 = time.perf_counter()
    last_err = None
    for attempt in range(1, MAX_SNAPSHOT_ATTEMPTS + 1):
        try:
            st1 = os.stat(path)
            with open(path, "rb") as fh:          # <-- read-only, always
                data = fh.read()                  # <-- COMPLETE file
            st2 = os.stat(path)
        except OSError as e:
            # Surface the exact OS error verbatim.
            return None, "%s: [Errno %s] %s: %r" % (
                type(e).__name__, e.errno, e.strerror, getattr(e, "filename", path))
        except Exception as e:  # pragma: no cover
            return None, "%s: %s" % (type(e).__name__, e)

        ok = (st1.st_size == st2.st_size ==
              len(data)) and (st1.st_mtime_ns == st2.st_mtime_ns)
        if ok:
            snap = Snapshot()
            snap.path = path
            snap.size = len(data)
            snap.mtime_ns = st1.st_mtime_ns
            snap.crc = zlib.crc32(data) & 0xFFFFFFFF
            snap.gen = "%d:%d:%08x" % (snap.size, snap.mtime_ns, snap.crc)
            snap.data = data
            snap.chunk_size = _chunk_size_for(snap.size)
            snap.chunk_crcs = _chunk_crcs(data, snap.chunk_size)
            snap.read_ms = (time.perf_counter() - t0) * 1000.0
            snap.attempts = attempt
            snap.consistent = True
            snap.stamp = time.time()
            return snap, None
        last_err = ("torn read: stat1(size=%d,mtime=%d) read=%d "
                    "stat2(size=%d,mtime=%d)" % (st1.st_size, st1.st_mtime_ns,
                                                 len(data), st2.st_size, st2.st_mtime_ns))
        time.sleep(RETRY_SLEEP)
    return None, "INCOHERENT after %d attempts -- %s" % (MAX_SNAPSHOT_ATTEMPTS, last_err)


def get_snapshot(path, force=False):
    """
    Returns (snapshot_or_None, error_or_None, refreshed_bool).
    Cheap stat gate: only re-reads when the file's size/mtime marker moved.
    On an incoherent read the previous coherent FRONT buffer is retained -- a
    torn frame is never published.
    """
    with _lock:
        cur = _front.get(path)
    if not force and cur is not None:
        try:
            st = os.stat(path)
            if st.st_size == cur.size and st.st_mtime_ns == cur.mtime_ns:
                return cur, None, False
        except OSError as e:
            return None, "%s: [Errno %s] %s: %r" % (
                type(e).__name__, e.errno, e.strerror, getattr(e, "filename", path)), False

    snap, err = read_coherent(path)
    if snap is None:
        # keep the last coherent front buffer if we have one
        return cur, err, False
    with _lock:
        _front[path] = snap          # atomic buffer swap
    return snap, None, True


# ---------------------------------------------------------------------------
# Path allowlist
# ---------------------------------------------------------------------------


def resolve_target(qs):
    raw = (qs.get("file", [None])[0]) or DEFAULT_FILE
    try:
        p = os.path.abspath(os.path.realpath(raw))
    except Exception as e:
        return None, "bad path: %s" % e
    nc = os.path.normcase(p)
    if os.path.basename(nc) in FORBIDDEN_BASENAMES:
        return None, "refused: %s is not surfaceable by this viewer" % os.path.basename(p)
    for root in ALLOW_ROOTS:
        if nc == root or nc.startswith(root + os.sep):
            return p, None
    return None, ("not allowlisted: %r is outside the permitted roots %s"
                  % (p, ALLOW_ROOTS))


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = "LoomSurface/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # quiet

    def _send(self, code, body, ctype, extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, str(v))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def _json(self, code, obj, extra=None):
        self._send(code, json.dumps(obj), "application/json; charset=utf-8", extra)

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        route = u.path

        if route in ("/", "/index.html", "/loom_surface.html"):
            fp = os.path.join(HERE, "loom_surface.html")
            try:
                with open(fp, "rb") as fh:
                    body = fh.read()
            except OSError as e:
                self._send(500, "loom_surface.html missing: %s" % e, "text/plain")
                return
            self._send(200, body, "text/html; charset=utf-8")
            return

        if route == "/api/roots":
            self._json(200, {"roots": ALLOW_ROOTS, "default": DEFAULT_FILE})
            return

        if route == "/api/state":
            path, perr = resolve_target(qs)
            if perr:
                self._json(200, {"ok": False, "path": None, "error": perr,
                                 "kind": "policy"})
                return
            t0 = time.perf_counter()
            snap, err, refreshed = get_snapshot(path)
            poll_ms = (time.perf_counter() - t0) * 1000.0
            if snap is None:
                self._json(200, {"ok": False, "path": path, "error": err,
                                 "kind": "os", "server_time": time.time()})
                return
            self._json(200, {
                "ok": True,
                "path": path,
                "error": err,                 # non-null => live read was torn,
                                              # front buffer retained
                "size": snap.size,
                "mtime_ns": snap.mtime_ns,
                "crc32": "%08x" % snap.crc,
                "gen": snap.gen,
                "chunk_size": snap.chunk_size,
                "chunk_count": len(snap.chunk_crcs),
                "chunk_crcs": snap.chunk_crcs,
                "consistent": bool(snap.consistent and err is None),
                "read_attempts": snap.attempts,
                "read_ms": round(snap.read_ms, 3),
                "poll_ms": round(poll_ms, 3),
                "refreshed": refreshed,
                "snapshot_time": snap.stamp,
                "server_time": time.time(),
            })
            return

        if route == "/api/range":
            path, perr = resolve_target(qs)
            if perr:
                self._send(403, perr, "text/plain")
                return
            want_gen = qs.get("gen", [None])[0]
            with _lock:
                snap = _front.get(path)
            if snap is None:
                snap, err, _ = get_snapshot(path)
                if snap is None:
                    self._send(404, err or "no snapshot", "text/plain")
                    return
            if want_gen and want_gen != snap.gen:
                # The coherent buffer moved under the client. Never splice bytes
                # from two generations into one frame.
                self._send(409, "gen mismatch: have %s want %s" % (snap.gen, want_gen),
                           "text/plain", {"X-Loom-Gen": snap.gen})
                return
            try:
                off = int(qs.get("off", ["0"])[0])
                ln = int(qs.get("len", [str(snap.size)])[0])
            except ValueError:
                self._send(400, "bad off/len", "text/plain")
                return
            off = max(0, min(off, snap.size))
            ln = max(0, min(ln, snap.size - off))
            self._send(200, snap.data[off:off + ln], "application/octet-stream", {
                "X-Loom-Gen": snap.gen,
                "X-Loom-Size": snap.size,
                "X-Loom-Off": off,
                "X-Loom-Len": ln,
                "X-Loom-Consistent": "1" if snap.consistent else "0",
            })
            return

        self._send(404, "no route %s" % route, "text/plain")

    def do_POST(self):
        self._send(405, "this surface is read-only", "text/plain")

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST


def main():
    mimetypes.init()
    for r in ALLOW_ROOTS:
        if not os.path.isdir(r):
            try:
                os.makedirs(r, exist_ok=True)
            except OSError:
                pass
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    srv.daemon_threads = True
    print("LOOM SURFACE  http://%s:%d/" % (HOST, PORT))
    print("  default container : %s" % DEFAULT_FILE)
    print("  exists            : %s" % os.path.exists(DEFAULT_FILE))
    print("  allowlisted roots :")
    for r in ALLOW_ROOTS:
        print("      %s" % r)
    print("  READ-ONLY. No writes. Ctrl-C to stop.")
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
