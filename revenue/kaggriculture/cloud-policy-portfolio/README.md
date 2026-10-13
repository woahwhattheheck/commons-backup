# TITAN policy portfolio

`selected.py::agent(observation, configuration=None)` runs the selected frozen
SELL baseline. `main.py` retains the executable frozen research selector. Its
conditional validation regressed two wins, so it is not promoted. Both preserve
one live policy state. The selector uses decision-time observations and a small
frozen table; all game-time code uses the Python standard library.

Run focused checks with `python -m unittest discover -s . -p 'test_*.py'`.
Decode retained evidence with `python artifacts/decode.py --output /tmp/t14-evidence`.
The receipt archive contains all panels, paired labels and every searched prefix;
the trace archive preserves all 191,254 observation/action rows. The decoder's
manifest verifies bytes. `evidence.py unpack ARCHIVE OUTPUT` restores full JSONL.

For a new, collision-checked development panel, run `python run_panel.py --panel
development --seeds SEED --arms sell carrot_sell --output results/NAME`. The pinned
official interpreter and process-isolated evaluator are included. Apex requires
the C++17 compile command in `prepare.py`; it is only an offline opponent. The
retained runtime archive also contains the tested Linux binary. Evaluation uses
one-second action limits and reports the complete agent call.

See `results/SUMMARY.json` for actual cash and W/T/L. The original held panel and
later observation-conditioned validation remain separate. No historical held
panel is new validation. These are offline game scores, not hosted ratings or
money earned. No submission or notebook upload is performed by this package.

See `SOURCE-PINS.json` for exact dependency bytes and `NOTICE.md` for attribution.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
