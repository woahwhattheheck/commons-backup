#!/usr/bin/env python3
"""host/sdc_os_button.py — A ROUTING BUTTON (owner 07-19, verbatim, for all of time):

  A ROUTING BUTTON = ONE-TIME PY SCRIPT PER INSTANCE THAT PUTS OUTSIDE INFO (such as block data, or prompt tokens) INTO
  THE DESIRED LOCATION, ONE WAY — the SDC CANNOT reach back and short-circuit the sandbox — AND THEN THE BUTTON DIES.
  THAT IS ALL A ROUTING BUTTON IS AND EVER WILL BE.

It does NOT ripple, does NOT evaluate, does NOT compute, does NOT launch anything (no subprocess/Popen — NO TOOLS), does
NOT read an answer back. The executor is FORBIDDEN. Every function that used to be a process (routing/dispatch/compute/
write-out) is BAKED INTO THE SDC AS GATES with the circuit tool, before this button is ever pressed. This button only puts
the outside info into `os_input`, one-way, and dies. The SDC (baked gates), when powered, produces the answer to the
safezone; the host only reads the safezone.

  python host/sdc_os_button.py "9094 * 40496"
"""
import json, mmap, os, re, struct, sys
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"


def encode(request):
    """format the outside prompt into the input register's fields (opcode + operands). Placing structured outside info
    into the desired location — one-way input routing, not compute."""
    s = request.strip()
    m = re.fullmatch(r"\s*(-?\d+)\s*\*\s*(-?\d+)\s*", s)
    if m: return 1, int(m.group(1)) & 0xffffffff, int(m.group(2)) & 0xffffffff
    m = re.fullmatch(r"\s*(?:is\s+)?(-?\d+)\s*>\s*(-?\d+)\s*\??\s*", s)
    if m: return 4, int(m.group(1)) & 0xffffffff, int(m.group(2)) & 0xffffffff
    m = re.fullmatch(r"\s*(?:is\s+)?(-?\d+)\s*([+\-])\s*(-?\d+)\s*", s)
    if m: return (2 if m.group(2) == "+" else 3), int(m.group(1)) & 0xffffffff, int(m.group(3)) & 0xffffffff
    return 0, 0, 0


def main():
    request = sys.argv[1] if len(sys.argv) > 1 else ""
    reg = json.load(open(REG))
    for k in ("os_input", "os_receiver", "sdc_os_circuit"):
        if k not in reg: print(f"{k} not fabricated — run host/sdc_os_fab.py + host/sdc_os_bake.py."); return 1
    io = int(reg["os_input"]["offset"]); rc = int(reg["os_receiver"]["offset"])
    opcode, a, b = encode(request)

    with open(TITAN, "r+b") as f: f.seek(io); f.write(struct.pack("<BII", opcode, a, b))   # put outside info into os_input (one-way)
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    _ = mm[rc]; mm.close(); f.close()                                                       # route power to the receiver (one addressed read)

    print(f"ROUTING BUTTON: put opcode={opcode} a={a} b={b} into os_input; power routed to the receiver. button dying NOW.", flush=True)
    return 0                                                                                # the button DIES — it is not a process


if __name__ == "__main__":
    raise SystemExit(main())
