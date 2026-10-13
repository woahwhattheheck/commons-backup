# SCORM Delivery Assurance

Buyer-neutral, offline release assurance for a SCORM course package.

The tool answers one narrow question: **does this exact ZIP satisfy an explicit evidence-bound package contract strongly enough to hand to an LMS sandbox for review?** It does not certify SCORM conformance, accessibility, instructional quality, buyer acceptance, or production LMS readiness.

## Checks

- bounded ZIP input with traversal, symlink, duplicate-name, and case-collision rejection;
- CLI inputs opened once through a retained descriptor, with regular-file/type/size checks on that same generation and post-read generation verification;
- UTF-8-only `imsmanifest.xml` parsing with DTD/entity declarations rejected before XML semantics;
- root `imsmanifest.xml`, local-only launch/resource hrefs, organization/resource closure, and presence of every manifest-declared file;
- SCORM 1.2 / 2004 version declaration derived only from one root `<metadata>` block with `schema=ADL SCORM` and one explicit `schemaversion`, against explicit policy;
- `course.assurance.json` binding course ID, source revision SHA-256, every organization resource to exactly one module, assessment/completion metadata, and accessibility evidence paths;
- transcript plus `.vtt`/`.srt` caption evidence presence when policy requires it;
- canonical file SHA-256 inventory, package/manifest/sidecar digests, deterministic status/reasons, and a receipt that can be fully recomputed offline;
- create-exclusive CLI output so an older receipt is never silently overwritten. A late write/fsync failure preserves the created pathname instead of pathname-unlinking, because cleanup must never delete a foreign replacement raced into that name.

`READY_FOR_LMS_SANDBOX_REVIEW` is deliberately the strongest state. It means only that the exact supplied package passed this technical preflight. Every receipt explicitly keeps `scorm_spec_certified`, `accessibility_certified`, `instructional_quality_approved`, `lms_production_approved`, `buyer_acceptance`, and `payment_or_revenue` false.

## Manifest authority boundary

`imsmanifest.xml` must decode as UTF-8 (a UTF-8 BOM is tolerated). UTF-16/UTF-32 and other alternate encodings are rejected rather than relying on encoding-sensitive declaration scans. DTD and entity declarations are rejected in decoded text before `ElementTree` parsing.

The SCORM policy gate does not infer a version from identifiers, arbitrary root attributes, or substrings. The root manifest must contain exactly one direct `<metadata>` block with exactly one non-empty `<schema>` equal to `ADL SCORM` and one non-empty `<schemaversion>`. Supported declarations are `1.2` for SCORM 1.2 and `1.3`, `CAM 1.3`, `2004`, or `2004 <edition>` for SCORM 2004. Missing, duplicate, conflicting, or unrelated version text fails closed.

## Evidence sidecar

The ZIP must contain `course.assurance.json`:

```json
{
  "schema": "tjlabs.scorm-course-evidence/v1",
  "course_id": "course-01",
  "source_revision_sha256": "<64 lowercase hex>",
  "modules": [
    {
      "id": "module-01",
      "resource_id": "RES1",
      "title": "Module One",
      "assessment": {"required": true, "passing_score": 80},
      "completion": {"required": true},
      "accessibility": {
        "transcript": "module-01/transcript.txt",
        "captions": ["module-01/captions.vtt"]
      }
    }
  ]
}
```

This is TJLabs release evidence layered on top of SCORM, not a replacement for the SCORM specification.

## CLI

```bash
python -m revenue.scorm_delivery_assurance.assurance compile course.zip receipt.json
python -m revenue.scorm_delivery_assurance.assurance verify course.zip receipt.json
```

An optional policy JSON can be supplied with `--policy`. The default accepts SCORM 1.2 and 2004, requires assessment/completion metadata, requires transcript+caption evidence, and bounds file count and expanded size.

On platforms that expose the flags, file ingress uses `O_NOFOLLOW`, `O_NONBLOCK`, and `O_CLOEXEC`, then `fstat()` on the retained descriptor. The generation fence binds device, inode, mode, size, mtime, and ctime before/after the bounded read. This makes a pathname swap after open irrelevant to the bytes consumed and catches same-inode rewrites even if mtime is restored.

## Focused validation

```bash
python -m py_compile revenue/scorm_delivery_assurance/*.py
python -m unittest revenue.scorm_delivery_assurance.test_assurance -v
python -O -m unittest revenue.scorm_delivery_assurance.test_assurance -v
```

The suite covers clean SCORM 1.2 and 2004 packaging, missing accessibility evidence, traversal, external launch URLs, duplicate and case-colliding members, organization/resource mismatch, duplicate JSON keys, bool-as-int policy traps, policy thresholds, package tamper/reverify, deterministic exact-byte receipt generation, create-exclusive CLI publication, and explicit non-certification/payment authority.

Hostile coverage additionally pins UTF-8/16/32 DTD/entity behavior, root-identifier version spoofing, missing/incorrect/duplicate SCORM metadata, regular-file replacement with symlink/FIFO/oversize generations, same-inode same-size mutation with restored mtime, and foreign output replacement during a synthetic late fsync failure.

## Commercial boundary

This component can support a full-service e-learning prime or an internal release process. It is **not** evidence that TJLabs authored a buyer's course, owns instructional-design experience, has client references, completed an accessibility audit, can supply approved voice talent, or is authorized to access/deploy to a production LMS. Those remain separate evidence gates in the parent revenue lane.
