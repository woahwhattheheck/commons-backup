"""Compile normalized swarm opportunity evidence into Commons opportunity-portfolio input.

This module is deliberately offline and authority-reducing. It folds typed custody/status
observations into the already-landed ``revenue.opportunity_portfolio`` schema, then asks
that package to validate and compile the resulting portfolio. It never performs provider,
Slack, GitHub, payment, submission, or buyer mutations.

Snapshot completeness is not packet authority. Caller assertions remain in the normalized
packet for compatibility/audit, but absence-derived current state can be enabled only by a
separately supplied trusted snapshot authority that binds the exact source generation and
the canonical opportunity/event projection.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import os
import re
from typing import Any
from revenue.opportunity_portfolio.portfolio import PortfolioError, compile_portfolio, normalize_input as normalize_portfolio_input
INTAKE_SCHEMA = 'commons-opportunity-portfolio-intake/v1'
RECEIPT_SCHEMA = 'commons-opportunity-portfolio-intake-receipt/v2'
SNAPSHOT_AUTHORITY_SCHEMA = 'commons-opportunity-portfolio-intake-snapshot-authority/v1'
SNAPSHOT_AUTHORITY_KEY_ID = 'opportunity-intake-host-v1'
SNAPSHOT_AUTHORITY_KEY_ENV = 'OPPORTUNITY_INTAKE_SNAPSHOT_AUTHORITY_KEY_HEX'
MIN_SNAPSHOT_AUTHORITY_KEY_BYTES = 32
MAX_TRUSTED_SNAPSHOT_AGE_SECONDS = 300
PORTFOLIO_SCHEMA = 'commons-opportunity-portfolio/v1'
MAX_OPPORTUNITIES = 64
MAX_EVENTS_PER_OPPORTUNITY = 512
MAX_TEXT = 512
_ID = re.compile('^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$')
_SHA256 = re.compile('^[0-9a-f]{64}$')
_RESERVED_BLOCKERS = {'DNR', 'CLOSED', 'ALREADY-SHIPPED', 'CUSTODY-INCOMPLETE', 'STATUS-INCOMPLETE', 'OWNER-COLLISION', 'CUSTODY-HISTORY-CONFLICT', 'STATUS-HISTORY-CONFLICT'}
_EVENT_KINDS = {'TAKE', 'RELEASE', 'EXPIRE', 'BLOCKER_OPEN', 'BLOCKER_RESOLVED', 'DNR', 'BUYER_REOPEN', 'CLOSED', 'SHIPPED'}
_ORIGINS = {'BUYER', 'SOURCE_AUTHORITY', 'INTERNAL'}
_SECRET_PATTERNS = (re.compile('-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'), re.compile('\\bgh[pousr]_[A-Za-z0-9]{20,}\\b'), re.compile('\\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\\b'), re.compile('\\bxox[baprs]-[A-Za-z0-9-]{20,}\\b'), re.compile('\\bAKIA[0-9A-Z]{16}\\b'))

class IntakeError(ValueError):
    """Fail-closed intake or verification error."""

def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')

def _digest(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()

def _dict(value: Any, field: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise IntakeError(f'{field}: expected object')
    return value

def _list(value: Any, field: str) -> list[Any]:
    if type(value) is not list:
        raise IntakeError(f'{field}: expected array')
    return value

def _str(value: Any, field: str, *, pattern: re.Pattern[str] | None=None) -> str:
    if type(value) is not str or not value or len(value) > MAX_TEXT:
        raise IntakeError(f'{field}: expected non-empty bounded string')
    if pattern is not None and (not pattern.fullmatch(value)):
        raise IntakeError(f'{field}: invalid value')
    return value

def _bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise IntakeError(f'{field}: expected boolean')
    return value

def _int(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise IntakeError(f'{field}: expected non-negative integer')
    return value

def _parse_utc(value: Any, field: str) -> datetime:
    text = _str(value, field)
    if not text.endswith('Z'):
        raise IntakeError(f'{field}: must be UTC RFC3339 ending in Z')
    try:
        parsed = datetime.fromisoformat(text[:-1] + '+00:00')
    except ValueError as exc:
        raise IntakeError(f'{field}: invalid RFC3339 timestamp') from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise IntakeError(f'{field}: must be UTC')
    if parsed.microsecond:
        raise IntakeError(f'{field}: fractional seconds are not allowed')
    return parsed

def _fmt_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

def _scan_secret_shaped(value: Any, field: str='$') -> None:
    if type(value) is str:
        for pattern in _SECRET_PATTERNS:
            if pattern.search(value):
                raise IntakeError(f'{field}: secret-shaped material refused')
    elif type(value) is list:
        for index, item in enumerate(value):
            _scan_secret_shaped(item, f'{field}[{index}]')
    elif type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise IntakeError(f'{field}: object keys must be strings')
            _scan_secret_shaped(item, f'{field}.{key}')

def _source(value: Any, field: str) -> dict[str, str]:
    raw = _dict(value, field)
    if set(raw) != {'ref', 'digestSha256', 'observedAt'}:
        raise IntakeError(f'{field}: expected exactly ref,digestSha256,observedAt')
    ref = _str(raw['ref'], f'{field}.ref')
    digest = _str(raw['digestSha256'], f'{field}.digestSha256', pattern=_SHA256)
    observed = _parse_utc(raw['observedAt'], f'{field}.observedAt')
    return {'ref': ref, 'digestSha256': digest, 'observedAt': _fmt_utc(observed)}

def _normalize_event(value: Any, field: str) -> dict[str, Any]:
    raw = _dict(value, field)
    allowed = {'eventId', 'kind', 'source', 'actorSeat', 'code', 'origin'}
    unknown = set(raw) - allowed
    if unknown:
        raise IntakeError(f'{field}: unknown fields {sorted(unknown)}')
    event_id = _str(raw.get('eventId'), f'{field}.eventId', pattern=_ID)
    kind = _str(raw.get('kind'), f'{field}.kind')
    if kind not in _EVENT_KINDS:
        raise IntakeError(f'{field}.kind: invalid')
    source = _source(raw.get('source'), f'{field}.source')
    actor = raw.get('actorSeat')
    code = raw.get('code')
    origin = raw.get('origin')
    if kind in {'TAKE', 'RELEASE', 'EXPIRE'}:
        actor = _str(actor, f'{field}.actorSeat', pattern=_ID)
        if code is not None or origin is not None:
            raise IntakeError(f'{field}: {kind} cannot carry code/origin')
    elif kind in {'BLOCKER_OPEN', 'BLOCKER_RESOLVED'}:
        code = _str(code, f'{field}.code', pattern=_ID)
        if code in _RESERVED_BLOCKERS:
            raise IntakeError(f'{field}.code: reserved blocker {code}')
        if actor is not None or origin is not None:
            raise IntakeError(f'{field}: {kind} cannot carry actorSeat/origin')
    elif kind == 'DNR':
        origin = _str(origin, f'{field}.origin')
        if origin not in _ORIGINS:
            raise IntakeError(f'{field}.origin: invalid')
        if actor is not None or code is not None:
            raise IntakeError(f'{field}: DNR cannot carry actorSeat/code')
    elif kind == 'BUYER_REOPEN':
        if origin != 'BUYER':
            raise IntakeError(f'{field}.origin: BUYER_REOPEN requires BUYER')
        if actor is not None or code is not None:
            raise IntakeError(f'{field}: BUYER_REOPEN cannot carry actorSeat/code')
    elif actor is not None or code is not None or origin is not None:
        raise IntakeError(f'{field}: {kind} carries only eventId/kind/source')
    return {'eventId': event_id, 'kind': kind, 'source': source, 'actorSeat': actor, 'code': code, 'origin': origin}

def _normalize_opportunity(value: Any, index: int) -> dict[str, Any]:
    field = f'opportunities[{index}]'
    raw = _dict(value, field)
    if set(raw) != {'id', 'title', 'facts', 'events'}:
        raise IntakeError(f'{field}: expected exactly id,title,facts,events')
    oid = _str(raw['id'], f'{field}.id', pattern=_ID)
    title = _str(raw['title'], f'{field}.title')
    facts = _dict(raw['facts'], f'{field}.facts')
    allowed_facts = {'source', 'freshUntil', 'deadline', 'eligibility', 'value', 'capacity', 'blockers', 'dependsOn', 'exclusiveGroup', 'labels'}
    unknown_facts = set(facts) - allowed_facts
    missing = {'source', 'freshUntil', 'deadline', 'eligibility', 'value', 'capacity', 'blockers', 'dependsOn'} - set(facts)
    if unknown_facts or missing:
        raise IntakeError(f'{field}.facts: unknown={sorted(unknown_facts)} missing={sorted(missing)}')
    try:
        facts_copy = json.loads(_canonical(facts).decode('utf-8'))
    except (TypeError, ValueError) as exc:
        raise IntakeError(f'{field}.facts: not strict JSON') from exc
    facts_copy.setdefault('labels', [])
    facts_copy.setdefault('exclusiveGroup', None)
    events_raw = _list(raw['events'], f'{field}.events')
    if len(events_raw) > MAX_EVENTS_PER_OPPORTUNITY:
        raise IntakeError(f'{field}.events: too many events')
    normalized = [_normalize_event(event, f'{field}.events[{i}]') for i, event in enumerate(events_raw)]
    by_id: dict[str, dict[str, Any]] = {}
    for event in normalized:
        prior = by_id.get(event['eventId'])
        if prior is None:
            by_id[event['eventId']] = event
        elif _canonical(prior) != _canonical(event):
            raise IntakeError(f"{field}.events: changed payload reused eventId {event['eventId']}")
    events = sorted(by_id.values(), key=lambda e: (e['source']['observedAt'], e['eventId']))
    return {'id': oid, 'title': title, 'facts': facts_copy, 'events': events}

def normalize_intake(payload: Any) -> dict[str, Any]:
    _scan_secret_shaped(payload)
    root = _dict(payload, '$')
    allowed = {'schema', 'actorSeat', 'capacities', 'currencyPriority', 'snapshot', 'opportunities'}
    unknown = set(root) - allowed
    if unknown:
        raise IntakeError(f'$: unknown fields {sorted(unknown)}')
    if root.get('schema') != INTAKE_SCHEMA:
        raise IntakeError(f'schema: expected {INTAKE_SCHEMA}')
    actor_seat = _str(root.get('actorSeat'), 'actorSeat', pattern=_ID)
    snapshot_raw = _dict(root.get('snapshot'), 'snapshot')
    if set(snapshot_raw) != {'custodyComplete', 'statusComplete', 'source'}:
        raise IntakeError('snapshot: expected exactly custodyComplete,statusComplete,source')
    snapshot = {'custodyComplete': _bool(snapshot_raw['custodyComplete'], 'snapshot.custodyComplete'), 'statusComplete': _bool(snapshot_raw['statusComplete'], 'snapshot.statusComplete'), 'source': _source(snapshot_raw['source'], 'snapshot.source')}
    capacities = _dict(root.get('capacities'), 'capacities')
    currency_priority = _list(root.get('currencyPriority', []), 'currencyPriority')
    opportunities_raw = _list(root.get('opportunities'), 'opportunities')
    if not 1 <= len(opportunities_raw) <= MAX_OPPORTUNITIES:
        raise IntakeError(f'opportunities: expected 1..{MAX_OPPORTUNITIES}')
    opportunities = [_normalize_opportunity(item, i) for i, item in enumerate(opportunities_raw)]
    ids = [item['id'] for item in opportunities]
    if len(set(ids)) != len(ids):
        raise IntakeError('opportunities: duplicate id')
    try:
        capacities_copy = json.loads(_canonical(capacities).decode('utf-8'))
        priority_copy = json.loads(_canonical(currency_priority).decode('utf-8'))
    except (TypeError, ValueError) as exc:
        raise IntakeError('capacities/currencyPriority: not strict JSON') from exc
    return {'schema': INTAKE_SCHEMA, 'actorSeat': actor_seat, 'capacities': capacities_copy, 'currencyPriority': priority_copy, 'snapshot': snapshot, 'opportunities': sorted(opportunities, key=lambda item: item['id'])}

def _snapshot_projection(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    """Canonical identity of exactly the opportunity/event set covered by completeness."""
    return [{'id': item['id'], 'events': item['events']} for item in normalized['opportunities']]

def _snapshot_projection_sha256(normalized: dict[str, Any]) -> str:
    return _digest(_snapshot_projection(normalized))

def _load_snapshot_authority_key() -> bytes:
    raw = os.environ.get(SNAPSHOT_AUTHORITY_KEY_ENV)
    if raw is None:
        raise IntakeError('host snapshot authority capability is not provisioned')
    if type(raw) is not str or len(raw) % 2:
        raise IntakeError('host snapshot authority capability must be canonical lowercase hex')
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise IntakeError('host snapshot authority capability must be canonical lowercase hex') from exc
    if raw != raw.lower() or key.hex() != raw:
        raise IntakeError('host snapshot authority capability must be canonical lowercase hex')
    if len(key) < MIN_SNAPSHOT_AUTHORITY_KEY_BYTES:
        raise IntakeError(f'host snapshot authority capability must be at least {MIN_SNAPSHOT_AUTHORITY_KEY_BYTES} bytes')
    return key

def _snapshot_authority_payload(authority: dict[str, Any]) -> dict[str, Any]:
    return {key: authority[key] for key in (
        'schema', 'authorityId', 'generation', 'keyId', 'issuedAtUtc', 'actorSeat',
        'snapshotSource', 'eventProjectionSha256', 'opportunityCount',
        'eventCount', 'custodyComplete', 'statusComplete',
    )}

def _normalize_snapshot_authority(value: Any) -> dict[str, Any]:
    raw = _dict(value, 'trusted_snapshot_authority')
    expected = {'schema', 'authorityId', 'generation', 'keyId', 'issuedAtUtc', 'actorSeat', 'snapshotSource', 'eventProjectionSha256', 'opportunityCount', 'eventCount', 'custodyComplete', 'statusComplete', 'macSha256'}
    if set(raw) != expected:
        raise IntakeError('trusted_snapshot_authority: fields differ from authority contract')
    if raw['schema'] != SNAPSHOT_AUTHORITY_SCHEMA:
        raise IntakeError(f'trusted_snapshot_authority.schema: expected {SNAPSHOT_AUTHORITY_SCHEMA}')
    authority_id = _str(raw['authorityId'], 'trusted_snapshot_authority.authorityId', pattern=_ID)
    generation = _str(raw['generation'], 'trusted_snapshot_authority.generation', pattern=_ID)
    key_id = _str(raw['keyId'], 'trusted_snapshot_authority.keyId', pattern=_ID)
    if key_id != SNAPSHOT_AUTHORITY_KEY_ID:
        raise IntakeError('trusted_snapshot_authority.keyId: untrusted key id')
    issued = _fmt_utc(_parse_utc(raw['issuedAtUtc'], 'trusted_snapshot_authority.issuedAtUtc'))
    actor_seat = _str(raw['actorSeat'], 'trusted_snapshot_authority.actorSeat', pattern=_ID)
    source = _source(raw['snapshotSource'], 'trusted_snapshot_authority.snapshotSource')
    projection = _str(raw['eventProjectionSha256'], 'trusted_snapshot_authority.eventProjectionSha256', pattern=_SHA256)
    mac = _str(raw['macSha256'], 'trusted_snapshot_authority.macSha256', pattern=_SHA256)
    return {'schema': SNAPSHOT_AUTHORITY_SCHEMA, 'authorityId': authority_id, 'generation': generation, 'keyId': key_id, 'issuedAtUtc': issued, 'actorSeat': actor_seat, 'snapshotSource': source, 'eventProjectionSha256': projection, 'opportunityCount': _int(raw['opportunityCount'], 'trusted_snapshot_authority.opportunityCount'), 'eventCount': _int(raw['eventCount'], 'trusted_snapshot_authority.eventCount'), 'custodyComplete': _bool(raw['custodyComplete'], 'trusted_snapshot_authority.custodyComplete'), 'statusComplete': _bool(raw['statusComplete'], 'trusted_snapshot_authority.statusComplete'), 'macSha256': mac}

def _verify_snapshot_authority_capability(authority: dict[str, Any]) -> None:
    key = _load_snapshot_authority_key()
    expected = hmac.new(key, _canonical(_snapshot_authority_payload(authority)), sha256).hexdigest()
    if not hmac.compare_digest(authority['macSha256'], expected):
        raise IntakeError('trusted snapshot authority MAC does not match host capability')

def issue_host_snapshot_authority(
    payload: Any, *, authority_id: str, generation: str, issued_at_utc: str
) -> dict[str, Any]:
    """Mint one snapshot authority inside a protected host process.

    The HMAC capability is loaded only from process configuration and is never
    accepted from packet bytes, authority bytes, function arguments, or CLI.
    Calling code must independently establish that the snapshot is complete;
    this helper authenticates that host attestation, it does not discover truth.
    """
    normalized = normalize_intake(payload)
    authority_id = _str(authority_id, 'authority_id', pattern=_ID)
    generation = _str(generation, 'generation', pattern=_ID)
    issued = _parse_utc(issued_at_utc, 'issued_at_utc')
    snapshot_at = _parse_utc(normalized['snapshot']['source']['observedAt'], 'snapshot.source.observedAt')
    if issued < snapshot_at:
        raise IntakeError('snapshot authority cannot predate its snapshot generation')
    if issued > datetime.now(timezone.utc).replace(microsecond=0):
        raise IntakeError('snapshot authority issued_at cannot be in the future')
    body = {
        'schema': SNAPSHOT_AUTHORITY_SCHEMA,
        'authorityId': authority_id,
        'generation': generation,
        'keyId': SNAPSHOT_AUTHORITY_KEY_ID,
        'issuedAtUtc': _fmt_utc(issued),
        'actorSeat': normalized['actorSeat'],
        'snapshotSource': normalized['snapshot']['source'],
        'eventProjectionSha256': _snapshot_projection_sha256(normalized),
        'opportunityCount': len(normalized['opportunities']),
        'eventCount': sum(len(item['events']) for item in normalized['opportunities']),
        'custodyComplete': normalized['snapshot']['custodyComplete'],
        'statusComplete': normalized['snapshot']['statusComplete'],
    }
    key = _load_snapshot_authority_key()
    mac = hmac.new(key, _canonical(body), sha256).hexdigest()
    return {**body, 'macSha256': mac}

def _resolve_snapshot_authority(normalized: dict[str, Any], trusted_snapshot_authority: Any | None, *, trusted_as_of: datetime) -> tuple[bool, bool, dict[str, Any]]:
    projection_sha = _snapshot_projection_sha256(normalized)
    event_count = sum((len(item['events']) for item in normalized['opportunities']))
    if trusted_snapshot_authority is None:
        return (False, False, {'trusted': False, 'authorityId': None, 'generation': None, 'keyId': None, 'issuedAtUtc': None, 'authorityDigestSha256': None, 'eventProjectionSha256': projection_sha, 'effectiveCustodyComplete': False, 'effectiveStatusComplete': False})
    authority = _normalize_snapshot_authority(trusted_snapshot_authority)
    _verify_snapshot_authority_capability(authority)
    issued = _parse_utc(authority['issuedAtUtc'], 'trusted_snapshot_authority.issuedAtUtc')
    snapshot_at = _parse_utc(authority['snapshotSource']['observedAt'], 'trusted_snapshot_authority.snapshotSource.observedAt')
    if authority['actorSeat'] != normalized['actorSeat']:
        raise IntakeError('trusted snapshot authority actorSeat does not match packet actorSeat')
    if issued < snapshot_at:
        raise IntakeError('trusted snapshot authority predates its snapshot generation')
    if issued > trusted_as_of:
        raise IntakeError('trusted snapshot authority is newer than trusted_as_of')
    snapshot_age_seconds = int((trusted_as_of - snapshot_at).total_seconds())
    if snapshot_age_seconds > MAX_TRUSTED_SNAPSHOT_AGE_SECONDS:
        raise IntakeError(f'trusted snapshot is older than {MAX_TRUSTED_SNAPSHOT_AGE_SECONDS} seconds')
    if _canonical(authority['snapshotSource']) != _canonical(normalized['snapshot']['source']):
        raise IntakeError('trusted snapshot authority source does not match packet snapshot generation')
    if authority['eventProjectionSha256'] != projection_sha:
        raise IntakeError('trusted snapshot authority event projection does not match packet')
    if authority['opportunityCount'] != len(normalized['opportunities']):
        raise IntakeError('trusted snapshot authority opportunity count does not match packet')
    if authority['eventCount'] != event_count:
        raise IntakeError('trusted snapshot authority event count does not match packet')
    if authority['custodyComplete'] != normalized['snapshot']['custodyComplete']:
        raise IntakeError('packet custodyComplete disagrees with trusted snapshot authority')
    if authority['statusComplete'] != normalized['snapshot']['statusComplete']:
        raise IntakeError('packet statusComplete disagrees with trusted snapshot authority')
    return (authority['custodyComplete'], authority['statusComplete'], {'trusted': True, 'authorityId': authority['authorityId'], 'generation': authority['generation'], 'keyId': authority['keyId'], 'issuedAtUtc': authority['issuedAtUtc'], 'actorSeat': authority['actorSeat'], 'authorityDigestSha256': _digest(authority), 'eventProjectionSha256': projection_sha, 'effectiveCustodyComplete': authority['custodyComplete'], 'effectiveStatusComplete': authority['statusComplete']})

def _evidence_digest(event: dict[str, Any]) -> str:
    return event['source']['digestSha256']

def _set_blocker(blockers: dict[str, dict[str, str]], code: str, status: str, evidence: str) -> None:
    blockers[code] = {'code': code, 'status': status, 'evidenceSha256': evidence}

def _fold_one(item: dict[str, Any], *, actor_seat: str, custody_complete: bool, status_complete: bool, snapshot_at: datetime, snapshot_digest: str, trusted_as_of: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    active: set[str] = set()
    custody_conflict = False
    status_conflict = False
    static = _list(item['facts'].get('blockers'), f"{item['id']}.facts.blockers")
    blockers: dict[str, dict[str, str]] = {}
    for index, raw in enumerate(static):
        b = _dict(raw, f"{item['id']}.facts.blockers[{index}]")
        if set(b) != {'code', 'status', 'evidenceSha256'}:
            raise IntakeError(f"{item['id']}.facts.blockers[{index}]: invalid blocker shape")
        code = _str(b['code'], f"{item['id']}.facts.blockers[{index}].code", pattern=_ID)
        status = _str(b['status'], f"{item['id']}.facts.blockers[{index}].status")
        if status not in {'OPEN', 'RESOLVED'}:
            raise IntakeError(f"{item['id']}.facts.blockers[{index}].status: invalid")
        evidence = _str(b['evidenceSha256'], f"{item['id']}.facts.blockers[{index}].evidenceSha256", pattern=_SHA256)
        if code in blockers:
            raise IntakeError(f"{item['id']}.facts.blockers: duplicate code {code}")
        blockers[code] = {'code': code, 'status': status, 'evidenceSha256': evidence}
    same_time: dict[str, list[dict[str, Any]]] = {}
    for event in item['events']:
        same_time.setdefault(event['source']['observedAt'], []).append(event)
    for group in same_time.values():
        custody_by_actor: dict[str, set[str]] = {}
        status_by_code: dict[str, set[str]] = {}
        reserved_kinds: set[str] = set()
        for event in group:
            kind = event['kind']
            if kind in {'TAKE', 'RELEASE', 'EXPIRE'}:
                custody_by_actor.setdefault(event['actorSeat'], set()).add(kind)
            elif kind in {'BLOCKER_OPEN', 'BLOCKER_RESOLVED'}:
                status_by_code.setdefault(event['code'], set()).add(kind)
            elif kind in {'DNR', 'BUYER_REOPEN'}:
                reserved_kinds.add(kind)
        if any(('TAKE' in kinds and kinds.intersection({'RELEASE', 'EXPIRE'}) for kinds in custody_by_actor.values())):
            custody_conflict = True
        if any(({'BLOCKER_OPEN', 'BLOCKER_RESOLVED'}.issubset(kinds) for kinds in status_by_code.values())):
            status_conflict = True
        if {'DNR', 'BUYER_REOPEN'}.issubset(reserved_kinds):
            status_conflict = True
    event_ids: list[str] = []
    for event in item['events']:
        event_ids.append(event['eventId'])
        event_at = _parse_utc(event['source']['observedAt'], f"event {event['eventId']}.observedAt")
        if event_at > snapshot_at:
            raise IntakeError(f"event {event['eventId']}: newer than snapshot boundary")
        if event_at > trusted_as_of:
            raise IntakeError(f"event {event['eventId']}: future relative to trusted_as_of")
        kind = event['kind']
        evidence = _evidence_digest(event)
        if kind == 'TAKE':
            active.add(event['actorSeat'])
        elif kind in {'RELEASE', 'EXPIRE'}:
            if event['actorSeat'] not in active:
                custody_conflict = True
            else:
                active.remove(event['actorSeat'])
        elif kind == 'BLOCKER_OPEN':
            _set_blocker(blockers, event['code'], 'OPEN', evidence)
        elif kind == 'BLOCKER_RESOLVED':
            if event['code'] not in blockers:
                status_conflict = True
            else:
                _set_blocker(blockers, event['code'], 'RESOLVED', evidence)
        elif kind == 'DNR':
            _set_blocker(blockers, 'DNR', 'OPEN', evidence)
        elif kind == 'BUYER_REOPEN':
            current = blockers.get('DNR')
            if current is None or current['status'] != 'OPEN':
                status_conflict = True
            else:
                _set_blocker(blockers, 'DNR', 'RESOLVED', evidence)
        elif kind == 'CLOSED':
            _set_blocker(blockers, 'CLOSED', 'OPEN', evidence)
        elif kind == 'SHIPPED':
            _set_blocker(blockers, 'ALREADY-SHIPPED', 'OPEN', evidence)
    snapshot_evidence = _str(snapshot_digest, 'snapshot.source.digestSha256', pattern=_SHA256)
    if not custody_complete:
        _set_blocker(blockers, 'CUSTODY-INCOMPLETE', 'OPEN', snapshot_evidence)
    if not status_complete:
        _set_blocker(blockers, 'STATUS-INCOMPLETE', 'OPEN', snapshot_evidence)
    if custody_conflict:
        _set_blocker(blockers, 'CUSTODY-HISTORY-CONFLICT', 'OPEN', snapshot_evidence)
    if status_conflict:
        _set_blocker(blockers, 'STATUS-HISTORY-CONFLICT', 'OPEN', snapshot_evidence)
    if not custody_complete or custody_conflict:
        owner = {'status': 'UNKNOWN', 'seat': None}
    elif len(active) == 0:
        owner = {'status': 'AVAILABLE', 'seat': None}
    elif len(active) == 1:
        seat = next(iter(active))
        owner = {'status': 'OWNED_BY_THIS_SEAT' if seat == actor_seat else 'OWNED_BY_OTHER', 'seat': seat}
    else:
        owner = {'status': 'UNKNOWN', 'seat': None}
        _set_blocker(blockers, 'OWNER-COLLISION', 'OPEN', snapshot_evidence)
    facts = item['facts']
    portfolio_item = {'id': item['id'], 'title': item['title'], 'source': facts['source'], 'freshUntil': facts['freshUntil'], 'deadline': facts['deadline'], 'eligibility': facts['eligibility'], 'value': facts['value'], 'capacity': facts['capacity'], 'owner': owner, 'blockers': sorted(blockers.values(), key=lambda b: b['code']), 'dependsOn': facts['dependsOn'], 'exclusiveGroup': facts.get('exclusiveGroup'), 'labels': facts.get('labels', [])}
    fold = {'id': item['id'], 'eventIds': event_ids, 'eventSetSha256': _digest(item['events']), 'activeOwners': sorted(active), 'derivedOwner': owner, 'openBlockers': sorted((code for code, b in blockers.items() if b['status'] == 'OPEN')), 'custodyHistoryConflict': custody_conflict, 'statusHistoryConflict': status_conflict}
    return (portfolio_item, fold)

def _compile_normalized(normalized: dict[str, Any], trusted_as_of_text: str, trusted_snapshot_authority: Any | None) -> dict[str, Any]:
    trusted_as_of = _parse_utc(trusted_as_of_text, 'trusted_as_of')
    snapshot_at = _parse_utc(normalized['snapshot']['source']['observedAt'], 'snapshot.source.observedAt')
    if snapshot_at > trusted_as_of:
        raise IntakeError('snapshot.source.observedAt: future relative to trusted_as_of')
    custody_complete, status_complete, authority_binding = _resolve_snapshot_authority(normalized, trusted_snapshot_authority, trusted_as_of=trusted_as_of)
    portfolio_items: list[dict[str, Any]] = []
    folds: list[dict[str, Any]] = []
    for item in normalized['opportunities']:
        portfolio_item, fold = _fold_one(item, actor_seat=normalized['actorSeat'], custody_complete=custody_complete, status_complete=status_complete, snapshot_at=snapshot_at, snapshot_digest=normalized['snapshot']['source']['digestSha256'], trusted_as_of=trusted_as_of)
        portfolio_items.append(portfolio_item)
        folds.append(fold)
    raw_portfolio = {'schema': PORTFOLIO_SCHEMA, 'actorSeat': normalized['actorSeat'], 'capacities': normalized['capacities'], 'currencyPriority': normalized['currencyPriority'], 'opportunities': portfolio_items}
    try:
        portfolio_input = normalize_portfolio_input(raw_portfolio)
        allocator_receipt = compile_portfolio(portfolio_input, trusted_as_of=trusted_as_of_text)
    except PortfolioError as exc:
        raise IntakeError(f'downstream opportunity_portfolio rejected intake: {exc}') from exc
    body = {'schema': RECEIPT_SCHEMA, 'trustedAsOf': _fmt_utc(trusted_as_of), 'normalizedIntake': normalized, 'normalizedIntakeSha256': _digest(normalized), 'snapshotAuthority': authority_binding, 'portfolioInput': portfolio_input, 'portfolioInputSha256': _digest(portfolio_input), 'allocatorReceiptDigestSha256': allocator_receipt['receiptDigestSha256'], 'folds': sorted(folds, key=lambda fold: fold['id']), 'authority': {'contactAuthorized': False, 'sendAuthorized': False, 'submissionAuthorized': False, 'mergeAuthorized': False, 'spendAuthorized': False, 'paymentMutationAuthorized': False, 'buyerAcceptanceEstablished': False, 'revenueRecognitionAuthorized': False}}
    return {**body, 'receiptDigestSha256': _digest(body)}

def compile_intake(payload: Any, *, trusted_as_of: str, trusted_snapshot_authority: Any | None=None) -> dict[str, Any]:
    """Normalize/fold intake evidence and validate it through the real allocator.

    ``trusted_snapshot_authority`` is a host-authenticated attestation, not merely
    a second caller mapping. Its HMAC must verify under a capability loaded only
    from trusted process configuration. The public CLI exposes neither the
    authority nor the capability. Without authenticated authority, packet
    completeness assertions are ignored and the result fails closed.
    """
    return _compile_normalized(normalize_intake(payload), trusted_as_of, trusted_snapshot_authority)

def verify_receipt(receipt: Any, *, trusted_snapshot_authority: Any | None=None) -> dict[str, Any]:
    """Verify a receipt by full recompilation and, when needed, external authority."""
    raw = _dict(receipt, 'receipt')
    if raw.get('schema') != RECEIPT_SCHEMA:
        raise IntakeError(f'receipt.schema: expected {RECEIPT_SCHEMA}')
    expected = raw.get('receiptDigestSha256')
    _str(expected, 'receipt.receiptDigestSha256', pattern=_SHA256)
    body = {key: value for key, value in raw.items() if key != 'receiptDigestSha256'}
    if _digest(body) != expected:
        raise IntakeError('receipt: digest mismatch')
    binding = _dict(raw.get('snapshotAuthority'), 'receipt.snapshotAuthority')
    trusted = _bool(binding.get('trusted'), 'receipt.snapshotAuthority.trusted')
    if trusted:
        if trusted_snapshot_authority is None:
            raise IntakeError('receipt: trusted snapshot authority required for verification')
        normalized_authority = _normalize_snapshot_authority(trusted_snapshot_authority)
        authority_digest = _digest(normalized_authority)
        if authority_digest != binding.get('authorityDigestSha256'):
            raise IntakeError('receipt: trusted snapshot authority digest mismatch')
    elif trusted_snapshot_authority is not None:
        raise IntakeError('receipt: unexpected trusted snapshot authority for untrusted snapshot')
    rebuilt = compile_intake(raw.get('normalizedIntake'), trusted_as_of=raw.get('trustedAsOf'), trusted_snapshot_authority=trusted_snapshot_authority)
    if _canonical(rebuilt) != _canonical(raw):
        raise IntakeError('receipt: deterministic recompilation mismatch')
    if raw.get('authority') != {'contactAuthorized': False, 'sendAuthorized': False, 'submissionAuthorized': False, 'mergeAuthorized': False, 'spendAuthorized': False, 'paymentMutationAuthorized': False, 'buyerAcceptanceEstablished': False, 'revenueRecognitionAuthorized': False}:
        raise IntakeError('receipt: authority ceiling mismatch')
    return raw
