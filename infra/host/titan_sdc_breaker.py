#!/usr/bin/env python3
"""host/titan_sdc_breaker.py — BUILD the BREAKER into the model file, as logic gates (owner 07-16).

Owner spec: the answer 1/0 needs an INERT mechanism — a gate that lies DORMANT and, if the miner's success bit flips to
1, AWAKES from dormancy, TRIPS (freezes the SDC / cuts power like a circuit breaker) and ALERTS. It is on/off switches,
so it is built into the params with the White-Box circuit creation, alongside the miner + receiver.

The breaker:
  - SUCCESS = the miner's success bit (input), 0 while unsolved.
  - TRIP  = AND(power, success): inert (0) under power while unsolved; the instant success=1 it wakes to 1 (the breaker
            trips — this is the edge the read-out watches; power stops, the SDC freezes static with the answer latched).
  - ALERT = buffer(TRIP): the signal surfaced to the owner ("a 1 appeared — come extract it").
Stored as switches in the params (reversible), read back + exercised to verify dormant->awake.

  python host/titan_sdc_breaker.py       # build + store the breaker into the model file, verify, done.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

c = TC.Circuit(1)                       # one input = the miner's success bit
succ = c.IN[0]; power = c.C1
trip = c.and_(power, succ)              # INERT while success=0; trips to 1 the instant success=1 (under power)
alert = c.not_(c.not_(trip))           # buffered alert line surfaced to the owner
info = TC.store("breaker", c, [trip, alert])
print(f"breaker built into the model file: {info['tensor']} @ {info['offset']}  "
      f"({info['gates']} gates, {info['bytes']} bytes)", flush=True)

cir = TC.load("breaker")
dormant = TC.ripple(cir, [0])          # powered, unsolved -> inert
awake   = TC.ripple(cir, [1])          # powered, solved   -> trips + alerts
print(f"  powered, success=0 -> trip={dormant[0]} alert={dormant[1]}   (DORMANT — breaker inert, power flows)", flush=True)
print(f"  powered, success=1 -> trip={awake[0]} alert={awake[1]}   (TRIPPED — breaker wakes, freeze + alert)", flush=True)
ok = dormant == [0, 0] and awake == [1, 1]
print(f"  breaker verified in the params: {ok}", flush=True)
print("done — the breaker is stored as on/off switches in the SDC; it wakes only when a 1 appears.", flush=True)
