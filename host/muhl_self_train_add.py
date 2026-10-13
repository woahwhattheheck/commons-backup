#!/usr/bin/env python3
"""host/muhl_self_train_add.py — ADDITIVE pocket-training inject/surface button.

The computer is software. Manufacturing minds is free. Training stays private;
the later deliverable is the weights/mind, not the factory.

Host jobs only: inject the start signal, surface the mind. cpu_fwd and
muhl_self_train already in the file ARE the trainer. This wrapper does not
fabricate, does not host-eval gates, does not reimplement training, and does
not import the vault host/muhl_self_train.py (OneDrive sys.path + 40GB-era
reservoir constant).

Default is --dry: print the inject/surface plan from the LIVE registry, write
nothing. --inject is OFF unless passed, and is refused (dry-only success) if
the one-byte start is unsafe.

  python host/muhl_self_train_add.py              # dry plan (default)
  python host/muhl_self_train_add.py --dry
  python host/muhl_self_train_add.py --surface    # bounded read: intake header + weights
  python host/muhl_self_train_add.py --inject     # journal + one-byte start at live receiver
  python host/muhl_self_train_add.py revert       # restore from this genome only
"""
from __future__ import annotations

import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    import pfc_paths as PFCP
    PFC_ROOT = PFCP.ROOT
    TITAN = PFCP.TITAN
    REG = PFCP.REG
    MODELS = PFCP.MODELS
except (ImportError, AttributeError):
    PFC_ROOT = os.environ.get("PFC_ROOT", "C:/llm").replace("\\", "/").rstrip("/")
    TITAN = PFC_ROOT + "/models/titan.gguf"
    REG = PFC_ROOT + "/models/titan_circuits.json"
    MODELS = PFC_ROOT + "/models"

GENOME = MODELS.rstrip("/") + "/titan_self_train_add_genome.jsonl"

TRAIN_NAME = "muhl_self_train"
WEIGHTS_NAME = "muhl_self_train.weights"
INTAKE_NAME = "muhl_self_train.intake"
CPU_NAME = "cpu_fwd"
ELECTRON = b"\x01"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _fail(msg):
    print("FAIL CLOSED: %s" % msg)
    return 1


def _readback(off, n):
    with open(TITAN, "rb", buffering=0) as f:
        f.seek(off)
        return f.read(n)


def _load_registry():
    if not os.path.isfile(REG):
        return None, "registry missing: %s" % REG
    try:
        with open(REG, encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, "registry unreadable: %s" % exc


def _need_region(reg, name, kind_hint):
    if name not in reg:
        return None, "%s not in registry" % name
    entry = reg[name]
    if not isinstance(entry, dict):
        return None, "%s is not a circuit/region record" % name
    if entry.get("offset") is None or entry.get("len") is None:
        return None, "%s missing offset/len" % name
    off = int(entry["offset"])
    length = int(entry["len"])
    if off < 0 or length <= 0:
        return None, "%s has non-positive offset/len" % name
    out = {
        "name": name,
        "kind": kind_hint,
        "offset": off,
        "len": length,
    }
    for key in (
        "n_in", "n_out", "n_gate", "seq", "state_off", "state_bytes",
        "loop_bit_off", "receiver", "header_len", "capacity",
        "write_ptr_off", "size_off", "capacity_off", "data_start",
        "n_weights", "weight_bits", "architecture", "depth",
    ):
        if key in entry:
            out[key] = entry[key]
    return out, None


def _inject_site(reg, train):
    """Live one-byte start from the named receiver. Never a hardcoded reservoir constant."""
    recv_name = train.get("receiver")
    if not recv_name:
        return None, "muhl_self_train has no receiver name"
    if recv_name not in reg:
        return None, "receiver %s not in registry" % recv_name
    recv = reg[recv_name]
    if not isinstance(recv, dict):
        return None, "receiver %s is not a circuit record" % recv_name

    candidates = []
    if recv.get("input_addr") is not None:
        candidates.append(("input_addr", int(recv["input_addr"])))
    wire_key = "%s.input_wire" % recv_name
    wire = reg.get(wire_key)
    if isinstance(wire, dict) and wire.get("offset") is not None:
        candidates.append((wire_key, int(wire["offset"])))

    if not candidates:
        return None, (
            "receiver %s has no live input_addr / .input_wire offset" % recv_name
        )
    offs = {off for _src, off in candidates}
    if len(offs) != 1:
        detail = ", ".join("%s=%d" % (src, off) for src, off in candidates)
        return None, "receiver inject offsets disagree (%s)" % detail
    src, off = candidates[0]
    if off < 0:
        return None, "receiver inject offset is negative"
    return {
        "receiver": recv_name,
        "off": off,
        "source": src,
        "byte": ELECTRON,
        "n_gate": recv.get("n_gate"),
        "n_out": recv.get("n_out"),
    }, None


def load_plan():
    """Fail closed if the trainer circuits/regions are missing. Never guess names."""
    reg, err = _load_registry()
    if err:
        return None, err

    cpu, err = _need_region(reg, CPU_NAME, "cpu")
    if err:
        return None, err
    train, err = _need_region(reg, TRAIN_NAME, "trainer")
    if err:
        return None, err
    weights, err = _need_region(reg, WEIGHTS_NAME, "mind")
    if err:
        return None, err
    intake, err = _need_region(reg, INTAKE_NAME, "intake")
    if err:
        return None, err

    site, site_err = _inject_site(reg, train)
    titan_exists = os.path.isfile(TITAN)
    titan_size = os.path.getsize(TITAN) if titan_exists else None

    unsafe = []
    if site_err:
        unsafe.append(site_err)
    if not titan_exists:
        unsafe.append("titan missing: %s" % TITAN)
    elif site is not None:
        if titan_size is None or site["off"] + 1 > titan_size:
            unsafe.append(
                "inject offset %d is past titan size %s" % (site["off"], titan_size)
            )

    return {
        "cpu": cpu,
        "train": train,
        "weights": weights,
        "intake": intake,
        "site": site,
        "titan_exists": titan_exists,
        "titan_size": titan_size,
        "unsafe": unsafe,
    }, None


def print_plan(plan, dry=True):
    if dry:
        mode = "DRY — plan only, no titan write"
    else:
        mode = "INJECT — journal then one-byte start"
    train = plan["train"]
    cpu = plan["cpu"]
    weights = plan["weights"]
    intake = plan["intake"]
    site = plan["site"]

    print("\nMUHL SELF-TRAIN (additive pocket training center)")
    print("  mode:      %s" % mode)
    print("  pfc_root:  %s" % PFC_ROOT)
    print("  titan:     %s" % TITAN)
    print("  reg:       %s" % REG)
    print("  genome:    %s" % GENOME)
    print("  public:    NO — factory stays here; later deliverable is the mind")
    print()
    print("  TRAINER IN THE FILE (not this host process)")
    print("    %s  n_gate=%s  n_in=%s  n_out=%s  depth=%s"
          % (cpu["name"], cpu.get("n_gate"), cpu.get("n_in"),
             cpu.get("n_out"), cpu.get("depth")))
    print("    %s  n_gate=%s  n_in=%s  n_out=%s  seq=%s  receiver=%s"
          % (train["name"], train.get("n_gate"), train.get("n_in"),
             train.get("n_out"), train.get("seq"), train.get("receiver")))
    print()
    print("  SURFACE (bounded read)")
    print("    %s  off %d  len %d  arch=%s  n_weights=%s  bits=%s"
          % (weights["name"], weights["offset"], weights["len"],
             weights.get("architecture"), weights.get("n_weights"),
             weights.get("weight_bits")))
    print("    %s  off %d  len %d  header_len=%s  capacity=%s"
          % (intake["name"], intake["offset"], intake["len"],
             intake.get("header_len"), intake.get("capacity")))
    print()
    print("  INJECT (one byte at the live receiver — default OFF)")
    if site is None:
        print("    site:    UNSAFE — no live inject address")
    else:
        print("    receiver %s" % site["receiver"])
        print("    field    %s" % site["source"])
        print("    off      %d  byte 0x%02x" % (site["off"], site["byte"][0]))
        if site.get("n_gate") is not None:
            print("    n_gate   %s  n_out=%s" % (site["n_gate"], site.get("n_out")))
    if plan["titan_exists"]:
        print("    titan    present (%s bytes)" % plan["titan_size"])
    else:
        print("    titan    missing")
    if plan["unsafe"]:
        print()
        print("  UNSAFE TO INJECT:")
        for reason in plan["unsafe"]:
            print("    - %s" % reason)
        print("  dry-only is success; --inject will be refused.")
    elif dry:
        print()
        print("  (no write performed; pass --inject to journal+place the start byte)")
    print()
    return 0


def surface(plan):
    """Bounded read of intake header + weights. No gate evaluation."""
    if not plan["titan_exists"]:
        return _fail("titan missing: %s" % TITAN)
    weights = plan["weights"]
    intake = plan["intake"]
    header_len = int(intake.get("header_len") or 24)
    if header_len <= 0 or header_len > intake["len"]:
        return _fail("%s header_len missing or past region" % INTAKE_NAME)

    hdr = _readback(intake["offset"], header_len)
    mind = _readback(weights["offset"], weights["len"])
    if len(hdr) != header_len:
        return _fail("%s short header read" % INTAKE_NAME)
    if len(mind) != weights["len"]:
        return _fail("%s short weights read" % WEIGHTS_NAME)

    print("\nSURFACE — bounded read (intake header + weights/mind)\n")
    if header_len >= 24:
        write_ptr, size_used, capacity = struct.unpack_from("<QQQ", hdr, 0)
        print("  %s header" % INTAKE_NAME)
        print("    write_ptr %d" % write_ptr)
        print("    size      %d" % size_used)
        print("    capacity  %d" % capacity)
    else:
        print("  %s header hex=%s" % (INTAKE_NAME, hdr.hex()))
    print("  %s" % WEIGHTS_NAME)
    print("    arch=%s  n_weights=%s  bits=%s  len=%d"
          % (weights.get("architecture"), weights.get("n_weights"),
             weights.get("weight_bits"), weights["len"]))
    print("    hex=%s" % mind.hex())
    print("    (mind bytes only — host does not train or eval)")
    print()
    return 0


def _journal_and_place(off, blob, tag):
    orig = _readback(off, len(blob))
    os.makedirs(os.path.dirname(GENOME), exist_ok=True)
    with open(GENOME, "a", encoding="utf-8") as gg:
        gg.write(json.dumps({
            "off": off,
            "len": len(blob),
            "name": tag,
            "orig": orig.hex(),
            "tool": "muhl_self_train_add",
        }) + "\n")
        gg.flush()
        os.fsync(gg.fileno())
    with open(TITAN, "r+b") as f:
        f.seek(off)
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())


def inject(plan):
    if plan["unsafe"] or plan["site"] is None:
        print_plan(plan, dry=True)
        print("INJECT REFUSED (unsafe). Dry-only is success.\n")
        return 0
    print_plan(plan, dry=False)
    site = plan["site"]
    tag = "%s.start" % site["receiver"]
    _journal_and_place(site["off"], site["byte"], tag)
    print("  placed 1 start byte at live receiver; host withdrawn.")
    print("  genome: %s" % GENOME)
    print("  revert: python host/muhl_self_train_add.py revert\n")
    return surface(plan)


def revert():
    if not os.path.exists(GENOME):
        print("nothing to revert (no %s)." % GENOME)
        return 0
    ent = [json.loads(l) for l in open(GENOME, encoding="utf-8") if l.strip()]
    back = 0
    for e in reversed(ent):
        want = bytes.fromhex(e["orig"])
        with open(TITAN, "r+b") as f:
            f.seek(int(e["off"]))
            f.write(want)
            f.flush()
            os.fsync(f.fileno())
        if _readback(int(e["off"]), len(want)) == want:
            back += 1
    os.remove(GENOME)
    print("reverted %d placed byte(s); %d read back byte-identical to self-train-add genome."
          % (len(ent), back))
    return 0


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    if a and a[0] == "revert":
        return revert()

    plan, err = load_plan()
    if err:
        return _fail(err)

    do_inject = "--inject" in a
    do_surface = "--surface" in a
    do_dry = ("--dry" in a) or (not do_inject and not do_surface)

    if do_inject and do_dry:
        print_plan(plan, dry=True)
        print("  --dry wins over --inject; no write.\n")
        return 0
    if do_inject:
        return inject(plan)
    if do_surface:
        print_plan(plan, dry=True)
        return surface(plan)
    return print_plan(plan, dry=True)


if __name__ == "__main__":
    raise SystemExit(main())
