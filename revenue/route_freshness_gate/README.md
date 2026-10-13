# Route freshness proof gate

Isolated compiler for caller-supplied retained route evidence.

Decisions, fail-closed precedence:

1. `HARD_DNR`
2. `DEAD_ROUTE`
3. `HOLD_PROVIDER_AMBIGUOUS`
4. `HOLD_COMPANY_PRIOR_TOUCH`
5. `HOLD_STALE_ROUTE`
6. `READY_FOR_MUSE_CENSUS`

`READY_FOR_MUSE_CENSUS` means only that this evidence layer found no blocking predecessor. Every send/provider/contact/payment/revenue flag stays false. Optional Muse receipt digest is trace metadata and cannot promote HOLD to READY.

## CLI

```bash
python revenue/route_freshness_gate/engine.py compile \
  --input revenue/route_freshness_gate/example_manifest.json \
  --output /tmp/route-freshness.packet.json \
  --markdown /tmp/route-freshness.packet.md

python revenue/route_freshness_gate/engine.py verify \
  --input /tmp/route-freshness.packet.json
```

Inputs bind organization digest, route identity digest, route kind, source authority, timestamps, provider-history events, and company-level prior-touch records. No raw email, phone, token, or message body is accepted in the durable packet.
