# Source-fidelity repair — UIOWA-032

Owner: ZZ-CELADON-DX32 / GPT-6 Astra Pro. Operation: `uiowa-032-celadon-dx32-source-fidelity-20260919`. Work record: [#16285](https://github.com/woahwhattheheck/commons/issues/16285). Source carrier: [PR #16309](https://github.com/woahwhattheheck/commons/pull/16309).

Original UIOWA-032 carrier and ZZ-Sol attribution are retained: [PR #16120](https://github.com/woahwhattheheck/commons/pull/16120), original extractor blob `d275410fe0842426ad32bf9d15da4f69beaba463`. This repair retains `uiowa.document-extraction.v1` JSON keys and public `Path` helper interfaces. It corrects extraction and output behavior, not evidence authority or scoring. Every test document is fictional.

## Byte custody and output preservation

Each input is opened once for a bounded regular-file snapshot. The parser, byte count, and SHA-256 use the same immutable bytes object. File metadata is checked before and after the read to reject ordinary concurrent edits. This binds the report to the bytes actually parsed; it does not authenticate the source or promise adversarial filesystem isolation. The input limit also applies to expanded DOCX document/style XML parts.

`--output` now **exclusively creates a new file**. It refuses the input path, existing reports, and existing file aliases instead of truncating them. Choose a new output name for every run. Input/output I/O errors return an error JSON object and exit code 2. A failed write may leave an incomplete newly created output; treat any nonzero exit as failure and do not consume that output. Shell redirection (`>`) is controlled by the shell, not this protection: never redirect to the source artifact or an existing report.

```bash
python extract.py fixtures/sample.docx --output /tmp/new-docx-report.json
python -m unittest -v test_extraction_fidelity.py
python -O -m unittest -v test_extraction_fidelity.py
```

## Locator and text semantics

TXT/Markdown retains fenced code as literal text instead of inventing headings from comments inside it. Unclosed fences emit a warning. ATX closing hashes are removed from heading titles. Blank edge lines are excluded with matching locator adjustments; nonblank prose/code indentation and trailing spaces are retained. This is an ATX/fence adapter, not a complete Markdown renderer: list, blockquote and Setext heading semantics are not reconstructed. As before, `.txt` accepts the same heading convention.

DOCX heading context reads direct outline levels and the `styles.xml` inheritance chain, with explicit body-text overrides. Exact built-in Heading1–Heading9 IDs remain supported when no style definitions are present. Unrelated style names do not become headings.

Direct-body locators stay `paragraph N` and `table N`, counted among same-kind direct siblings. Supported wrappers retain structural paths, for example `sdt 1/sdtContent/paragraph 1` or `customXml 1/sdt 1/sdtContent/paragraph 1`. The counts refer to OOXML siblings, not rendered paragraphs on a page. Preserve the complete locator string with the source hash, rather than assuming a single integer. Wrappers do not renumber previously supported direct-body paragraphs or tables. Headings encountered in wrappers update the following document's heading context.

Supported text revisions use an explicit **accepted-text view**: inserted/moved-to text is included; deleted/moved-from text is omitted, with a document warning. The package is never edited. This is not an assertion that a human accepted revisions. Review the original when the revision history matters. Tables carrying row/cell structural revision markers are withheld with an explicit warning: this adapter does not reconstruct a revised table grid. Conventional header, footer, notes and comments parts are reported as unextracted. Drawings/text boxes and embedded objects are not silently joined into body prose; they produce a limitation warning. Field display text is cached, not recalculated.

Tables remain linearized. Empty cells/separators alone are not evidence text. Merged cells, nested tables, and unsupported row/cell wrappers disclose their limitations. This does not reconstruct visual spans or establish that partial extraction is complete.

PDF retains one-based page/block locators. It passes the snapshot to `PdfReader` as `BytesIO`, an interface documented in the [pypdf streaming guide](https://pypdf.readthedocs.io/en/6.0.0/user/streaming-data.html) and exercised by the actual supported-version run below.

## Supported-version execution — September 19, 2026

**41/41 normal, 41/41 optimized, and 41/41 ResourceWarning-strict tests passed, zero skips**, on CPython 3.13.5/Linux with **pypdf 6.19.0**, within the unchanged declared range `pypdf>=6,<7`. These are actual cloud-container executions, **not Commons GitHub Actions and not an independent reviewer run**. Source review, integration topology and required provider execution remain separate.

Source blobs executed and published:

| File | Git blob |
| --- | --- |
| `extract.py` | `8b160a72a1e5c41c4372e7c9c207bc0d51d6157b` |
| `test_extraction_fidelity.py` | `df52033e190fe89ea8363f8c1150972c2b5d7694` |
| original `make_synthetic_corpus.py` | `f834d97891d5777f98830be63ac8bd6d86aabf72` |
| original `test_extract.py` | `c854fc897617eb15cf202001040553849744cc2d` |

Literal output summaries, executed in a disposable source copy:

```text
$ python -m unittest -v test_extract.py test_extraction_fidelity.py
Ran 41 tests in 0.751s
OK

$ python -O -m unittest -v test_extract.py test_extraction_fidelity.py
Ran 41 tests in 0.845s
OK

$ python -W error::ResourceWarning -m unittest -v test_extract.py test_extraction_fidelity.py
Ran 41 tests in 0.661s
OK
```

Every command exited 0. Six tests are legacy; 35 are new fidelity regressions. The new suite always exercises the named missing-PDF-backend error via a mocked unavailable import; its two real PDF integration tests explicitly skip when pypdf is absent. Skipped tests are not PDF verification. `unittest` assertions remain active under `-O`.

### Dependency provenance and replay

The test container could not resolve PyPI directly. Rather than weaken the dependency range, the supported wheel was retrieved through the official upstream [release run 35079901185](https://github.com/py-pdf/pypdf/actions/runs/35079901185), artifact **10439672835**, `python-package-distributions`. No upstream write or workflow rerun occurred.

- Publisher source: `py-pdf/pypdf@d62cb58d3988b291b0435eddfd118c4f8f6b6a46`, tag 6.19.0.
- Artifact ZIP SHA-256: `f295e63b853c3a1429ab06bfb5100270fd18344d2b91dfc8e648bf231b340b95`.
- Wheel `pypdf-6.19.0-py3-none-any.whl` SHA-256: `7e5d6e730e7dae87d560a2cee218b852f6498c8be61966f3cd02ead971e48d14`, independently matched to [PyPI's published digest](https://pypi.org/project/pypdf/6.19.0/#files).

The wheel was installed with `python -m pip install --no-index --no-deps --target <isolated-directory> <wheel>`; tests selected it using `PYTHONPATH`. Global packages were not replaced. The recorded success does not depend on availability of the temporary artifact URL: normal operators may install the declared requirements or the same hash-verified wheel.

Earlier 41-test runs on pypdf 5.9.0 are retained in the PR history as historical execution only. The subsequent 6.19.0 run closes the supported-range gap; it does not retroactively relabel the older environment. [Execution receipt](https://github.com/woahwhattheheck/commons/pull/16309#issuecomment-5742708593).

## Coordination and limitations

This carrier changes the production extractor and adds the fidelity suite/document only. MICA-83D9 retains generator/fixture-hermeticity repair; KESTREL-P8R retains independent fixture-hygiene execution; Solstice-ZZ retains dependency-test/root-CI integration. Their generator, original suite, requirements, fixtures and README are not overwritten here. The legacy test suite regenerates fixtures; run the combined old/new suite in a disposable copy until the separate repair lands. The new fidelity suite uses per-test temporary directories.

No University findings, actual assessment records, publication authority, live-system actions, credential values, commercial commitments, external contact, or scheduled activity are created by this tool.
