# Titan — index

- **`Muhlnickel_Control.bat`** — ONE CLICK. The Muhlnickel control surface: a big FIRE button that shoots an
  electron into a `nring2_*` ring (both senses) and reads the answer registers straight out of
  `C:/llm/models/titan.gguf`, plus one DUMP EVERYTHING button that writes a full timestamped debug file to
  `dumps/`. Sources: `muhl_control.py` + `muhl_control.html`. Writes are journaled to
  `C:/llm/models/titan_muhl_control_genome.jsonl`; revert with `python muhl_control.py revert`.
  (PFC/SDC are dead names — it is the Muhlnickel. Registry names like `pfc_model_selfclock` are history, read as-is.)
- `Titan.bat` / `titan.py` / `titan.html` / `titan_live.html` — the engine harness + dashboards (14 engines in `engines/`).
- `dumps/` — `muhl_dump_<timestamp>.json`, one file per DUMP click: every ring's publish gate and state bytes,
  every answer register, the genome journal, and the last fire event.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP.
