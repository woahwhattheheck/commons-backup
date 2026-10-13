# Proposal compliance gate

A buyer-neutral, stdlib-only gate for turning an RFP requirement register into a deterministic readiness check across proposal lifecycle stages.

It exists to prevent a common failure mode in proposal work: polished prose silently substituting for evidence. Requirements can be marked `mandatory`, `scored`, or `informational`; evidence is tracked as `available`, `pending`, `missing`, or `not_applicable`; and owner/authorized-human decisions can be hard-gated so an automated workflow cannot certify its own signature, financial statements, references, insurance, or other human-controlled facts.

Requirements default to the `submission` stage for backward compatibility. A requirement may instead declare `"stage": "award"` when it becomes controlling only after selection or during contracting. Submission-stage controls remain controlling at award. An award-only row is shown as `DEFERRED` during a submission check; it is not counted as satisfied evidence and does not block submission until the award horizon is evaluated.

## Usage

```bash
python tools/proposal_gate/proposal_gate.py requirements.json evidence.json \
  --stage submission \
  --markdown-out compliance.md \
  --json-out compliance.json \
  --skeleton-out response.md \
  --draft-out draft.md \
  --check
```

Use `--stage award` to evaluate the later contracting/award horizon. `--check` exits `2` unless the selected target stage is ready.

Minimal requirement:

```json
{
  "requirements": [
    {
      "id": "A-1",
      "section": "Architecture",
      "type": "mandatory",
      "statement": "Describe scalability",
      "evidence": ["architecture-note"],
      "response": "Horizontal workers with bounded queues."
    },
    {
      "id": "INS-1",
      "section": "Award",
      "type": "mandatory",
      "stage": "award",
      "statement": "Provide required insurance evidence before contracting",
      "evidence": ["insurance-certificate"],
      "response": "Certificate is required before contract execution.",
      "owner_gate": true
    }
  ]
}
```

Minimal evidence inventory:

```json
{
  "evidence": [
    {"id": "architecture-note", "status": "available"},
    {"id": "insurance-certificate", "status": "pending"}
  ]
}
```

At `--stage submission`, `INS-1` is reported `DEFERRED`, the submission denominator excludes it, and it does not falsely block proposal delivery. At `--stage award`, both the submission requirement and `INS-1` are controlling; missing/pending evidence or an owner gate blocks award readiness.

Machine-readable summaries expose both `submission_ready` and `stage_ready`. This keeps a later award-only blocker from retroactively claiming that a proposal was not submission-ready while still preventing the later contract horizon from going green.

## Safety properties

- Missing or pending mandatory evidence blocks readiness once that requirement is controlling.
- `not_applicable` is a classification, not waiver authority. A controlling mandatory requirement whose required evidence is marked `not_applicable` remains `BLOCKED`; a scored requirement is `AT_RISK`. This package has no waiver-minting path.
- An empty requirement universe is rejected rather than reported as 100% ready or silently relabeled as the submission horizon.
- `[TBD]`, `TODO`, and insert-style placeholders do not count as responses.
- `owner_gate: true` blocks the horizon where that requirement controls, even if an artifact is present.
- Requirements default to `submission`; only exact built-in strings `submission` and `award` are accepted as stages.
- Submission controls remain active at award; award-only controls are explicit `DEFERRED` rows at submission rather than being treated as READY.
- Deferred rows do not inflate or depress the readiness percentage for the current horizon.
- Requirement IDs and evidence IDs are validated for uniqueness and status vocabulary.
- Output is human-readable Markdown plus machine-readable JSON, and can render both a blank response skeleton and the current evidence-backed draft.
- Buyer-specific requirements stay runtime data; the engine itself contains no procurement-confidential content.

## Tests

```bash
python -m unittest tools/proposal_gate/test_proposal_gate.py -v
python -O -m unittest tools/proposal_gate/test_proposal_gate.py -v
```
