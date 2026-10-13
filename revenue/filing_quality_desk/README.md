# Filing Quality Desk

Offline analyst-QA tooling for retained SEC Company Facts JSON. It selects exact taxonomy, concept, unit, and period observations under an explicit filing-date cutoff; fails closed on ambiguity; records prior values without labeling them restatements; evaluates same-unit/same-period arithmetic checks; and emits deterministic JSON, CSV, HTML, and a byte-verifiable manifest.

Use `python -m revenue.filing_quality_desk.cli` with the `compile` or `verify` subcommand and `--source`, `--policy`, and `--out` arguments.

Published regressions cover strict JSON, CIK/period selection, same-day ambiguity, filing cutoffs, changed prior values, exact arithmetic, incompatible checks, HTML escaping, deterministic semantics, and output tamper detection. The filesystem compile/verify roundtrip was also executed locally in normal Python and real `python -O`; that one small test file was rejected by the repository write safety layer and is not claimed as published.

Supplied bytes are not authenticated SEC custody, and filtering a later snapshot by filing date is not a historical-vintage guarantee. This package is analysis/QA tooling only.
