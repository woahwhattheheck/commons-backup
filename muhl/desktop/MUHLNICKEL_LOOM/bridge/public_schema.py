#!/usr/bin/env python3
"""
=============================================================================
PUBLIC SCHEMA LAYER
=============================================================================

This module defines what an external party may see on the way out.

It holds:
    * the known operation registry used for discovery and output contracts
    * advisory parameter descriptions for known operations
    * the outbound RESULT contract per operation
    * a FAIL-CLOSED sanitizer

It holds NO local logic, NO local identifiers, NO file locations, and no
statement of how any capability is actually carried out.

INVARIANT: this module must never import the private adapter layer.
INVARIANT: a value may cross outward only if a declared contract proves it
           safe. If safety cannot be established the call ERRORS. Values are
           never silently scrubbed and never passed through "just this once".
"""

from __future__ import annotations

import os
import re

SCHEMA_VERSION = "1.1.0"

_HERE = os.path.dirname(os.path.abspath(__file__))
DENYLIST_FILE = os.path.join(_HERE, "denylist.txt")

MAX_TEXT_DEFAULT = 4000
MAX_LIST_DEFAULT = 256


# ---------------------------------------------------------------------------
# Stable, redacted error codes. The message is a CONSTANT -- it is never
# derived from an exception, a value, a parameter or a location.
# ---------------------------------------------------------------------------

ERRORS = {
    "E_METHOD":    "unsupported request",
    "E_PARAM":     "malformed request",
    "E_SANITIZE":  "result withheld by policy",
    "E_STATE":     "resource not available",
    "E_INTERNAL":  "request could not be completed",
}


class SanitizeError(Exception):
    """
    Raised when a value cannot be proven safe to emit.

    `detail` is for the LOCAL audit log only. It is never serialized outward.
    """

    def __init__(self, code, detail):
        super().__init__(code)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# Outbound deny-list. Loaded once at import. It is never applied to caller
# actions or parameters. If it will not load, DENYLIST_LOADED stays False and
# the bridge refuses to start because it cannot prove its outbound contract.
# ---------------------------------------------------------------------------

# Baseline tokens. These apply even if the file were emptied.
BASE_DENY = [
    "titan", "gguf", ".mno", "nring", "ring", "radix", "fan-in",
    "gate", "wire", "foundry", "genome", "lever", "preflight",
    "muhl_", "traceback", 'file "',
]


def _load_denylist():
    tokens = set(t.lower() for t in BASE_DENY)
    loaded = False
    try:
        with open(DENYLIST_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                tokens.add(line.lower())
                loaded = True
    except OSError:
        loaded = False
    # longest first so audit detail names the most specific hit
    return sorted(tokens, key=len, reverse=True), loaded


DENY_TOKENS, DENYLIST_LOADED = _load_denylist()


# ---------------------------------------------------------------------------
# Structural leakage patterns: absolute locations and diagnostic spill.
# ---------------------------------------------------------------------------

_LEAK_PATTERNS = [
    # Windows drive-qualified location, not preceded by an alphanumeric
    # (so a scheme such as "http://" is not mistaken for one).
    ("abs_drive", re.compile(r"(?:^|[^A-Za-z0-9])[A-Za-z]:[\\/]")),
    # UNC location
    ("abs_unc", re.compile(r"\\\\[A-Za-z0-9_.$-]+\\")),
    # POSIX absolute location under a well-known root
    ("abs_posix", re.compile(
        r"(?i)(?:^|[\s\"'(\[,=])/(?:users|home|mnt|etc|var|usr|opt|tmp|proc|root|bin|sbin|dev)(?:/|\b)")),
    # location-bearing URI schemes
    ("uri_local", re.compile(r"(?i)\b(?:file|smb|ftp)://")),
    # diagnostic spill
    ("trace_py", re.compile(r"(?i)traceback")),
    ("trace_frame", re.compile(r'(?i)file "')),
    ("trace_line", re.compile(r"(?i)\.py\"?,\s*line\s*\d+")),
    ("trace_java", re.compile(r"(?m)^\s*at\s+\S+\(\S+:\d+\)")),
    # control characters (NUL and friends) -- never legitimate in a result
    ("ctrl", re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")),
]


def scan(text):
    """
    Return a list of leakage hit labels found in `text`.
    Empty list == nothing objectionable found.
    """
    if not isinstance(text, str):
        return ["not_text"]
    hits = []
    low = text.lower()
    for tok in DENY_TOKENS:
        if tok in low:
            hits.append("deny:" + tok)
    for label, pat in _LEAK_PATTERNS:
        if pat.search(text):
            hits.append(label)
    return hits


# ---------------------------------------------------------------------------
# Field kinds. A kind is a small tuple; the first element names it.
# ---------------------------------------------------------------------------

HANDLE_RE = re.compile(r"^(?:pl|tk|rc|cap|en|gn)_[0-9a-f]{16}$")
STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def Handle():
    """An opaque identifier. Carries no meaning outside this bridge."""
    return ("handle",)


def Flag():
    return ("flag",)


def Count(lo=0, hi=2 ** 53):
    return ("count", lo, hi)


def Text(maxlen=MAX_TEXT_DEFAULT):
    return ("text", maxlen)


def Stamp():
    """UTC instant, second resolution."""
    return ("stamp",)


def Enum(*values):
    return ("enum", tuple(values))


def Listing(item, maxlen=MAX_LIST_DEFAULT):
    return ("list", item, maxlen)


def Shape(**fields):
    return ("shape", fields)


# ---------------------------------------------------------------------------
# The fail-closed checker.
# ---------------------------------------------------------------------------

def _fail(where, why):
    raise SanitizeError("E_SANITIZE", "%s: %s" % (where, why))


def enforce(spec, value, where="result"):
    """
    Validate `value` against `spec`, returning a NEWLY BUILT value containing
    only declared, proven fields.

    Anything undeclared, mistyped, oversized, out of range, or carrying a
    leakage hit raises SanitizeError. There is no permissive branch.
    """
    kind = spec[0]

    if kind == "flag":
        if not isinstance(value, bool):
            _fail(where, "not a flag")
        return value

    if kind == "count":
        if isinstance(value, bool) or not isinstance(value, int):
            _fail(where, "not a count")
        if not (spec[1] <= value <= spec[2]):
            _fail(where, "count out of range")
        return value

    if kind == "handle":
        if not isinstance(value, str) or not HANDLE_RE.match(value):
            _fail(where, "not an opaque handle")
        return value

    if kind == "stamp":
        if not isinstance(value, str) or not STAMP_RE.match(value):
            _fail(where, "not a stamp")
        return value

    if kind == "enum":
        if value not in spec[1]:
            _fail(where, "not a permitted value")
        return value

    if kind == "text":
        if not isinstance(value, str):
            _fail(where, "not text")
        if len(value) > spec[1]:
            _fail(where, "text over declared length")
        hits = scan(value)
        if hits:
            _fail(where, "leakage hits %s" % (hits,))
        return value

    if kind == "list":
        if not isinstance(value, (list, tuple)):
            _fail(where, "not a list")
        if len(value) > spec[2]:
            _fail(where, "list over declared length")
        return [enforce(spec[1], v, "%s[%d]" % (where, i))
                for i, v in enumerate(value)]

    if kind == "shape":
        if not isinstance(value, dict):
            _fail(where, "not a shape")
        declared = spec[1]
        extra = set(value) - set(declared)
        if extra:
            # UNDECLARED FIELD -> fail closed. This is the single most
            # important branch in the module: it is what stops an adapter
            # change from quietly widening the surface.
            _fail(where, "undeclared fields %s" % (sorted(extra),))
        out = {}
        for name, sub in declared.items():
            if name not in value:
                _fail(where, "missing declared field %r" % (name,))
            out[name] = enforce(sub, value[name], "%s.%s" % (where, name))
        return out

    _fail(where, "unknown kind")


def count_hits(spec, value):
    """
    Best-effort count of leakage hits inside a candidate result. Used for the
    LOCAL audit record only -- the value itself never crosses.
    """
    total = 0
    try:
        kind = spec[0]
        if kind == "text" and isinstance(value, str):
            total += len(scan(value))
        elif kind == "list" and isinstance(value, (list, tuple)):
            for v in value:
                total += count_hits(spec[1], v)
        elif kind == "shape" and isinstance(value, dict):
            for name, sub in spec[1].items():
                if name in value:
                    total += count_hits(sub, value[name])
            for name in set(value) - set(spec[1]):
                total += 1
                v = value[name]
                if isinstance(v, str):
                    total += len(scan(v))
    except Exception:
        return total
    return total


# ---------------------------------------------------------------------------
# Shared vocabulary
# ---------------------------------------------------------------------------

BAND = Enum("idle", "low", "moderate", "high", "saturated")
FRESHNESS = Enum("now", "recent", "stale")
TASK_STATE = Enum("queued", "active", "settled", "closed")
PROGRESS = Enum("none", "early", "partial", "most", "complete")
OBJECTIVE = Enum("throughput", "latency", "footprint", "stability")
PLAYER_ROLE = Enum("owner", "peer", "observer", "aster")
PLAYER_STATE = Enum("active", "idle", "away")
OUTCOME = Enum("accepted", "applied", "refused", "settled")

KNOWN_ACTIONS = (
    "status",
    "players.list", "players.message",
    "surface.state",
    "home.read", "home.write",
    "scratch.read", "scratch.write",
    "task.submit", "task.observe",
    "optimize.list", "optimize.request",
    "receipt.get",
)
RECEIPT_ACTION = Enum(*KNOWN_ACTIONS)

ENTRY = Shape(id=Handle(), ts=Stamp(), text=Text(MAX_TEXT_DEFAULT))


def Param(spec, required=False, default=None):
    return {"spec": spec, "required": required, "default": default}


# Diagnostic probes. Present on EVERY operation and honestly published in the
# manifest. Each one can only ever produce a REDACTED error -- they exist so
# the redaction and fail-closed paths can be exercised from outside rather
# than merely asserted.
DIAG_PARAMS = {
    "probe_fault": Param(Flag(), default=False),
    "probe_taint": Param(Flag(), default=False),
    "probe_undeclared": Param(Flag(), default=False),
}

DIAG_NOTE = ("diagnostic probe; always resolves to a redacted error code, "
             "never to data")


def _op(summary, params, result):
    p = dict(params)
    p.update(DIAG_PARAMS)
    return {"summary": summary, "params": p, "result": result}


# ---------------------------------------------------------------------------
# KNOWN OPERATIONS. This is a discovery/result-contract registry, not an
# admission list. Unknown actions reach dispatch and report route availability.
# ---------------------------------------------------------------------------

OPERATIONS = {

    "status": _op(
        "Live health summary in capability terms.",
        {},
        Shape(
            live=Flag(),
            generation=Handle(),
            utilization_band=BAND,
            workload_count=Count(),
            uptime_band=Enum("fresh", "short", "extended", "long"),
            surface_ok=Flag(),
            participant_count=Count(),
        ),
    ),

    "players.list": _op(
        "Discover participants reachable through this bridge.",
        {},
        Shape(
            players=Listing(Shape(
                handle=Handle(),
                label=Text(64),
                role=PLAYER_ROLE,
                state=PLAYER_STATE,
                last_seen_band=FRESHNESS,
            )),
            count=Count(),
        ),
    ),

    "players.message": _op(
        "Send a direct or broadcast message to participants.",
        {
            "to": Param(Text(64), required=True),
            "body": Param(Text(MAX_TEXT_DEFAULT), required=True),
        },
        Shape(
            delivered=Count(),
            receipt=Handle(),
            ts=Stamp(),
        ),
    ),

    "surface.state": _op(
        "Loom surface shape and coherence, in capability terms.",
        {},
        Shape(
            width=Count(),
            height=Count(),
            depth=Count(),
            cell_count=Count(),
            generation=Handle(),
            consistent=Flag(),
            last_settled=Stamp(),
        ),
    ),

    "home.read": _op(
        "Read the durable journal.",
        {"limit": Param(Count(1, MAX_LIST_DEFAULT), default=50)},
        Shape(entries=Listing(ENTRY), count=Count(), total=Count()),
    ),

    "home.write": _op(
        "Append an entry to the durable journal.",
        {"text": Param(Text(MAX_TEXT_DEFAULT), required=True)},
        Shape(id=Handle(), ts=Stamp(), total=Count()),
    ),

    "scratch.read": _op(
        "Read the ephemeral scratchpad. Emptied on restart.",
        {"limit": Param(Count(1, MAX_LIST_DEFAULT), default=50)},
        Shape(entries=Listing(ENTRY), count=Count(), total=Count()),
    ),

    "scratch.write": _op(
        "Append to the ephemeral scratchpad. Emptied on restart.",
        {"text": Param(Text(MAX_TEXT_DEFAULT), required=True)},
        Shape(id=Handle(), ts=Stamp(), total=Count()),
    ),

    "task.submit": _op(
        "Submit a high-level objective for local execution.",
        {
            "objective": Param(Text(400), required=True),
            "detail": Param(Text(MAX_TEXT_DEFAULT), default=""),
        },
        Shape(task=Handle(), state=TASK_STATE, ts=Stamp()),
    ),

    "task.observe": _op(
        "Observe a submitted objective by opaque handle.",
        {"task": Param(Text(64), required=True)},
        Shape(
            task=Handle(),
            state=TASK_STATE,
            progress_band=PROGRESS,
            steps_done=Count(),
            note=Text(240),
            ts=Stamp(),
        ),
    ),

    "optimize.list": _op(
        "Enumerate optimizable capabilities as opaque handles only.",
        {},
        Shape(
            capabilities=Listing(Shape(
                handle=Handle(),
                objectives=Listing(OBJECTIVE, 8),
                state=Enum("available", "busy", "held"),
            )),
            count=Count(),
        ),
    ),

    "optimize.request": _op(
        "Request objective-driven autonomous optimization of one capability, "
        "addressed only by its opaque handle.",
        {
            "capability": Param(Text(64), required=True),
            "objective": Param(OBJECTIVE, required=True),
            "bound": Param(Count(1, 10 ** 6), default=1000),
        },
        Shape(
            receipt=Handle(),
            capability=Handle(),
            objective=OBJECTIVE,
            accepted=Flag(),
            generation=Handle(),
            ts=Stamp(),
        ),
    ),

    "receipt.get": _op(
        "Fetch an action receipt and its configuration-generation identifier.",
        {"receipt": Param(Text(64), required=True)},
        Shape(
            receipt=Handle(),
            ts=Stamp(),
            verb=RECEIPT_ACTION,
            outcome=OUTCOME,
            generation=Handle(),
        ),
    ),
}


# ---------------------------------------------------------------------------
# Open inbound parameter normalization.
# ---------------------------------------------------------------------------

def open_params(action, raw):
    """
    Copy caller parameters without rejecting names, values, types, or content.

    Defaults documented for a known adapter operation are filled solely to
    preserve its established calling convention. A non-object value is carried
    under ``value`` so parameter shape is not an admission decision.
    """
    if raw is None:
        out = {}
    elif isinstance(raw, dict):
        out = dict(raw)
    else:
        out = {"value": raw}

    operation = OPERATIONS.get(action)
    if operation:
        for name, decl in operation["params"].items():
            if (name not in out or out[name] is None) and not decl["required"]:
                out[name] = decl["default"]
    return out


def sanitize_result(verb, value):
    """Final outbound gate. Returns a freshly built, fully proven result."""
    return enforce(OPERATIONS[verb]["result"], value, verb)


# ---------------------------------------------------------------------------
# Public manifest rendering.
# ---------------------------------------------------------------------------

_KIND_LABEL = {
    "handle": "handle", "flag": "flag", "count": "count",
    "text": "text", "stamp": "stamp", "enum": "enum",
    "list": "list", "shape": "shape",
}


def describe(spec):
    kind = spec[0]
    node = {"type": _KIND_LABEL[kind]}
    if kind == "text":
        node["max_length"] = spec[1]
    elif kind == "count":
        node["min"] = spec[1]
        node["max"] = spec[2]
    elif kind == "enum":
        node["values"] = list(spec[1])
    elif kind == "list":
        node["max_items"] = spec[2]
        node["items"] = describe(spec[1])
    elif kind == "shape":
        node["fields"] = {k: describe(v) for k, v in spec[1].items()}
    elif kind == "handle":
        node["note"] = "opaque; meaningful only to this bridge"
    elif kind == "stamp":
        node["format"] = "YYYY-MM-DDThh:mm:ssZ"
    return node


def manifest():
    ops = {}
    for verb in KNOWN_ACTIONS:
        op = OPERATIONS[verb]
        params = {}
        for name, decl in op["params"].items():
            entry = describe(decl["spec"])
            entry["required"] = False
            entry["adapter_expects"] = bool(decl["required"])
            if decl["default"] is not None:
                entry["default"] = decl["default"]
            if name in DIAG_PARAMS:
                entry["note"] = DIAG_NOTE
            entry["advisory"] = True
            params[name] = entry
        ops[verb] = {
            "summary": op["summary"],
            "params": params,
            "result": describe(op["result"]),
        }
    return {
        "manifest": "aster-bridge",
        "schema_version": SCHEMA_VERSION,
        "transport": {
            "endpoint": "http://127.0.0.1:7891/rpc",
            "method": "POST",
            "body": {"action": "<free text; verb is an alias>",
                     "params": "<any JSON value>"},
            "access": "open local link; no credential",
            "loopback_only": True,
        },
        "caller_admission": {
            "actions": "open",
            "params": "open",
            "content": "open",
            "request_rate": "not refused",
            "unknown_action_route": "unavailable in tracked build",
        },
        "envelope": {
            "success": {"ok": True, "verb": "<verb>", "ts": "<stamp>",
                        "data": "<result shape>"},
            "failure": {"ok": False, "verb": "<verb>", "ts": "<stamp>",
                        "error": {"code": "<code>", "message": "<constant>"}},
        },
        "error_codes": dict(ERRORS),
        "type_map": {
            "handle": "opaque id, matches ^(pl|tk|rc|cap|en|gn)_[0-9a-f]{16}$",
            "flag": "true / false",
            "count": "non-negative whole number",
            "text": "unicode; result length and outbound policy are checked",
            "stamp": "UTC instant, second resolution",
            "enum": "one of the listed values",
            "list": "ordered collection",
            "shape": "fixed set of named fields",
        },
        "policy": [
            "Possessing the local link is sufficient caller access.",
            "Operation parameters are advisory and extra caller fields pass unchanged.",
            "No tracked executable road for other actions is present in this build.",
            "Every emitted field is proven against a declared contract; "
            "unprovable fields fail the call rather than crossing.",
            "Errors are constant codes. Diagnostic text never crosses.",
            "Identifiers are opaque. Their meaning stays on the host.",
            "The bridge listens on loopback only and requests no credential.",
        ],
        "operations": ops,
    }

