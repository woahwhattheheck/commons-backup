# Reproducible operator verification

This is the existing OP5-SLATE verifier from donor commit `51b483e1a6c5634482c333f7522ed2177b979745`, selectively integrated with its required fixtures, manifest, UNKNOWN register and guide renderer. OP5-CONTROL identified timestamp, duration and temporary-path churn; ZZ-QUARTZ-V9N2 implemented and tested the observation/provenance split. The separate six-file operator guide/preflight package already on main is preserved unchanged. No other fleet lane or old generated fleet-status snapshot is imported.

## Run a fictional, executable rehearsal

Python 3.10+ and the standard library are sufficient. From the repository root:

```bash
cd revenue/uiowa_rfq_18649_operator_handoff
mkdir -p /tmp/uiowa-kit-run
python3 verify_kit.py --root fixtures/minikit --manifest fixtures/minikit_manifest.json \
  --out-json /tmp/uiowa-kit-run/component_status.json \
  --out-csv /tmp/uiowa-kit-run/component_status.csv \
  --out-md /tmp/uiowa-kit-run/verification_log.md \
  --out-run-json /tmp/uiowa-kit-run/raw_run.json
python3 render_guide.py --manifest fixtures/minikit_manifest.json \
  --status /tmp/uiowa-kit-run/component_status.json \
  --out /tmp/uiowa-kit-run/OPERATOR_GUIDE.md
python3 -m unittest test_verify_kit test_verification_artifacts -v
python3 -O -m unittest test_verify_kit test_verification_artifacts -v
```

The minikit intentionally contains one passing lane, one failing lane, a document-only lane, one missing lane, and one unmapped lane. A failing fictional component is expected evidence, not a failing verifier test. These commands do not assess the University's real systems. All real-input register rows remain UNKNOWN.

For a curated full-kit survey, use `--root ../ --manifest kit_manifest.json`. A manifest entry is not proof that a lane exists or runs. Missing components remain MISSING and newly discovered components remain UNMAPPED. No full-repository result is asserted by this repair's synthetic tests.

## Two views, one observation

`--out-json`, `--out-csv` and `--out-md` write the stable observation view. It retains statuses, reasons, test counts, exit/timeout facts, Python version and optimization mode, manifest digest, copied-lane source digests, and normalized command/output evidence. `render_guide.py` accepts this view without inventing a generation timestamp. It also accepts the raw record for legacy callers.

`--out-run-json` writes the separate raw execution record: actual timestamp, root, durations, exact argv and cwd, full decoded output and the original tail. `survey()` still returns this raw record; stable rendering does not mutate it. Keep the raw record when chronology or execution details matter. The stable view is explicitly marked `operator-verification-semantic-v1`; it is not a verbatim transcript. Distinct output destinations are required so raw metadata cannot overwrite observations.

Only known executor paths and the exact standard unittest summary timing line are normalized. Replacement is longest-root-first and respects path boundaries. Application durations, dates, numbers and unrelated temporary paths are retained. Normalization precedes truncation, and a SHA-256 digest of the full normalized output detects changed diagnostics even outside the displayed 1,200-character tail. A changed application failure (`latency=2.750s` versus `3.125s`) stays changed.

Write reports outside the surveyed input tree, as the commands above do. A report written into its own input lane becomes a changed input on the next run; the source digest should expose that change rather than conceal it. Existing truncated legacy reports must be re-collected: they cannot reconstruct information already lost before normalization.

## Evidence and limits

The unchanged original 24 tests and 26 added regressions passed together: **50/50 normal and 50/50 optimized**, Python 3.13.5 in the cloud execution environment. The optimized regression verifies the actual child interpreter receives `-O`; the command and raw argv record it. Repeated real executions in differently named checkout roots produced equal JSON, CSV, Markdown log and normalized guide views. Tests also cover real failures, zero collection, timeouts, no-exec, source changes, manifest changes, raw retention, idempotence and downstream renderer compatibility.

The classification policy remains the original verifier's suite/runner policy; this repair does not add assertion instrumentation or certify arbitrary component behavior. A successful documented runner is explicitly distinguished from a passing unittest suite. The CLI's zero exit status means the survey completed, not that every component is WORKING. Source digests bind copied lane paths and bytes, not a complete hermetic dependency closure; runners may read declared repository paths outside their copied lane.

Copying a working directory is **not a security sandbox**. It avoids incidental relative writes to the source lane; arbitrary subprocess code can still use network access or absolute filesystem paths. Run curated, trusted kit code in an appropriately constrained environment. This clarification applies to the inherited isolation wording in the donor verifier and renderer. No live access, outreach, scheduling, University findings, maturity ranking, or new paid compute is authorized by this kit.

Operation: `uiowa100-verification-reproducibility-quartzv9n2-20260919`. Work record: https://github.com/woahwhattheheck/commons/issues/16273 . Source review and local evidence are separate from provider execution authority and merge state.
