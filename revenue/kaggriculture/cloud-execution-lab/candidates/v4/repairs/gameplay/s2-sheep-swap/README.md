# S2 sheep-swap recovery

Recovered from the retained TITAN V4 library after the original standalone lane never received Git/ref plumbing.

- Source blob: `84b025aa9ead6bf362445ad9c3e97598c175c5fd` (`r04_s2_sheep_swap.py`)
- Focused test blob: `207fbc5fe76121b61bd5f4ee3b5703f01a91e732` (`test_r04_s2_sheep_swap.py`)
- Local recovery validation: `py_compile` PASS; 19/19 focused unittest methods PASS.
- Integration contract from the recovered source: invoke only after the existing V231/V233 parent action, pass the selected native tape, and keep the feature default-OFF.
- This directory preserves reviewed donor bytes in the sole canonical `main` V4 workspace. It does not activate S2, does not alter shared `apply_v4.py`, and does not execute the legacy materializer.

Any later semantic wiring must be reviewed against the then-current canonical source and retain the fail-closed transaction/cash-ownership guards in the recovered implementation.
