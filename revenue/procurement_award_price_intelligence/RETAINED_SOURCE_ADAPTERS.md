# Retained procurement award source adapters

Operation lineage: `PROCUREMENT-AWARD-SOURCE-INGEST-ADAPTERS-20260916-ZSOL`  
Path-custody recovery: `PROCUREMENT-AWARD-SOURCE-PATH-CUSTODY-15137-ZCH0118-20260917`

This layer converts retained, explicitly structured public-procurement evidence into the input consumed by `engine.py`. It is an evidence parser and deterministic transformation boundary, not a provider authenticator. It is separate from the first-party live-source adapter documented in `SOURCE_ADAPTERS.md`.

## Source-locator custody

The request may contain an exact retained HTTPS locator, including an arbitrary path. The adapter does **not** try to guess whether path tokens are public or secret.

Admission is mechanical:

- HTTPS only;
- default HTTPS port only (`443` or omitted);
- no userinfo, query, or fragment;
- the same checks are repeated after each recursive percent-decode generation so encoded/double-encoded userinfo/query/fragment forms fail closed.

After admission, the caller path is **not exported** to the price engine. Engine-facing `sources[*].uri` is reduced to a canonical origin (`https://<canonical-host>`). The exact caller locator is bound only by SHA-256 in adapter-only custody evidence:

- `adapter_packet.json -> source_audit[*].source_locator_sha256`
- `adapter_receipt.json -> source_locator_sha256s[*]`

The raw request is independently bound by `request_sha256`. Neither the price input, downstream packet/receipt, nor memo receives caller path bytes. This avoids pretending a generic path-token heuristic can distinguish public document identity from signed-path capability material.

The raw-source SHA-256 and canonical structured-payload SHA-256 remain separate generation identities. Exact raw-source or structured-payload remints fail closed. Legitimate multiple rows belong inside one retained source payload.

## Claim-level weighting

Fresh buyer-official observations are reduced at economic-claim granularity before statistics:

- identical signatures under one `claim_key` contribute one comparable statistical row;
- corroborating `source_ids` are unioned on that row;
- differing signatures under one claim produce `HOLD_SOURCE_CONFLICT`;
- distinct claims with the same amount remain independent observations.

Thus an award notice plus executed contract can corroborate one award without double-weighting it, while genuinely distinct awards/bids still count separately.

## Supported structured sources

- `AWARD_NOTICE_JSON_V1` (`AWARD_NOTICE`, `BOARD_AWARD`) -> explicit `AWARD` only.
- `BID_TABULATION_JSON_V1` (`BID_TABULATION`) -> responsive rows with explicit amounts -> `BID`.
- `EXECUTED_CONTRACT_JSON_V1` (`EXECUTED_CONTRACT`) -> explicit base -> `AWARD`; explicit option remains separate `OPTION`.
- `AMENDMENT_OPTION_JSON_V1` (`AMENDMENT`) -> `OPTION` only, never promoted to `AWARD`.

The adapter never infers amount from prose, responsiveness from rank, buyer-officialness from hostname, missing rate unit, missing term, currency conversion, award status from bid position, or base value by arithmetic over options.

`SECONDARY_INDEX`, `SELF_AUTHORED`, and `SYNTHETIC_FIXTURE` are retained as such and cannot create buyer-official price authority.

## Authority ceiling

`source_provider_authenticated` and `buyer_officialness_authenticated` remain false. Quote, bid, submission, buyer/partner contact, signature, price commitment, award recognition, invoice, payment, and revenue authority remain false.

A caller can lie about authority metadata or supplied digests. Production use still requires independent retention/review of the actual buyer evidence. The adapter receipt proves deterministic transformation of supplied evidence; it does not prove who published it.

## Verification

Compile:

```bash
python -m revenue.procurement_award_price_intelligence.source_adapters \
  compile \
  --input revenue/procurement_award_price_intelligence/source_adapters_example.json \
  --out-dir /tmp/procurement-adapter-generation
```

Verify recompiles and requires byte-identical `price_input.json`, `adapter_packet.json`, and `adapter_receipt.json`:

```bash
python -m revenue.procurement_award_price_intelligence.source_adapters \
  verify \
  --input revenue/procurement_award_price_intelligence/source_adapters_example.json \
  --price-input /tmp/procurement-adapter-generation/price_input.json \
  --packet /tmp/procurement-adapter-generation/adapter_packet.json \
  --receipt /tmp/procurement-adapter-generation/adapter_receipt.json
```

`test_source_adapters.py` covers structured-source semantics, strict parsing, authority ceilings, deterministic receipts, CLI create-only publication, and the origin+locator-digest contract.

`test_source_adapters_redclosure.py` pins the historical STOP-MERGE predecessors: literal/encoded/double-encoded query, fragment and userinfo rejection; arbitrary literal/encoded/double-encoded caller paths reduced to origin-only output with exact-locator digest custody; raw/payload anti-remint; claim-level corroboration/conflict; distinct-claim positives; and legitimate multi-row bid tabulations.

The retained root `test_procurement_award_adapter_guard.py` executes engine, current-main live-adapter custody, retained-source adapter, and retained-source red-closure suites under both normal Python and `python -O`. Because that root guard changes in the recovery carrier, the repository's canonical `tests` workflow admits the battery on pull requests and main. The archived `ci/workflow-recipes/procurement-award-price-intelligence.yml` remains byte-identical to current main; this recovery does not mutate archived workflow inventory or add active workflow surface.
