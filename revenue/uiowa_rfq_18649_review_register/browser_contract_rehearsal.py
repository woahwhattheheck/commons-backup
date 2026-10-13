#!/usr/bin/env python3
"""Real parent compiler -> real browser export -> offline review intake rehearsal.

Uses fictional evidence only. A91C-N3 continues the retained A91C rehearsal and
consumes PR #16290's separate native_handoff adapter without replacing its core. The actual workbench HTML/JS are loaded into an
offline page without external asset requests; installReport receives an actually
compiled report. The production HTTP inspection adapter is not exercised. Playwright/Chromium are test-only dependencies.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any

import review_register as register
import native_handoff as native

PARENT_FILES = (
    'workshare_constants.py', 'workshare_core.py', 'workshare_candidate.py',
    'workshare_authority.py', 'workshare_contract.py', 'workshare_assessment.py',
    'workshare_compile.py', 'workshare_verify.py',
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def write_json(path: Path, value: Any) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def file_receipt(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'git_blob': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()}


def parent_modules(parent: Path):
    sys.path.insert(0, str(parent))
    for filename in PARENT_FILES:
        require((parent / filename).is_file(), 'missing actual parent file: ' + filename)
    compile_module = importlib.import_module('workshare_compile')
    verify_module = importlib.import_module('workshare_verify')
    constants = importlib.import_module('workshare_constants')
    for filename in PARENT_FILES:
        module = sys.modules[filename[:-3]]
        require(Path(module.__file__).resolve() == (parent / filename).resolve(),
                'wrong parent module loaded: ' + filename)
    return compile_module, verify_module, constants


def synthetic_packet(constants, output: Path):
    """Fictional records demonstrate consistent, missing, stale, and conflict states."""
    generation, prime = 'synthetic-quartz-a91c-v1', 'Fictional prime rehearsal'
    evidence_dir = output / 'fictional-evidence'
    evidence_dir.mkdir()
    sources = []
    for group in constants.GROUPS:
        for dimension in constants.DIMENSIONS:
            if (group, dimension) == ('IAM', 'ai_readiness'):
                continue
            sid = f'fictional-{group}-{dimension}'
            text = f'FICTIONAL ONLY. {group} / {dimension}. Rehearsal process record.\n'
            (evidence_dir / (sid + '.txt')).write_text(text, encoding='utf-8')
            sources.append({
                'source_id': sid, 'authority_generation': generation,
                'solicitation_id': constants.SOLICITATION_ID, 'prime_candidate': prime,
                'group': group, 'dimension': dimension, 'evidence_kind': 'artifact',
                'source_ref': f'fictional-evidence/{sid}.txt:line-1',
                'source_content_sha256': hashlib.sha256(text.encode()).hexdigest(),
                'observed_at': '2026-01-01T00:00:00Z' if (group, dimension) == ('RIS', 'deployment') else '2026-09-18T00:00:00Z',
                'claim': text.strip(), 'maturity': 2, 'confidence_bp': 7000,
            })
    conflict = deepcopy(next(row for row in sources if (row['group'], row['dimension']) == ('ESS', 'security')))
    conflict['source_id'] += '-different-account'
    conflict['maturity'] = 1
    conflict['evidence_kind'] = 'interview'
    text = 'FICTIONAL ONLY. A different account for the ESS security rehearsal.\n'
    conflict['claim'] = text.strip()
    conflict['source_ref'] = f"fictional-evidence/{conflict['source_id']}.txt:line-1"
    conflict['source_content_sha256'] = hashlib.sha256(text.encode()).hexdigest()
    (evidence_dir / (conflict['source_id'] + '.txt')).write_text(text, encoding='utf-8')
    sources.append(conflict)
    authority = {'schema': constants.AUTHORITY_SCHEMA, 'generation': generation,
                 'solicitation_id': constants.SOLICITATION_ID,
                 'prime_candidate': prime, 'sources': sources}
    candidate = {'schema': constants.CANDIDATE_SCHEMA, 'authority_generation': generation,
                 'engagement': {'solicitation_id': constants.SOLICITATION_ID,
                                'buyer': constants.BUYER, 'prime_candidate': prime,
                                'subcontractor': constants.SUBCONTRACTOR,
                                'base_fee_usd': constants.BASE_FEE_USD,
                                'optional_readout_usd': constants.OPTIONAL_READOUT_USD},
                 'source_ids': [s['source_id'] for s in sources]}
    return candidate, authority


def run(source_root: Path, output: Path, chromium: str) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    parent = source_root / 'revenue' / 'uiowa_rfq_18649_workshare'
    workbench = source_root / 'revenue' / 'uiowa_rfq_18649_workbench'
    output.mkdir(parents=False, exist_ok=False)
    compiled, verified, constants = parent_modules(parent)
    candidate, authority = synthetic_packet(constants, output)
    report = compiled.compile_untrusted_inspection(candidate, authority, now='2026-09-19T13:00:00Z')
    parent_verification = verified.verify_report_integrity(report)
    require(parent_verification['semantic_recompile_valid'] is True, 'parent semantics not verified')
    require(report['status_counts'] == {'HOLD_CONFLICT': 1, 'HOLD_MISSING_EVIDENCE': 1,
            'HOLD_STALE_EVIDENCE': 1, 'UNTRUSTED_EVIDENCE_CONSISTENT': 9}, 'synthetic state counts changed')
    require(all(c['maturity'] is None and c['confidence_bp'] is None for c in report['assessment_matrix']),
            'inspection unexpectedly has maturity/confidence values')
    source_before = register.canonical(report)
    write_json(output / 'candidate.json', candidate)
    write_json(output / 'authority.json', authority)
    write_json(output / 'compiler-report.json', report)
    write_json(output / 'parent-verification.json', parent_verification)
    snapshots = {f'workshare/{n}': file_receipt(parent / n) for n in PARENT_FILES}
    snapshots.update({f'workbench/{n}': file_receipt(workbench / n) for n in ('app.js', 'index.html')})

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium, headless=True,
                                   args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(accept_downloads=True, offline=True)
        page = context.new_page()
        browser_errors = []
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        page.set_default_timeout(6000)
        # Preserve DOM and actual script bytes while removing network loading.
        markup = (workbench / 'index.html').read_text(encoding='utf-8')
        markup = markup.replace('<link rel="stylesheet" href="/style.css">', '')
        markup = markup.replace('<script src="/app.js" defer></script>', '')
        page.set_content(markup)
        page.add_script_tag(content=(workbench / 'app.js').read_text(encoding='utf-8'))
        page.evaluate('(report) => installReport(report)', report)
        require(page.locator('#matrix button').count() == 12, 'native matrix is not twelve cells')
        for index, c in enumerate(report['assessment_matrix']):
            selector = '#matrix button[data-key="' + c['group'] + '|' + c['dimension'] + '"]'
            page.locator(selector).click()
            page.locator('#note').fill(f"Fictional reviewer note {index + 1}: {c['group']} / {c['dimension']} — résumé\nFollow up; no University conclusion.")
            page.locator('#disposition').select_option('NEEDS_EVIDENCE' if c['status'].startswith('HOLD_') else 'TECHNICAL_DRAFT_NOTE')
        page.locator('#search').fill('software')
        require(page.locator('#matrix button').count() == 3, 'native software search is not three cells')
        with page.expect_download() as downloading:
            page.locator('#exportBtn').click()
        download = downloading.value
        download.save_as(output / 'native-browser-handoff.json')
        handoff = json.loads((output / 'native-browser-handoff.json').read_text())
        require(len(handoff['cell_notes']) == 12, 'filter changed export coverage')
        require(handoff['synthetic_demo'] is False, 'real compiler was relabeled as UI-only demo')
        require(handoff['report_receipt_sha256'] == report['receipt_sha256'], 'browser receipt changed')
        before_intake = register.canonical(handoff)
        try:
            intake = native.convert(handoff, 'Fictional browser reviewer')
            native.verify(handoff, 'Fictional browser reviewer', intake)
        except register.ValidationError as exc:
            write_json(output / 'intake-failure.json', {'status': 'FAIL', 'stage': 'actual native browser export -> intake', 'diagnosis': str(exc)})
            raise
        require(len(intake['comments']) == 12, 'notes disappeared during intake')
        expected_cells = {(r['group'], r['dimension']): r for r in handoff['cell_notes']}
        for c in intake['comments']:
            row = expected_cells[(c['cell']['group'], c['cell']['dimension'])]
            require(c['analyst_note'] == row['analyst_note'], 'note changed')
            require(c['compiler_status'] == row['compiler_status'], 'compiler status changed')
            require(c['finding_id'] is None and c['kind'] is None, 'intake invented a finding')
        require(intake['authority'] == register.AUTHORITY, 'intake has authority')
        require(register.canonical(handoff) == before_intake, 'original handoff mutated')
        write_json(output / 'native-intake.json', intake)
        results.append({'case': 'native_compiler_browser_intake', 'cell_notes': 12, 'intake_comments': 12, 'result': 'PASS'})

        require(intake['source_handoff'] == handoff, 'source handoff envelope lost')
        for item in intake['comments']:
            expected = 'software_development' if item['cell']['dimension'] == 'software' else item['cell']['dimension']
            require(item['register_cell'] == {'group': item['cell']['group'], 'dimension': expected}, 'incorrect register alias')
        # A resealed output is not enough: compare it with the source handoff.
        forged = deepcopy(intake)
        forged['comments'][0]['analyst_note'] = 'Fictional unsupported replacement'
        forged.pop('receipt_sha256')
        forged['receipt_sha256'] = register.sha(forged)
        try:
            native.verify(handoff, 'Fictional browser reviewer', forged)
        except register.ValidationError:
            results.append({'case': 'resealed_intake_tamper_rejected', 'result': 'PASS'})
        else:
            raise RuntimeError('resealed fabricated intake accepted')
        mixed = deepcopy(handoff)
        next(row for row in mixed['cell_notes'] if row['dimension'] == 'software')['dimension'] = 'software_development'
        try:
            native.convert(mixed, 'Fictional browser reviewer')
        except register.ValidationError:
            results.append({'case': 'mixed_vocabulary_rejected', 'result': 'PASS'})
        else:
            raise RuntimeError('mixed vocabulary accepted')
        changed_source = deepcopy(handoff)
        changed_source['report_receipt_sha256'] = '1' * 64
        try:
            native.verify(changed_source, 'Fictional browser reviewer', intake)
        except register.ValidationError:
            results.append({'case': 'changed_source_receipt_rejected', 'result': 'PASS'})
        else:
            raise RuntimeError('changed source receipt accepted')


        page.evaluate('(report) => installReport(report)', report)
        with page.expect_download() as downloading:
            page.locator('#exportBtn').click()
        downloading.value.save_as(output / 'reset-browser-handoff.json')
        reset = json.loads((output / 'reset-browser-handoff.json').read_text())
        require(all(r['analyst_note'] == '' and r['disposition'] == 'UNREVIEWED' for r in reset['cell_notes']), 'new report retained previous notes')
        require(native.convert(reset, 'Fictional reviewer')['comments'] == [], 'reset invented intake')
        results.append({'case': 'same_receipt_reimport_resets_notes', 'result': 'PASS'})

        # Current workspace collapses this panel after a successful import.
        if not page.locator('#demoBtn').is_visible():
            page.locator('#importPanel > summary').click()
        page.locator('#demoBtn').click()
        page.locator('#matrix button[data-key="ESS|software_development"]').click()
        page.locator('#note').fill('Fictional legacy UI demonstration only.')
        with page.expect_download() as downloading:
            page.locator('#exportBtn').click()
        downloading.value.save_as(output / 'legacy-browser-handoff.json')
        legacy = json.loads((output / 'legacy-browser-handoff.json').read_text())
        legacy_intake = native.convert(legacy, 'Fictional demo reviewer')
        native.verify(legacy, 'Fictional demo reviewer', legacy_intake)
        require(legacy_intake['synthetic_demo'] is True, 'UI-only demo lost provenance label')
        require(legacy_intake['comments'][0]['cell']['dimension'] == 'software_development', 'legacy label rewritten')
        write_json(output / 'legacy-intake.json', legacy_intake)
        results.append({'case': 'legacy_ui_demo_intake', 'result': 'PASS'})
        require(browser_errors == [], 'browser errors: ' + repr(browser_errors))
        browser_version = browser.version
        context.close()
        browser.close()
    require(register.canonical(report) == source_before, 'report mutated')
    verified.verify_report_integrity(report)
    receipt = {'schema': 'quartz-a91c-browser-contract-rehearsal/v1', 'result': 'PASS',
               'synthetic_input': True, 'python': sys.version, 'optimization': sys.flags.optimize,
               'chromium': browser_version, 'cases': results,
               'parent_report_receipt_sha256': report['receipt_sha256'],
               'parent_status_counts': report['status_counts'], 'source_files': snapshots,
               'executed_modules': {'review_register': file_receipt(Path(register.__file__)),
                                    'native_handoff': file_receipt(Path(native.__file__)),
                                    'rehearsal': file_receipt(Path(__file__))},
               'browser_errors': browser_errors,
               'scope': 'actual parent compilation and semantic verification; actual browser installReport, edit, filter, export and reimport; actual review intake',
               'not_executed': ['production HTTP /api/inspect adapter', 'hosted CI', 'full repository suite', 'deployment or production access']}
    write_json(output / 'BROWSER_RECEIPT.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--chromium', default=shutil.which('chromium') or shutil.which('chromium-browser'))
    args = parser.parse_args()
    if not args.chromium:
        parser.error('Chromium is required; provide --chromium. No browser test was executed.')
    try:
        receipt = run(args.source_root.resolve(), args.out.resolve(), args.chromium)
        print(json.dumps({'result': receipt['result'], 'cases': receipt['cases']}, sort_keys=True))
        return 0
    except Exception as exc:
        print(f'browser_contract_rehearsal: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
