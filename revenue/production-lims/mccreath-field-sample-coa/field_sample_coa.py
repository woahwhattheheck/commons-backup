#!/usr/bin/env python3
"""Synthetic McCreath field-sample-to-CoA reconciliation lane.

This module is intentionally dependency-free and performs no network, provider,
customer, production-LIMS, or regulatory writes. It consumes synthetic fixture
rows and builds an in-memory reconciliation ledger only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

READY = 'READY'
HOLD = 'HOLD'
STAGED_HUMAN_REVIEW = 'STAGED_HUMAN_REVIEW'
RELEASED = 'RELEASED'

HOLD_CUSTODY_WEIGHT = 'CUSTODY_WEIGHT_CONFLICT'
HOLD_DUPLICATE_CONTAINER = 'DUPLICATE_CONTAINER'
HOLD_FORM_PACKAGE = 'FORM_PACKAGE_MISMATCH'
HOLD_CONTRACT_SPEC = 'CONTRACT_SPEC_MISMATCH'

EXPECTED_HOLDS = {
    HOLD_CUSTODY_WEIGHT: 10,
    HOLD_DUPLICATE_CONTAINER: 5,
    HOLD_FORM_PACKAGE: 5,
    HOLD_CONTRACT_SPEC: 5,
}

METHOD_CYCLE = [
    {'analyte': 'Moisture', 'method': 'ASTM-D2216', 'method_version': 'ASTM-D2216-2026.09', 'unit': '%', 'rounding': 2},
    {'analyte': 'Ash', 'method': 'ASTM-D3174', 'method_version': 'ASTM-D3174-2026.09', 'unit': '%', 'rounding': 2},
    {'analyte': 'Protein', 'method': 'ISO-1871', 'method_version': 'ISO-1871-2026.09', 'unit': '%', 'rounding': 2},
    {'analyte': 'Sulfur', 'method': 'ASTM-D4239', 'method_version': 'ASTM-D4239-2026.09', 'unit': '%', 'rounding': 3},
    {'analyte': 'Calcium', 'method': 'ISO-11885', 'method_version': 'ISO-11885-2026.09', 'unit': 'mg/kg', 'rounding': 1},
]

RESERVED_REVIEWER_TOKENS = {
    'ai', 'agent', 'auto', 'automated', 'automation',
    'bot', 'robot', 'service', 'system',
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def sha256_hex(value: Any) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode('utf-8')
    else:
        payload = canonical_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def result_identity(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Return exactly the analytical fields whose identity must not drift."""
    return {
        'analyte': result['analyte'],
        'method': result['method'],
        'method_version': result['method_version'],
        'value': result['value'],
        'unit': result['unit'],
        'rounding': result['rounding'],
        'source_hash': result['source_hash'],
    }


def _public_outcome(stored: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in stored.items() if not key.startswith('_')}


def _reviewer_tokens(value: str) -> List[str]:
    return re.findall(r'[A-Za-z]+', value.casefold())


def _contains_segmented_reserved(tokens: List[str]) -> bool:
    run: List[str] = []
    for token in [*tokens, '__END__']:
        if len(token) == 1 and token.isalpha():
            run.append(token)
            continue
        if len(run) >= 2 and ''.join(run) in RESERVED_REVIEWER_TOKENS:
            return True
        run = []
    return False


def _named_human(value: Any) -> bool:
    """Label-level fail-closed guard. This is not identity authentication."""
    if not isinstance(value, str):
        return False
    tokens = _reviewer_tokens(value.strip())
    if len(tokens) < 2:
        return False
    if any(token in RESERVED_REVIEWER_TOKENS for token in tokens):
        return False
    if _contains_segmented_reserved(tokens):
        return False
    return True


@dataclass
class Ledger:
    """In-memory synthetic reconciliation ledger.

    `seen_job_outcomes` binds each first-seen job_id to a canonical full-job
    payload hash so only byte-equivalent canonical replays are idempotent.
    """

    accessions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    container_to_accession: Dict[str, str] = field(default_factory=dict)
    splits: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    coas: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    holds: Dict[str, str] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    seen_job_outcomes: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def _append_event(self, job_id: str, kind: str, payload: Mapping[str, Any]) -> None:
        ordinal = len(self.events) + 1
        event_core = {
            'ordinal': ordinal,
            'job_id': job_id,
            'kind': kind,
            'payload': dict(payload),
        }
        self.events.append({**event_core, 'event_hash': sha256_hex(event_core)})

    def mutation_counts(self) -> Dict[str, int]:
        return {
            'accessions': len(self.accessions),
            'splits': len(self.splits),
            'results': len(self.results),
            'coas': len(self.coas),
            'holds': len(self.holds),
            'events': len(self.events),
        }

    def snapshot_hash(self) -> str:
        payload = {
            'accessions': self.accessions,
            'container_to_accession': self.container_to_accession,
            'splits': self.splits,
            'results': self.results,
            'coas': self.coas,
            'holds': self.holds,
            'events': self.events,
            'seen_job_outcomes': self.seen_job_outcomes,
        }
        return sha256_hex(payload)


def _hold_reason(job: Mapping[str, Any], ledger: Ledger) -> Optional[str]:
    if not job['custody']['weight_matches_shipment']:
        return HOLD_CUSTODY_WEIGHT
    if job['container_id'] in ledger.container_to_accession:
        return HOLD_DUPLICATE_CONTAINER
    if not job['shipment']['form_matches_package']:
        return HOLD_FORM_PACKAGE
    if not job['contract']['spec_matches']:
        return HOLD_CONTRACT_SPEC
    return None


def process_job(job: Mapping[str, Any], ledger: Ledger) -> Dict[str, Any]:
    job_id = job['job_id']
    payload_sha256 = sha256_hex(job)

    if job_id in ledger.seen_job_outcomes:
        previous = ledger.seen_job_outcomes[job_id]
        if previous.get('_payload_sha256') != payload_sha256:
            raise ValueError(f'JOB_ID_PAYLOAD_MISMATCH: {job_id}')
        return {**_public_outcome(previous), 'idempotent_replay': True}

    hold_reason = _hold_reason(job, ledger)
    if hold_reason:
        outcome = {'job_id': job_id, 'status': HOLD, 'hold_code': hold_reason}
        ledger.holds[job_id] = hold_reason
        ledger.seen_job_outcomes[job_id] = {
            **outcome,
            '_payload_sha256': payload_sha256,
        }
        ledger._append_event(job_id, 'HOLD', {'hold_code': hold_reason})
        return {**outcome, 'idempotent_replay': False}

    accession_id = f'ACC-{job_id}'
    if accession_id in ledger.accessions:
        raise AssertionError(f'duplicate accession id: {accession_id}')
    container_id = job['container_id']
    if container_id in ledger.container_to_accession:
        raise AssertionError(f'container collision escaped validation: {container_id}')

    # Build and validate the entire per-job object graph before mutating ledger.
    accession = {
        'accession_id': accession_id,
        'job_id': job_id,
        'container_id': container_id,
        'field_event_hash': job['field_event']['source_hash'],
        'shipment_form_hash': job['shipment']['source_hash'],
        'custody_hash': job['custody']['source_hash'],
        'contract_hash': job['contract']['source_hash'],
    }
    split_id = f'SPLIT-{job_id}-A'
    split = {
        'split_id': split_id,
        'accession_id': accession_id,
        'preparation': job['preparation'],
        'source_hash': sha256_hex({
            'accession_id': accession_id,
            'preparation': job['preparation'],
            'container_id': container_id,
        }),
    }
    result_id = f'RESULT-{job_id}-A'
    result = {
        'result_id': result_id,
        'accession_id': accession_id,
        'split_id': split_id,
        **result_identity(job['analytical_result']),
    }
    observed_result_hash = sha256_hex(result_identity(result))
    if observed_result_hash != job['golden_result_hash']:
        raise AssertionError(
            f"golden result drift for {job_id}: "
            f"{observed_result_hash} != {job['golden_result_hash']}"
        )
    result['result_hash'] = observed_result_hash

    coa_id = f'COA-{job_id}'
    coa = {
        'coa_id': coa_id,
        'accession_id': accession_id,
        'result_id': result_id,
        'state': STAGED_HUMAN_REVIEW,
        'released_by': None,
        'approval_id': None,
        'source_result_hash': observed_result_hash,
    }

    # Commit only after all per-job validation succeeds.
    ledger.accessions[accession_id] = accession
    ledger.container_to_accession[container_id] = accession_id
    ledger._append_event(job_id, 'ACCESSION', accession)
    ledger.splits[split_id] = split
    ledger._append_event(job_id, 'PREPARATION_SPLIT', split)
    ledger.results[result_id] = result
    ledger._append_event(job_id, 'ANALYTICAL_RESULT', result)
    ledger.coas[coa_id] = coa
    ledger._append_event(job_id, 'COA_STAGED', coa)

    outcome = {'job_id': job_id, 'status': READY, 'hold_code': None}
    ledger.seen_job_outcomes[job_id] = {
        **outcome,
        '_payload_sha256': payload_sha256,
    }
    return {**outcome, 'idempotent_replay': False}


def process_fixture(
    rows: Iterable[Mapping[str, Any]],
    ledger: Optional[Ledger] = None,
) -> Dict[str, Any]:
    ledger = ledger or Ledger()
    before = ledger.mutation_counts()
    outcomes = [process_job(row, ledger) for row in rows]
    after = ledger.mutation_counts()
    delta = {key: after[key] - before[key] for key in after}
    statuses = Counter(o['status'] for o in outcomes)
    hold_codes = Counter(o['hold_code'] for o in outcomes if o['hold_code'])
    return {
        'ledger': ledger,
        'outcomes': outcomes,
        'status_counts': dict(statuses),
        'hold_counts': dict(hold_codes),
        'delta': delta,
        'idempotent_replays': sum(1 for o in outcomes if o['idempotent_replay']),
    }


def release_coa(
    ledger: Ledger,
    coa_id: str,
    *,
    reviewer: str,
    approval_id: str,
) -> Dict[str, Any]:
    if not _named_human(reviewer):
        raise PermissionError('named human reviewer is required')
    if not isinstance(approval_id, str) or not approval_id.strip():
        raise PermissionError('approval_id is required')

    reviewer = reviewer.strip()
    approval_id = approval_id.strip()
    coa = ledger.coas[coa_id]
    if coa['state'] != STAGED_HUMAN_REVIEW:
        raise ValueError(f'CoA {coa_id} is not staged')

    coa['state'] = RELEASED
    coa['released_by'] = reviewer
    coa['approval_id'] = approval_id
    ledger._append_event(
        coa['accession_id'].removeprefix('ACC-'),
        'COA_RELEASED',
        {'coa_id': coa_id, 'reviewer': reviewer, 'approval_id': approval_id},
    )
    return coa


def verify_contract(
    rows: List[Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> Dict[str, Any]:
    run = process_fixture(rows)
    ledger: Ledger = run['ledger']

    if len(rows) != 100:
        raise AssertionError(f'fixture rows: {len(rows)} != 100')
    if run['status_counts'] != {READY: 75, HOLD: 25}:
        raise AssertionError(f"status distribution mismatch: {run['status_counts']}")
    if run['hold_counts'] != EXPECTED_HOLDS:
        raise AssertionError(f"hold distribution mismatch: {run['hold_counts']}")
    if len(ledger.accessions) != 75 or len(set(ledger.accessions)) != 75:
        raise AssertionError('expected exactly 75 unique accessions')
    if len(ledger.splits) != 75:
        raise AssertionError('expected exactly 75 preparation splits')
    if any(split['accession_id'] not in ledger.accessions for split in ledger.splits.values()):
        raise AssertionError('orphan preparation split detected')
    if len(ledger.container_to_accession) != 75:
        raise AssertionError('expected exactly 75 unique accessioned containers')
    if len(ledger.results) != 75:
        raise AssertionError('expected exactly 75 analytical results')
    if len(ledger.coas) != 75:
        raise AssertionError('expected exactly 75 staged CoAs')
    if any(coa['state'] != STAGED_HUMAN_REVIEW for coa in ledger.coas.values()):
        raise AssertionError('CoA released without named approval')

    expected_result_hashes = {
        row['job_id']: row['golden_result_hash']
        for row in rows
        if row['expected_status'] == READY
    }
    observed_result_hashes = {
        result['accession_id'].removeprefix('ACC-'): result['result_hash']
        for result in ledger.results.values()
    }
    if expected_result_hashes != observed_result_hashes:
        raise AssertionError('result/value/unit/rounding/source hashes drifted')

    ready_digest = sha256_hex([
        expected_result_hashes[job_id]
        for job_id in sorted(expected_result_hashes)
    ])
    if manifest.get('golden_ready_result_digest_sha256') != ready_digest:
        raise AssertionError('manifest golden result digest mismatch')

    first_snapshot = ledger.snapshot_hash()
    before_replay = ledger.mutation_counts()
    replay = process_fixture(rows, ledger)
    after_replay = ledger.mutation_counts()

    if before_replay != after_replay:
        raise AssertionError(f'replay mutated ledger: {before_replay} -> {after_replay}')
    if replay['idempotent_replays'] != 100:
        raise AssertionError('expected 100/100 idempotent replay outcomes')
    if any(replay['delta'].values()):
        raise AssertionError(f"replay delta non-zero: {replay['delta']}")
    if ledger.snapshot_hash() != first_snapshot:
        raise AssertionError('replay changed ledger snapshot hash')

    expected_manifest = {
        'row_count': 100,
        'expected_status_counts': {READY: 75, HOLD: 25},
        'expected_hold_counts': EXPECTED_HOLDS,
    }
    for key, value in expected_manifest.items():
        if manifest.get(key) != value:
            raise AssertionError(f'manifest {key} mismatch: {manifest.get(key)} != {value}')

    return {
        'rows': len(rows),
        'ready': run['status_counts'].get(READY, 0),
        'hold': run['status_counts'].get(HOLD, 0),
        'hold_counts': run['hold_counts'],
        'accessions': len(ledger.accessions),
        'splits': len(ledger.splits),
        'results': len(ledger.results),
        'staged_coas': len(ledger.coas),
        'events': len(ledger.events),
        'replay_idempotent': replay['idempotent_replays'],
        'replay_delta': replay['delta'],
        'ledger_sha256': first_snapshot,
    }


def _expand_compact_job(item: Mapping[str, Any]) -> Dict[str, Any]:
    number = int(item['id'])
    scenario = str(item['scenario'])
    if scenario not in {READY, *EXPECTED_HOLDS}:
        raise ValueError(f'unknown fixture scenario: {scenario}')

    method = METHOD_CYCLE[(number - 1) % len(METHOD_CYCLE)]
    job_id = f'MCC-{number:04d}'
    container_number = number - 85 if scenario == HOLD_DUPLICATE_CONTAINER else number
    container_id = f'CONT-{container_number:04d}'
    weight = round(100.0 + number * 0.5, 1)
    weight_matches = scenario != HOLD_CUSTODY_WEIGHT
    declared_weight = weight if weight_matches else round(weight + 1.0, 1)
    form_matches = scenario != HOLD_FORM_PACKAGE
    spec_matches = scenario != HOLD_CONTRACT_SPEC
    value = round(10.0 + number * 0.137, int(method['rounding']))

    result = {
        'analyte': method['analyte'],
        'method': method['method'],
        'method_version': method['method_version'],
        'value': value,
        'unit': method['unit'],
        'rounding': method['rounding'],
        'source_hash': sha256_hex({
            'job_id': job_id,
            'source': 'analytical_result',
            'method': method['method'],
            'value': value,
            'unit': method['unit'],
        }),
    }
    expected_hold = None if scenario == READY else scenario

    return {
        'job_id': job_id,
        'container_id': container_id,
        'expected_status': READY if scenario == READY else HOLD,
        'expected_hold': expected_hold,
        'preparation': 'homogenize-and-split-synthetic',
        'field_event': {
            'inspection_id': f'INSP-{number:04d}',
            'sample_weight_g': weight,
            'source_hash': sha256_hex({'job_id': job_id, 'source': 'field_event'}),
        },
        'shipment': {
            'shipment_form_id': f'SHIP-{number:04d}',
            'package_id': f'PKG-{number:04d}',
            'declared_weight_g': declared_weight,
            'form_matches_package': form_matches,
            'source_hash': sha256_hex({'job_id': job_id, 'source': 'shipment'}),
        },
        'custody': {
            'chain_id': f'COC-{number:04d}',
            'weight_matches_shipment': weight_matches,
            'source_hash': sha256_hex({'job_id': job_id, 'source': 'custody'}),
        },
        'contract': {
            'contract_id': f'CTR-{(number - 1) // 20 + 1:03d}',
            'spec_id': f"SPEC-{method['method']}",
            'spec_matches': spec_matches,
            'source_hash': sha256_hex({'job_id': job_id, 'source': 'contract'}),
        },
        'analytical_result': result,
        'golden_result_hash': sha256_hex(result_identity(result)),
    }


def load_fixture(path: Path) -> List[Dict[str, Any]]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(value, list):
        return value
    if not isinstance(value, dict) or value.get('schema_version') != 3:
        raise ValueError('fixture must be a legacy JSON array or schema_version=3 object')
    jobs = value.get('jobs')
    if not isinstance(jobs, list):
        raise ValueError('compact fixture missing jobs')
    return [_expand_compact_job(item) for item in jobs]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args(argv)

    rows = load_fixture(args.fixture)
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    fixture_hash = file_sha256(args.fixture)
    if fixture_hash != manifest['fixture_sha256']:
        raise SystemExit(
            f"fixture hash mismatch: {fixture_hash} != {manifest['fixture_sha256']}"
        )

    if args.verify:
        print(json.dumps(verify_contract(rows, manifest), sort_keys=True))
    else:
        run = process_fixture(rows)
        print(json.dumps({
            'status_counts': run['status_counts'],
            'hold_counts': run['hold_counts'],
            'delta': run['delta'],
        }, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
