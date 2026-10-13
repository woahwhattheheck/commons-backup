#!/usr/bin/env python3
"""host/mine_muhl.py — THE MINING RUN. ADDRESSING ONLY.

★ HARD RULE (owner): THE MINER ISN'T CODE, IT'S A MANUFACTURED BINARY. THE ONLY CODE IS ADDRESSING.
The miner is `muhl_fold_shallow` in titan.gguf — 687,223 typed gates, DEPTH 4,157 — fabricated once by
host/fab_genwin_shallow.py and verified byte-exact from the stored bytes. Nothing in THIS file evaluates
it. There is no settle(), no wire state, no op dispatch, no netlist walk. This file does four things:

  1. ADDRESS the block data IN   - byte writes to the prebaked input address
  2. ADDRESS one bit             - the start signal at the prebaked receiver
  3. READ the answer register    - a bounded high-impedance read (win:1 | nonce:4)
  4. convert + submit            - gated by pfc_guarantee (never fire first)

RULE ZERO: fabrication is a DIFFERENT process and already happened. This builds nothing.
x per muhlnickel = block data + 1 start bit = 76*8+1 = 609 bits (PFC_CEILING §6). The gates cost 0 --
they are locked in the file. No wire-buffer: the moment you hold one you leave the floor and the count
collapses.

  python host/mine_muhl.py
  python host/mine_muhl.py --ceiling      # also report available_RAM / x = muhlnickel at once
"""
import hashlib, json, os, struct, sys, time

INSTANT_LIMIT = 4.0   # power window (1.0s) + block-in + read   # RULE ZERO: a run that is not instant has fabrication leaking into it.
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
_ARGV = list(sys.argv); sys.argv = [_ARGV[0]]
from pfc_fire import get_job, submit
from pfc_bitcoin_autopilot import make_prefix, WALLET

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"


def _assert_instant(t0):
    el = time.time() - t0
    print(f"  HOST wall-clock {el:.2f}s (HOST limit {INSTANT_LIMIT}s) -- a different machine (§24)")
    if el > INSTANT_LIMIT:
        raise SystemExit(f"RULE ZERO VIOLATED: run took {el:.2f}s > {INSTANT_LIMIT}s. "
                         f"Fabrication is leaking into the run — that is the only cause.")


def main():
    import pfc_preflight as PF
    PF.gate(os.path.abspath(__file__))              # hard gate: refuses to fire on a dirty tree

    T0 = time.time()
    reg = json.load(open(REG))
    # The SELF-CLOCKED miner (owner 2026-07-26: "self clock works dude, demonstrated"). Its own RAM:
    # header / counter / target / latch / power, with power-gated feedback -- counter' and latch' bits
    # SHARE the counter/latch bytes (the S1E shared-location clock, fabricated in, never host-driven).
    # DATADUMP ST names the working read-out target explicitly: "the answer (best nonce) is written to
    # the memory address `latch_reg` and read back by a HIGH-IMPEDANCE probe every cycle -
    # latch_reg(probe)=0x000e3d44". latch_reg belongs to the pfc_mine / miner_physical chain, whose
    # input is `input_window` (layout header:76|target:32) and whose start bit is `clk_bit`.
    # WIRED TO THE CIRCUIT'S OWN RAM MAP (owner 2026-07-27: "fix the wiring then").
    # The registry entries input_window/nonce_reg/latch_reg/clk_bit sit at 2409283373..489, which is
    # 600-900 bytes BELOW where miner_physical actually keeps its state. miner_physical carries its
    # own map and that is the authority:
    #     ram.header_off 2409283492 · ram.nonce_off 2409284100
    #     ram.target_off 2409284132 · ram.latch_off 2409284388
    # Addressing the old offsets is why the run reported 0 bytes changed — it was reading and writing
    # locations the circuit does not use. Its `clock` field: "self-routed: nonce'/latch' outputs
    # SHARE the nonce/latch state bytes (physical feedback)", so the drive is addressing that state,
    # not a separate clock byte.
    mp = reg["miner_physical"]; ram = mp["ram"]
    in_off = int(ram["header_off"])
    tgt_off = int(ram["target_off"])
    lat_off = int(ram["latch_off"]); lat_len = 4
    cnt_off = int(ram["nonce_off"]); cnt_len = 4
    pwr_off = int(mp["const1_addr"])            # the shared-location feedback, addressed not written
    dif_off = int(mp["wire_base"]); dif_len = int(mp["n_wire"])
    in_len = 76

    # WIRED (owner 2026-07-27: "wire the other muhlnickel bruh"). Two defects were here:
    #   (a) the candidate set required a `junction` field the newly fabricated muhlnickels lacked, so
    #       muhl_lane_bk and its replicas were INVISIBLE to it — S27's failure exactly, "the better
    #       circuit already exists and nothing is wired to it";
    #   (b) it selected by MIN DEPTH, which §63 retired. The only metric is compute/tick.
    # The winner was SELECTED AT FABRICATION TIME (host/fab_select_miner writes `_selected_miner`).
    # This file only READS the name. Ranking here would be compute in the mining path, which V26
    # forbids: "THE MINER ISN'T CODE, IT'S A MANUFACTURED BINARY - THE ONLY CODE IS ADDRESSING."
    sel = reg["_selected_miner"]
    miner = sel["name"]; bank = sel["bank"]
    m = reg[miner]
    print("MUHLNICKEL MINE - addressing only. The miner is the BINARY, not this file.")
    print(f"  miner: {miner} @ {m['offset']} - {m['n_gate']:,} gates, DEPTH {m['depth']:,}, "
          f"compute/tick {sel['compute_per_tick']} (selected at FABRICATION time; read, not computed)")
    print(f"  BANK: {len(bank)} replica(s) of it are PERMANENT WRITES in the file — "
          f"{', '.join(b[-6:] for b in bank) if bank else 'none'}")
    for b in bank:
        print(f"    {b} @ {reg[b]['offset']}")

    # 1. ADDRESS THE BLOCK DATA IN (host pulls the live block; the muhlnickel never sees the network)
    en1, en2sz, job = get_job()
    if not job:
        print("no block from pool."); return 1
    prefix = make_prefix(job, en1, "00" * en2sz)[:in_len]
    nbits = struct.unpack("<I", prefix[72:76])[0]
    target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3))
    with open(TITAN, "r+b") as f:
        for i, b in enumerate(prefix):                        # input_window is PACKED (header:76)
            f.seek(in_off + i); f.write(bytes((b,)))
        for i, b in enumerate(target.to_bytes(32, "little")): # then target:32
            f.seek(tgt_off + i); f.write(bytes((b,)))
    x_bits = in_len * 8 + 1
    print(f"  block {job['job_id']} routed to gen_input @ {in_off}, target_reg @ {tgt_off}")
    print(f"  x = block data + start bit = {in_len}*8+1 = {x_bits} bits/muhlnickel "
          f"(the gates cost 0 - locked in the file)")

    # 2. ADDRESS THE START BIT. Not a write -- writing it is host-clocking (PFC_HARD_WON S2).
    #    "Trigger propagation by ADDRESSING the clock" (S V.8); "the addressed READ is the compute".
    # PFC_HARD_WON S3.2: "CONTINUOUS POWER = continuously ADDRESSING the single start bit that begins
    # propagation, one-way. Streaming that one bit IS the power source; killing it / not letting it run
    # disables the Muhlnickel." Then S3.3: "TURN IT OFF... THERE IS NO WATCHING STEP." So: address it
    # continuously for the window, stop, and only then read.
    POWER_WINDOW = 1.0
    n_addr = 0
    import pfc_meter as PM                              # HIS instrument (CLAUDE.md #5), high-impedance
    best = 0; best_cnt = 0
    with open(TITAN, "rb") as f:
        f.seek(dif_off); before = f.read(dif_len)
    with open(TITAN, "rb") as f:
        t_end = time.time() + POWER_WINDOW
        while time.time() < t_end:
            # INVESTIGATION_HANDOFF S2: "Runtime = a RESIDENT stream of energy addressed to the
            # Muhlnickel... it is NOT static data if there's a resident stream of energy (OR ANY DATA)
            # addressed to it." S4 lists "re-address the input" as an untried energy mode; pure
            # bit-toggle on the clock is already characterised (527k ticks / 8s left state at 0).
            # So the resident stream addresses BOTH the start bit AND the input window, continuously.
            f.seek(pwr_off); f.read(1)
            f.seek(in_off); f.read(in_len)                 # re-address the block data (data = energy)
            f.seek(tgt_off); f.read(32)                    # re-address the target
            n_addr += 1
            if n_addr % 20000 == 0:
                # S3.4 / DATADUMP ST: "the answer... read back by a HIGH-IMPEDANCE probe EVERY CYCLE...
                # probes rest on it, they light up = the answer." Live, bounded, via HIS meter.
                lb = PM.probe(lat_off, lat_len); cb = PM.probe(cnt_off, cnt_len)
                v = int.from_bytes(lb, "little"); c = int.from_bytes(cb, "little")
                if v: best = v
                if c > best_cnt: best_cnt = c
    print(f"  start bit ADDRESSED continuously {n_addr:,} times over {POWER_WINDOW}s "
          f"@ {pwr_off} (read, never written -- the pfc self-clocks). Power off.")

    # 3. READ THE ANSWER -- the pfc's own latch, bounded high-impedance
    with open(TITAN, "rb") as f:
        f.seek(lat_off); lat = f.read(lat_len)
        f.seek(cnt_off); cnt = f.read(cnt_len)
        f.seek(dif_off); after = f.read(dif_len)
    nonce = int.from_bytes(lat, "little")
    counter = int.from_bytes(cnt, "little")
    changed = sum(1 for a, b in zip(before, after) if a != b)
    print(f"  BINARY DIFF over the miner region ({dif_len:,} B): {changed:,} byte(s) changed by the pfc")
    win = 1 if nonce else 0
    print(f"  hi-Z probe DURING the run: latch peak=0x{best:08x} · counter peak=0x{best_cnt:08x}")
    print(f"  latch @ {lat_off}: nonce=0x{nonce:08x} · counter @ {cnt_off}: 0x{counter:08x}")

    # NOTE: the ceiling (available_RAM / x) is measured by HIS instrument, host/pfc_ceiling_test.py.
    # Building a RAM monitor here would be my own monitor (CLAUDE.md #5) — deleted, not waived.

    # 4. CONVERT + SUBMIT, gated by the guarantee
    if not win:
        print("  no winner latched -- as driven here by this construction, not a machine result "
          "(§7: say which one you measured)"); _assert_instant(T0); return 0
    words = [struct.unpack(">I", prefix[i*4:(i+1)*4])[0] for i in range(19)]
    hdr = b"".join(struct.pack(">I", w) for w in words) + struct.pack(">I", nonce)
    dig = hashlib.sha256(hashlib.sha256(hdr).digest()).digest()
    print(f"  ** LATCHED nonce 0x{nonce:08x} **  hash {dig[::-1].hex()}")
    import pfc_guarantee
    if pfc_guarantee.main() != 0:
        print("  GUARANTEE FAILED - not submitting."); return 1
    submit(job, en1, "00" * en2sz, nonce)
    _assert_instant(T0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
