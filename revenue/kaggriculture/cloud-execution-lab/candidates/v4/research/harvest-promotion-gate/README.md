# V4 harvest promotion gate — W1 executable, H1 shadow-only

This additive research lane closes a specific evidence gap in the single canonical V4: W1 (dead-water harvest) and H1 (terminal harvest) had source/custody proofs but no common current-runtime reachability/economics surface.

`harvest_probe.py` consumes the **already returned canonical action**. It evaluates the landed `w1-capacity-subset` transform and the preserved H1 theorem side-by-side without calling a producer. `apply_candidate()` deliberately executes **only W1**. H1 is shadow-only because its historical theorem proves harvest timing, not end-of-episode shed capacity or monetization; final-day H1-only activations are therefore evidence, not promotion authority.

`run_native_harvest.py` authenticates the same canonical archive and official engine hashes as the landed FEEDPATH full-engine runner, then runs one complete two-player game against `official_starter`. Its inputs are deliberately split: `--root` is the materialized native runtime root containing `main.py` plus the authenticated `checks/reference/...` engine/loader surfaces, while `--workspace` is the canonical repository `candidates/v4` directory containing the W1 and H1 donor sources. The runner records SHA-256 for both donor source files in every result, so runtime and research custody cannot be silently conflated.

Use identical seed and seat once with `--variant baseline` and once with `--variant w1`. The result records exact action/state trace hashes, terminal rewards, parent deadline status, W1/H1 natural reachability, W1 executed changes, H1-only events, and donor source hashes. Counterfactual H1 output never enters `state.action`.

Focused checks exercise the useful separation directly: a day-28 EOD capacity-safe case is W1-executable; a full-shed case and final-day expiry are H1-only shadows; malformed/non-WATER actions fail closed. The gate itself does **not** modify production, `TITAN-CONFIG.json`, the canonical archive, or Kaggle defaults.

Promotion policy remains strict: W1 needs matched seed/seat economics beyond a single starter opponent before any production/default change. H1 needs a separate capacity/delivery/monetization certificate first; this lane must not be used to turn H1 on merely because it is naturally reachable.
