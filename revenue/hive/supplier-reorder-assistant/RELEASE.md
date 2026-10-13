# Standalone supplier reorder delivery

`build_release.py` packages the existing local browser desk, reorder engine,
backup tool, usage documents and four fictional CSV examples into one runnable
`supplier-reorder-desk.zip`. The recipient extracts
it and follows `START_HERE.md`; no Commons checkout, API key or pip install is
needed. Python with standard-library SQLite is required. No order is sent.

## Build from a clean source checkout

```sh
cd revenue/hive/supplier-reorder-assistant
python3 -B build_release.py --out /path/to/new/supplier-reorder-desk.zip
```

The destination directory must exist, and the output filename must be new. The
command prints JSON with archive bytes and SHA-256. Validation and complete ZIP
construction happen before publication; a completed temporary file is linked
without replacing an existing output. This needs same-filesystem hard-link
support. A failed operation removes its staging file. It is not a power-loss
recovery protocol or a lock against concurrent source modifications.

`SOURCE_FILES` is a fixed allowlist, not a directory walk. It includes only
`reorder_assistant.py`, `desk.py`, `desk.html`, `workspace_backup.py`, four usage
documents and the four named examples. Databases, WAL files, exported inventory,
private backups, environment files, caches and arbitrary added examples are not
selected. Build from a clean, trusted checkout: an allowlist does not identify
private content that someone has put inside an allowed source file. Symbolic
links and non-regular source files are rejected; input sizes are bounded.

The ZIP has a single `supplier-reorder-desk/` root, fixed file ordering, modes
and timestamps, plus generated `START_HERE.md` and `manifest.json`. Stored entries
avoid compression-version differences. The same selected bytes produce the same
archive across source locations and mtimes. The manifest hashes every payload
file except itself. It is a content inventory, not an authenticity signature.
Optional import-mapping and workspace-CLI adapters are outside this release; no
unlanded peer directory is included. Existing runtime and UI files are unchanged.

## Tests and the isolated release workflow

Builder-only tests use synthetic source files and can run without the whole app:

```sh
python3 -B -m unittest -v test_release_package.ReleaseBuilderTests
```

All tests require the real allowlisted app files; missing files fail, not skip:

```sh
PYTHONWARNINGS=error::ResourceWarning python3 -B -m unittest -v test_release_package
```

The extracted-product tests start real CLI and loopback HTTP subprocesses from
an extracted folder with repository PYTHONPATH removed. They exercise plan,
receive, exact replay, browser API saves, restart/reopen, cumulative receipt caps, source exports and
whole-workspace backup/restore with receipt replay. They compare served HTML bytes but are not
Chromium DOM tests or evidence of a real retailer's acceptance.

`.github/workflows/supplier-reorder-release.yml` uses a sparse product checkout,
Python 3.11 and read-only repository permissions. It runs the isolated release tests and whole-product discovery on the same
pinned checkout, then builds the downloadable package only on success. The
whole-product count includes the release tests; these counts must not be summed. Package artifacts also
carry their source-commit and interpreter version. Artifacts are internal
delivery staging, not an application deployment, customer send or storefront.
The workflow is scoped to this product and does not run the full Commons battery.

Local pre-publication record (ASTRA-WILLOW, 2026-09-08): 17 builder methods passed
on Python 3.13.5 with ResourceWarnings treated as errors. Extracted-app, whole-product and hosted
results must be read from the actual execution log, not inferred from this code.
No customer records, supplier contact, payment, provider provisioning or owner-PC
computation are part of the build or tests.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
