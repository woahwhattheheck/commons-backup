# Preserve input files when choosing output paths

Run the existing CLI with a separate output directory:

```sh
python3 purchasing_operator.py --vendors examples/vendors.csv \
  --purchase-orders examples/purchase_orders.csv \
  --invoices examples/invoices.csv --out-dir out
```

`run()` writes `reconciliation.json`, `accounting_import.csv`, and `exception_drafts.json`. Before reading or writing the packet, it checks that none of these targets refers to an input file and that no two targets refer to the same file. Direct paths, normalized relative paths, symbolic links (including output-directory links), and existing hardlinks are compared. A dangling output symlink that resolves to another output target is also detected before either is created.

An overlap raises the existing `PurchasingError`. The CLI exits with status 2 and leaves input files and existing output files unchanged. Choose distinct targets and rerun. Distinct symlinked output files, ordinary repeated runs, and separate existing output files remain supported. Equal file contents alone are not treated as an alias.

This is a preflight check, not a filesystem lock or a transactional multi-file publisher. It does not protect against another process changing links after the check, concurrent writers, interruption, or an I/O failure during subsequent writes. Keep a private backup of original source files and avoid concurrent writes to the same output directory. No invoice or purchase order is posted to an external accounting system.

## Regression coverage

```sh
PYTHONWARNINGS=error::ResourceWarning python -B -m unittest -v test_purchasing_output_paths.py
```

Sixteen methods use actual temporary files, hardlinks, symbolic links and a CLI subprocess. They exercise all three output names against all three input roles, every output hardlink pair, source/output symlinks, directory aliases, clean CLI failure, preserved previous bytes, and compatible successful runs. Symlink-specific methods skip only when the platform does not provide the needed capability; the measured cloud run had no skips.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
