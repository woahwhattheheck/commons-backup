# Read an MCP capture without confusing integrity with successful work

This is an operator companion for the existing offline auditor. The new
`--format markdown` option is a presentation path, not another protocol engine.
It applies to both `audit` and `verify`. JSON remains the default and remains the
saved input used by `verify`.

Run the examples from the repository root in an existing cloud checkout with
this source generation. They use the checked-in fictional capture and temporary
outputs, not a real endpoint, customer session or provider account. No dependency
installation is needed by the tool or its focused tests.

## Read the known example

```sh
python -m tools.mcp_transcript_audit.cli audit tools/mcp_transcript_audit/example_session.jsonl --format markdown
```

The five-event example has an initialize request on line 1, its response on line
2, and the initialized notification on line 3. Lines 4 and 5 record a tools/list
request and its correlated response. The report shows two requests, two responses
and one notification, with capture audit **PASS** and exit 0.

The exact existing capture is 921 bytes. Its SHA-256 is
`5fe95680d1bfd2de06b24a0bab38e9ea93b8ce216be011c427d975cda5333fbb`.
Its audit receipt SHA-256 is
`3f8bfdaa7f530b2883188ec7690cbeb2adb48c1a5057e9e7008ca4f241ab9acc`.
These identify fictional capture evidence, not endpoint identity or evidence
that a tool was actually executed.

## Retain JSON; use Markdown to read it

In a POSIX cloud shell, create a fresh output directory:

```sh
work=$(mktemp -d)
python -m tools.mcp_transcript_audit.cli audit tools/mcp_transcript_audit/example_session.jsonl --output "$work/receipt.json"
python -m tools.mcp_transcript_audit.cli audit tools/mcp_transcript_audit/example_session.jsonl --format markdown --output "$work/audit.md"
python -m tools.mcp_transcript_audit.cli verify tools/mcp_transcript_audit/example_session.jsonl "$work/receipt.json" --format markdown --output "$work/verification.md"
```

Each output path must be new. Existing files are not overwritten, including an
output path that names the input capture or saved receipt. Output errors retain
exit 2. A Markdown report supplied as the saved receipt is invalid JSON for this
purpose: verification reports **MISMATCH**, not a successful conversion.

The JSON receipt's embedded `receipt_sha256` and verification's
`receipt_file_sha256` are different identities. The former binds the canonical
unsigned audit result. The latter hashes the exact saved JSON file, including
its whitespace and final newline. The report labels both rather than treating
them as interchangeable. The third verification hash identifies the computed
verification result itself.

## Three distinct questions

| Question | What to inspect | What it does not establish |
| --- | --- | --- |
| Did the supplied capture pass the existing checks? | Audit PASS/HOLD, diagnostics and coverage | Tool success, business correctness, real-world execution or endpoint identity |
| Does this saved JSON receipt match this capture? | Verification MATCH/MISMATCH and exact hashes | That the matched capture had audit PASS |
| Did a provider action really happen? | Separate provider-side evidence | Neither of the two reports supplies that evidence |

A saved receipt for an empty or otherwise HOLD capture can verify as MATCH and
exit 0. This is correct integrity verification, not a promotion to capture PASS.
The Markdown verification result explicitly explains the distinction. It does
not invent an audit status absent from the existing verification schema. Run
`audit --format markdown` on those same capture bytes to see their status.

## Read a HOLD report without filling in missing evidence

For a safe empty-capture exercise, keep using the temporary directory:

```sh
: > "$work/empty.jsonl"
python -m tools.mcp_transcript_audit.cli audit "$work/empty.jsonl" --format markdown
```

Expected: capture audit HOLD, `EMPTY_CAPTURE`, no invented lifecycle lines, and
exit 3. A failing command is expected in this exercise; a shell configured to
stop on nonzero exits will stop here.

The coverage section distinguishes nonempty records counted, recorded evidence
rows, and classified messages. After a parsing or resource-limit failure, an
evidence row may contain only byte information. Such rows are displayed as
**not classified**, never successful. Physical capture line numbers are retained,
including when blank lines occur between events. Every evidence row returned by
the auditor is indexed; no hidden display truncation is applied. A resource-limited
audit may itself contain only partial evidence, so recorded rows are not a claim
that the original capture is complete.

Diagnostics retain their exact code and line, or their capture-wide scope. The
method table is sorted for stable comparison. For full per-line, payload and
typed-ID hashes where available, retain the JSON receipt.

## Handling and display limits

The renderer uses only the existing audit/verification result fields. It does
not copy request parameters, response results, error payloads or raw request IDs.
Method names and other retained metadata can still contain sensitive text; this
is not a de-identification or public-release guarantee. Review an internal report
before sharing it. No customer destination is created by this feature.

Untrusted metadata is kept within a literal Markdown table cell. Markdown
punctuation and HTML are escaped; line breaks, terminal controls and Unicode
format controls are displayed as escape text instead of changing the report's
layout invisibly. The report neither opens an endpoint nor executes a captured
request. It does not change the auditor's fixed protocol version, classification
rules, result schemas, hashes or authority fields.

For programmatic use, call the existing engine first:

```python
from tools.mcp_transcript_audit import audit_transcript
from tools.mcp_transcript_audit.report import render_markdown

result = audit_transcript(source_bytes)
text = render_markdown(result)
```

`render_markdown` is display-only; it does not authenticate an arbitrary result
dictionary. It returns text without a trailing newline. The CLI adds exactly one
newline using the existing stdout/create-exclusive output path. Never substitute
rendering for `verify_receipt`.

## Focused regression exercise

```sh
python -m unittest -q test_mcp_transcript_audit_report
python -O -m unittest -q test_mcp_transcript_audit_report
python -W error -m unittest -q test_mcp_transcript_audit_report
```

These tests execute the actual existing audit engine and real CLI subprocesses.
They cover both formats, byte-identical default JSON, exit 0/2/3 behavior, a matching
HOLD receipt, changed and resealed receipt mismatches, physical line numbers,
unclassified tails, metadata escaping, privacy scope and non-overwriting output.
They use only fictional temporary inputs. They are focused source tests, not a
whole-repository or hosted-execution claim. The original auditor and its retained
regression suite keep their implementation credit; the report adds no second
verification engine.
