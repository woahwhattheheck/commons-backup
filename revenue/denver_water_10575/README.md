# Denver Water solicitation 10575 — evidence-bound qualification

Operation: `DENVER-WATER-10575-AI-AGENT-ASSIST-ZNAVEC-H3V7-20260913`  
Issue: `woahwhattheheck/commons#13798`

## Current commercial disposition

**HOLD — controlling buyer packet not acquired.** Denver Water's official current-opportunities page lists solicitation **10575 — Customer Experience AI Chatbot**, released 2026-08-31 and due 2026-09-30. The official page routes procurement downloads to Denver Water's BidNet surface. The controlling package was not retrievable from this harness during this build, so the current trusted authority root is deliberately `NOT_ACQUIRED` and contains **no deadline, buyer requirement manifest, or readiness material**.

Secondary procurement summaries are discovery evidence only. They cannot establish a mandatory buyer gate, supplier qualification, exact deadline, or proposal readiness.

## Trust model

The reusable evaluator is split across two authorities:

1. **Candidate qualification payload** — `current_qualification.json`. It may carry observed sources, proposed requirement/evidence rows, and supplier evidence. It cannot define what the buyer's controlling package is, what the complete requirement universe is, or what the commercial deadline is.
2. **Verifier-pinned buyer authority** — `trusted_authority.json`. Its canonical SHA-256 is compiled into `qualification.py` as `TRUSTED_AUTHORITY_SHA256`. A different authority document is rejected even if a caller recomputes its internal hashes.

A future `ACQUIRED` trusted authority update must itself bind:

- the exact opportunity and solicitation;
- the **complete current controlling official file/addendum set** by URL + SHA-256;
- the buyer-controlled proposal deadline and which trusted file establishes it;
- an explicit freshness horizon;
- the **complete mandatory requirement manifest**, including title/text summary, route, mandatory flag, cure semantics, exact controlling source id and source locator, supplier-evidence subject/category, and whether one proof artifact may legitimately support multiple gates;
- `requirements_sha256`, the canonical digest of that complete descriptor set.

Changing that file requires changing the compiled trust-root digest, so packet acquisition/extraction is a reviewed source change rather than candidate-controlled runtime input.

## Promotion fences

Readiness fails closed when any of these drift:

- trusted authority bytes;
- official packet/addendum file set or digest;
- complete requirement descriptors, including source locator / mandatory / route / cure semantics;
- authority freshness;
- trusted proposal deadline;
- supplier evidence claim id, subject, category, source digest/ref;
- unapproved reuse of one proof artifact across unrelated requirements.

Production `compile` and `verify` sample the verifier process's current UTC. The payload has no `as_of` or deadline field and the CLI exposes no current-time override. A historical receipt can remain internally authentic while losing **current commercial authority** after the trusted deadline or authority freshness horizon.

## Current fixture

The current repository-pinned authority root is intentionally:

- state: `NOT_ACQUIRED`;
- official controlling files: none;
- complete buyer requirement manifest: none;
- trusted deadline: none;
- current disposition: `HOLD / CONTROLLING_PACKET_NOT_ACQUIRED`.

`current_qualification.json` retains provisional discovery rows only so the future acquisition work has an explicit research checklist. Because those rows are not the verifier-pinned buyer manifest, they cannot green a route.

## High-value specialist seam if PRIME is unsupported

If the controlling package ultimately permits teaming, the credible bounded contribution is **agent reliability + enterprise-integration acceptance QA**, not pretending Commons/TJLabs supplies the enterprise contact-center platform, public-utility past performance, insurance, or certifications. See `TEAMING_PACKET.md`.

## Run

```bash
python revenue/denver_water_10575/qualification.py compile \
  --input revenue/denver_water_10575/current_qualification.json \
  --authority revenue/denver_water_10575/trusted_authority.json \
  --output /tmp/denver-10575-receipt.json

python revenue/denver_water_10575/qualification.py verify \
  --input revenue/denver_water_10575/current_qualification.json \
  --authority revenue/denver_water_10575/trusted_authority.json \
  --receipt /tmp/denver-10575-receipt.json

python -m unittest discover -s revenue/denver_water_10575 -p 'test_qualification.py' -v
python -O -m unittest discover -s revenue/denver_water_10575 -p 'test_qualification.py' -v
```

## Hostile coverage

The suite covers, among other failures:

- caller-minted "official packet" authority even with recomputed internal hashes;
- omitted buyer gate / one-easy-gate replacement;
- mutation of mandatory, route, cure, or source locator semantics;
- omitted later addendum or changed official digest;
- extra untrusted controlling file;
- cross-gate evidence claim/category mismatch;
- unapproved exact proof-artifact reuse across unrelated requirements;
- future source/evidence timestamps;
- stale trusted authority;
- trusted deadline expiry;
- historical READY receipt replay after current deadline;
- payload deadline injection;
- duplicate keys/ids, nonfinite JSON, type traps, malformed time/URL, receipt tamper;
- output overwrite and symlink alias attacks.

## Authority ceiling

This package performs no buyer contact, BidNet login/registration/terms action, question, proposal submission, pricing commitment, signature, contract action, provider mutation, deployment, spend, award or revenue recognition. It does not invent supplier references, insurance, certifications, platform status or implementation history.
