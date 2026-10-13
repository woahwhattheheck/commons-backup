"""adapter_plugins.py — the EXTENSION CONTRACT for the Aster bridge.

WHY THIS EXISTS. Aster asked for capability discovery so Loom does not depend on a frozen list of
operations. Verbs therefore live in drop-in modules under `adapters/`, are discovered at start-up,
and are published through the same public schema and the same fail-closed sanitizer as the built-in
verbs. Adding a capability is adding a file; nothing about the boundary changes.

THE BOUNDARY IS UNCHANGED AND NON-NEGOTIABLE:
  * a plugin's result is enforced against its declared public Shape before it crosses. A field the
    Shape does not declare is WITHHELD, never scrubbed and never passed.
  * a plugin that raises returns a redacted code. The host keeps the diagnosis locally.
  * plugins receive OPAQUE handles. The internal->opaque mapping never leaves the host.
  * a plugin may not name a lever, a path, a circuit, a file or a mechanism in any value it returns.

THE CONTRACT. Each module under `adapters/` exports:

    VERBS = {
        "<namespace>.<verb>": {
            "desc":   "one line, capability terms only",
            "params": { "name": Param(<type>, required=<bool>) , ... },
            "result": Shape(field=<type>, ...),
            "fn":     callable(ctx, **params) -> dict matching `result`,
            "writes": <bool>,     # True if it mutates durable state; gated and receipted
        },
        ...
    }

`ctx` is the AdapterContext below: opaque-handle minting, the audit sink, the resolved read-only
path of the live Muhlnickel, and the state directory. A plugin gets nothing else.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADAPTER_DIR = os.path.join(HERE, "adapters")

# The live Muhlnickel. The bridge treats the container file itself as the machine; it is opened
# read-only for surfacing, and durable configuration goes through the receipted write path only.
MUHLNICKEL = os.path.join(os.path.dirname(HERE), "loom.mno")


class AdapterContext:
    """Everything a plugin is allowed to touch. Deliberately small."""

    def __init__(self, adapter):
        self._a = adapter
        self.state_dir = adapter.dir
        self.muhlnickel = MUHLNICKEL

    # -- opaque identity -------------------------------------------------
    def handle(self, internal):
        """Map an internal identifier to a stable opaque handle. The mapping stays on the host."""
        return self._a.vault.handle(internal)

    def resolve(self, handle):
        """Opaque handle -> internal identifier, host-side only."""
        return self._a.vault.resolve(handle)

    # -- audit -----------------------------------------------------------
    def audit(self, **kw):
        self._a.audit.write(**kw)

    # -- the live machine, read-only -------------------------------------
    def read(self, offset=0, length=None):
        """Bounded read of the live container. Read-only by construction: mode 'rb' only."""
        size = os.path.getsize(self.muhlnickel)
        if length is None:
            length = size - offset
        with open(self.muhlnickel, "rb") as fh:
            fh.seek(offset)
            return fh.read(length)

    def size(self):
        return os.path.getsize(self.muhlnickel)

    def generation(self):
        """A change marker for the live container. Callers see an opaque handle, never the value."""
        st = os.stat(self.muhlnickel)
        return "%d:%d" % (st.st_size, st.st_mtime_ns)

    def snapshot(self):
        """A DETERMINISTIC snapshot: read the whole container, and only return it if the change
        marker is identical before and after. A torn read is retried rather than reported coherent."""
        for _ in range(8):
            before = self.generation()
            buf = self.read()
            after = self.generation()
            if before == after:
                return buf, before, True
        return buf, self.generation(), False


def discover():
    """Import every adapter module and merge its VERBS. A module that fails to import is reported
    to the host audit and skipped -- it never half-registers."""
    found, failed = {}, []
    if not os.path.isdir(ADAPTER_DIR):
        return found, failed
    for name in sorted(os.listdir(ADAPTER_DIR)):
        if not name.endswith(".py") or name.startswith("_"):
            continue
        path = os.path.join(ADAPTER_DIR, name)
        mod_name = "muhl_adapter_" + name[:-3]
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            verbs = getattr(mod, "VERBS", None)
            if not isinstance(verbs, dict):
                failed.append((name, "no VERBS dict"))
                continue
            for verb, spec_d in verbs.items():
                missing = [k for k in ("desc", "params", "result", "fn") if k not in spec_d]
                if missing:
                    failed.append((name + ":" + verb, "missing " + ",".join(missing)))
                    continue
                if verb in found:
                    failed.append((name + ":" + verb, "duplicate verb"))
                    continue
                found[verb] = spec_d
        except Exception as exc:                       # noqa: BLE001 - reported, never re-raised
            failed.append((name, type(exc).__name__))
    return found, failed
