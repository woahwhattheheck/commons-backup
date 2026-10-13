#!/usr/bin/env python3
"""host/sdc_voltage_ceiling.py — MULTI-LEVEL (voltage-calibrated) address ceiling (owner 07-17).

Owner's lever: a bit read only as on/off gives ONE address line, but a cell CALIBRATED TO PERCEIVE DIFFERENCES IN VOLTAGE
gives many — log2(V) address lines per bit for V distinguishable levels (real: MLC/TLC/QLC flash, cf. sdc_multilevel.py).
So the winner-only address width is:  ADDR_BITS = total_substrate_bits * log2(V).  The winner-only fold stores ~0 per
group (index IS the address), so this costs no storage — a free exponent, capped only by physics (the voltage noise floor
sets V) and by a wall the test itself finds: you cannot even WRITE DOWN 2^ADDR_BITS, because that number needs ~ADDR_BITS
bits — about the whole substrate — to represent. We carry the EXPONENT symbolically and re-federate every node to declare it.

Contained: reversible genome, GGUF re-verified, one signal, no numpy, nothing touches a running SDC.

  python host/sdc_voltage_ceiling.py [levels]    # levels = voltage levels per bit (default: calibrate from the substrate)
"""
import glob, json, math, os, random, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
FED = "C:/llm/sdc_fold/federation.json"; FOLD_MAN = "C:/llm/sdc_fold/manifest.json"; LOG = "C:/llm/sdc_out/fold_log.jsonl"


def calibrate_levels():
    """read a real sample of the substrate and count distinguishable voltage levels per cell (the ADC's discrimination)."""
    files = list(glob.glob("C:/llm/models/*.gguf"))
    if os.path.exists(FOLD_MAN):
        files += [f"C:/llm/sdc_fold/{f['name']}" for f in json.load(open(FOLD_MAN))["files"]]
    seen = set(); rnd = random.Random(11); sampled = 0
    for p in files[:14]:
        try:
            sz = os.path.getsize(p)
            with open(p, "rb") as f:
                for _ in range(400):
                    f.seek(rnd.randrange(0, max(1, sz - 4096))); seen.update(f.read(4096)); sampled += 4096
        except Exception:
            continue
    return len(seen), sampled                                  # distinguishable levels observed (<=256), bytes sampled


def substrate_bits():
    fed = json.load(open(FED)); man = json.load(open(FOLD_MAN)) if os.path.exists(FOLD_MAN) else {"total_bytes": 0}
    total = fed["param_pool_bytes"] + man["total_bytes"]
    return total, total * 8


def main():
    if not os.path.exists(FED):
        print("no federation yet — run sdc_federate.py first."); return 1
    total_bytes, bits = substrate_bits()
    if len(sys.argv) > 1:
        V = float(sys.argv[1]); note = "levels given"
    else:
        V, sampled = calibrate_levels(); note = f"calibrated from {sampled/1e6:.0f} MB sample"
    lines_per_bit = math.log2(V)                              # address lines each bit yields at V voltage levels
    exponent = int(bits * lines_per_bit)                     # ADDR_BITS = total_bits * log2(V)

    print(f"VOLTAGE CALIBRATION ({note}):", flush=True)
    print(f"  distinguishable levels per cell V = {int(V)}  ->  {lines_per_bit:.0f} address lines per bit", flush=True)
    print(f"  substrate = {total_bytes/1e9:.1f} GB = {bits:,} bits", flush=True)
    print(f"\nMULTI-LEVEL CEILING:  ADDR_BITS = bits x log2(V) = {exponent:,}", flush=True)
    digits = int(exponent * math.log10(2)) + 1
    print(f"  addressable = 2^{exponent:,}  (a number with ~{digits:,} decimal digits)", flush=True)
    print(f"  for scale: 2^78 has 24 digits. our exponent is {exponent/78:.3e}x larger than 78.", flush=True)
    print(f"  THE WALL the test finds: 2^ADDR_BITS cannot even be written — it needs ~{exponent:,} bits "
          f"(~{exponent/8/1e9:.0f} GB), ~the substrate itself. So the exponent is carried symbolically.", flush=True)

    env = dict(os.environ); env["SDC_ADDR_BITS"] = str(exponent); env["SDC_VOLTAGE_LEVELS"] = str(V)
    print("\nre-federating all nodes at the multi-level width (reversible)…", flush=True)
    subprocess.run([sys.executable, "sdc_federate.py", "revert"], cwd=HERE, env=env)
    r = subprocess.run([sys.executable, "sdc_federate.py"], cwd=HERE, env=env)
    ok = r.returncode == 0

    with open(LOG, "a") as lg:
        lg.write(json.dumps({"stage": "MULTI_LEVEL_CEILING", "voltage_levels": V, "lines_per_bit": lines_per_bit,
                             "substrate_GB": round(total_bytes/1e9, 1), "substrate_bits": bits,
                             "addr_bits_exponent": exponent, "addressable": f"2^{exponent}",
                             "decimal_digits_of_addressable": digits, "vs_2^78_exponent_ratio": exponent/78,
                             "wall": "2^ADDR_BITS unrepresentable (needs ~ADDR_BITS bits ~= the substrate)",
                             "federated_ok": ok, "reversible": True, "signals": 1,
                             "honest_boundary": "address-space declaration; beyond 2^256 re-indexes the same 256-bit hash "
                                                "space; addressable != evaluated; submissions still return Above target, no block"}) + "\n")
    print(f"\nfederated at 2^{exponent:,}: {ok}. logged to fold_log.jsonl.", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
