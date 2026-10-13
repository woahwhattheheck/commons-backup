#!/usr/bin/env python3
"""Public fail-closed facade for the P04 route-matrix row receipt bridge."""
import _route_matrix_row_receipt_core as _core

# Re-export the already-reviewed row/snapshot helpers, including underscored
# test seams, while replacing only the CLI with candidate-custody execution.
for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

from route_matrix_candidate_custody import main as _custody_main
main = _custody_main

if __name__ == "__main__":
    raise SystemExit(main())
