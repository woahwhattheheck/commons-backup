# UIOWA-096 — interoperable evidence/report handoffs

Isolated kit under `revenue/uiowa_rfq_18649_interchange/`.

Typed JSON-Pointer transport for synthetic assessment envelopes. Whole existing
JSON objects are retained. Assessment and authority fields are not translated
or elevated.

## Formats

| Format | Round trip | Limitation |
| --- | --- | --- |
| JSON | exact Python JSON types | duplicate keys are rejected |
| CSV | meaning-preserving typed rows | values are serialized; types live in the `type` column |
| XLSX | same row contract | minimal OOXML writer; not Excel-formula evaluation |
| DOCX | reader projection only | paragraph text; page layout unknown |
| PDF | reader projection only | no OCR; text marked unknown without a parser |

Missing vs empty vs null is preserved on JSON/CSV/XLSX via `presence`.

## Commands

```bash
python cli.py json-to-csv examples/synthetic_envelope.json /tmp/out.csv
python cli.py csv-to-json /tmp/out.csv /tmp/back.json
python cli.py json-to-xlsx examples/synthetic_envelope.json /tmp/out.xlsx
python cli.py xlsx-to-json /tmp/out.xlsx /tmp/back-xlsx.json
```

## Scope

### Recover a disclosed machine payload

`python cli.py embedded-to-json review.docx /tmp/recovered.json` also accepts
the recovered KESTREL-I96 XLSX and PDF reader packages. It reads only their
explicit `Canonical` worksheet, `customXml/uiowa-interchange.xml` part, or
single `uiowa-interchange.json` attachment. DOCX/XLSX payload digests are checked
with the existing canonical codec; duplicate JSON keys and lossy decimal tokens
are rejected by that same codec. It preserves the payload's existing values and
authority fields without adopting the old contribution's local fixture schema.
Ordinary reader projections without these payloads remain projections and return
a clear error from this command. Edited prose, page text and worksheet review
views are never converted into records. This is payload recovery, not proof of
authenticity or agreement with edited human views. PDF input needs `pypdf`.
Existing import/export and projection commands are unchanged.

No University records, live provider calls, scheduling, or occupied
workbench/compiler edits.
