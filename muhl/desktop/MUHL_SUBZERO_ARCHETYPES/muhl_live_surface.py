#!/usr/bin/env python3
"""
MUHLNICKEL LIVE BINARY SURFACE
Built by Bryce Muhlnickel

An instrument that SURFACES the live state of titan.gguf.
Host verb: SURFACE only — bounded reads, no writes, no computation, no gate evaluation.

Usage:
    python muhl_live_surface.py [--port 7880] [--no-browser]

Endpoints:
    GET  /              — dashboard (Matrix rain + human-readable toggle)
    GET  /stream        — SSE stream of byte changes
    GET  /api/state     — current snapshot of all watched addresses
    GET  /api/changes   — changes since ?since=<epoch_ms>
    GET  /api/circuit/<name> — full state of a named circuit
    GET  /api/rings     — all ring states
    GET  /api/reservoir — reservoir state
    GET  /api/log       — last 1000 interpretability log entries
    GET  /api/stats     — summary statistics
    POST /api/annotate  — add annotation to an address
"""

import argparse
import json
import mmap
import os
import struct
import sys
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TITAN_PATH = r"C:\llm\models\titan.gguf"
REGISTRY_PATH = r"C:\llm\models\titan_circuits.json"
LOG_DIR = Path(r"C:\Users\lucys\OneDrive\Desktop\MUHLNICKEL_BUILD_LAB_20260801_025117\interpretability_logs")
POLL_INTERVAL = 0.1  # 100ms heartbeat
MAX_LOG_ENTRIES = 10000
MAX_SSE_QUEUE = 500

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
registry = {}
ring_info = []          # list of {name, fwd, rev, carry, recv, offset, len}
reservoir_info = {}
circuit_regions = []    # list of {name, offset, len, ...} for address lookup
watch_addrs = {}        # addr -> {name, field, circuit}
change_log = deque(maxlen=MAX_LOG_ENTRIES)
annotations = {}        # addr -> [annotation_text, ...]
sse_clients = []        # list of queue objects
stats = {
    "start_time": 0,
    "total_changes": 0,
    "changes_per_circuit": {},
    "ring_activity": [0] * 1024,
    "last_file_size": 0,
    "last_file_mtime": 0,
}
prev_values = {}        # addr -> byte_value
mm = None               # mmap object
titan_fh = None         # file handle
lock = threading.Lock()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_file_handle = None
log_file_hour = None

def ensure_log_dir():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

def get_log_file():
    global log_file_handle, log_file_hour
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y%m%d_%H")
    if hour_key != log_file_hour:
        if log_file_handle:
            log_file_handle.close()
        ensure_log_dir()
        path = LOG_DIR / f"surface_{hour_key}.jsonl"
        log_file_handle = open(path, "a", encoding="utf-8")
        log_file_hour = hour_key
    return log_file_handle

def log_change(entry):
    """Write an interpretability log entry."""
    try:
        fh = get_log_file()
        fh.write(json.dumps(entry) + "\n")
        fh.flush()
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------
def load_registry():
    global registry, ring_info, reservoir_info, circuit_regions, watch_addrs

    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            registry = json.load(f)
    except Exception as e:
        print(f"[WARN] Cannot load registry: {e}")
        registry = {}
        return

    ring_info = []
    circuit_regions = []
    watch_addrs = {}

    for name, entry in registry.items():
        if not isinstance(entry, dict):
            continue

        # Collect circuit regions
        offset = entry.get("offset")
        length = entry.get("len")
        if offset is not None and length is not None:
            circuit_regions.append({
                "name": name,
                "offset": offset,
                "len": length,
                "depth": entry.get("depth") or entry.get("depth_ticks"),
                "n_gate": entry.get("n_gate"),
                "n_in": entry.get("n_in"),
                "n_out": entry.get("n_out"),
                "format": entry.get("format"),
                "magic": entry.get("magic"),
                "powered_by": entry.get("powered_by"),
            })

        # Collect ring info (first 1024 non-STALE nring2_NNN)
        if name.startswith("nring2_") and "STALE" not in name and ".gates" not in name and ".rail" not in name:
            ram = entry.get("ram", {})
            if ram:
                idx = name.replace("nring2_", "")
                try:
                    idx_num = int(idx)
                except ValueError:
                    continue
                if idx_num < 1024:
                    ri = {
                        "name": name,
                        "index": idx_num,
                        "fwd": ram.get("fwd"),
                        "rev": ram.get("rev"),
                        "carry": ram.get("carry"),
                        "recv": ram.get("recv"),
                        "offset": entry.get("offset"),
                        "len": entry.get("len"),
                    }
                    ring_info.append(ri)
                    # Watch fwd byte for pulse detection
                    if ri["fwd"] is not None:
                        watch_addrs[ri["fwd"]] = {"name": name, "field": "fwd", "circuit": name}
                    if ri["recv"] is not None:
                        watch_addrs[ri["recv"]] = {"name": name, "field": "recv", "circuit": name}

        # Reservoir
        if name == "muhl_reservoir":
            reservoir_info = entry
            inp = entry.get("input_addr")
            if inp is not None:
                watch_addrs[inp] = {"name": "muhl_reservoir", "field": "input", "circuit": "muhl_reservoir"}

    ring_info.sort(key=lambda r: r["index"])

    # Sort circuit regions by offset for binary search
    circuit_regions.sort(key=lambda c: c["offset"])

    # Add circuit output addresses to watch list
    for name, entry in registry.items():
        if not isinstance(entry, dict):
            continue
        out_base = entry.get("out_base")
        if out_base is not None:
            watch_addrs[out_base] = {"name": name, "field": "output", "circuit": name}
        recv = entry.get("recv")
        if recv is not None and recv not in watch_addrs:
            watch_addrs[recv] = {"name": name, "field": "recv", "circuit": name}

    print(f"[INFO] Registry loaded: {len(registry)} entries, {len(ring_info)} rings, {len(circuit_regions)} regions, {len(watch_addrs)} watched addresses")


def lookup_circuit(addr):
    """Find which circuit an address belongs to using binary search."""
    lo, hi = 0, len(circuit_regions) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        c = circuit_regions[mid]
        if addr < c["offset"]:
            hi = mid - 1
        elif addr >= c["offset"] + c["len"]:
            lo = mid + 1
        else:
            return c["name"]
    return None


# ---------------------------------------------------------------------------
# Binary reading (SURFACE only — bounded reads)
# ---------------------------------------------------------------------------
def open_titan():
    global mm, titan_fh
    try:
        titan_fh = open(TITAN_PATH, "rb")
        mm = mmap.mmap(titan_fh.fileno(), 0, access=mmap.ACCESS_READ)
        print(f"[INFO] titan.gguf mapped read-only: {mm.size():,} bytes")
        return True
    except Exception as e:
        print(f"[ERROR] Cannot open titan.gguf: {e}")
        return False


def read_byte(addr):
    """Read a single byte from the mapped file. Returns None if out of range."""
    if mm is None:
        return None
    if 0 <= addr < mm.size():
        return mm[addr]
    return None


def read_bytes(addr, length):
    """Read multiple bytes from the mapped file."""
    if mm is None:
        return None
    if 0 <= addr < mm.size() and addr + length <= mm.size():
        return mm[addr:addr + length]
    return None


# ---------------------------------------------------------------------------
# Heartbeat / polling thread
# ---------------------------------------------------------------------------
def heartbeat_loop():
    """Main polling loop — reads watched addresses, detects changes, streams events."""
    global prev_values

    while True:
        try:
            now_ms = int(time.time() * 1000)
            changes = []

            # Check file metadata
            try:
                st = os.stat(TITAN_PATH)
                new_size = st.st_size
                new_mtime = st.st_mtime
                if stats["last_file_size"] and new_size != stats["last_file_size"]:
                    evt = {
                        "type": "file_growth",
                        "ts": now_ms,
                        "old_size": stats["last_file_size"],
                        "new_size": new_size,
                        "delta": new_size - stats["last_file_size"],
                    }
                    changes.append(evt)
                    log_change(evt)
                stats["last_file_size"] = new_size
                stats["last_file_mtime"] = new_mtime
            except Exception:
                pass

            # Scan watched addresses
            for addr, info in watch_addrs.items():
                val = read_byte(addr)
                if val is None:
                    continue
                old = prev_values.get(addr)
                if old is not None and val != old:
                    circuit_name = info.get("circuit", lookup_circuit(addr) or "unknown")
                    entry = {
                        "type": "byte_change",
                        "ts": now_ms,
                        "offset": addr,
                        "old": old,
                        "new": val,
                        "circuit": circuit_name,
                        "field": info.get("field", ""),
                        "region": info.get("name", ""),
                    }
                    changes.append(entry)
                    log_change(entry)

                    with lock:
                        change_log.append(entry)
                        stats["total_changes"] += 1
                        stats["changes_per_circuit"][circuit_name] = stats["changes_per_circuit"].get(circuit_name, 0) + 1
                        # Track ring activity
                        if circuit_name.startswith("nring2_"):
                            try:
                                idx = int(circuit_name.replace("nring2_", ""))
                                if 0 <= idx < 1024:
                                    stats["ring_activity"][idx] += 1
                            except ValueError:
                                pass

                prev_values[addr] = val

            # Also do a broader sample: read 256 evenly-spaced bytes across the file
            # to build the heatmap data
            if mm is not None:
                file_size = mm.size()
                sample_count = 256
                sample_step = file_size // sample_count
                heatmap_changes = []
                for i in range(sample_count):
                    sample_addr = i * sample_step
                    val = read_byte(sample_addr)
                    if val is not None:
                        key = f"_hm_{i}"
                        old = prev_values.get(key)
                        if old is not None and val != old:
                            heatmap_changes.append({"idx": i, "addr": sample_addr, "old": old, "new": val})
                        prev_values[key] = val
                if heatmap_changes:
                    changes.append({
                        "type": "heatmap_delta",
                        "ts": now_ms,
                        "cells": heatmap_changes,
                    })

            # Send SSE to all connected clients
            if changes:
                data = json.dumps(changes)
                dead = []
                for i, q in enumerate(sse_clients):
                    try:
                        if len(q) < MAX_SSE_QUEUE:
                            q.append(data)
                    except Exception:
                        dead.append(i)
                for i in reversed(dead):
                    sse_clients.pop(i)

        except Exception as e:
            print(f"[ERROR] heartbeat: {e}")

        time.sleep(POLL_INTERVAL)


# Also sample ring states in bulk periodically (every second)
def ring_bulk_sample():
    """Sample all 1024 ring fwd bytes once per second for the dashboard."""
    while True:
        try:
            now_ms = int(time.time() * 1000)
            states = []
            for ri in ring_info[:1024]:
                fwd = ri.get("fwd")
                if fwd is not None:
                    val = read_byte(fwd)
                    states.append(val if val is not None else 0)
                else:
                    states.append(0)

            data = json.dumps([{
                "type": "ring_bulk",
                "ts": now_ms,
                "states": states,
            }])
            dead = []
            for i, q in enumerate(sse_clients):
                try:
                    if len(q) < MAX_SSE_QUEUE:
                        q.append(data)
                except Exception:
                    dead.append(i)
            for i in reversed(dead):
                sse_clients.pop(i)
        except Exception as e:
            print(f"[ERROR] ring_bulk_sample: {e}")

        time.sleep(1.0)


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------
class SurfaceHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # Suppress default logging

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/":
            self.serve_dashboard()
        elif path == "/stream":
            self.serve_sse()
        elif path == "/api/state":
            self.api_state()
        elif path == "/api/changes":
            since = int(params.get("since", ["0"])[0])
            self.api_changes(since)
        elif path.startswith("/api/circuit/"):
            name = path[len("/api/circuit/"):]
            self.api_circuit(name)
        elif path == "/api/rings":
            self.api_rings()
        elif path == "/api/reservoir":
            self.api_reservoir()
        elif path == "/api/log":
            limit = int(params.get("limit", ["1000"])[0])
            self.api_log(limit)
        elif path == "/api/stats":
            self.api_stats()
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/annotate":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                addr = data["address"]
                text = data["text"]
                if addr not in annotations:
                    annotations[addr] = []
                annotations[addr].append({
                    "text": text,
                    "ts": int(time.time() * 1000),
                })
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"error": str(e)}, 400)
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # --- API endpoints ---

    def api_state(self):
        """Current snapshot of all watched addresses."""
        snapshot = {}
        for addr, info in watch_addrs.items():
            val = read_byte(addr)
            snapshot[str(addr)] = {
                "value": val,
                "hex": f"0x{val:02x}" if val is not None else None,
                "circuit": info.get("circuit"),
                "field": info.get("field"),
                "name": info.get("name"),
            }
        self.send_json({"ts": int(time.time() * 1000), "addresses": snapshot})

    def api_changes(self, since):
        """All changes since a timestamp."""
        with lock:
            result = [e for e in change_log if e.get("ts", 0) >= since]
        self.send_json({"since": since, "count": len(result), "changes": result[-1000:]})

    def api_circuit(self, name):
        """Full state of a named circuit."""
        entry = registry.get(name)
        if entry is None:
            self.send_json({"error": f"circuit '{name}' not found"}, 404)
            return
        result = dict(entry) if isinstance(entry, dict) else {"value": entry}
        result["name"] = name

        # Read first 64 bytes of circuit data
        offset = entry.get("offset") if isinstance(entry, dict) else None
        if offset is not None:
            raw = read_bytes(offset, min(64, entry.get("len", 64)))
            if raw is not None:
                result["head_bytes"] = [b for b in raw]
                result["head_hex"] = raw.hex()

        # Read output if available
        out_base = entry.get("out_base") if isinstance(entry, dict) else None
        if out_base is not None:
            n_out = entry.get("n_out", 1)
            raw = read_bytes(out_base, min(n_out, 256))
            if raw is not None:
                result["output_bytes"] = [b for b in raw]
                result["output_hex"] = raw.hex()

        self.send_json(result)

    def api_rings(self):
        """All ring states."""
        rings = []
        for ri in ring_info[:1024]:
            fwd_val = read_byte(ri["fwd"]) if ri.get("fwd") else None
            rev_val = read_byte(ri["rev"]) if ri.get("rev") else None
            recv_val = read_byte(ri["recv"]) if ri.get("recv") else None
            rings.append({
                "name": ri["name"],
                "index": ri["index"],
                "fwd": fwd_val,
                "rev": rev_val,
                "recv": recv_val,
                "fwd_addr": ri.get("fwd"),
                "rev_addr": ri.get("rev"),
                "recv_addr": ri.get("recv"),
            })
        self.send_json({"count": len(rings), "rings": rings})

    def api_reservoir(self):
        """Reservoir state."""
        result = dict(reservoir_info)
        inp = reservoir_info.get("input_addr")
        if inp is not None:
            val = read_byte(inp)
            result["input_value"] = val
            result["input_hex"] = f"0x{val:02x}" if val is not None else None
        self.send_json(result)

    def api_log(self, limit):
        """Last N interpretability log entries."""
        with lock:
            entries = list(change_log)[-limit:]
        self.send_json({"count": len(entries), "entries": entries})

    def api_stats(self):
        """Summary statistics."""
        with lock:
            s = dict(stats)
            s["uptime_s"] = int(time.time() - s["start_time"]) if s["start_time"] else 0
            s["log_size"] = len(change_log)
            s["sse_clients"] = len(sse_clients)
            s["watched_addresses"] = len(watch_addrs)
            s["ring_count"] = len(ring_info)
            s["circuit_count"] = len(circuit_regions)
        self.send_json(s)

    # --- SSE ---

    def serve_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = deque(maxlen=MAX_SSE_QUEUE)
        sse_clients.append(q)

        try:
            # Send initial state
            init_data = json.dumps([{
                "type": "init",
                "ts": int(time.time() * 1000),
                "file_size": stats["last_file_size"],
                "ring_count": len(ring_info),
                "circuit_count": len(circuit_regions),
                "watched": len(watch_addrs),
            }])
            self.wfile.write(f"data: {init_data}\n\n".encode())
            self.wfile.flush()

            while True:
                if q:
                    data = q.popleft()
                    self.wfile.write(f"data: {data}\n\n".encode())
                    self.wfile.flush()
                else:
                    # keepalive
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            try:
                sse_clients.remove(q)
            except ValueError:
                pass

    # --- Dashboard ---

    def serve_dashboard(self):
        html = build_dashboard_html()
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Dashboard HTML builder
# ---------------------------------------------------------------------------
def build_dashboard_html():
    # Build a JSON blob of circuit info for the client
    circuits_json = []
    for c in circuit_regions[:500]:  # top 500 by offset
        circuits_json.append({
            "name": c["name"],
            "offset": c["offset"],
            "len": c["len"],
            "depth": c["depth"],
            "n_gate": c["n_gate"],
            "format": c["format"],
            "magic": c["magic"],
            "powered_by": c["powered_by"],
        })

    ring_json = []
    for ri in ring_info[:1024]:
        ring_json.append({
            "name": ri["name"],
            "index": ri["index"],
            "fwd": ri.get("fwd"),
            "rev": ri.get("rev"),
            "recv": ri.get("recv"),
        })

    reservoir_json = {
        "input_addr": reservoir_info.get("input_addr"),
        "offset": reservoir_info.get("offset"),
        "len": reservoir_info.get("len"),
        "ring_count": reservoir_info.get("ring_count"),
        "depth": reservoir_info.get("depth"),
    }

    file_size = stats.get("last_file_size", 0) or 0

    return DASHBOARD_HTML.replace(
        "/*__CIRCUITS_JSON__*/", json.dumps(circuits_json)
    ).replace(
        "/*__RINGS_JSON__*/", json.dumps(ring_json)
    ).replace(
        "/*__RESERVOIR_JSON__*/", json.dumps(reservoir_json)
    ).replace(
        "/*__FILE_SIZE__*/", str(file_size)
    )


# ---------------------------------------------------------------------------
# The Dashboard — one self-contained HTML string
# ---------------------------------------------------------------------------
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MUHLNICKEL Live Binary Surface</title>
<style>
/* ================================================================
   MUHLNICKEL LIVE BINARY SURFACE — Matrix Rain + Human Readable
   Dark theme, copper/gold/green accents
   ================================================================ */

:root {
  --bg: #0a0a08;
  --surface: #111110;
  --surface-2: #1a1a17;
  --border: #2a2a24;
  --text: #e0dfd0;
  --text-dim: #888878;
  --text-muted: #555548;
  --copper: #cd7f32;
  --copper-bright: #e8a84c;
  --gold: #daa520;
  --gold-bright: #ffd700;
  --matrix-green: #00ff41;
  --matrix-green-dim: #008f11;
  --matrix-green-dark: #003b00;
  --ring-copper: #b87333;
  --active-white: #ffffff;
  --fab-red: #ff3333;
  --reservoir-blue: #3399ff;
  --mono: 'Cascadia Mono', 'Consolas', 'Courier New', monospace;
  --sans: system-ui, -apple-system, 'Segoe UI', sans-serif;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--mono);
  overflow: hidden;
  width: 100vw;
  height: 100vh;
}

/* ---- Matrix Rain Canvas ---- */
#matrix-canvas {
  position: fixed;
  top: 0; left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 1;
}

/* ---- Overlays ---- */
.overlay {
  position: fixed;
  z-index: 10;
  pointer-events: none;
}
.overlay > * { pointer-events: auto; }

/* Top bar */
#top-bar {
  top: 0; left: 0; right: 0;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: rgba(10,10,8,0.85);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
  z-index: 20;
}

#top-bar h1 {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 2px;
  color: var(--copper-bright);
  text-transform: uppercase;
}

#top-bar .status-lights {
  display: flex;
  gap: 16px;
  align-items: center;
  font-size: 11px;
  color: var(--text-dim);
}

.status-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  display: inline-block;
  margin-right: 4px;
}
.status-dot.live { background: var(--matrix-green); box-shadow: 0 0 6px var(--matrix-green); }
.status-dot.idle { background: var(--text-muted); }

#view-toggle {
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--copper-bright);
  padding: 6px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 1px;
  transition: all 0.2s;
}
#view-toggle:hover {
  background: var(--copper);
  color: var(--bg);
}

/* Ring pulse monitor — bottom left */
#ring-monitor {
  bottom: 60px; left: 12px;
  width: 340px;
  max-height: 220px;
  background: rgba(10,10,8,0.88);
  backdrop-filter: blur(6px);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  overflow: hidden;
}

#ring-monitor h3 {
  font-size: 10px;
  letter-spacing: 1.5px;
  color: var(--copper);
  margin-bottom: 6px;
  text-transform: uppercase;
}

#ring-grid {
  display: grid;
  grid-template-columns: repeat(32, 1fr);
  gap: 1px;
}

.ring-cell {
  width: 100%; aspect-ratio: 1;
  border-radius: 1px;
  background: var(--matrix-green-dark);
  transition: background 0.3s, box-shadow 0.3s;
}
.ring-cell.active {
  background: var(--matrix-green);
  box-shadow: 0 0 4px var(--matrix-green);
}
.ring-cell.hot {
  background: var(--active-white);
  box-shadow: 0 0 6px var(--active-white);
}

/* Reservoir — bottom right */
#reservoir-panel {
  bottom: 60px; right: 12px;
  width: 280px;
  background: rgba(10,10,8,0.88);
  backdrop-filter: blur(6px);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}

#reservoir-panel h3 {
  font-size: 10px;
  letter-spacing: 1.5px;
  color: var(--reservoir-blue);
  margin-bottom: 8px;
  text-transform: uppercase;
}

.res-stat {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  padding: 3px 0;
  border-bottom: 1px solid rgba(42,42,36,0.5);
}
.res-stat .label { color: var(--text-dim); }
.res-stat .value { color: var(--text); font-variant-numeric: tabular-nums; }

/* Stats — top right */
#stats-panel {
  top: 60px; right: 12px;
  width: 260px;
  background: rgba(10,10,8,0.88);
  backdrop-filter: blur(6px);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}
#stats-panel h3 {
  font-size: 10px;
  letter-spacing: 1.5px;
  color: var(--gold);
  margin-bottom: 8px;
  text-transform: uppercase;
}

/* Change log — right side */
#change-log {
  top: 230px; right: 12px;
  width: 380px;
  max-height: calc(100vh - 340px);
  background: rgba(10,10,8,0.88);
  backdrop-filter: blur(6px);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  overflow-y: auto;
  overflow-x: hidden;
}
#change-log h3 {
  font-size: 10px;
  letter-spacing: 1.5px;
  color: var(--gold);
  margin-bottom: 6px;
  text-transform: uppercase;
  position: sticky;
  top: 0;
  background: rgba(10,10,8,0.95);
  padding: 2px 0 4px;
}
#change-log::-webkit-scrollbar { width: 4px; }
#change-log::-webkit-scrollbar-track { background: transparent; }
#change-log::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.log-entry {
  font-size: 10px;
  padding: 3px 0;
  border-bottom: 1px solid rgba(42,42,36,0.3);
  display: flex;
  gap: 6px;
  align-items: baseline;
  color: var(--text-dim);
  animation: logFade 0.5s ease-out;
}
.log-entry .ts { color: var(--text-muted); min-width: 60px; }
.log-entry .circuit { color: var(--copper); max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.log-entry .vals { color: var(--matrix-green); }
.log-entry .addr { color: var(--text-muted); }

@keyframes logFade {
  from { background: rgba(0,255,65,0.15); }
  to   { background: transparent; }
}

/* Circuit labels floating on Matrix rain */
.circuit-label {
  position: fixed;
  z-index: 5;
  font-size: 9px;
  letter-spacing: 1px;
  color: rgba(205,127,50,0.4);
  text-transform: uppercase;
  pointer-events: none;
  white-space: nowrap;
  text-shadow: 0 0 8px rgba(205,127,50,0.2);
}

/* Footer */
#footer {
  position: fixed;
  bottom: 0; left: 0; right: 0;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: rgba(10,10,8,0.85);
  backdrop-filter: blur(8px);
  border-top: 1px solid var(--border);
  z-index: 20;
  font-size: 10px;
  color: var(--text-muted);
}
#footer .attribution { color: var(--copper); }

/* ---- HUMAN READABLE VIEW ---- */
#human-view {
  position: fixed;
  top: 48px; left: 0; right: 0; bottom: 36px;
  z-index: 15;
  background: var(--bg);
  overflow-y: auto;
  padding: 20px;
  display: none;
}
#human-view.visible { display: block; }

#human-view::-webkit-scrollbar { width: 6px; }
#human-view::-webkit-scrollbar-track { background: var(--bg); }
#human-view::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

.hv-section {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.hv-section h2 {
  font-size: 12px;
  letter-spacing: 2px;
  color: var(--copper-bright);
  text-transform: uppercase;
  margin-bottom: 12px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}

.hv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}

.hv-card {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px;
}
.hv-card h4 {
  font-size: 11px;
  color: var(--gold);
  margin-bottom: 8px;
}
.hv-card .field {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  padding: 2px 0;
}
.hv-card .field .k { color: var(--text-dim); }
.hv-card .field .v { color: var(--text); font-variant-numeric: tabular-nums; }

/* Ring grid in human view */
.hv-ring-grid {
  display: grid;
  grid-template-columns: repeat(32, 1fr);
  gap: 2px;
}
.hv-ring-cell {
  aspect-ratio: 1;
  border-radius: 2px;
  font-size: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--bg);
  font-weight: 700;
  cursor: pointer;
  position: relative;
}
.hv-ring-cell:hover::after {
  content: attr(data-tip);
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 10px;
  white-space: nowrap;
  z-index: 100;
  pointer-events: none;
}

/* Training section */
.hv-progress-bar {
  width: 100%;
  height: 8px;
  background: var(--surface);
  border-radius: 4px;
  overflow: hidden;
  margin: 4px 0;
}
.hv-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--copper), var(--gold));
  border-radius: 4px;
  transition: width 0.5s;
}

/* Change table */
.hv-change-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 10px;
}
.hv-change-table th {
  text-align: left;
  padding: 4px 8px;
  color: var(--text-dim);
  border-bottom: 1px solid var(--border);
  font-weight: 600;
  letter-spacing: 0.5px;
}
.hv-change-table td {
  padding: 3px 8px;
  border-bottom: 1px solid rgba(42,42,36,0.3);
  font-variant-numeric: tabular-nums;
}
.hv-change-table .addr-col { color: var(--text-muted); }
.hv-change-table .circuit-col { color: var(--copper); }
.hv-change-table .val-col { color: var(--matrix-green); }
.hv-change-table .ts-col { color: var(--text-muted); }

</style>
</head>
<body>

<!-- Matrix Rain Canvas -->
<canvas id="matrix-canvas"></canvas>

<!-- Top Bar -->
<div id="top-bar" class="overlay">
  <h1>MUHLNICKEL LIVE BINARY SURFACE</h1>
  <div class="status-lights">
    <span><span class="status-dot" id="dot-sse"></span><span id="lbl-sse">CONNECTING</span></span>
    <span><span class="status-dot idle" id="dot-changes"></span><span id="lbl-changes">0 changes</span></span>
    <span id="lbl-filesize"></span>
  </div>
  <button id="view-toggle" onclick="toggleView()">HUMAN READABLE</button>
</div>

<!-- Ring Pulse Monitor -->
<div id="ring-monitor" class="overlay">
  <h3>RING PULSE MONITOR (1,024 RINGS)</h3>
  <div id="ring-grid"></div>
</div>

<!-- Reservoir Panel -->
<div id="reservoir-panel" class="overlay">
  <h3>RESERVOIR STATUS</h3>
  <div id="reservoir-content"></div>
</div>

<!-- Stats Panel -->
<div id="stats-panel" class="overlay">
  <h3>INSTRUMENT STATS</h3>
  <div id="stats-content"></div>
</div>

<!-- Change Log -->
<div id="change-log" class="overlay">
  <h3>RECENT BYTE CHANGES</h3>
  <div id="change-log-entries"></div>
</div>

<!-- Circuit Labels (positioned on the Matrix) -->
<div id="circuit-labels"></div>

<!-- Human Readable View (hidden by default) -->
<div id="human-view">
  <div class="hv-section">
    <h2>FILE STATUS</h2>
    <div id="hv-file-status" class="hv-grid"></div>
  </div>
  <div class="hv-section">
    <h2>RESERVOIR</h2>
    <div id="hv-reservoir" class="hv-grid"></div>
  </div>
  <div class="hv-section">
    <h2>RING STATES (1,024 RINGS)</h2>
    <div id="hv-ring-grid" class="hv-ring-grid"></div>
    <div id="hv-ring-summary" style="margin-top:8px; font-size:11px; color:var(--text-dim);"></div>
  </div>
  <div class="hv-section">
    <h2>TRAINING CIRCUITS</h2>
    <div id="hv-training" class="hv-grid"></div>
  </div>
  <div class="hv-section">
    <h2>ACTIVE CIRCUITS</h2>
    <div id="hv-circuits" class="hv-grid"></div>
  </div>
  <div class="hv-section">
    <h2>RECENT CHANGES</h2>
    <div style="overflow-x:auto;">
      <table class="hv-change-table" id="hv-change-table">
        <thead>
          <tr><th>TIME</th><th>OFFSET</th><th>OLD</th><th>NEW</th><th>CIRCUIT</th><th>FIELD</th></tr>
        </thead>
        <tbody id="hv-change-tbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- Footer -->
<div id="footer">
  <span class="attribution">Built by Bryce Muhlnickel</span>
  <span>SURFACE ONLY — bounded reads, no writes, no computation | host clock timing</span>
  <span id="footer-uptime"></span>
</div>

<script>
// ================================================================
// MUHLNICKEL LIVE BINARY SURFACE — Client JS
// ================================================================

// --- Data from server ---
const CIRCUITS = /*__CIRCUITS_JSON__*/[];
const RINGS = /*__RINGS_JSON__*/[];
const RESERVOIR = /*__RESERVOIR_JSON__*/{};
const FILE_SIZE = /*__FILE_SIZE__*/0;

// --- State ---
let matrixMode = true;
let totalChanges = 0;
let ringStates = new Uint8Array(1024);
let ringActivity = new Uint32Array(1024); // change count per ring
let changeLogs = [];
const MAX_LOG = 200;
let sseConnected = false;
let startTime = Date.now();
let heatmapActivity = new Float32Array(256); // activity level per heatmap cell

// ================================================================
// MATRIX RAIN
// ================================================================
const canvas = document.getElementById('matrix-canvas');
const ctx = canvas.getContext('2d');

let columns = [];
let colCount = 0;
const CHAR_SIZE = 14;
const HEX_CHARS = '0123456789ABCDEF';
const MATRIX_CHARS = HEX_CHARS + '.:;|/\\[]{}()=+-*&^%$#@!~`<>?';

function resizeCanvas() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  const newColCount = Math.floor(canvas.width / CHAR_SIZE);
  if (newColCount !== colCount) {
    colCount = newColCount;
    const oldCols = columns;
    columns = [];
    for (let i = 0; i < colCount; i++) {
      if (oldCols[i]) {
        columns.push(oldCols[i]);
      } else {
        columns.push({
          y: Math.random() * canvas.height,
          speed: 0.5 + Math.random() * 2,
          chars: [],
          brightness: 0.3 + Math.random() * 0.4,
          activity: 0,
          flashTimer: 0,
          regionIdx: Math.floor((i / colCount) * 256),
          circuitName: null,
        });
      }
    }
    // Assign circuit names to columns
    assignCircuitLabels();
  }
}

function assignCircuitLabels() {
  if (!CIRCUITS.length || !FILE_SIZE) return;
  for (let i = 0; i < columns.length; i++) {
    const filePos = (i / columns.length) * FILE_SIZE;
    // Find closest circuit
    let best = null;
    let bestDist = Infinity;
    for (const c of CIRCUITS) {
      const mid = c.offset + c.len / 2;
      const dist = Math.abs(mid - filePos);
      if (dist < bestDist && dist < FILE_SIZE / columns.length * 5) {
        bestDist = dist;
        best = c;
      }
    }
    columns[i].circuitName = best ? best.name : null;
  }
}

function drawMatrix() {
  if (!matrixMode) {
    requestAnimationFrame(drawMatrix);
    return;
  }

  // Fade effect — trails
  ctx.fillStyle = 'rgba(10, 10, 8, 0.06)';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.font = CHAR_SIZE + 'px Consolas, Courier New, monospace';

  for (let i = 0; i < columns.length; i++) {
    const col = columns[i];

    // Determine color based on activity and region
    let r = 0, g = 180, b = 0; // base green
    let alpha = col.brightness;

    // Map column to file region
    const regionIdx = col.regionIdx;
    const activityLevel = heatmapActivity[regionIdx] || 0;

    if (col.flashTimer > 0) {
      // Flash: white -> gold -> green
      const f = col.flashTimer / 30;
      if (f > 0.7) {
        r = 255; g = 255; b = 255; alpha = 1.0;
      } else if (f > 0.3) {
        r = 232; g = 168; b = 76; alpha = 0.9; // gold
      } else {
        r = 0; g = 255; b = 65; alpha = 0.8;
      }
      col.flashTimer--;
    } else if (activityLevel > 0.5) {
      // Active region — brighter green
      g = 255;
      alpha = Math.min(1.0, col.brightness + activityLevel * 0.3);
    }

    // Check if this column is in a ring region
    if (col.circuitName && col.circuitName.startsWith('nring2_')) {
      r = 184; g = 115; b = 51; // copper for rings
      alpha = Math.min(1.0, alpha + 0.1);
    }

    // Draw the head character (brightest)
    const headChar = MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)];
    ctx.fillStyle = `rgba(${Math.min(255, r+80)}, ${Math.min(255, g+80)}, ${Math.min(255, b+80)}, ${Math.min(1, alpha+0.3)})`;
    ctx.fillText(headChar, i * CHAR_SIZE, col.y);

    // Draw trail
    const trailLen = 8 + Math.floor(Math.random() * 12);
    for (let t = 1; t < trailLen; t++) {
      const ty = col.y - t * CHAR_SIZE;
      if (ty < 0) break;
      const ta = alpha * (1 - t / trailLen) * 0.7;
      if (ta < 0.02) break;
      const tc = MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)];
      ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${ta})`;
      ctx.fillText(tc, i * CHAR_SIZE, ty);
    }

    // Move column
    const speedMod = 1 + activityLevel * 3; // active regions rain faster
    col.y += col.speed * speedMod * CHAR_SIZE * 0.3;

    // Reset when off screen
    if (col.y > canvas.height + CHAR_SIZE * 10) {
      col.y = -CHAR_SIZE * (Math.random() * 20);
      col.speed = 0.5 + Math.random() * 2;
      col.brightness = 0.3 + Math.random() * 0.4;
    }
  }

  // Draw circuit name labels semi-transparently
  ctx.font = '9px Consolas';
  for (let i = 0; i < columns.length; i += Math.floor(columns.length / 30)) {
    const col = columns[i];
    if (col.circuitName) {
      ctx.fillStyle = 'rgba(205, 127, 50, 0.25)';
      ctx.save();
      ctx.translate(i * CHAR_SIZE + CHAR_SIZE/2, canvas.height / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.fillText(col.circuitName, 0, 0);
      ctx.restore();
    }
  }

  requestAnimationFrame(drawMatrix);
}

// Decay heatmap activity
setInterval(() => {
  for (let i = 0; i < heatmapActivity.length; i++) {
    heatmapActivity[i] *= 0.92;
  }
}, 200);

// ================================================================
// RING GRID
// ================================================================
function initRingGrid() {
  const grid = document.getElementById('ring-grid');
  grid.innerHTML = '';
  for (let i = 0; i < 1024; i++) {
    const cell = document.createElement('div');
    cell.className = 'ring-cell';
    cell.id = 'ring-' + i;
    cell.title = 'Ring ' + i.toString().padStart(3, '0');
    grid.appendChild(cell);
  }
}

function updateRingGrid(states) {
  for (let i = 0; i < Math.min(states.length, 1024); i++) {
    const cell = document.getElementById('ring-' + i);
    if (!cell) continue;
    const val = states[i];
    const prev = ringStates[i];
    ringStates[i] = val;

    if (val !== prev && prev !== undefined) {
      cell.className = 'ring-cell hot';
      ringActivity[i]++;
      setTimeout(() => { cell.className = 'ring-cell active'; }, 500);
      setTimeout(() => {
        if (val === 0) cell.className = 'ring-cell';
        else cell.className = 'ring-cell active';
      }, 2000);
    } else if (val > 0) {
      if (!cell.classList.contains('hot')) {
        cell.className = 'ring-cell active';
      }
    } else {
      if (!cell.classList.contains('hot')) {
        cell.className = 'ring-cell';
      }
    }
  }
}

// ================================================================
// RESERVOIR
// ================================================================
function updateReservoir(data) {
  const el = document.getElementById('reservoir-content');
  if (!RESERVOIR.input_addr) {
    el.innerHTML = '<div class="res-stat"><span class="label">Status</span><span class="value">No reservoir in registry</span></div>';
    return;
  }
  el.innerHTML = `
    <div class="res-stat"><span class="label">Input Wire</span><span class="value">${formatAddr(RESERVOIR.input_addr)}</span></div>
    <div class="res-stat"><span class="label">Offset</span><span class="value">${formatAddr(RESERVOIR.offset)}</span></div>
    <div class="res-stat"><span class="label">Size</span><span class="value">${(RESERVOIR.len || 0).toLocaleString()} B</span></div>
    <div class="res-stat"><span class="label">Ring Count</span><span class="value">${RESERVOIR.ring_count || '?'}</span></div>
    <div class="res-stat"><span class="label">Depth</span><span class="value">${RESERVOIR.depth || '?'} ticks</span></div>
  `;
}

// ================================================================
// STATS
// ================================================================
function updateStats() {
  const el = document.getElementById('stats-content');
  const uptime = Math.floor((Date.now() - startTime) / 1000);
  const mins = Math.floor(uptime / 60);
  const secs = uptime % 60;
  el.innerHTML = `
    <div class="res-stat"><span class="label">Uptime (host clock)</span><span class="value">${mins}m ${secs}s</span></div>
    <div class="res-stat"><span class="label">Total Changes</span><span class="value">${totalChanges.toLocaleString()}</span></div>
    <div class="res-stat"><span class="label">File Size</span><span class="value">${formatSize(FILE_SIZE)}</span></div>
    <div class="res-stat"><span class="label">Watched Addrs</span><span class="value">${Object.keys(RINGS).length + (RESERVOIR.input_addr ? 1 : 0)}</span></div>
    <div class="res-stat"><span class="label">SSE</span><span class="value">${sseConnected ? 'CONNECTED' : 'DISCONNECTED'}</span></div>
  `;

  document.getElementById('footer-uptime').textContent = `host clock: ${mins}m ${secs}s`;
}
setInterval(updateStats, 1000);

// ================================================================
// CHANGE LOG
// ================================================================
function addChangeLogEntry(entry) {
  changeLogs.unshift(entry);
  if (changeLogs.length > MAX_LOG) changeLogs.pop();

  const container = document.getElementById('change-log-entries');
  const div = document.createElement('div');
  div.className = 'log-entry';

  const ts = new Date(entry.ts);
  const timeStr = ts.toTimeString().slice(0, 8);

  div.innerHTML = `
    <span class="ts">${timeStr}</span>
    <span class="circuit" title="${entry.circuit}">${entry.circuit || '?'}</span>
    <span class="vals">0x${(entry.old||0).toString(16).padStart(2,'0')} &rarr; 0x${(entry.new||0).toString(16).padStart(2,'0')}</span>
    <span class="addr">${formatAddr(entry.offset)}</span>
  `;

  container.insertBefore(div, container.firstChild);
  // Trim old entries from DOM
  while (container.children.length > MAX_LOG) {
    container.removeChild(container.lastChild);
  }
}

// ================================================================
// HUMAN READABLE VIEW
// ================================================================
function toggleView() {
  matrixMode = !matrixMode;
  const btn = document.getElementById('view-toggle');
  const hv = document.getElementById('human-view');
  const matrixOverlays = ['ring-monitor', 'reservoir-panel', 'stats-panel', 'change-log'];

  if (matrixMode) {
    btn.textContent = 'HUMAN READABLE';
    hv.classList.remove('visible');
    canvas.style.display = 'block';
    matrixOverlays.forEach(id => document.getElementById(id).style.display = '');
  } else {
    btn.textContent = 'MATRIX VIEW';
    hv.classList.add('visible');
    canvas.style.display = 'none';
    matrixOverlays.forEach(id => document.getElementById(id).style.display = 'none');
    refreshHumanView();
  }
}

async function refreshHumanView() {
  // File status
  const fileEl = document.getElementById('hv-file-status');
  fileEl.innerHTML = `
    <div class="hv-card">
      <h4>titan.gguf</h4>
      <div class="field"><span class="k">Size</span><span class="v">${formatSize(FILE_SIZE)}</span></div>
      <div class="field"><span class="k">Total Changes Observed</span><span class="v">${totalChanges.toLocaleString()}</span></div>
      <div class="field"><span class="k">Circuits in Registry</span><span class="v">${CIRCUITS.length}</span></div>
      <div class="field"><span class="k">Rings Tracked</span><span class="v">${RINGS.length}</span></div>
    </div>
  `;

  // Reservoir
  const resEl = document.getElementById('hv-reservoir');
  if (RESERVOIR.input_addr) {
    resEl.innerHTML = `
      <div class="hv-card">
        <h4>muhl_reservoir</h4>
        <div class="field"><span class="k">Input Wire</span><span class="v">${formatAddr(RESERVOIR.input_addr)}</span></div>
        <div class="field"><span class="k">Offset</span><span class="v">${formatAddr(RESERVOIR.offset)}</span></div>
        <div class="field"><span class="k">Size</span><span class="v">${(RESERVOIR.len || 0).toLocaleString()} B</span></div>
        <div class="field"><span class="k">Topology</span><span class="v">flat_fanout</span></div>
        <div class="field"><span class="k">Depth</span><span class="v">${RESERVOIR.depth || '?'} ticks</span></div>
        <div class="field"><span class="k">Ring Count</span><span class="v">${RESERVOIR.ring_count || '?'}</span></div>
      </div>
    `;
  } else {
    resEl.innerHTML = '<div class="hv-card"><h4>No reservoir found</h4></div>';
  }

  // Ring grid in human view
  const hvRingGrid = document.getElementById('hv-ring-grid');
  if (!hvRingGrid.children.length) {
    for (let i = 0; i < 1024; i++) {
      const cell = document.createElement('div');
      cell.className = 'hv-ring-cell';
      cell.id = 'hv-ring-' + i;
      cell.setAttribute('data-tip', `Ring ${i.toString().padStart(3,'0')}: fwd=0x${ringStates[i].toString(16).padStart(2,'0')}`);
      hvRingGrid.appendChild(cell);
    }
  }
  updateHumanRingGrid();

  // Training circuits
  const trainEl = document.getElementById('hv-training');
  const trainCircuits = CIRCUITS.filter(c => c.name && (c.name.includes('train') || c.name.includes('mdl_') || c.name === 'muhl_transformer'));
  trainEl.innerHTML = trainCircuits.map(c => `
    <div class="hv-card">
      <h4>${c.name}</h4>
      <div class="field"><span class="k">Offset</span><span class="v">${formatAddr(c.offset)}</span></div>
      <div class="field"><span class="k">Size</span><span class="v">${(c.len || 0).toLocaleString()} B</span></div>
      <div class="field"><span class="k">Gates</span><span class="v">${(c.n_gate || 0).toLocaleString()}</span></div>
      <div class="field"><span class="k">Depth</span><span class="v">${c.depth || '?'} ticks</span></div>
      <div class="field"><span class="k">Format</span><span class="v">${c.format || '?'}</span></div>
      <div class="field"><span class="k">Powered By</span><span class="v">${c.powered_by || '?'}</span></div>
    </div>
  `).join('');

  // Active circuits (top by gate count)
  const topCircuits = [...CIRCUITS].sort((a, b) => (b.n_gate || 0) - (a.n_gate || 0)).slice(0, 20);
  const circuitsEl = document.getElementById('hv-circuits');
  circuitsEl.innerHTML = topCircuits.map(c => `
    <div class="hv-card">
      <h4>${c.name}</h4>
      <div class="field"><span class="k">Offset</span><span class="v">${formatAddr(c.offset)}</span></div>
      <div class="field"><span class="k">Size</span><span class="v">${(c.len || 0).toLocaleString()} B</span></div>
      <div class="field"><span class="k">Gates</span><span class="v">${(c.n_gate || 0).toLocaleString()}</span></div>
      <div class="field"><span class="k">Depth</span><span class="v">${c.depth || '?'} ticks</span></div>
      <div class="field"><span class="k">Magic</span><span class="v">${c.magic || '?'}</span></div>
      <div class="field"><span class="k">Powered By</span><span class="v">${c.powered_by || '?'}</span></div>
    </div>
  `).join('');

  // Change table
  updateHumanChangeTable();

  // Fetch ring states from API
  try {
    const resp = await fetch('/api/rings');
    const data = await resp.json();
    if (data.rings) {
      data.rings.forEach(r => {
        if (r.index < 1024) {
          ringStates[r.index] = r.fwd || 0;
        }
      });
      updateHumanRingGrid();
    }
  } catch(e) {}
}

function updateHumanRingGrid() {
  let active = 0, total = 0;
  for (let i = 0; i < 1024; i++) {
    const cell = document.getElementById('hv-ring-' + i);
    if (!cell) continue;
    total++;
    const val = ringStates[i];
    const act = ringActivity[i] || 0;
    let bg;
    if (act > 10) {
      bg = '#ffffff'; active++;
    } else if (val > 0) {
      bg = '#00ff41'; active++;
    } else {
      bg = '#003b00';
    }
    cell.style.background = bg;
    cell.setAttribute('data-tip', `Ring ${i.toString().padStart(3,'0')}: fwd=0x${val.toString(16).padStart(2,'0')} rev=? recv=${act > 0 ? 'ACTIVE' : 'STILL'}`);
  }
  const summary = document.getElementById('hv-ring-summary');
  if (summary) {
    summary.textContent = `${active} of ${total} rings show non-zero fwd byte. NOTE: a still reading is NOT evidence of inactivity (settle-back law).`;
  }
}

function updateHumanChangeTable() {
  const tbody = document.getElementById('hv-change-tbody');
  tbody.innerHTML = changeLogs.slice(0, 100).map(e => {
    const ts = new Date(e.ts).toTimeString().slice(0, 12);
    return `<tr>
      <td class="ts-col">${ts}</td>
      <td class="addr-col">${formatAddr(e.offset)}</td>
      <td class="val-col">0x${(e.old||0).toString(16).padStart(2,'0')}</td>
      <td class="val-col">0x${(e.new||0).toString(16).padStart(2,'0')}</td>
      <td class="circuit-col">${e.circuit || '?'}</td>
      <td>${e.field || ''}</td>
    </tr>`;
  }).join('');
}

// ================================================================
// SSE CONNECTION
// ================================================================
function connectSSE() {
  const evtSource = new EventSource('/stream');

  evtSource.onopen = () => {
    sseConnected = true;
    document.getElementById('dot-sse').className = 'status-dot live';
    document.getElementById('lbl-sse').textContent = 'LIVE';
  };

  evtSource.onmessage = (event) => {
    try {
      const events = JSON.parse(event.data);
      for (const evt of events) {
        if (evt.type === 'byte_change') {
          totalChanges++;
          addChangeLogEntry(evt);

          // Flash the column in Matrix view
          if (columns.length && FILE_SIZE) {
            const colIdx = Math.floor((evt.offset / FILE_SIZE) * columns.length);
            if (colIdx >= 0 && colIdx < columns.length) {
              columns[colIdx].flashTimer = 30;
            }
          }

          // Update heatmap
          const hmIdx = Math.floor((evt.offset / FILE_SIZE) * 256);
          if (hmIdx >= 0 && hmIdx < 256) {
            heatmapActivity[hmIdx] = Math.min(1.0, (heatmapActivity[hmIdx] || 0) + 0.5);
          }

          document.getElementById('dot-changes').className = 'status-dot live';
          document.getElementById('lbl-changes').textContent = totalChanges.toLocaleString() + ' changes';
          setTimeout(() => {
            document.getElementById('dot-changes').className = 'status-dot idle';
          }, 300);

        } else if (evt.type === 'ring_bulk') {
          updateRingGrid(evt.states);

        } else if (evt.type === 'heatmap_delta') {
          for (const cell of evt.cells) {
            heatmapActivity[cell.idx] = Math.min(1.0, (heatmapActivity[cell.idx] || 0) + 0.8);
            // Flash column
            if (columns.length) {
              const colIdx = Math.floor((cell.idx / 256) * columns.length);
              if (colIdx >= 0 && colIdx < columns.length) {
                columns[colIdx].flashTimer = 20;
              }
            }
          }

        } else if (evt.type === 'file_growth') {
          const lbl = document.getElementById('lbl-filesize');
          lbl.textContent = `FILE GREW: +${formatSize(evt.delta)}`;
          lbl.style.color = '#ff3333';
          setTimeout(() => { lbl.style.color = ''; }, 5000);

        } else if (evt.type === 'init') {
          document.getElementById('lbl-filesize').textContent = formatSize(evt.file_size || FILE_SIZE);
        }
      }
    } catch(e) { /* ignore parse errors from keepalive */ }
  };

  evtSource.onerror = () => {
    sseConnected = false;
    document.getElementById('dot-sse').className = 'status-dot idle';
    document.getElementById('lbl-sse').textContent = 'RECONNECTING';
    // EventSource auto-reconnects
  };
}

// ================================================================
// UTILITIES
// ================================================================
function formatAddr(addr) {
  if (addr === null || addr === undefined) return '?';
  return '0x' + addr.toString(16).toUpperCase().padStart(10, '0');
}

function formatSize(bytes) {
  if (!bytes) return '0 B';
  if (bytes >= 1e12) return (bytes / 1e12).toFixed(2) + ' TB';
  if (bytes >= 1e9) return (bytes / 1e9).toFixed(2) + ' GB';
  if (bytes >= 1e6) return (bytes / 1e6).toFixed(2) + ' MB';
  if (bytes >= 1e3) return (bytes / 1e3).toFixed(2) + ' KB';
  return bytes + ' B';
}

// ================================================================
// INIT
// ================================================================
window.addEventListener('resize', resizeCanvas);
resizeCanvas();
initRingGrid();
updateReservoir();
updateStats();
connectSSE();
requestAnimationFrame(drawMatrix);

// Periodically refresh human view if visible
setInterval(() => {
  if (!matrixMode) {
    updateHumanRingGrid();
    updateHumanChangeTable();
  }
}, 2000);

</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="MUHLNICKEL Live Binary Surface")
    parser.add_argument("--port", type=int, default=7880)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("  MUHLNICKEL LIVE BINARY SURFACE")
    print("  Built by Bryce Muhlnickel")
    print("  SURFACE ONLY — bounded reads, no writes, no computation")
    print("=" * 60)
    print()

    # Load registry
    load_registry()

    # Open titan.gguf
    if not open_titan():
        print("[FATAL] Cannot proceed without titan.gguf")
        sys.exit(1)

    # Initialize prev_values with current state
    print("[INFO] Reading initial state of watched addresses...")
    for addr in watch_addrs:
        val = read_byte(addr)
        if val is not None:
            prev_values[addr] = val

    # Initialize heatmap samples
    if mm:
        sample_count = 256
        sample_step = mm.size() // sample_count
        for i in range(sample_count):
            sample_addr = i * sample_step
            val = read_byte(sample_addr)
            if val is not None:
                prev_values[f"_hm_{i}"] = val

    stats["start_time"] = time.time()
    stats["last_file_size"] = mm.size() if mm else 0

    # Ensure log dir
    ensure_log_dir()

    # Start heartbeat thread
    hb = threading.Thread(target=heartbeat_loop, daemon=True)
    hb.start()

    # Start ring bulk sampler
    rb = threading.Thread(target=ring_bulk_sample, daemon=True)
    rb.start()

    # Start HTTP server
    server = HTTPServer(("0.0.0.0", args.port), SurfaceHandler)
    server.daemon_threads = True
    print(f"\n[LIVE] http://localhost:{args.port}")
    print("[LIVE] Press Ctrl+C to stop\n")

    # Open browser
    if not args.no_browser:
        webbrowser.open(f"http://localhost:{args.port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOP] Shutting down...")
        server.shutdown()
        if mm:
            mm.close()
        if titan_fh:
            titan_fh.close()
        if log_file_handle:
            log_file_handle.close()


if __name__ == "__main__":
    main()
