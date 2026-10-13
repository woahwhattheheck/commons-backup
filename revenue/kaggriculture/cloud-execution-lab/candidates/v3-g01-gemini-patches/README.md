# G01 Gemini patches

Unpack titan-current.tar.gz @ ba1efc8732073d7ad566ea5090fb9aa3e8b2bc33 (SHA256 3b4b083ec2647bb0e715978c2565e916da0ee94c08b234902e3a7e4d3418c320).

From the extract root:

    patch -p0 < path/to/diffs/scheduler.py.diff
    patch -p0 < path/to/diffs/frozen_selected.py.diff
    patch -p0 < path/to/diffs/titan_runtime.py.diff

Those diffs are `diff -u` against the archive root filenames (verified `patch -p0 --dry-run` on a fresh extract).

Or copy `patched/scheduler.py`, `patched/frozen_selected.py`, `patched/titan_runtime.py` next to main.py.
Also copy rival_model.py e11_rival_sell.py e20_hire_shop.py and TITAN-CONFIG.json.

Flags default off: TITAN_E11_RIVAL_SELL TITAN_RIVAL_MODEL TITAN_E20_HIRE_GUARD TITAN_SHOP_ARB.
