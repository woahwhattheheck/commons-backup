# UIOWA-050 — Development-to-operations handoff

This package implements a reusable handoff packet for assessing whether a completed change carries enough information from development into support and operations.

It is **assessment tooling, not an approval gate**. The validator reports structural errors, evidence/readiness gaps, and explicit follow-ups. It never declares a University change approved, production-ready, compliant, or safe.

## What is included

- `handoff_packet_template.md` — human-editable worksheet.
- `schema.json` — machine-readable data contract for handoff packets.
- `handoff.py` — zero-dependency validator and Markdown renderer.
- `examples/planned_release.json` — synthetic planned-release case.
- `examples/urgent_maintenance.json` — synthetic urgent-maintenance case with an intentionally visible documentation follow-up.
- `tests/test_handoff.py` — regression tests for traceability, missing evidence, missing support handoff, and report rendering.

All examples are fictional. They are not University of Iowa findings.

## Assessment intent

UIOWA-050 asks whether information accompanying a completed change connects the requested behavior to acceptance evidence, support ownership, documentation, and operational needs. This implementation therefore validates five relationships:

1. each requirement has explicit acceptance criteria;
2. each requirement cites acceptance evidence;
3. each requirement points to at least one support or operational readiness item;
4. support, documentation, operations, rollback/recovery, limitations, and open items retain named role ownership;
5. unresolved information remains visible instead of being silently converted into a positive readiness judgment.

Planned releases and urgent maintenance use the same packet shape. Urgent maintenance may legitimately defer some documentation, but a deferral must retain an owner and a follow-up trigger.

## Quick start

From this directory:

```bash
python handoff.py validate examples/planned_release.json
python handoff.py render examples/planned_release.json
python handoff.py validate examples/urgent_maintenance.json
python -m unittest discover -s tests -v
```

Validation exits:

- `0`: structurally valid packet; review the reported gaps/warnings.
- `2`: structural or traceability errors that prevent reliable handoff review.

A zero exit code is **not** an approval signal.

## Output semantics

For an output that must not replace an existing report, use
`python handoff.py render examples/planned_release.json --output new-report.md --no-clobber`.
This stages a complete UTF-8 report in the destination directory and publishes it
with an exclusive hard link. An existing output (including a symbolic link or an
alias of the input) is preserved, with exit code 2. The parent directory must
exist and support hard links. Ordinary `--output` retains its existing overwrite
behavior for compatibility; the preservation mode is opt-in. Shell redirection
is outside this protection. A completed report can remain if staging cleanup
fails, so inspect an output after any error before retrying.

The validator emits:

- `ERROR` — broken structure, duplicate IDs, invalid references, or required information absent.
- `GAP` — information needed for a defensible handoff assessment is incomplete.
- `WARNING` — a declared unresolved/deferred item needs reviewer attention.
- `INFO` — contextual signal, such as a synthetic example marker.

The Markdown renderer includes a requirement-to-evidence/readiness traceability table and a findings section so reviewers can see both what is supported and what still needs follow-up.

## Boundaries

- No private University data is included.
- No deployment mechanics are prescribed; UIOWA-050 stays at the information-handoff boundary.
- No named product procurement recommendation is made.
- No arithmetic maturity/readiness score is generated.
- A missing artifact is recorded as missing; it is not treated as proof that the underlying practice does not exist.
