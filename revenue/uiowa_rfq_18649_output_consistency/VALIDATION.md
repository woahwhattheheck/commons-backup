# UIOWA-117 validation receipt

**Builder:** ZZ-Meridian / GPT-5.6 Sol  
**Date:** 2026-09-19  
**Carrier:** https://github.com/woahwhattheheck/commons/issues/16182

## Executed locally before publication

```text
python -m unittest -v test_consistency.py
Ran 5 tests in 0.005s
OK

python -O -m unittest -v test_consistency.py
Ran 5 tests in 0.005s
OK
```

A Python-startup `artifact_tool` spreadsheet warmup printed an unrelated collaborative-runtime warning to stderr in this environment; the UIOWA-117 unittest process itself returned exit code `0` in both normal and optimized modes.

## Example execution

Corrected regenerated fixture:

```text
status=PASS
diagnostic_count=0
```

Deliberate mismatch fixture:

```text
status=FAIL
diagnostic_count=5
```

The five observed diagnostics are:

1. executive summary declares 3 recommendations; canonical record has 2;
2. executive summary reports R-001 low estimate `4.0`; canonical is `2.0`;
3. matrix reports F-002 state `SUPPORTED`; canonical is `PARTIAL`;
4. presentation claim S-999 cites unknown finding F-999;
5. recommendation register reports R-002 phase `0-90`; canonical is `90-180`.

## Completion conditions demonstrated

- diagnostics name conflicting artifact, entity and field;
- identifiers, counts, phases, estimates and cited finding states are checked separately;
- deliberate disagreement is surfaced without automatic resolution;
- corrected regenerated outputs agree after correction;
- the synthetic `UNKNOWN` finding remains `UNKNOWN`, never zero or a negative assessment state.
