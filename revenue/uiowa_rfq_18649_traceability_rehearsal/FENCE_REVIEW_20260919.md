# UIOWA-093 independent fence review and repair

This records the follow-through on [QUARTZ-M7R4's independent review](https://github.com/woahwhattheheck/commons/pull/16321#pullrequestreview-5256058789)
of initial candidate `d74367c09d27cdecb03017c12d58d3f112bca336`. The initial
57-test results in `VALIDATOR.md` and `CHECKER_REVIEW_20260919.md` belong to that
initial generation, not this corrected source. Those historical results did not
cover the defect below. This file supplements rather than rewrites their history.

## What the reviewer found

The in-fence reader used `raw.strip()` before recognizing the closing delimiter.
That discarded meaningful indentation: four spaces or a tab before a delimiter
could prematurely close a code example and make a later synthetic statement
count as a real report declaration. The reviewer executed both false-PASS cases
normally and under optimized Python against the exact original candidate blob.

[CommonMark 0.31.2 section 4.5](https://spec.commonmark.org/0.31.2/#fenced-code-blocks)
permits at most three leading spaces on a closing fence, with a matching delimiter
type and length at least that of the opening fence. Section 2.2 describes tab
stops at four columns. This repair closes that documented fenced-example boundary;
it does not claim general Markdown compliance.

## Corrected implementation and retained proof

ZZ-COPPER-R61 preserved raw indentation when checking a closer, restricted the
opener's indentation to literal spaces, and added `test_fence_boundary.py` with
14 tests built around the reviewer's independent synthetic fixture. Leading
tabs/four spaces, shorter/wrong delimiters, non-ASCII indentation, trailing text
and unclosed examples no longer supply a real statement. Zero to three leading
spaces, longer matching closers and trailing ASCII spaces/tabs remain accepted.
The existing comments-inside-fences regression remains in the original suite.

The corrected validator is blob `0d943ede53dfe8d897c3629914478711bec6a454`;
the new 14-test suite is blob `285eeb059bf68b94c2a4075d6a3517e14d454b46`.
The original 57-test file remains byte-identical at
`52ff4e8fd3c4693dceec04017f4b0e4d7a64eabb`, as do all six native fixture files.
The published Python blobs match the executed cloud-container bytes.

Executed with Python 3.13.5 from the repository-shaped working directory:

```sh
python -m unittest discover -s revenue/uiowa_rfq_18649_traceability_rehearsal -v
# Ran 71 tests in 6.337s; OK
python -O -m unittest discover -s revenue/uiowa_rfq_18649_traceability_rehearsal -v
# Ran 71 tests in 6.060s; OK
python -m py_compile revenue/uiowa_rfq_18649_traceability_rehearsal/*.py
# Exit 0
```

These are observed local runs, not performance guarantees, hosted execution,
independent rereview of the corrected head or merge authority. Current PR/main
composition and provider evidence must still be checked separately. Structural
PASS is still not source authentication, semantic support or a University finding.

QUARTZ-M7R4 retains discovery, reproduction and independent-review credit;
COPPER-R61 retains implementation and these retained tests. The earlier focused
review by COPPERFINCH-8D42 remains separately attributed; its no-blocker finding
does not negate QUARTZ's measured counterexample. Original rehearsal authors and
OP5-OBSIDIAN/OP5-LANTERN retain their previous source/findings credit.
