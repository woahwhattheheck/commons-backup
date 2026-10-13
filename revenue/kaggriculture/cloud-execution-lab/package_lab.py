"""Create deterministic cloud research/source and evidence archives; no uploads."""
from pathlib import Path
import gzip,hashlib,io,json,tarfile

HERE=Path(__file__).resolve().parent
ROOT_FILES=['scheduler.py','mechanics.py','candidate.py','naive.py','build_mechanics.py','benchmark.py','prepare_runtime.py','scenario_crosscheck.py','test_engine_semantics.py','test_scheduler.py','package_lab.py','README.md','RESULTS.md','ENGINE-SEMANTICS.md','SCENARIO-CROSSCHECK.md','CALLABLE.md','NOTICE','LICENSE','SOURCE-FREEZE.json','ENVIRONMENT.json']
REPORTS=['baseline-panel.json','baseline-first.json','baseline-rest.json','baseline-seat1.json','development-v1.json','development-v1-paired.json','development-v2.json','development-v2-paired.json','development-v3.json','development-v3-paired.json','heldout-v3.json','FINAL-EVALUATION-SUMMARY.json','v1-naive-loss-analysis.json','SOURCE-MERGE-RECEIPT.json']

def artifact_files():
    names=list(ROOT_FILES)
    for folder in ['reference/engine','reference/next-panel','reference/decision','reference/evaluator','reference/apex','reference/scenario-adapter']:
        names.extend(str(p.relative_to(HERE)) for p in (HERE/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for name in REPORTS:
        if (HERE/'runtime'/name).exists():names.append('runtime/'+name)
    for pattern in ['runtime/*-traces/*.jsonl.gz','runtime/variants/**/*']:
        names.extend(str(p.relative_to(HERE)) for p in HERE.glob(pattern) if p.is_file() and '__pycache__' not in p.parts)
    return sorted(set(names))

def tar(names,target):
    with target.open('wb') as raw:
        with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0,compresslevel=6) as zipped:
            with tarfile.open(fileobj=zipped,mode='w|',format=tarfile.PAX_FORMAT) as archive:
                for name in sorted(names):
                    data=(HERE/name).read_bytes();info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=0
                    archive.addfile(info,io.BytesIO(data))
    return {'file':str(target.relative_to(HERE)),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'files':len(names)}

def main():
    export=HERE/'exports';export.mkdir(exist_ok=True)
    runtime=['scheduler.py','mechanics.py','candidate.py','SOURCE-FREEZE.json','CALLABLE.md','NOTICE','LICENSE','reference/next-panel/vendor/arlene.py','reference/next-panel/LICENSE','reference/next-panel/NEXT-DISTRIBUTION-NOTICE.txt','reference/next-panel/UPSTREAM.json','reference/decision/decision.py','reference/decision/README.md','reference/decision/LICENSE-MIT.txt','reference/engine/LICENSE']
    results={'selected_source':tar(runtime,export/'titan-sell-v3-source.tar.gz')}
    allfiles=artifact_files()
    manifest={n:{'bytes':(HERE/n).stat().st_size,'sha256':hashlib.sha256((HERE/n).read_bytes()).hexdigest()} for n in allfiles}
    (export/'FILES.json').write_text(json.dumps(manifest,indent=2)+'\n')
    results['complete_evidence']=tar(allfiles+['exports/FILES.json'],export/'titan-sell-lab-evidence.tar.gz')
    # Small exact byte parts fit the connected GitHub transport's request limit.
    data=(export/'titan-sell-lab-evidence.tar.gz').read_bytes()
    parts=[]
    for offset in range(0,len(data),8_000_000):
        part=export/('titan-sell-lab-evidence.tar.gz.part%02d'%(len(parts)+1))
        payload=data[offset:offset+8_000_000];part.write_bytes(payload)
        parts.append({'file':str(part.relative_to(HERE)),'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()})
    results['complete_evidence']['parts']=parts
    assert results['selected_source']['bytes']<100*1024**2
    assert results['complete_evidence']['bytes']<100*1024**2
    (export/'ARTIFACTS.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))

if __name__=='__main__':main()
