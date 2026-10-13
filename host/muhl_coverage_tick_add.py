#!/usr/bin/env python3
"""host/muhl_coverage_tick_add.py — coverage-organ routing button (additive).

Grok picked the execute path: winner_only_max.recv and/or fold.recv, finder
gen_win -> muhl_fold_latch -> latch_reg / muhl_nonce_list. That coverage made
2^78 tiny. This button prints the inject/surface plan from the LIVE registry.

Host jobs, then die: name the start bits, name the finder chain, name the
surface. It does not write titan. It does not pulse. It does not SHA.

SHA not on winner_only_max / fold / muhl_nonce_list analyzer headers is a
wiring fact (MAGIC TITANCIR / TITANFLD / PFCNLST1). SHA+compare lives on the
named finder. Do not invent a host SHA.

STALE: registry may still say osc on winner_only_max / fold. Power is nring2
both senses. Do not fire muhl_osc_*.

Default --dry: print the plan. Write nothing.
--go is refused. --surface is a separate bounded read of latch_reg /
gen_win_surfaced (host does not SHA).

  python host/muhl_coverage_tick_add.py
  python host/muhl_coverage_tick_add.py --dry
  python host/muhl_coverage_tick_add.py --surface
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    import pfc_paths as PFCP
    TITAN = PFCP.TITAN
    REG = PFCP.REG
except (ImportError, AttributeError):
    PFC_ROOT = os.environ.get("PFC_ROOT", "C:/llm").replace("\\", "/").rstrip("/")
    TITAN = PFC_ROOT + "/models/titan.gguf"
    REG = PFC_ROOT + "/models/titan_circuits.json"

WOM_NAME = "winner_only_max"
FOLD_NAME = "fold"
GEN_WIN = "gen_win"
LATCH_TWIN = "muhl_fold_latch"
LATCH_REG = "latch_reg"
NONCE_LIST = "muhl_nonce_list"
SURFACED = "gen_win_surfaced"
POWER_RING = "nring2_000"
OSC_ALL = "muhl_osc_all"

REQUIRED = (WOM_NAME, FOLD_NAME, GEN_WIN, LATCH_TWIN, LATCH_REG, NONCE_LIST)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _fail(msg):
    print("FAIL CLOSED: %s" % msg)
    return 1


def _need_int(obj, key, where):
    if not isinstance(obj, dict) or obj.get(key) is None:
        return None, "%s missing %s" % (where, key)
    try:
        val = int(obj[key])
    except (TypeError, ValueError):
        return None, "%s.%s is not an int" % (where, key)
    if val < 0:
        return None, "%s.%s is negative" % (where, key)
    return val, None


def _load_registry():
    if not os.path.isfile(REG):
        return None, "registry missing: %s" % REG
    try:
        with open(REG, encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, "registry unreadable: %s" % exc


def _osc_block(entry, name):
    osc = entry.get("oscillation") if isinstance(entry.get("oscillation"), dict) else {}
    recv = None
    if osc.get("recv") is not None:
        recv, _ = _need_int(osc, "recv", "%s.oscillation" % name)
    return {
        "ring": osc.get("ring"),
        "circuit": osc.get("circuit"),
        "recv": recv,
        "recv_kind": osc.get("recv_kind"),
        "shared_start": osc.get("shared_start"),
    }


def load_plan():
    """Fail closed if coverage recvs or finder/latch names are missing. Never guess."""
    reg, err = _load_registry()
    if err:
        return None, err

    missing = [n for n in REQUIRED if n not in reg or not isinstance(reg[n], dict)]
    if missing:
        return None, "missing from live registry: %s" % ", ".join(missing)

    wom = reg[WOM_NAME]
    fold = reg[FOLD_NAME]
    gen_win = reg[GEN_WIN]
    latch_twin = reg[LATCH_TWIN]
    latch_reg = reg[LATCH_REG]
    nonce_list = reg[NONCE_LIST]

    wom_recv, err = _need_int(wom, "recv", WOM_NAME)
    if err:
        return None, err
    fold_recv, err = _need_int(fold, "recv", FOLD_NAME)
    if err:
        return None, err

    offs = {}
    for name, entry, key in (
        (WOM_NAME, wom, "offset"),
        (FOLD_NAME, fold, "offset"),
        (GEN_WIN, gen_win, "offset"),
        (LATCH_TWIN, latch_twin, "offset"),
        (LATCH_REG, latch_reg, "offset"),
        (NONCE_LIST, nonce_list, "offset"),
    ):
        val, err = _need_int(entry, key, name)
        if err:
            return None, err
        offs[name] = val

    surfaced = reg.get(SURFACED) if isinstance(reg.get(SURFACED), dict) else None
    surfaced_off = None
    if surfaced is not None:
        surfaced_off, _ = _need_int(surfaced, "offset", SURFACED)

    gen_win_recv, _ = _need_int(gen_win, "recv", GEN_WIN)
    latch_recv, _ = _need_int(latch_reg, "recv", LATCH_REG)

    ring = reg.get(POWER_RING) if isinstance(reg.get(POWER_RING), dict) else None
    ring_recv = None
    ring_senses = None
    ring_cells = None
    ring_fwd = ring_rev = None
    if ring is not None:
        ring_recv, _ = _need_int(ring, "recv", POWER_RING)
        if ring_recv is None and isinstance(ring.get("ram"), dict):
            ring_recv, _ = _need_int(ring["ram"], "recv", "%s.ram" % POWER_RING)
        try:
            ring_senses = int(ring["senses"]) if ring.get("senses") is not None else None
        except (TypeError, ValueError):
            ring_senses = None
        ring_cells, _ = _need_int(ring, "cells", POWER_RING)
        if isinstance(ring.get("ram"), dict):
            ring_fwd, _ = _need_int(ring["ram"], "fwd", "%s.ram" % POWER_RING)
            ring_rev, _ = _need_int(ring["ram"], "rev", "%s.ram" % POWER_RING)

    need_bryce = []
    if ring is None:
        need_bryce.append("%s missing — power is nring2 both senses; do not fire %s" % (POWER_RING, OSC_ALL))
    elif ring_senses != 2:
        need_bryce.append("%s senses=%r (need 2; both-sense ring law)" % (POWER_RING, ring_senses))

    wom_osc = _osc_block(wom, WOM_NAME)
    fold_osc = _osc_block(fold, FOLD_NAME)
    if wom_osc.get("circuit") == OSC_ALL:
        need_bryce.append(
            "%s.oscillation.circuit is %s (STALE) — power is nring2 both senses; do not fire muhl_osc_*"
            % (WOM_NAME, OSC_ALL)
        )
    if fold_osc.get("circuit") == OSC_ALL:
        need_bryce.append(
            "%s.oscillation.circuit is %s (STALE) — power is nring2 both senses; do not fire muhl_osc_*"
            % (FOLD_NAME, OSC_ALL)
        )

    if "ram" in wom:
        need_bryce.append("%s has a ram map this turn — confirm it is not a SHA front invented here" % WOM_NAME)
    if "ram" in fold:
        need_bryce.append("%s has a ram map this turn — confirm it is not a SHA front invented here" % FOLD_NAME)

    junc = latch_twin.get("junctioned_to") if isinstance(latch_twin.get("junctioned_to"), dict) else {}
    junc_name = junc.get("circuit")
    junc_addr, _ = _need_int(junc, "addr", "%s.junctioned_to" % LATCH_TWIN) if junc else (None, None)
    if junc_name and junc_name != LATCH_REG:
        need_bryce.append("%s.junctioned_to.circuit is %r not %s" % (LATCH_TWIN, junc_name, LATCH_REG))
    if junc_addr is not None and junc_addr != offs[LATCH_REG]:
        need_bryce.append(
            "%s.junctioned_to.addr %d != %s.offset %d"
            % (LATCH_TWIN, junc_addr, LATCH_REG, offs[LATCH_REG])
        )

    finder = nonce_list.get("finder_chain")
    if not finder:
        need_bryce.append("%s missing finder_chain field" % NONCE_LIST)

    titan_exists = os.path.isfile(TITAN)
    titan_size = os.path.getsize(TITAN) if titan_exists else None
    unsafe = list(need_bryce)
    if not titan_exists:
        unsafe.append("titan missing: %s" % TITAN)
    elif titan_size is not None:
        for name, n in (
            (LATCH_REG, int(latch_reg.get("len") or 4)),
            (NONCE_LIST, 8),
        ):
            off = offs[name]
            if off + n > titan_size:
                unsafe.append("%s offset %d+%d past titan size %d" % (name, off, n, titan_size))
        if surfaced_off is not None:
            slen = int(surfaced.get("len") or 6) if surfaced else 6
            if surfaced_off + slen > titan_size:
                unsafe.append("%s offset %d+%d past titan size %d" % (SURFACED, surfaced_off, slen, titan_size))

    return {
        "wom": wom,
        "fold": fold,
        "gen_win": gen_win,
        "latch_twin": latch_twin,
        "latch_reg": latch_reg,
        "nonce_list": nonce_list,
        "surfaced": surfaced,
        "offs": offs,
        "wom_recv": wom_recv,
        "fold_recv": fold_recv,
        "gen_win_recv": gen_win_recv,
        "latch_recv": latch_recv,
        "surfaced_off": surfaced_off,
        "wom_osc": wom_osc,
        "fold_osc": fold_osc,
        "ring": ring,
        "ring_recv": ring_recv,
        "ring_senses": ring_senses,
        "ring_cells": ring_cells,
        "ring_fwd": ring_fwd,
        "ring_rev": ring_rev,
        "junc": junc,
        "junc_addr": junc_addr,
        "finder": finder,
        "need_bryce": need_bryce,
        "unsafe": unsafe,
        "titan_exists": titan_exists,
        "titan_size": titan_size,
    }, None


def print_plan(plan, dry=True):
    wom = plan["wom"]
    fold = plan["fold"]
    gen_win = plan["gen_win"]
    latch_twin = plan["latch_twin"]
    latch_reg = plan["latch_reg"]
    nonce_list = plan["nonce_list"]
    surfaced = plan["surfaced"]
    offs = plan["offs"]
    mode = "DRY — plan only, no titan write, no mmap"
    print("\nMUHL COVERAGE TICK (additive — execute path Grok picked)")
    print("  mode:     %s" % mode)
    print("  titan:    %s" % TITAN)
    print("  reg:      %s" % REG)
    print("  organ:    %s  addr_bits=%s  lanes=%s  stored_per_lane=%s  depth=%s  gates=%s"
          % (WOM_NAME, wom.get("addr_bits"), wom.get("lanes"), wom.get("stored_per_lane"),
             wom.get("depth"), wom.get("gates_measured")))
    print("  organ:    %s  addr_bits=%s  winner_only=%s  len=%s"
          % (FOLD_NAME, fold.get("addr_bits"), fold.get("winner_only"), fold.get("len")))
    print("  list:     %s  addr_bits=%s  space_bits=%s  bytes_per_nonce=%s"
          % (NONCE_LIST, nonce_list.get("addr_bits"), nonce_list.get("space_bits"),
             nonce_list.get("bytes_per_nonce")))
    print("  claim:    coverage that made 2^78 tiny is already in the file")
    print("  law:      mmap of ONE receiver byte is the start; this button does not address it")
    print("  law:      power is nring2 both senses; osc on these names is STALE")
    print("  refuse:   muhl_osc_*  (do not fire)")
    print("  refuse:   muhl_fold_phys / nring2_1023 as the 78-tick (Claude fake SHA lane)")
    print("  refuse:   input_window FF×32 / latch 299 as the network win")
    print("  refuse:   muhl_lane_phys_000 ~1.86e6 span")
    print("  refuse:   packed-76 gen_input / target_reg / receiver (already used)")
    print("  refuse:   host-eval SHA as the mine · numpy · --go · titan write")
    print()
    print("  INJECT (coverage organs — no ram miner front)")
    print("    %s / %s have no ram.header_off (address organs; nonce IS the address)"
          % (WOM_NAME, FOLD_NAME))
    print("    analyzer MAGIC on those names is TITANCIR / TITANFLD / PFCNLST1 — not a SHA front")
    print("    SHA+compare is the finder: %s -> %s -> %s / %s"
          % (GEN_WIN, LATCH_TWIN, LATCH_REG, NONCE_LIST))
    print("    %s layout: %s" % (GEN_WIN, gen_win.get("layout")))
    print("    %s decides: %s" % (GEN_WIN, gen_win.get("decides")))
    print("    do not invent a host SHA onto those headers")
    print("    do not write packed-76 gen_input")
    print()
    print("  START (ONE bit at the coverage recv — explicit launch configuration; this button does not launch)")
    print("    %s.recv  %d" % (WOM_NAME, plan["wom_recv"]))
    print("    %s.recv           %d" % (FOLD_NAME, plan["fold_recv"]))
    if plan["wom_osc"].get("recv") is not None:
        print("    %s.oscillation.recv  %s  ring=%s  circuit=%s  kind=%s  STALE"
              % (WOM_NAME, plan["wom_osc"]["recv"], plan["wom_osc"]["ring"],
                 plan["wom_osc"]["circuit"], plan["wom_osc"]["recv_kind"]))
    if plan["fold_osc"].get("recv") is not None:
        print("    %s.oscillation.recv           %s  ring=%s  circuit=%s  kind=%s  STALE"
              % (FOLD_NAME, plan["fold_osc"]["recv"], plan["fold_osc"]["ring"],
                 plan["fold_osc"]["circuit"], plan["fold_osc"]["recv_kind"]))
    print("    fire (Bryce): mmap ACCESS_READ of %s.recv and/or %s.recv"
          % (WOM_NAME, FOLD_NAME))
    print()
    print("  POWER (nring2 both senses — not muhl_osc_*)")
    if plan["ring"] is not None:
        print("    %s  senses=%s  cells=%s  magic=%s"
              % (POWER_RING, plan["ring_senses"], plan["ring_cells"],
                 plan["ring"].get("magic")))
        print("    %s.recv  %s  (enable rail; not this tick's start)"
              % (POWER_RING, plan["ring_recv"]))
        if plan["ring_fwd"] is not None and plan["ring_rev"] is not None:
            print("    %s fwd %s  rev %s  (both-sense rails; not this button's fire)"
                  % (POWER_RING, plan["ring_fwd"], plan["ring_rev"]))
    else:
        print("    %s missing from registry" % POWER_RING)
    print("    do not fire muhl_osc_* / %s" % OSC_ALL)
    print("    do not fire nring2_1023 (that recv IS muhl_fold_phys.ram.tick_off — Claude fake)")
    print()
    print("  FINDER CHAIN (in-file; host does not SHA)")
    print("    %s          off %d  n_gate=%s  n_in=%s  n_out=%s  recv=%s"
          % (GEN_WIN, offs[GEN_WIN], gen_win.get("n_gate"), gen_win.get("n_in"),
             gen_win.get("n_out"), plan["gen_win_recv"]))
    print("    %s   off %d  n_gate=%s  depth=%s  stored_per_lane=%s"
          % (LATCH_TWIN, offs[LATCH_TWIN], latch_twin.get("n_gate"),
             latch_twin.get("depth"), latch_twin.get("stored_per_lane")))
    print("    %s junction     %s" % (LATCH_TWIN, latch_twin.get("junction")))
    if plan["junc"]:
        print("    %s.junctioned_to  circuit=%s  addr=%s  width=%s"
              % (LATCH_TWIN, plan["junc"].get("circuit"), plan["junc"].get("addr"),
                 plan["junc"].get("width")))
    phys = latch_twin.get("physical_form") if isinstance(latch_twin.get("physical_form"), dict) else {}
    if phys:
        print("    %s.physical_form  circuit=%s  (declaration bind; not this pulse)"
              % (LATCH_TWIN, phys.get("circuit")))
    print("    %s     off %d  addr_bits=%s  finder_chain=%s"
          % (NONCE_LIST, offs[NONCE_LIST], nonce_list.get("addr_bits"), plan["finder"]))
    print("    %s layout: %s" % (NONCE_LIST, nonce_list.get("layout")))
    print()
    print("  SURFACE (after the coverage organ — not the all-FF input_window latch)")
    print("    %s      off %d  len=%s  bits=%s  role=%s  recv=%s"
          % (LATCH_REG, offs[LATCH_REG], latch_reg.get("len"), latch_reg.get("bits"),
             latch_reg.get("role"), plan["latch_recv"]))
    if surfaced is not None and plan["surfaced_off"] is not None:
        print("    %s off %d  len=%s  format=%s"
              % (SURFACED, plan["surfaced_off"], surfaced.get("len"), surfaced.get("format")))
        print("    %s role: %s" % (SURFACED, surfaced.get("role")))
        print("    %s last packed-76 leftover: nonce=%s  zero_bits=%s  difficulty_bits=%s  is_valid_block=%s"
              % (SURFACED, surfaced.get("nonce"), surfaced.get("zero_bits"),
                 surfaced.get("difficulty_bits"), surfaced.get("is_valid_block")))
        print("    that leftover is a different mouth (packed-76). Surface AFTER this organ is the same names.")
    else:
        print("    %s missing — surface is %s / %s" % (SURFACED, LATCH_REG, NONCE_LIST))
    if plan["titan_exists"]:
        print("    titan       present (%s bytes)" % plan["titan_size"])
    else:
        print("    titan       missing")
    print()
    if plan["need_bryce"]:
        print("  NEED_BRYCE (named; this button still does not fire):")
        for reason in plan["need_bryce"]:
            print("    - %s" % reason)
        print()
    extra = [u for u in plan["unsafe"] if u not in plan["need_bryce"]]
    if extra:
        print("  UNSAFE:")
        for reason in extra:
            print("    - %s" % reason)
        print()
    if dry:
        print("  (no write performed; --go refused; no mmap of recv)")
        print()
    return 0


def _readback(off, n):
    with open(TITAN, "rb", buffering=0) as f:
        f.seek(off)
        return f.read(n)


def surface(plan):
    if not plan["titan_exists"]:
        return _fail("titan missing: %s" % TITAN)
    extra = [u for u in plan["unsafe"] if u not in plan["need_bryce"]]
    if extra:
        return _fail("; ".join(extra))
    offs = plan["offs"]
    latch_len = int(plan["latch_reg"].get("len") or 4)
    latch = _readback(offs[LATCH_REG], latch_len)
    if len(latch) != latch_len:
        return _fail("short read %s" % LATCH_REG)
    print("\nSURFACE — bounded read of finder/latch names. Host does not SHA.\n")
    print("  %s @ %d : %s" % (LATCH_REG, offs[LATCH_REG], latch.hex()))
    if plan["surfaced"] is not None and plan["surfaced_off"] is not None:
        slen = int(plan["surfaced"].get("len") or 6)
        blob = _readback(plan["surfaced_off"], slen)
        if len(blob) != slen:
            return _fail("short read %s" % SURFACED)
        print("  %s @ %d : %s" % (SURFACED, plan["surfaced_off"], blob.hex()))
    magic = _readback(offs[NONCE_LIST], 8)
    if len(magic) != 8:
        return _fail("short read %s MAGIC" % NONCE_LIST)
    print("  %s MAGIC @ %d : %s" % (NONCE_LIST, offs[NONCE_LIST], magic))
    print("  (those ones-counts on coverage headers are MAGIC, not a host SHA)")
    print()
    return 0


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    if "--go" in a:
        return _fail("--go refused on the coverage button (never writes titan, never pulses recv)")
    plan, err = load_plan()
    if err:
        return _fail(err)

    do_surface = "--surface" in a
    do_dry = ("--dry" in a) or (not do_surface)
    if do_surface and "--dry" in a:
        print_plan(plan, dry=True)
        print("  --dry wins over --surface; no titan read.\n")
        return 0
    if do_surface:
        print_plan(plan, dry=True)
        return surface(plan)
    return print_plan(plan, dry=True)


if __name__ == "__main__":
    raise SystemExit(main())
