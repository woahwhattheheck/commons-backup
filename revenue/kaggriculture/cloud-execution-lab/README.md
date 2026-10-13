# TITAN

The runtime entrypoint is `main.py::agent`. Build the current submission package with:

```sh
python build_integrated.py
python build_integrated.py --check
python test_release_consistency.py
python test_history_archive.py
```

`exports/titan-current.tar.gz` is the single current package. Its exact receipt is `runtime/integrated-selected/CURRENT-ARCHIVE.json`; `CURRENT-SOURCE.json` binds every packaged file to its selected repository source. `RELEASE.json` records component decisions and evidence. The archive includes its manifest, deterministic configuration and licenses.

See [TITAN-RELEASE.md](TITAN-RELEASE.md) for runtime and evidence boundaries. Named archives and old controls are immutable historical/test-only evidence. Earlier component instructions are preserved in [reference/historical/pre-canonical-README.md](reference/historical/pre-canonical-README.md); they are not release selection instructions. Root owns the authorized checkpoint upload (`titan-kaggriculture-checkpoint-20260908-01`); this lane supplies the single exact package and does not duplicate submission.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
