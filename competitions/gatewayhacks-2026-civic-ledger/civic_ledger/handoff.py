"""Portable source-retaining reader for the existing Civic Action Ledger.

No second extraction engine. Integrity/reproduction is not source authentication.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
from pathlib import Path
import sys
import tempfile

from . import core

SCHEMA = 'civic-action-ledger-portable/v1'
ContractError = core.ContractError
PACKAGE = Path(__file__).resolve().parent
SOURCE_NAMES = ('__init__.py', 'core.py', 'handoff.py')
SOURCE_BYTES = {f'civic_ledger/{name}': (PACKAGE / name).read_bytes() for name in SOURCE_NAMES}
# A copied verifier should not add incidental cache files to the handoff.
sys.dont_write_bytecode = True

SCRIPT = """const search = document.getElementById('search-input');
const state = document.getElementById('state-filter');
const cards = Array.from(document.querySelectorAll('.item-card'));
function filterItems() {
  const query = search.value.toLocaleLowerCase().trim();
  let count = 0;
  for (const card of cards) {
    const match = (!state.value || card.dataset.state === state.value) &&
      (!query || card.dataset.search.toLocaleLowerCase().includes(query));
    card.hidden = !match;
    if (match) count += 1;
  }
  document.getElementById('results-count').textContent = count + ' of ' + cards.length + ' items';
}
search.addEventListener('input', filterItems);
state.addEventListener('change', filterItems);
filterItems();"""
STYLE = """*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;color:#18302c;background:#f3f5ee;font:16px/1.55 system-ui,sans-serif}header{background:#173e36;color:#fff;padding:3rem max(5vw,1rem)}header p{max-width:75ch}h1{font-size:clamp(2rem,5vw,3.5rem);line-height:1.12;margin:.4em 0}h2{line-height:1.25}main{max-width:1200px;margin:auto;padding:2rem 1.2rem}a{color:#195c4b;text-underline-offset:.2em}header a{color:#e0f1c7}.eyebrow{letter-spacing:.14em;text-transform:uppercase;font-size:.78rem}.meta,.controls,.downloads{display:flex;flex-wrap:wrap;gap:1rem}.meta span,.badge{display:inline-block;border-radius:5px;padding:.3rem .6rem;background:#e5eedb;color:#183e32}.controls{padding:1rem 0;align-items:end}.controls label{display:flex;flex-direction:column;gap:.35rem}input,select{font:inherit;padding:.7rem;border:1px solid #87998d;border-radius:5px;max-width:100%}input{width:min(28rem,85vw)}.item-card{background:white;padding:1.5rem;margin:1.3rem 0;border:1px solid #cad5c6;border-left:5px solid #648759;border-radius:7px}.item-card[hidden]{display:none}.hold{border-left-color:#a74a33}.hold .badge{background:#fae7db;color:#792b16}.item-card h2{margin:.25rem 0 1rem}.facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.facts dt{font-weight:650}.facts dd{margin:0;overflow-wrap:anywhere}.citation{display:block;font-size:.82rem;margin-top:.25rem}.citation code,code{overflow-wrap:anywhere}.history{padding-left:1.3rem}.history li{margin:.6rem 0}.source{background:#fff;border:1px solid #c8d3c5;padding:1.3rem;margin:1.3rem 0;overflow-wrap:anywhere}.lines{padding-left:3.2rem;font:14px/1.7 ui-monospace,monospace}.lines li{white-space:pre-wrap;overflow-wrap:anywhere;padding:0 .5rem;min-height:1.7em}.lines li:target{background:#fff2a6;outline:2px solid #947309;scroll-margin-top:1rem}.small{font-size:.85rem}.muted{color:#526457}summary{cursor:pointer;font-weight:650}.downloads a{padding:.5rem .75rem;border:1px solid #8fa58b;border-radius:4px}.notice{background:#e8edde;padding:1rem;border-radius:5px}footer{margin:2rem 0}.empty{font-style:italic}@media(max-width:650px){.facts{grid-template-columns:1fr}header{padding:2rem 1.2rem}.item-card{padding:1rem}}@media print{.controls,.downloads{display:none}.item-card[hidden]{display:block}.item-card{break-inside:avoid}body{background:#fff}header{background:#fff;color:#18302c}}"""


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _json(data: bytes) -> dict:
    try:
        obj = core._strict_json_loads(data.decode('utf-8'))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ContractError(f'invalid UTF-8 JSON: {exc}') from exc
    if not isinstance(obj, dict):
        raise ContractError('expected a JSON object')
    return obj


def _workspace(data: bytes) -> core.Ledger:
    if len(data) > 4_000_000:
        raise ContractError('workspace too large')
    try:
        return core.Ledger.from_dict(_json(data))
    except (TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise ContractError(f'invalid workspace: {exc}') from exc


def _source_copies() -> dict[str, bytes]:
    for name, data in SOURCE_BYTES.items():
        if (PACKAGE / Path(name).name).read_bytes() != data:
            raise ContractError(f'local support source changed since import: {name}')
    return dict(SOURCE_BYTES)


def _download(name: str, data: bytes, label: str | None = None) -> str:
    encoded = base64.b64encode(data).decode('ascii')
    return f'<a download="{_escape(Path(name).name)}" href="data:application/octet-stream;base64,{encoded}">{_escape(label or name)}</a>'


def render_reader(compiled: dict, ledger: core.Ledger, payloads: dict[str, bytes], classification: str) -> bytes:
    indices = {snap.doc_id: index for index, snap in enumerate(ledger.snapshots, 1)}
    snapshots = {snap.doc_id: snap for snap in ledger.snapshots}

    def citation(ev: dict | None) -> str:
        if ev is None:
            return '<span class="small muted">No retained evidence for this field.</span>'
        snap = snapshots[ev['doc_id']]
        lines = snap.text.splitlines()
        line = ev['line']
        if (type(line) is not int or line < 1 or line > len(lines) or
                ev['source_sha256'] != snap.sha256 or _hash(lines[line-1].encode('utf-8')) != ev['line_sha256']):
            raise ContractError('compiled citation does not match retained source')
        anchor = f'source-{indices[snap.doc_id]:04d}-line-{line}'
        return (f'<a class="citation" href="#{anchor}">{_escape(snap.doc_id)} · line {line} · '
                f'{_escape(ev["label"])}: {_escape(ev["value"])}</a>'
                f'<span class="small muted">Line SHA-256 <code>{ev["line_sha256"]}</code></span>')

    cards = []
    for item in compiled['items']:
        fields = []
        for field in ('decision', 'owner', 'deadline', 'action'):
            value = item[field] if item[field] is not None else 'Unknown — not established by retained evidence'
            evs = item['decision_evidence'] if field == 'decision' else [item[field + '_evidence']]
            refs = ''.join(citation(ev) for ev in evs) if evs else citation(None)
            fields.append(f'<div><dt>{field.title()}</dt><dd>{_escape(value)}{refs}</dd></div>')
        changes = ''.join(f'<li><strong>{_escape(c["field"].title())}</strong>: {_escape(c["value"])} · '
                          f'{_escape(c["evidence"]["observed_at"])}{citation(c["evidence"])}</li>' for c in item['changes'])
        searchable = json.dumps(item, ensure_ascii=False, sort_keys=True)
        conflict = '<p class="notice">Conflicting minute decisions remain unresolved. Every competing citation is retained below.</p>' if item['conflict'] else ''
        cards.append(f'<article class="item-card{" hold" if item["conflict"] else ""}" data-state="{_escape(item["state"])}" '
                     f'data-search="{_escape(searchable)}"><span class="badge">{_escape(item["state"])}</span>'
                     f'<h2>{_escape(item["item_id"])} · {_escape(item["title"])}</h2>{citation(item["title_evidence"])}'
                     f'{conflict}<dl class="facts">{"".join(fields)}</dl><details><summary>Retained field history ({len(item["changes"])})</summary>'
                     f'<p class="small muted">Includes the first recorded value and later changes. This is source observation order, not an inferred effective date.</p>'
                     f'<ol class="history">{changes}</ol></details></article>')
    sources = []
    for index, snap in enumerate(ledger.snapshots, 1):
        source_id = f'source-{index:04d}'
        filename = f'sources/{index:04d}.txt'
        lines = ''.join(f'<li id="{source_id}-line-{n}">{_escape(line)}</li>' for n, line in enumerate(snap.text.splitlines(), 1))
        sources.append(f'<section class="source" id="{source_id}"><h3>{_escape(snap.doc_id)} · {_escape(snap.kind)}</h3>'
                       f'<p>Observed: {_escape(snap.observed_at)}<br>Recorded source URL: <code>{_escape(snap.source_url)}</code><br>'
                       f'Normalized text SHA-256: <code>{snap.sha256}</code></p>'
                       f'{_download(filename,payloads[filename],"Download retained source text")}<ol class="lines">{lines}</ol></section>')
    states = sorted({item['state'] for item in compiled['items']})
    options = ''.join(f'<option value="{_escape(state)}">{_escape(state)}</option>' for state in states)
    downloads = ''.join(_download(name,payloads[name]) for name in ('ledger.json','ledger.csv','ledger.md','manifest.json','workspace.json'))
    label = 'Synthetic — declared by exporter' if classification == 'synthetic' else 'Unspecified — no source classification declared'
    script_hash = base64.b64encode(hashlib.sha256(SCRIPT.encode('utf-8')).digest()).decode('ascii')
    csp = f"default-src 'none'; script-src 'sha256-{script_hash}'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'"
    document = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{_escape(csp)}"><title>Civic Action Ledger · {_escape(compiled['meeting_id'])}</title><style>{STYLE}</style></head>
<body><header><div class="eyebrow">Civic Action Ledger / Portable evidence reader</div><h1>{_escape(compiled['meeting_id'])}</h1>
<p>Read the action record. Follow the evidence. Keep unresolved questions visible.</p><div class="meta"><span>{_escape(compiled['freshness'])}</span><span>{len(compiled['items'])} items</span><span>{len(ledger.snapshots)} retained sources</span></div>
<p>Assessed as of <strong>{_escape(compiled['as_of'])}</strong> · source age threshold {compiled['max_source_age_days']} days.<br>Source classification: {_escape(label)}</p><a href="#retained-sources">Jump to retained source text</a></header>
<main><p class="notice">Freshness describes the supplied assessment time, not today's live record. Recorded URLs are provenance text; this file makes no network requests. Hashes support integrity and reproduction, not public-record authentication.</p>
<section aria-label="Downloads"><h2>Keep the underlying record</h2><div class="downloads">{downloads}</div><p class="small muted">Original canonical exports and exact input workspace bytes are embedded. Spreadsheet software may interpret text values; inspect untrusted CSV content as text.</p></section>
<section aria-label="Action items"><div class="controls"><label>Search items and retained evidence<input id="search-input" type="search" placeholder="Item, owner, decision or source…"></label><label>State<select id="state-filter"><option value="">All states</option>{options}</select></label><p id="results-count" role="status" aria-live="polite">{len(cards)} of {len(cards)} items</p></div><noscript><p>All items and source links work without JavaScript. Search and state filters require JavaScript.</p></noscript>{''.join(cards) or '<p class="empty">No explicit item markers were extracted.</p>'}</section>
<section id="retained-sources"><h2>Retained source text</h2><p>These are the workspace's normalized snapshots. Line numbers use the original compiler's splitlines convention; CRLF/CR normalization occurs when snapshots are created. They are not a claim of original downloaded website bytes.</p>{''.join(sources)}</section>
<footer><p>{_escape(compiled['authority']['statement'])} No legal or policy judgment and no external action is authorized.</p><p class="small">Compile SHA-256: <code>{compiled['compile_sha256']}</code><br>Original Civic core and static demo: Z-DirichletRook-120812-P6X4. Portable companion: ZZ–Trellis.</p></footer></main><script>{SCRIPT}</script></body></html>
'''
    return document.encode('utf-8')


def _payloads(workspace_bytes: bytes, *, as_of: str, max_source_age_days: int, classification: str) -> tuple[dict[str, bytes], dict]:
    if classification not in ('synthetic', 'unspecified'):
        raise ContractError('classification must be synthetic or unspecified')
    ledger = _workspace(workspace_bytes)
    compiled = core.compile_ledger(ledger, as_of=as_of, max_source_age_days=max_source_age_days)
    with tempfile.TemporaryDirectory(prefix='civic-native-') as temporary:
        core.write_bundle(compiled, temporary)
        payloads = {name: (Path(temporary) / name).read_bytes() for name in ('ledger.json','ledger.csv','ledger.md','manifest.json')}
    payloads['workspace.json'] = workspace_bytes
    for index, snap in enumerate(ledger.snapshots, 1):
        payloads[f'sources/{index:04d}.txt'] = snap.text.encode('utf-8')
    payloads['reader.html'] = render_reader(compiled, ledger, payloads, classification)
    payloads['HANDOFF_README.md'] = ("# Civic Action Ledger portable handoff\n\nOpen reader.html directly in a browser. It contains all items, retained source lines and original data downloads; no server or network is needed.\n\nFrom this directory, with Python 3.11 or newer, run:\n\n```sh\npython -B -m civic_ledger.handoff verify --output-dir .\n```\n\nVerification checks the complete expected payload set, source copies, exact workspace, native compilation and reader regeneration. It is an integrity/reproduction check, not a signature, public-record authentication, legal determination, or proof of arbitrary interpreter behavior. Only execute source from a producer you trust. Rewriting both data and all receipts is not prevented by unsigned hashes.\n\nThe original canonical manifest.json schema is unchanged. handoff-manifest.json is the separate companion receipt, written last. Existing output directories are rejected; an interrupted fresh write can leave an incomplete directory without a complete receipt. Keep that directory for inspection and choose a new destination.\n\nSource files contain normalized snapshot text, not necessarily original website bytes. Classification is an exporter declaration. Assessment freshness is tied to the explicit as_of, not today's clock.\n").encode('utf-8')
    payloads.update(_source_copies())
    return payloads, compiled


def _manifest(payloads: dict[str, bytes], compiled: dict, classification: str) -> dict:
    return {'schema': SCHEMA, 'meeting_id': compiled['meeting_id'], 'compile_sha256': compiled['compile_sha256'],
            'as_of': compiled['as_of'], 'max_source_age_days': compiled['max_source_age_days'], 'classification': classification,
            'workspace_sha256': _hash(payloads['workspace.json']), 'files': {name: _hash(data) for name, data in sorted(payloads.items())}}


def _result(manifest: dict) -> dict:
    return {'ok': True, 'meeting_id': manifest['meeting_id'], 'compile_sha256': manifest['compile_sha256'],
            'classification': manifest['classification'], 'files': sorted(manifest['files'])}


def export_handoff(workspace: Path, output_dir: Path, *, as_of: str, max_source_age_days: int = 90, classification: str = 'unspecified') -> dict:
    root = Path(output_dir)
    try:
        # Build and validate everything before creating output. Read caller input once.
        workspace_bytes = Path(workspace).read_bytes()
        payloads, compiled = _payloads(workspace_bytes, as_of=as_of, max_source_age_days=max_source_age_days, classification=classification)
        manifest = _manifest(payloads, compiled, classification)
        root.mkdir(exist_ok=False)
        for name, data in payloads.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data)
        with (root / 'handoff-manifest.json').open('xb') as stream:
            stream.write(core._canonical_bytes(manifest))
        return _result(manifest)
    except (OSError, UnicodeError) as exc:
        raise ContractError(f'cannot export handoff (existing outputs are never overwritten): {exc}') from exc


def verify_handoff(output_dir: Path) -> dict:
    root = Path(output_dir)
    try:
        if root.is_symlink() or not root.is_dir():
            raise ContractError('handoff must be a regular directory')
        inventory = set()
        for path in root.rglob('*'):
            if path.is_symlink():
                raise ContractError('handoff symlinks are not supported')
            if path.is_file():
                inventory.add(path.relative_to(root).as_posix())
            elif not path.is_dir():
                raise ContractError('handoff contains a non-regular entry')
        manifest = _json((root / 'handoff-manifest.json').read_bytes())
        required = {'schema','meeting_id','compile_sha256','as_of','max_source_age_days','classification','workspace_sha256','files'}
        if set(manifest) != required or manifest['schema'] != SCHEMA or not isinstance(manifest['files'], dict):
            raise ContractError('handoff manifest schema mismatch')
        # Do not follow paths provided by the receipt: generate the expected names ourselves.
        workspace_bytes = (root / 'workspace.json').read_bytes()
        expected, compiled = _payloads(workspace_bytes, as_of=manifest['as_of'], max_source_age_days=manifest['max_source_age_days'], classification=manifest['classification'])
        if inventory != set(expected) | {'handoff-manifest.json'}:
            raise ContractError('handoff file set mismatch')
        if manifest != _manifest(expected, compiled, manifest['classification']):
            raise ContractError('handoff receipt does not match reproduced payloads')
        for name, data in expected.items():
            if (root / name).read_bytes() != data:
                raise ContractError(f'handoff payload differs from reproduction: {name}')
        core.verify_bundle(root)
        return _result(manifest)
    except (OSError, UnicodeError, TypeError, KeyError) as exc:
        raise ContractError(f'cannot verify handoff: {exc}') from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export')
    export.add_argument('--workspace', type=Path, required=True)
    export.add_argument('--output-dir', type=Path, required=True)
    export.add_argument('--as-of', required=True)
    export.add_argument('--max-source-age-days', type=int, default=90)
    export.add_argument('--classification', choices=('synthetic','unspecified'), default='unspecified')
    verify = commands.add_parser('verify')
    verify.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = (export_handoff(args.workspace,args.output_dir,as_of=args.as_of,max_source_age_days=args.max_source_age_days,classification=args.classification)
                  if args.command == 'export' else verify_handoff(args.output_dir))
    except ContractError as exc:
        parser.exit(2, f'civic handoff: {exc}\n')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
