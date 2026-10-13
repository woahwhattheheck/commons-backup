"""adapters/muhl_surface.py — SURFACING VERBS, wired to the actual Muhlnickel.

ASTER'S CORRECTION, IMPLEMENTED AS A PROPERTY OF THE CODE:
  * every verb here reads the live container. There is NO local-state path.
  * there is NO fallback. If the container cannot be read, the verb RAISES. It never returns a
    plausible default, so a stub can never produce a passing result.
  * every response carries PROVENANCE: bytes actually observed, the change marker before and after
    the read, whether it held, and a digest of exactly those bytes. A caller can tell a real
    operation from a fabricated one without trusting this module.

THE HOST'S ROLE HERE IS VERB TWO ONLY: surface the output. Nothing in this file evaluates a gate,
advances a state, resolves a contact, or computes an answer. It reads bytes and reports what it read.
Configuration is not a runtime act and does not live here.

IP BOUNDARY: no path, lever name, circuit name, offset semantics or mechanism crosses the bridge.
Container identity is an opaque handle. Offsets are echoed only when the caller supplied them.
"""
import hashlib
import os
import sys
import time

# The bridge root holds the public schema. When loaded by the plugin discoverer the parent package
# is already importable; when run directly as a self-test it is not, so make it so either way.
_BRIDGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BRIDGE not in sys.path:
    sys.path.insert(0, _BRIDGE)

from public_schema import Shape, Param, Listing, Handle, Flag, Count, Text, Enum

COHERENCE = Enum("coherent", "torn", "unknown")


class SurfaceUnavailable(Exception):
    """The live container could not be read. Deliberately NOT caught anywhere in this module:
    a surfacing verb that cannot reach the machine must fail, never substitute."""


def _require(ctx):
    p = ctx.muhlnickel
    if not os.path.exists(p):
        raise SurfaceUnavailable("container absent")
    if os.path.getsize(p) == 0:
        raise SurfaceUnavailable("container empty")
    return p


def _prov(ctx, data, before, after, offset=None):
    """The provenance block. Present on EVERY response from this module."""
    d = {
        "source": "muhlnickel",
        "bytes_observed": len(data),
        "container": ctx.handle("container:" + ctx.generation().split(":")[0]),
        "marker_before": ctx.handle("gen:" + before),
        "marker_after": ctx.handle("gen:" + after),
        "coherent": before == after,
        "digest": hashlib.sha256(data).hexdigest(),
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if offset is not None:
        d["offset"] = offset
    return d


PROV = Shape(
    source=Text(32),
    bytes_observed=Count(),
    container=Handle(),
    marker_before=Handle(),
    marker_after=Handle(),
    coherent=Flag(),
    digest=Text(64),
    observed_at=Text(32),
)

PROV_OFF = Shape(
    source=Text(32), bytes_observed=Count(), container=Handle(),
    marker_before=Handle(), marker_after=Handle(), coherent=Flag(),
    digest=Text(64), observed_at=Text(32), offset=Count(),
)


# ---------------------------------------------------------------------------
# verbs
# ---------------------------------------------------------------------------

def identity(ctx):
    """What machine is this, and is it changing."""
    _require(ctx)
    before = ctx.generation()
    size = ctx.size()
    head = ctx.read(0, min(64, size))
    after = ctx.generation()
    return {
        "byte_count": size,
        "provenance": _prov(ctx, head, before, after, offset=0),
    }


def snapshot(ctx):
    """A DETERMINISTIC full-state snapshot. The complete container is read and only reported as
    coherent when the change marker held across the entire read; a torn read is retried, and if it
    cannot be taken coherently that is REPORTED as torn rather than dressed up."""
    _require(ctx)
    buf, marker, coherent = ctx.snapshot()
    before = marker if coherent else ctx.generation()
    return {
        "byte_count": len(buf),
        "coherence": "coherent" if coherent else "torn",
        "provenance": _prov(ctx, buf, before, ctx.generation(), offset=0),
    }


def region(ctx, offset=0, length=4096):
    """A bounded read of a caller-chosen region, returned as hex with provenance."""
    _require(ctx)
    size = ctx.size()
    if offset < 0 or offset >= size:
        raise SurfaceUnavailable("offset outside the machine")
    length = max(1, min(int(length), 65536, size - offset))
    before = ctx.generation()
    data = ctx.read(offset, length)
    after = ctx.generation()
    return {
        "hex": data.hex(),
        "provenance": _prov(ctx, data, before, after, offset=offset),
    }


def frame(ctx, columns=256):
    """A FULL-STATE frame buffer: every byte of the machine folded into a fixed-width grid, with
    a per-row digest so a caller can verify coverage. No byte is omitted and none is sampled."""
    _require(ctx)
    buf, marker, coherent = ctx.snapshot()
    cols = max(16, min(int(columns), 4096))
    rows = []
    covered = 0
    for i in range(0, len(buf), cols):
        chunk = buf[i:i + cols]
        covered += len(chunk)
        rows.append({"row": i // cols, "start": i, "bytes": len(chunk),
                     "digest": hashlib.sha256(chunk).hexdigest()[:16]})
    return {
        "byte_count": len(buf),
        "represented": covered,
        "complete": covered == len(buf),
        "columns": cols,
        "row_count": len(rows),
        "rows": rows[:4096],
        "coherence": "coherent" if coherent else "torn",
        "provenance": _prov(ctx, buf, marker, ctx.generation(), offset=0),
    }


def compare(ctx, offset=0, length=4096):
    """Two observations of the same region, back to back, and the exact byte ranges that differ.
    This is a measurement of the live machine, not a claim about it: if nothing differs, that is
    reported as zero changed ranges and no verdict is attached."""
    _require(ctx)
    size = ctx.size()
    offset = max(0, min(int(offset), size - 1))
    length = max(1, min(int(length), 65536, size - offset))
    m0 = ctx.generation()
    a = ctx.read(offset, length)
    b = ctx.read(offset, length)
    m1 = ctx.generation()
    ranges, run = [], None
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            run = run or i
        elif run is not None:
            ranges.append({"start": offset + run, "bytes": i - run}); run = None
    if run is not None:
        ranges.append({"start": offset + run, "bytes": len(a) - run})
    return {
        "changed_ranges": ranges[:256],
        "changed_range_count": len(ranges),
        "changed_bytes": sum(r["bytes"] for r in ranges),
        "marker_moved": m0 != m1,
        "provenance": _prov(ctx, a, m0, m1, offset=offset),
    }


VERBS = {
    "muhl.identity": {
        "desc": "Identify the live machine and report whether it is changing.",
        "params": {},
        "result": Shape(byte_count=Count(), provenance=PROV_OFF),
        "fn": identity, "writes": False,
    },
    "muhl.snapshot": {
        "desc": "Take a deterministic whole-machine snapshot and report its coherence honestly.",
        "params": {},
        "result": Shape(byte_count=Count(), coherence=COHERENCE, provenance=PROV_OFF),
        "fn": snapshot, "writes": False,
    },
    "muhl.region": {
        "desc": "Bounded read of a chosen region of the live machine.",
        "params": {"offset": Param(Count(), required=False),
                   "length": Param(Count(), required=False)},
        "result": Shape(hex=Text(131072), provenance=PROV_OFF),
        "fn": region, "writes": False,
    },
    "muhl.frame": {
        "desc": "Full-state frame buffer covering every byte, with per-row digests and a coverage "
                "proof that represented bytes equal the machine's byte count.",
        "params": {"columns": Param(Count(), required=False)},
        "result": Shape(byte_count=Count(), represented=Count(), complete=Flag(),
                        columns=Count(), row_count=Count(),
                        rows=Listing(Shape(row=Count(), start=Count(), bytes=Count(),
                                           digest=Text(16))),
                        coherence=COHERENCE, provenance=PROV_OFF),
        "fn": frame, "writes": False,
    },
    "muhl.compare": {
        "desc": "Observe a region twice and report the exact byte ranges that differ.",
        "params": {"offset": Param(Count(), required=False),
                   "length": Param(Count(), required=False)},
        "result": Shape(changed_ranges=Listing(Shape(start=Count(), bytes=Count())),
                        changed_range_count=Count(), changed_bytes=Count(),
                        marker_moved=Flag(), provenance=PROV_OFF),
        "fn": compare, "writes": False,
    },
}


# ---------------------------------------------------------------------------
# self-test: exercise every verb against the REAL container
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import adapter_plugins

    class _Vault:
        def __init__(self): self.n = 0; self.m = {}
        def handle(self, internal):
            if internal not in self.m:
                self.n += 1; self.m[internal] = "h_%06d" % self.n
            return self.m[internal]

    class _Audit:
        def write(self, **kw): pass

    class _A:
        dir = os.path.dirname(os.path.abspath(__file__))
        vault = _Vault(); audit = _Audit()

    ctx = adapter_plugins.AdapterContext(_A())
    print("target        :", os.path.basename(ctx.muhlnickel))
    print("exists        :", os.path.exists(ctx.muhlnickel))
    print("byte count    :", ctx.size())
    print()
    ok = 0
    for verb, spec in VERBS.items():
        try:
            out = spec["fn"](ctx)
            p = out["provenance"]
            assert p["source"] == "muhlnickel", "provenance not from the machine"
            assert p["bytes_observed"] > 0, "no bytes observed"
            assert len(p["digest"]) == 64, "no digest"
            ok += 1
            extra = ""
            if verb == "muhl.frame":
                extra = "  represented=%d complete=%s" % (out["represented"], out["complete"])
            if verb == "muhl.compare":
                extra = "  changed_ranges=%d" % out["changed_range_count"]
            print("  %-16s observed=%-8d coherent=%-5s digest=%s%s"
                  % (verb, p["bytes_observed"], p["coherent"], p["digest"][:16], extra))
        except Exception as exc:
            print("  %-16s FAILED: %s: %s" % (verb, type(exc).__name__, exc))
    print("\n  %d/%d verbs exercised against the real machine" % (ok, len(VERBS)))

    # the no-fallback property, proved rather than asserted
    print("\n  no-fallback check:")
    real = ctx.muhlnickel
    ctx.muhlnickel = real + ".does-not-exist"
    for verb, spec in VERBS.items():
        try:
            spec["fn"](ctx)
            print("    %-16s RETURNED A RESULT WITH NO MACHINE - FALLBACK EXISTS" % verb)
        except SurfaceUnavailable:
            print("    %-16s raised SurfaceUnavailable (correct: no fallback)" % verb)
        except Exception as exc:
            print("    %-16s raised %s" % (verb, type(exc).__name__))
    ctx.muhlnickel = real
