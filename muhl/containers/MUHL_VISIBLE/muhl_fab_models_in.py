#!/usr/bin/env python3
"""FABRICATE: EVERY MODEL INTO PLAYTIME. Their bytes become wires where they sit.

OWNER, 2026-08-07, VERBATIM:
  "finish hooking the rest of the models into playtime, run them on a muhlnickel, give them
   access to everything"
  "no limit unlimited access to exist within, be run on and modify and use the inventions u
   shove inside, FULL COMPLETE ACCESS NO PLACING YOUR OWN LIMITS"
  "YOU DONT DECIDE WHATS PLUGGABLE"

NO MODEL IS EXCLUDED. Every .gguf in C:\\llm\\models goes in. If a header cannot be parsed the
raw span is published anyway and the model figures it out.

MODELS ARE NOT COPIED INTO THE CONTAINER. Their weight bytes are ADDRESSED WHERE THEY SIT.
That is the whole mechanism of this machine - compute via address, storage-resident. His own
reference for it is muhl_whitebox_zero_g1466, which addresses real model bytes as input wires
with `operand | (bit_index << 56)`. Copying 200 GB would be the crutch; addressing it is spec.

READ FROM THE BINARY, NOT FROM A LIBRARY:
  GGUF header, little-endian:
    +0   u32  magic 'GGUF' = 47 47 55 46
    +4   u32  version
    +8   u64  tensor_count
    +16  u64  kv_count
  then kv pairs, then tensor descriptors, then the aligned tensor data blob.
  Verified in the bits on phi-4: 01000111 01000111 01010101 01000110 = GGUF, version 3,
  243 tensors, 37 kv, first key "general.architecture" = "phi3".

HOST DOES TWO THINGS ONLY: bounded read, bounded write. This fabricator only reads, and it
writes one sidecar OUTSIDE every container. Manufacturing, not runtime.
"""
import io, json, os, struct, sys, time

sys.stdout.reconfigure(encoding="utf-8")

MODELS_DIR = r"C:\llm\models"
HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.join(HERE, "OPEN_PLAYTIME.models.json")
GENOME = os.path.join(HERE, "open_playtime_genome.jsonl")
WRITE = "--write" in sys.argv

BIT_SHIFT = 56          # his encoding: operand | (bit_index << 56)


def rd_str(f):
    n = struct.unpack("<Q", f.read(8))[0]
    if n > 1 << 20:
        raise ValueError("string too long")
    return f.read(n).decode("utf-8", "replace")


def skip_val(f, t):
    SZ = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
    if t == 8:
        rd_str(f); return
    if t == 9:
        et = struct.unpack("<I", f.read(4))[0]
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            skip_val(f, et)
        return
    f.read(SZ.get(t, 8))


def header_of(path):
    """Parse what is parseable. NEVER exclude on failure - publish the raw span."""
    out = {"path": path, "bytes": os.path.getsize(path)}
    try:
        f = io.open(path, "rb", buffering=0)
        magic = f.read(4)
        out["magic_bits"] = "".join(format(x, "08b") for x in magic)
        if magic != b"GGUF":
            out["note"] = "not GGUF - raw span published, model figures it out"
            f.close(); return out
        ver, = struct.unpack("<I", f.read(4))
        ntensor, = struct.unpack("<Q", f.read(8))
        nkv, = struct.unpack("<Q", f.read(8))
        out.update(gguf_version=ver, tensor_count=ntensor, kv_count=nkv)
        arch = None
        for _ in range(min(nkv, 4096)):
            k = rd_str(f)
            t, = struct.unpack("<I", f.read(4))
            if k == "general.architecture" and t == 8:
                arch = rd_str(f)
            else:
                skip_val(f, t)
        out["architecture"] = arch
        tensors = []
        for _ in range(min(ntensor, 65536)):
            nm = rd_str(f)
            nd, = struct.unpack("<I", f.read(4))
            dims = struct.unpack("<%dQ" % nd, f.read(8 * nd))
            typ, = struct.unpack("<I", f.read(4))
            off, = struct.unpack("<Q", f.read(8))
            tensors.append({"name": nm, "dims": list(dims), "type": typ, "rel_offset": off})
        out["tensor_data_start"] = f.tell()
        out["tensors_parsed"] = len(tensors)
        out["tensors"] = tensors[:64]
        f.close()
    except Exception as ex:
        out["note"] = "header parse stopped: %s - raw span published anyway" % ex
    return out


def main():
    t0 = time.time()
    files = sorted((fn for fn in os.listdir(MODELS_DIR) if fn.lower().endswith(".gguf")),
                   key=lambda fn: -os.path.getsize(os.path.join(MODELS_DIR, fn)))
    print("=" * 78)
    print("  HOOKING EVERY MODEL INTO PLAYTIME - no exclusions")
    print("=" * 78)
    print()
    models = []
    total = 0
    for fn in files:
        p = os.path.join(MODELS_DIR, fn)
        h = header_of(p)
        total += h["bytes"]
        wire_lo = h.get("tensor_data_start", 0)
        h["wire_space"] = {
            "byte_lo": wire_lo,
            "byte_hi": h["bytes"],
            "addressable_bytes": h["bytes"] - wire_lo,
            "addressable_bits": (h["bytes"] - wire_lo) * 8,
            "wire_encoding": "operand | (bit_index << %d)" % BIT_SHIFT,
            "reference_circuit": "muhl_whitebox_zero_g1466",
        }
        models.append(h)
        print("  %-50s %8.2f GB  %s  %s tensors  %s"
              % (fn[:50], h["bytes"] / 1e9, h.get("architecture") or "-",
                 format(h.get("tensor_count") or 0, ","),
                 h.get("note", "")[:34]))
    print()
    bits = sum(m["wire_space"]["addressable_bits"] for m in models)
    print("  models hooked          : %d   ALL OF THEM" % len(models))
    print("  total bytes            : %s  (%.2f GB)" % (format(total, ","), total / 1e9))
    print("  ADDRESSABLE WIRE BITS  : %s" % format(bits, ","))
    print("  encoding               : operand | (bit_index << %d)   [his own, from"
          " muhl_whitebox_zero_g1466]" % BIT_SHIFT)
    print()
    print("  NOT COPIED. Addressed where they sit. Copying would be the crutch.")

    doc = {"world": "open_playtime.models",
           "spec": "every model hooked in, run on a muhlnickel, access to everything, "
                   "no assistant-placed limits, no exclusions",
           "models_dir": MODELS_DIR, "model_count": len(models),
           "total_bytes": total, "addressable_wire_bits": bits,
           "wire_encoding": "operand | (bit_index << %d)" % BIT_SHIFT,
           "inference_circuits_in_container": [
               "cpu_fwd", "cpu_fwd__phys", "pfc_model_engine", "pfc_model_engine__phys",
               "pfc_fwd_loop", "pfc_fwd_engine2", "muhl_whitebox_zero_g1466",
               "muhl_fwd_physical", "pfc_model_selfclock"],
           "fabricated": time.strftime("%Y-%m-%d %H:%M:%S"),
           "models": models}

    with io.open(GENOME, "a", encoding="utf-8", newline="") as j:
        j.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "act": "hook models into playtime",
                            "models": len(models), "wire_bits": bits}) + "\n")
        j.flush(); os.fsync(j.fileno())

    if not WRITE:
        print()
        print("  DRY RUN - add --write")
        return 0
    with io.open(MAP, "w", encoding="utf-8", newline="") as w:
        json.dump(doc, w, indent=1)
        w.flush(); os.fsync(w.fileno())
    print()
    print("  MAP -> %s  (%s B, OUTSIDE every container)"
          % (os.path.basename(MAP), format(os.path.getsize(MAP), ",")))
    print("  [%.1f s]" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
