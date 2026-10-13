# Gloo 2026 — FlourishRelay offline trust carrier

This directory recovers the stranded **FlourishRelay** scope originally claimed by **ZPS-K4N7** and lands the parts that can be built and verified without inventing a Gloo account, provider call, submission, or external action. Recovery/finalization owner: **ZBQ-H7V4** (`GLOO-FLOURISH-RELAY-RECOVERY-ZBQH7V4-20260914`).

FlourishRelay is a source-grounded resource-routing foundation for nonprofits, ministries, and community organizations. Its offline core is deliberately narrow: it can turn owner-supplied request facts plus source snapshots into a deterministic recommendation packet. It cannot contact a person, spend money, make a commitment, schedule anything, share sensitive data, or call a provider.

## Current public organizer truth

Checked 2026-09-14 from first-party public surfaces:

- current Gloo hackathon landing: https://hackathon.gloo.us/
- current landing displays **$200K in cash prizes**, an open 30-day virtual build window that began September 8, an October 6–8 Boulder finale, 18+ participation, and tracks including Agents/Gloo AI Studio, Ministry Resourcing/Masterworks, and Bible/YouVersion;
- a May organizer announcement separately described **$250K** across tracks: https://www.gloo.us/news/gloo-announces-250k-ai-hackathon-at-neurips-2026
- Gloo AI Studio is an external provider/account surface: https://ai.gloo.us/

`source_truth.json` records the current display and historical conflict separately. This repository does **not** add those prize headlines together, infer why they differ, or turn either into a win/payment claim.

## Trust model

`flourish_relay.py` has five outcome states:

- `SUPPORTED` — at least one current, source-linked resource passes deterministic capacity, owner-fact, and budget gates. The only local authority is `RECOMMEND`.
- `OWNER_INPUT` — owner facts or a capacity confirmation are required before recommendation.
- `GAP` — no current resource satisfies the stated request.
- `STALE` — topical sources exist but are stale, expired, or future-dated.
- `HOLD` — recommendation consent is absent, sensitive context is declared, or an external action is requested.

The output packet intentionally does **not** echo values from `owner_fields`; it records only field names. The receipt still commits the complete input by SHA-256 so an exact replay can be verified without placing those values in the recommendation packet.

`provider_adapter.py` is a boundary, not an API client. Without independent provider evidence it returns `PROVIDER_EVIDENCE_REQUIRED`. Even verified provider evidence does not create CONTACT/SPEND/COMMIT/SCHEDULE/SHARE_SENSITIVE authority; it only creates a handoff that still requires external authority.

`pack.py` builds a deterministic source ZIP with fixed timestamps and a manifest, rejects symlinks/unsafe paths/duplicate members/extra files/content tampering, and re-derives hashes during verification.

## Run it locally

```bash
python - <<'PY'
import json, sys
from pathlib import Path
root = Path('competitions/gloo2026_flourish_relay')
sys.path.insert(0, str(root))
from flourish_relay import route
request = json.loads((root/'fixtures/request.example.json').read_text())
resources = json.loads((root/'fixtures/resources.example.json').read_text())
print(json.dumps(route(request, resources), indent=2, sort_keys=True))
PY

python -m unittest discover -s competitions/gloo2026_flourish_relay/tests -v
python -O -m unittest discover -s competitions/gloo2026_flourish_relay/tests -v
python competitions/gloo2026_flourish_relay/pack.py build competitions/gloo2026_flourish_relay /tmp/flourish-relay.zip
python competitions/gloo2026_flourish_relay/pack.py verify /tmp/flourish-relay.zip
```

## Authority ceiling

Checked-in state means **SOURCE_BUILT_OFFLINE** only. It is not evidence of Gloo registration, terms acceptance, credentials, provider execution, token spend, ministry/nonprofit contact, fundraising, commitment, scheduling, sensitive-data sharing, hackathon submission, leaderboard score/rank, prize, payment, or revenue. Those require separately proven provider/human events.
