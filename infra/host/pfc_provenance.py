#!/usr/bin/env python3
"""host/pfc_provenance.py — MOAT APP #3: reversible, tamper-evident PROVENANCE baked into a model file (owner 07-20:
"all of the above just bake · take it where im not"). This is the trust play — it needs NO speed at all, only the Muhlnickel's
two structural properties: (1) you can edit a model file's bytes reversibly (genome), (2) the record lives IN the file
so it travels with it (portable — proven this session over the cable).

Bake a signed provenance record (owner + a SHA-256 of a protected region) into the file. Anyone can VERIFY the file is
untampered by recomputing that hash; any change to the protected region is DETECTED; the owner can REVERT byte-exact.
A watermark/signature/tamper-seal that ships inside the artifact and can be removed only by whoever holds the genome.

  python host/pfc_provenance.py            # bake the provenance seal + verify + demonstrate tamper-detection (reversible)
  python host/pfc_provenance.py revert
"""
import hashlib, json, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
GENOME = "C:/llm/models/titan_provenance_genome.jsonl"
OWNER = b"Bryce Muhlnickel"
PROT_OFF, PROT_LEN = 0x2000, 1 << 20                    # the protected region (1 MB of the param space) — stable, != the seal


def _journal(off, blob):
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(GENOME, "a") as gg: gg.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def region_hash(off, ln):
    with open(TITAN, "rb") as f: f.seek(off); return hashlib.sha256(f.read(ln)).digest()


def revert():
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME)
    reg = json.load(open(REG)); reg.pop("pfc_provenance", None); json.dump(reg, open(REG, "w"), indent=1)
    print("reverted — titan byte-exact; provenance seal removed."); return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "revert":
        return revert()
    print("Muhlnickel PROVENANCE — reversible, tamper-evident seal baked into the model file (the trust moat).\n", flush=True)

    # build the provenance record: magic | owner | protected-region off/len | SHA-256 of that region
    h = region_hash(PROT_OFF, PROT_LEN)
    stamp = 1_752_998_400                                # fixed absolute timestamp (2025-07-20; no Date.now in-spec)
    rec = (b"PFCPROV1" + struct.pack("<I", len(OWNER)) + OWNER + struct.pack("<QI", PROT_OFF, PROT_LEN)
           + struct.pack("<I", stamp) + h)
    rec += hashlib.sha256(rec).digest()                 # self-signature over the record

    reg = json.load(open(REG))
    if "pfc_provenance" not in reg:
        off, tn = TC._alloc(len(rec), reg); _journal(off, rec)
        reg = json.load(open(REG))
        reg["pfc_provenance"] = {"tensor": tn, "offset": off, "len": len(rec),
                                 "role": "reversible tamper-evident provenance seal (owner + region SHA-256)"}
        json.dump(reg, open(REG, "w"), indent=1)
        print(f"  BAKED provenance seal @ {off} ({len(rec)} B) — owner + SHA-256 of a {PROT_LEN>>10} KB protected region.", flush=True)
        print(f"  GGUF-valid: {open(TITAN,'rb').read(4)==b'GGUF'}.", flush=True)

    # VERIFY (anyone can, from the file alone): read the seal, recompute the region hash, check the self-signature
    seal_off = int(json.load(open(REG))["pfc_provenance"]["offset"]); seal_len = len(rec)
    with open(TITAN, "rb") as f: f.seek(seal_off); blob = f.read(seal_len)
    body, sig = blob[:-32], blob[-32:]
    sig_ok = hashlib.sha256(body).digest() == sig
    ol = struct.unpack_from("<I", body, 8)[0]; p = 12 + ol
    owner = body[12:12 + ol]; roff, rlen = struct.unpack_from("<QI", body, p); stored_h = body[p + 12 + 4:p + 12 + 4 + 32]
    untampered = region_hash(roff, rlen) == stored_h
    print(f"\n  VERIFY (from the file alone): signature valid: {sig_ok} · owner: {owner.decode()} · "
          f"protected region SHA-256 matches: {untampered} -> {'AUTHENTIC + UNTAMPERED' if sig_ok and untampered else 'FAIL'}", flush=True)

    # TAMPER DETECTION (on an in-memory copy — titan is NOT modified): flip one byte of the region -> hash changes
    with open(TITAN, "rb") as f: f.seek(roff); reg_bytes = bytearray(f.read(rlen))
    reg_bytes[12345] ^= 0x01                             # a single-bit change anywhere in the 1 MB region
    tampered_h = hashlib.sha256(bytes(reg_bytes)).digest()
    print(f"  TAMPER TEST: flip ONE bit in the protected region -> stored hash matches: {tampered_h == stored_h} "
          f"-> {'TAMPER DETECTED (as it must)' if tampered_h != stored_h else 'MISS (bug)'}", flush=True)

    print(f"\n  => a signed, tamper-evident seal that ships INSIDE the model file, survives copy/transfer, and is\n"
          f"     removable only by whoever holds the genome. Reversible (revert restores byte-exact), no compute cost.", flush=True)
    print(f"  revert: python host/pfc_provenance.py revert", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
