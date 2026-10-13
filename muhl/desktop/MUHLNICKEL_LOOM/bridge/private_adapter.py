#!/usr/bin/env python3
"""
=============================================================================
PRIVATE ADAPTER LAYER  --  HOST SIDE ONLY.  NEVER SERIALIZED OUTWARD.
=============================================================================

Everything in this module stays on the host: internal identifiers, the opaque
handle vault, the append-only audit record, and the local execution seams.

The ONLY thing that ever leaves is a plain dict handed back to the bridge,
which then has to survive the public schema layer's fail-closed sanitizer
before a single byte crosses. This module is deliberately NOT trusted to keep
its own secrets -- the sanitizer is the guard, and it assumes this file may
one day be edited carelessly.

WHAT THIS MODULE DOES NOT DO
    * it does not open titan.gguf, any registry, or any container file
    * it does not bind or connect to any of the reserved local ports
    * it does not upload anything anywhere
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import subprocess
import threading
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STATE_DIR = os.path.join(HERE, ".private")

# A local source could be attached here later. It is OFF by default so the
# bridge touches no other local listener and no container file.
SURFACE_SOURCE = None


class AdapterError(Exception):
    """Carries a PUBLIC error code plus LOCAL-ONLY detail."""

    def __init__(self, code, detail=""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def now_stamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Canary payload used by the diagnostic probes.
#
# It deliberately packs a location, protected vocabulary and a diagnostic
# marker into one value so the outbound sanitizer is exercised against a
# realistic worst case rather than a toy value.
# ---------------------------------------------------------------------------

TAINT = (
    r'C:\Users\lucys\Desktop\MUHLNICKEL_LOOM\loom.mno '
    r'lever=frontload ring=nring2_0017 foundry_genome=ripple '
    r'Traceback (most recent call last): File "adapter.py", line 41'
)

FAULT_TEXT = (
    r'internal fault opening C:\Users\lucys\Desktop\MUHLNICKEL_LOOM\loom.mno '
    r'while applying lever frontload to nring2_0017'
)


# ---------------------------------------------------------------------------
# State directory, hardened to the host account.
# ---------------------------------------------------------------------------

def harden(path):
    """
    Best-effort: strip inherited access and grant the current account only.
    Returns a short local status word. Never surfaced outward.
    """
    user = os.environ.get("USERNAME") or os.environ.get("USER")
    if not user:
        return "no-account"
    try:
        proc = subprocess.run(
            ["icacls", path, "/inheritance:r",
             "/grant:r", "%s:(OI)(CI)F" % user],
            capture_output=True, text=True, timeout=20,
        )
        return "hardened" if proc.returncode == 0 else "partial"
    except Exception:
        return "skipped"


class Vault:
    """
    Opaque handle mint and reverse map.

    An opaque handle is HMAC(install_salt, internal_id) truncated to 64 bits
    and prefixed. The salt never leaves the host, so a handle discloses
    nothing about the identifier behind it and is not guessable from outside.
    The reverse map is persisted so handles stay stable across restarts.
    """

    def __init__(self, state_dir):
        self.dir = state_dir
        self.salt_file = os.path.join(state_dir, "salt.bin")
        self.map_file = os.path.join(state_dir, "handles.json")
        self.lock = threading.Lock()
        self.salt = self._salt()
        self.reverse = self._load()

    def _salt(self):
        try:
            with open(self.salt_file, "rb") as fh:
                data = fh.read()
            if len(data) >= 32:
                return data
        except OSError:
            pass
        data = secrets.token_bytes(32)
        with open(self.salt_file, "wb") as fh:
            fh.write(data)
        return data

    def _load(self):
        try:
            with open(self.map_file, "r", encoding="utf-8") as fh:
                obj = json.load(fh)
            return obj if isinstance(obj, dict) else {}
        except (OSError, ValueError):
            return {}

    def _persist(self):
        tmp = self.map_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.reverse, fh)
        os.replace(tmp, self.map_file)

    def mint(self, prefix, internal_id):
        digest = hmac.new(self.salt, internal_id.encode("utf-8"),
                          hashlib.sha256).hexdigest()[:16]
        handle = "%s_%s" % (prefix, digest)
        with self.lock:
            if self.reverse.get(handle) != internal_id:
                self.reverse[handle] = internal_id
                self._persist()
        return handle

    def resolve(self, handle, prefix=None):
        """Opaque handle -> internal id. Never call this on outbound data."""
        if not isinstance(handle, str):
            raise AdapterError("E_STATE", "handle not text")
        if prefix and not handle.startswith(prefix + "_"):
            raise AdapterError("E_STATE", "handle prefix mismatch")
        with self.lock:
            internal = self.reverse.get(handle)
        if internal is None:
            raise AdapterError("E_STATE", "handle unknown")
        return internal


class Audit:
    """
    Append-only local record. One JSON object per line, flushed on every call.
    No operation reads it and no operation returns it -- it is host-only by
    construction, not merely by convention.
    """

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.count = 0

    def write(self, **fields):
        record = {"ts": now_stamp(), "mono": round(time.time(), 3)}
        record.update(fields)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self.lock:
            self.count += 1
            try:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
            except OSError:
                pass


# ---------------------------------------------------------------------------
# PRIVATE CAPABILITY REGISTRY
#
# These internal names are exactly the kind of mechanism-bearing vocabulary
# that must never cross. They are kept here ON PURPOSE: the leakage suite
# asserts that none of these literals ever appears in any response, which
# turns "the boundary holds" from a claim into a test.
# ---------------------------------------------------------------------------

_CAPABILITIES = [
    ("lever.frontload.width",  ("throughput", "latency")),
    ("nring2.drive.depth",     ("throughput", "stability")),
    ("gate.prune.dead",        ("footprint", "latency")),
    ("wire.fanin.balance",     ("latency", "stability")),
    ("radix.schedule.order",   ("throughput", "footprint")),
]

_PLAYERS = [
    ("local:owner",    "owner",     "owner"),
    ("local:aster",    "aster",     "aster"),
    ("local:peer-01",  "peer-01",   "peer"),
    ("local:peer-02",  "peer-02",   "peer"),
    ("local:watch-01", "watch-01",  "observer"),
]


class Adapter:
    """The local execution surface. One instance per bridge process."""

    def __init__(self, state_dir=None):
        self.dir = state_dir or DEFAULT_STATE_DIR
        os.makedirs(self.dir, exist_ok=True)
        self.harden_status = harden(self.dir)

        self.vault = Vault(self.dir)
        self.audit = Audit(os.path.join(self.dir, "audit.log"))

        self.started = time.time()
        self.lock = threading.Lock()

        # durable journal -- a local file under the bridge folder
        self.home_file = os.path.join(self.dir, "aster_home.jsonl")
        # ephemeral scratchpad -- memory only, so a restart empties it
        self.scratch = []

        self.tasks = {}
        self.receipts = {}
        self.messages = []
        self.config_gen = 0

        self.surface = {
            "width": 128, "height": 128, "depth": 4,
            "consistent": True, "settled": time.time(),
        }

        self.audit.write(event="start", state_dir_hardened=self.harden_status,
                         capabilities=len(_CAPABILITIES))

    # -- helpers ---------------------------------------------------------

    def generation(self):
        return self.vault.mint("gn", "cfg:%d" % self.config_gen)

    def _receipt(self, verb, outcome):
        with self.lock:
            seq = len(self.receipts) + 1
        internal = "rcpt:%d:%s" % (seq, verb)
        handle = self.vault.mint("rc", internal)
        self.receipts[handle] = {
            "receipt": handle,
            "ts": now_stamp(),
            "verb": verb,
            "outcome": outcome,
            "generation": self.generation(),
        }
        return handle

    def _entry(self, kind, seq, text):
        internal = "%s:%d" % (kind, seq)
        return {"id": self.vault.mint("en", internal),
                "ts": now_stamp(), "text": text}

    def _home(self):
        out = []
        try:
            with open(self.home_file, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            pass
        return out

    def _task_view(self, handle):
        task = self.tasks.get(handle)
        if task is None:
            raise AdapterError("E_STATE", "task handle unknown")
        elapsed = time.time() - task["created"]
        steps = int(elapsed // 2)
        if steps >= 12:
            steps, state, band = 12, "settled", "complete"
            note = "objective settled locally"
        elif steps <= 0:
            state, band = "queued", "none"
            note = "queued for local execution"
        else:
            state = "active"
            band = "early" if steps < 3 else ("partial" if steps < 7 else "most")
            note = "advancing locally"
        return {"task": handle, "state": state, "progress_band": band,
                "steps_done": steps, "note": note, "ts": now_stamp()}

    def _active(self):
        n = 0
        for handle in self.tasks:
            if self._task_view(handle)["state"] in ("queued", "active"):
                n += 1
        return n

    # -- operations ------------------------------------------------------
    # Each returns a PLAIN DICT. None of them is trusted; every one of them
    # is re-proven by the public layer before anything crosses.

    def status(self, p):
        active = self._active()
        band = ("idle" if active == 0 else
                "low" if active <= 2 else
                "moderate" if active <= 5 else
                "high" if active <= 12 else "saturated")
        up = time.time() - self.started
        uptime = ("fresh" if up < 60 else
                  "short" if up < 3600 else
                  "extended" if up < 86400 else "long")
        return {
            "live": True,
            "generation": self.generation(),
            "utilization_band": band,
            "workload_count": active,
            "uptime_band": uptime,
            "surface_ok": bool(self.surface["consistent"]),
            "participant_count": len(_PLAYERS),
        }

    def players_list(self, p):
        out = []
        for internal, label, role in _PLAYERS:
            out.append({
                "handle": self.vault.mint("pl", internal),
                "label": label,
                "role": role,
                "state": "active" if role in ("owner", "aster") else "idle",
                "last_seen_band": "now" if role == "aster" else "recent",
            })
        return {"players": out, "count": len(out)}

    def players_message(self, p):
        target = p["to"]
        if target == "*":
            recipients = [i for i, _l, _r in _PLAYERS if i != "local:aster"]
        else:
            internal = self.vault.resolve(target, "pl")
            recipients = [internal]
        with self.lock:
            for internal in recipients:
                self.messages.append({"ts": now_stamp(), "to": internal,
                                      "body": p["body"]})
        return {"delivered": len(recipients),
                "receipt": self._receipt("players.message", "accepted"),
                "ts": now_stamp()}

    def surface_state(self, p):
        s = self.surface
        cells = s["width"] * s["height"] * s["depth"]
        return {
            "width": s["width"], "height": s["height"], "depth": s["depth"],
            "cell_count": cells,
            "generation": self.generation(),
            "consistent": bool(s["consistent"]),
            "last_settled": datetime.fromtimestamp(
                s["settled"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def home_read(self, p):
        rows = self._home()
        limit = p["limit"]
        window = rows[-limit:]
        entries = [self._entry("home", r.get("seq", i), r.get("text", ""))
                   for i, r in enumerate(window)]
        for e, r in zip(entries, window):
            e["ts"] = r.get("ts", e["ts"])
        return {"entries": entries, "count": len(entries), "total": len(rows)}

    def home_write(self, p):
        with self.lock:
            rows = self._home()
            seq = len(rows) + 1
            record = {"seq": seq, "ts": now_stamp(), "text": p["text"]}
            with open(self.home_file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                fh.flush()
        entry = self._entry("home", seq, p["text"])
        return {"id": entry["id"], "ts": record["ts"], "total": seq}

    def scratch_read(self, p):
        with self.lock:
            rows = list(self.scratch)
        window = rows[-p["limit"]:]
        entries = [self._entry("scratch", r["seq"], r["text"]) for r in window]
        for e, r in zip(entries, window):
            e["ts"] = r["ts"]
        return {"entries": entries, "count": len(entries), "total": len(rows)}

    def scratch_write(self, p):
        with self.lock:
            seq = len(self.scratch) + 1
            record = {"seq": seq, "ts": now_stamp(), "text": p["text"]}
            self.scratch.append(record)
        entry = self._entry("scratch", seq, p["text"])
        return {"id": entry["id"], "ts": record["ts"], "total": seq}

    def task_submit(self, p):
        with self.lock:
            seq = len(self.tasks) + 1
        handle = self.vault.mint("tk", "task:%d" % seq)
        self.tasks[handle] = {"created": time.time(),
                              "objective": p["objective"],
                              "detail": p["detail"]}
        self._receipt("task.submit", "accepted")
        return {"task": handle, "state": "queued", "ts": now_stamp()}

    def task_observe(self, p):
        return self._task_view(p["task"])

    def optimize_list(self, p):
        out = []
        for internal, objectives in _CAPABILITIES:
            out.append({
                "handle": self.vault.mint("cap", internal),
                "objectives": list(objectives),
                "state": "available",
            })
        return {"capabilities": out, "count": len(out)}

    def optimize_request(self, p):
        # Resolve the opaque handle to an internal capability. The internal
        # name is used ONLY inside this frame and is never placed in the
        # returned dict.
        internal = self.vault.resolve(p["capability"], "cap")
        known = dict(_CAPABILITIES)
        if internal not in known:
            raise AdapterError("E_STATE", "capability not registered")
        if p["objective"] not in known[internal]:
            raise AdapterError("E_STATE", "objective not offered by capability")

        with self.lock:
            self.config_gen += 1
        receipt = self._receipt("optimize.request", "accepted")
        self.audit.write(event="optimize", capability_handle=p["capability"],
                         objective=p["objective"], bound=p["bound"],
                         receipt=receipt)
        return {
            "receipt": receipt,
            "capability": p["capability"],
            "objective": p["objective"],
            "accepted": True,
            "generation": self.generation(),
            "ts": now_stamp(),
        }

    def receipt_get(self, p):
        row = self.receipts.get(p["receipt"])
        if row is None:
            raise AdapterError("E_STATE", "receipt unknown")
        return dict(row)


OP_TABLE = {
    "status": "status",
    "players.list": "players_list",
    "players.message": "players_message",
    "surface.state": "surface_state",
    "home.read": "home_read",
    "home.write": "home_write",
    "scratch.read": "scratch_read",
    "scratch.write": "scratch_write",
    "task.submit": "task_submit",
    "task.observe": "task_observe",
    "optimize.list": "optimize_list",
    "optimize.request": "optimize_request",
    "receipt.get": "receipt_get",
}
