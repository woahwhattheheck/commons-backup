# SPDX-License-Identifier: Apache-2.0
"""Build and verify the single current TITAN release."""
import gzip
import hashlib
import io
import json
import os
import stat
import uuid
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parent
RUNTIME=['integrated_selected.py','integrated_main.py','integrated_parent.py',
 'ordered_selected_sell.py','selected_action_sell.py','selected_sell_core.py','mechanics.py',
 'reference/decision/decision.py','reference/decision/README.md',
 'reference/ordered-feasibility/atlas/projection.py',
 'reference/selected-action/t08/arrival_contract.py','reference/selected-action/t08/LICENSE-ROOT',
 'reference/next-panel/vendor/arlene.py','reference/next-panel/LICENSE',
 'reference/next-panel/NEXT-DISTRIBUTION-NOTICE.txt','reference/next-panel/UPSTREAM.json',
 'reference/engine/LICENSE','reference/integrated-selected/alder/seed_budget.py',
 'reference/integrated-selected/UPSTREAM.json',
 *['reference/integrated-selected/claude/'+f for f in
   ['arlene_plan.py','native_motifs.py','run_cards.py','arrival_facts.py','engine_pin.py',
    'LICENSE-MIT.txt','LICENSE-APACHE-2.0.txt']]]

ARCHIVE='exports/titan-current.tar.gz'
RECORD='runtime/integrated-selected/'


def source_files():
    """Archive member -> actual current repository source; no version selector."""
    mapping={p:p for p in RUNTIME if p not in ('integrated_main.py','integrated_parent.py')}
    mapping['seller_snapshot.py']='../cloud-quickstep/seller_snapshot.py'
    mapping['observed_clone.py']='../cloud-runtime-pulse/observed_clone.py'
    mapping['plant_suffix.py']='../cloud-runtime-pulse/plant_suffix.py'
    # Reuse LARK's tested public-curve implementation byte-for-byte.  These two
    # modules become ordinary root modules inside the standalone archive.
    mapping['sell_priority.py']='../cloud-opponent-league/lark-responsive/sell_priority.py'
    mapping['pressure_priority.py']='../cloud-opponent-league/lark-responsive/pressure_priority.py'
    mapping['seed_retry.py']='../cloud-committed-seed-retry/seed_retry.py'
    for p in ['main.py','titan_runtime.py','frozen_selected.py','scheduler.py',
              'terminal_history_join.py','spatial_tempo.py','fourth_quadrant.py',
              'funded_payback_runtime.py','operating_stock.py','TITAN-CONFIG.json','LICENSE','NOTICE','TITAN-RELEASE.md']:
        mapping[p]=p
    # Package ECON's landed callback from its attributed source rather than
    # maintaining a second implementation in the canonical runtime tree.
    mapping['funded_payback.py']='../cloud-economic-stress/funded_payback/funded_payback.py'
    for directory in ('reference/titan-current','reference/titan-history'):
        for p in (ROOT/directory).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts:
                name=str(p.relative_to(ROOT));mapping[name]=name
    for name in ('integrated_selected.py','selected_action_sell.py','selected_sell_core.py','ordered_selected_sell.py'):
        mapping[name]='reference/titan-current/latest/'+name
    # The optional terminal owner pins the original frozen SELL source. Runtime
    # optimizations must not silently replace that dependency with new bytes.
    mapping['reference/titan-current/vendor/sell/scheduler.py']='reference/titan-current/vendor/sell/scheduler.py'
    for name in ('mechanics.py','reference/next-panel/vendor/arlene.py','reference/decision/decision.py'):
        mapping['reference/titan-current/vendor/sell/'+name]=name
    mapping['reference/titan-current/vendor/terminal.py']='reference/titan-current/terminal.py'
    # Controls and experimental configuration are reproduction inputs only.
    for name in ('TITAN-HISTORY-CONFIG.json','test_terminal_history_join.py',
                 'test_worker_deadline.py','test_worker_episode.py','test_entrypoint_clock.py','test_module_recovery.py','test_seed_derived.py','test_route_recovery.py','test_ordered_selected_sell.py','test_engine_semantics.py'):
        mapping['checks/'+name]=name
    mapping['checks/test_funded_payback_runtime.py']='test_funded_payback_runtime.py'
    mapping['checks/test_market_pressure_runtime.py']='test_market_pressure_runtime.py'
    mapping['checks/test_committed_seed_retry_runtime.py']='test_committed_seed_retry_runtime.py'
    mapping['checks/test_weed_continuation.py']='test_weed_continuation.py'
    mapping['checks/test_operating_stock.py']='test_operating_stock.py'
    mapping['checks/reference/weed-continuation/delta-native.json.gz']='reference/weed-continuation/delta-native.json.gz'
    mapping['checks/reference/weed-continuation/ash-native.json.gz']='reference/weed-continuation/ash-native.json.gz'
    mapping['checks/reference/weed-continuation/spruce-native.json.gz']='reference/weed-continuation/spruce-native.json.gz'
    mapping['checks/test_seed_retry.py']='../cloud-committed-seed-retry/test_seed_retry.py'
    for name in ('reference/historical/seed_budget-before-derived-cache.py','reference/engine/kaggriculture.py','reference/engine/kaggriculture.json',
                 'reference/engine/utils.py','reference/evaluator/official_agent.py','reference/evaluator/evaluate.py',
                 'reference/evaluator/loader.py','reference/evaluator/opponents.py'):
        mapping['checks/'+name]=name
    # Preserve the evaluator's historical adjacent layout. The historical
    # evaluate.py is byte-identical to the vendored loader; compact_no_expansion
    # requires the actual offline candidate module because it consumes POLICY
    # and agent, which reference/evaluator/official_agent.py does not expose.
    mapping['checks/reference/20260907-offline-agent/evaluate.py']='reference/evaluator/loader.py'
    mapping['checks/reference/20260907-offline-agent/main.py']='../20260907-offline-agent/main.py'
    return mapping


def render():
    mapping=source_files()
    blobs={p:(ROOT/source).read_bytes() for p,source in mapping.items()}
    manifest=json.loads((ROOT/(RECORD+'RELEASE.json')).read_text())
    manifest.update(entrypoint='main.py::agent',config='TITAN-CONFIG.json',
        default=json.loads(blobs['TITAN-CONFIG.json']),
        runtime={p:{'source_path':mapping[p],'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
                 for p,b in blobs.items()})
    encoded=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    blobs['SOURCE.json']=encoded
    output=io.BytesIO()
    with gzip.GzipFile(fileobj=output,mode='wb',mtime=0,filename='') as gz:
        with tarfile.open(fileobj=gz,mode='w') as archive:
            for path,data in sorted(blobs.items()):
                info=tarfile.TarInfo(path);info.size=len(data);info.mode=0o644;info.mtime=0
                archive.addfile(info,io.BytesIO(data))
    data=output.getvalue()
    receipt={'path':ARCHIVE,'entrypoint':'main.py::agent','config':'TITAN-CONFIG.json',
             'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
             'runtime_files':len(mapping),'source_manifest':RECORD+'CURRENT-SOURCE.json',
             'source_manifest_sha256':hashlib.sha256(encoded).hexdigest()}
    return data,encoded,receipt


def _publish_files(outputs):
    """Stage every complete file before replacing any published path.

    Each same-directory replace is atomic, not the group. The receipt is last;
    interruption between replacements remains detectable by verify_current().
    A hard process exit can leave an unreferenced temporary file, never a
    partially overwritten archive. Only this invocation's temporary paths are
    cleaned up; historical artifacts and other writers' files are untouched.
    """
    staged = []
    try:
        for target, content in outputs:
            temporary = target.with_name('.'+target.name+'.'+uuid.uuid4().hex+'.tmp')
            with temporary.open('xb') as stream:
                staged.append((temporary, target))
                if target.exists():
                    os.chmod(temporary, stat.S_IMODE(target.stat().st_mode))
                remaining = memoryview(content)
                while remaining:
                    written = stream.write(remaining)
                    if written is None or written <= 0:
                        raise OSError('Release staging write made no progress')
                    remaining = remaining[written:]
                stream.flush()
                os.fsync(stream.fileno())
        for temporary, target in staged:
            os.replace(temporary, target)
    finally:
        for temporary, _ in staged:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                # Cleanup is best-effort; retain the original publication error.
                pass


def build_release():
    data,manifest,receipt=render()
    outputs = []
    # Preserve every superseded current archive before advancing the one stream.
    current=ROOT/ARCHIVE
    old=current.read_bytes() if current.exists() else None
    if old is not None and old!=data:
        digest=hashlib.sha256(old).hexdigest()
        historical=ROOT/'exports/historical'/('titan-'+digest+'.tar.gz')
        historical.parent.mkdir(parents=True,exist_ok=True)
        if historical.exists():
            if historical.read_bytes()!=old:
                raise ValueError('Historical archive identity collision')
        else:
            outputs.append((historical, old))
    # Keep the receipt as the final publication point. All files are staged and
    # flushed first; a staging failure leaves the previous three outputs intact.
    receipt_bytes=(json.dumps(receipt,indent=2)+'\n').replace('\n',os.linesep).encode('utf-8')
    outputs.extend(((current, data),
                    (ROOT/(RECORD+'CURRENT-SOURCE.json'), manifest),
                    (ROOT/(RECORD+'CURRENT-ARCHIVE.json'), receipt_bytes)))
    _publish_files(outputs)
    verify_current()
    return receipt


def verify_current():
    """Fail on stale source, stale pointer, changed config or archive contents."""
    data,manifest,receipt=render()
    actual=json.loads((ROOT/(RECORD+'CURRENT-ARCHIVE.json')).read_text())
    if actual!=receipt:raise ValueError('Current release pointer differs from current source')
    if (ROOT/ARCHIVE).read_bytes()!=data:raise ValueError('Canonical archive differs from current source')
    if (ROOT/(RECORD+'CURRENT-SOURCE.json')).read_bytes()!=manifest:
        raise ValueError('Current manifest differs from current source')
    return receipt


build=build_release

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--release',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    print(json.dumps(verify_current() if args.check else build_release()))
