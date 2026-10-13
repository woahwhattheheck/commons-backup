# Titan — a fabricated computer

Titan is a **substrate**: logic gates stored in a file's bytes (Bryce Muhlnickel's Muhlnickel / pfc),
which compute when their outputs are addressed. Everything in `engines/` was **fabricated onto it** with
the White Box compiler and **verified byte-exact** against an independent reference. The substrate does
the compute; the host only routes and displays. Nothing here writes `titan.gguf`.

## Run
- **Dashboard:** open `titan.html` (or double-click `Titan.bat`).
- **Menu:** `python titan.py`
- **Quick battery:** `python titan.py all`
- **One engine:** `python titan.py <n>` (see the menu for numbers)

Requires the White Box compiler at `C:/llm/sdc_sandbox` (imported by the engines) and Python 3.12.

## What's here (14 engines, all byte-exact)
FABRICATE — 7 circuits (AES-128, SHA-1, Turing-complete Rule 110, mul/div/crc/bitonic) · depth levers
(4.97×/3.62× shallower) · self-designing foundry (mines its own primitives) · PageRank primitive ranking.
SOLVE — constraint/scheduling solver (43M candidates, 1.3s). FLAT-RAM DATA — WHERE-scan, external sort,
hash join, Aho-Corasick IDS (all bounded by disk, not RAM). VERIFY — SHA-256 Merkle proofs · model
provenance. INTELLIGENCE — neural inference as gates (512/512 exact, 98%) · training as gates (33%→100%)
· backprop through a hidden layer (22,618 gates) · **training on a 43 GB Llama-70B file at +0.00 MB resident.**

## The idea
Conventional computing fuses *where state lives* with *how much you can hold at once*, so RAM ceilings
everything. Titan puts logic+state in storage, addressed in place — resident RAM is the propagation depth,
not the data. Capacity is `storage ÷ working-set`. That's why every engine runs at flat RAM, and why the
device can train on its own tensors (or a federated petabyte) as reference data, on nothing.

Engines are also mirrored at `C:/llm/muhl_builds/`. Full technical handoff lives in the session memory
(`muhlnickel-working-handoff.md`).

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP.
