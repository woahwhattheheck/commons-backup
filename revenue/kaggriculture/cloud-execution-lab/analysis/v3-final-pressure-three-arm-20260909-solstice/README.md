# TITAN V3 final-pressure three-arm panel

This lane measures one unresolved release question on one immutable TITAN package: does the currently enabled final-boundary market-pressure composition help, hurt, or merely rewrite action bytes?

The merged P12 repair moved the unchanged public-curve pressure transform from `TitanAgent.act()` to the final returned-action boundary in `FinalPressureAgent`. Its tests prove stage composition, but the merge explicitly did not claim paired playing strength. This experiment supplies that missing attribution without modifying canonical source or pointers.

## Exact arms

All arms are copied from the same archive and verified by complete tree manifests.

- `pressure_off`: byte-identical `main.py`; only the JSON token for `market_pressure` changes from `true` to `false`.
- `legacy_in_pipeline`: byte-identical config; exactly one constructor return changes from `FinalPressureAgent(...)` to `TitanAgent(...)`, reactivating the existing in-pipeline pressure hook and removing only the final-boundary adapter.
- `final_boundary`: byte-identical canonical package.

Every other file and config value must remain identical. Arm materialization fails if the expected constructor/token is absent, duplicated, or already changed.

## Evidence contract

The runner:

1. opens and hashes the canonical archive once, then extracts only a private byte snapshot;
2. rejects traversal, links, devices, FIFOs, duplicate names, and file/directory collisions;
3. binds the root `SOURCE.json`, official engine, evaluator, loader, each runtime opponent, and every arm tree;
4. permits only the four declared development seeds and archive-transitive or official-engine opponents;
5. runs fresh process-isolated agents in identical opponent × seed × seat cells;
6. checkpoints a nonempty fail-closed receipt before and after every game;
7. rejects errors, timeouts, partial cells, duplicate cells, nonfinite scores, and incomplete episodes;
8. hashes candidate action bytes separately from normalized post-engine state after every step.

The separate traces distinguish:

- `identical`: no candidate-action or state divergence;
- `syntactic_only`: action bytes diverge but post-engine state never does;
- `realized`: both action and state diverge;
- `state_only`: state diverges before candidate action, which signals nondeterminism or a custody defect.

Primary comparisons are `final_boundary - pressure_off` (value of current pressure) and `final_boundary - legacy_in_pipeline` (value of moving the boundary). `legacy_in_pipeline - pressure_off` isolates the historical placement.

## Acceptance

```bash
python -B -m unittest discover -v
PYTHONPYCACHEPREFIX=/tmp/solstice-pyc python -B -m py_compile \
  evidence.py variants.py panel_analysis.py game_runner.py \
  run_final_pressure_panel.py test_evidence_variants.py test_analysis_game.py
```

The GitHub workflow executes 48 official-interpreter development games: three arms × two public opponents × four seeds × both seats. A result is development attribution only. It does not mutate canonical runtime/config/archive pointers, upload to a provider, authorize promotion, or claim hosted leaderboard rank.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
