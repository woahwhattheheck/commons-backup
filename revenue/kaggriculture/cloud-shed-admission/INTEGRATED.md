# Actual integrated-parent consumer follow-through

`TerminalAdmissionAgent.act(observation, config=None)` now accepts the same explicit-step or day/hour clock shape and optional configuration as the supplied PR9997 integrated parent. It calls that parent once with the original arguments, then normalizes only the admission view. A parent body exception still propagates without a retry. The admission optimizer and offline market primitives are unchanged.

## Source and usage

The actual parent is the existing PR9997 archive, source `843f6dbb7d564204802d54e1611fe912aea497df`, merged at `b15af38473a7f5ab315753ffebda7aba5177aee2`. Archive SHA256: `95c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153`. Existing transport artifact `10036877991` supplied those exact bytes; no new export was needed. Reuse the extraction root and the existing pinned engine cache.

```python
import integrated_selected
from market_primitives import make_primitives
from terminal_admission import TerminalAdmissionAgent

parent = integrated_selected.make_agent()  # One instance per match.
agent = TerminalAdmissionAgent(
    parent.act, make_primitives(integrated_selected.m), scenario_model,
    max_states=32, max_candidates=32, time_budget_s=0.15,
)
action = agent.act(observation, configuration)
```

`scenario_model(observation, configuration)` is caller-supplied and returns the existing `RivalScenario` objects. It receives an explicit-step observation and a configuration mapping. These are finite rival-sale hypotheses, not calibrated probabilities or observed private stock. This remains a final-market storage-capacity operator, not a general nonterminal deposit planner or a default-policy promotion.

## Executed compatibility result

Six new methods use the actual integrated parent, not a substitute controller: both positions, explicit and derived clock, omitted configuration, constructed terminal inputs, offline/official primitive correspondence, and one-call failure preservation. All six pass. The original consumer produces five subcase errors across three methods because it indexes `observation['step']` and calls `config.get` unconditionally. The first test-instrumentation attempt and its correction are retained separately from that runtime reproduction.

```bash
TITAN_INTEGRATED_ROOT=/extract \
TITAN_ENGINE_DIR=/engine \
TITAN_REPO_ROOT=/commons \
python -B revenue/kaggriculture/cloud-shed-admission/test_integrated_consumer.py
```

`/extract`, `/engine` and `/commons` denote the existing source caches. The original 23-method admission evidence and accepted upstream suites were retained, not rerun or attributed to this new source combination.

## Four complete development games

The existing evaluator gained an optional complete-agent path and seat selection; omitting the candidate still uses frozen SELL. It records the entrypoint hash and adjacent source manifest.

```bash
python -B revenue/kaggriculture/cloud-shed-admission/evaluate_terminal.py \
  --repo-root /commons --engine-dir /engine \
  --candidate /extract/integrated_main.py \
  --seeds 9957001 9957019 --seats 0 1 --opponent arlene \
  --out /tmp/admission-integrated-development
```

These are already-used ADMISSION development seeds, not a new held bank. Four full prefixes completed, with the original, same-worker-liquidation and admission terminal actions each executed independently by the official interpreter. Twelve terminal branch completions are not twelve independent games. All three alternatives finish **4W/0T/0L**; admission changes no action or cash because none of the reached final states has capacity pressure. No timeout or game failure occurred.

| Seed | Seats | Own cash | Rival cash | Margin |
| --- | --- | ---: | ---: | ---: |
| 9957001 | 0 and 1, exact cash mirrors | 93,969 | 93,948 | +21 |
| 9957019 | 0 and 1, exact cash mirrors | 76,742 | 76,609 | +133 |

Maximum measured candidate action is 80.82 ms; maximum final admission call is 0.282 ms. The latter is an inactive fast path, not a pressured-search or hosted-resource bound.

A separate retrospective comparison to the retained original frozen-SELL results is useful for T08: seed 9957001 changes margin +615 to +21 (own -209, rival +385); seed 9957019 changes -95 to +133 (own -173, rival -401), a mirrored L-to-W change. This is a whole-parent source comparison, **not admission credit**. There are two seed regimes, no fresh held or leaderboard result, and no claim of identical stochastic paths.

## Complete receipts

`INTEGRATED-VALIDATION.json.gz.b64` contains the complete 15,611-byte report, exact source/engine/opponent identities, original and repaired test logs, per-game terminal outcomes, timings, historical comparison and retained trace hashes. Decode without a dependency:

```bash
python - <<'PY'
import base64, gzip, hashlib
from pathlib import Path
p = Path('revenue/kaggriculture/cloud-shed-admission')
b = gzip.decompress(base64.b64decode((p/'INTEGRATED-VALIDATION.json.gz.b64').read_bytes()))
assert hashlib.sha256(b).hexdigest() == '0c207d649af52ab3057e50b365baa8f8e42ef5159f981eec7135691182ad31f6'
Path('/tmp/admission-integrated-validation.json').write_bytes(b)
PY
```

Full source, patches, logs, original manifests and all four new action traces are also saved in the owner's Library as `titan_admission_integrated_followthrough_2026-09-07.zip`, 105,009 bytes, SHA256 `a545d0127b1a644a50e68e761eff3b4c8980e82a52deace30110b22afe2351ca`. Library backing file: `file_00000000e62481f5964da9ec10b275a1`.

The original `SOURCE.json`, `RESULTS.json`, `VALIDATION.log` and reached-case archive deliberately remain the original frozen-SELL delivery's records. They do not identify this patched runtime. Use the new report for the exact follow-through hashes. Current scope supplies a compatible optional consumer and a runnable actual-parent evaluation path; natural admission gains and general nonterminal optimization remain unestablished.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
