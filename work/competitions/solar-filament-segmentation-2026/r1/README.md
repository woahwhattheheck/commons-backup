# Solar Filament Segmentation 2026 — R1 baseline/evaluator

Public-safe, dataset-agnostic baseline recovered from Slack Canvas `F0C70AKC2TC`.

## Scope

- Model-free dark-structure baseline for 2D H-alpha arrays.
- Class-agnostic panoptic quality (PQ) for non-overlapping instance maps.
- Foreground Dice, fragmentation, over-merging, SQ/RQ, and latency receipts.
- No competition data loader, private IDs, labels, test masks, registration, or submission code.
- Five focused synthetic unit tests.

## Evidence boundary

The committed benchmark and receipt are **synthetic plumbing evidence only**. They are not MAGFiLO results, organizer scores, leaderboard results, or competition performance. Before any performance claim, an authenticated competition seat must cross-check the local PQ implementation against the organizer self-evaluation notebook and run the unchanged baseline on a frozen private validation split.

The source Canvas recorded these original SHA-256 values:

- `solar_filament_baseline.py`: `aa96e7b8e6de7cf174f5a6ca1aeeac8f9b8c294f640678fe74f7d198a3746aa0`
- `test_solar_filament_baseline.py`: `34373e1c07cc8dd62207a658ff89650ffbdf85ac01339ef4bae537ead840b0cc`
- `benchmark_synthetic.py`: `79587f2a9ad14b331cd0afdfca3e1045d6fdb47fb09fc99e1760b14efa1d1b04`
- `synthetic_receipt.json`: `e4ee70d9b944b12cc4e7bc5e0b5e051f8db1e189566f92003e766597b170eff1`

The original README source was not embedded as a code block in the Canvas, so this README is a transport reconstruction and **does not claim** the Canvas-recorded README hash.

## Local synthetic check

```bash
python -m unittest test_solar_filament_baseline.py
python benchmark_synthetic.py
```

The recorded synthetic receipt reports mean PQ `0.96780845`, mean foreground Dice `0.98340486`, and stable metric-content receipt SHA-256 `02e8e99550752f6dc3a4ec510629fb008ac4cff929049fd43d1c2bbe92580db8`. Timing fields are machine-specific and should not be used as competition claims.

## Data-bearing promotion gate

An authenticated competition/local seat should privately mount MAGFiLO, verify this PQ implementation against the organizer reference evaluator, freeze a group-aware validation split, run this baseline unchanged, and return canonical PQ plus local PQ/Dice, fragmentation/over-merging, wall time, peak RSS/VRAM, and split/source/notebook hashes. Do not publish private competition data or identifiers.
