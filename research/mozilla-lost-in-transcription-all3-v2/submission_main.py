"""Offline multi-track entrypoint template.

Operator copies this file to main.py and supplies local model assets. The same runtime
shape is used across all three competitions; TRACK selects the profile only.
"""
from __future__ import annotations
import csv, json, math, os, sys
from pathlib import Path
SRC=Path(__file__).resolve().parent
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from core import ConsensusConfig, Hypothesis, TRACKS, TrackPrior, choose_consensus
DATA=Path('/code_execution/data'); FORMAT=DATA/'submission_format.csv'; CLIPS=DATA/'clips'; OUTPUT=Path('/code_execution/submission/submission.csv')
TRACK=os.environ.get('LIT_TRACK','').strip()

def _inside(path: Path) -> Path:
    r=path.resolve(); r.relative_to(SRC)
    if not r.exists(): raise FileNotFoundError(r)
    return r

def main() -> None:
    if TRACK not in TRACKS: raise RuntimeError('LIT_TRACK must be one of sp-en, sp-nh, id-jv')
    if any(os.environ.get(k) for k in ('http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY')): raise RuntimeError('network proxy variables forbidden')
    config=json.loads((SRC/'model_config.json').read_text(encoding='utf-8'))
    if config.get('track')!=TRACK: raise RuntimeError('model_config track mismatch')
    models=config.get('models')
    if not isinstance(models,list) or len(models)<2: raise RuntimeError('at least two local models required')
    from faster_whisper import WhisperModel
    loaded=[]
    for item in models:
        if item.get('kind')!='faster-whisper': raise RuntimeError('only audited faster-whisper adapter accepted')
        rel=float(item.get('reliability',1.0))
        if not math.isfinite(rel) or rel<=0: raise RuntimeError('invalid model reliability')
        loaded.append((item,WhisperModel(str(_inside(SRC/item['model_path'])),device=item.get('device','cuda'),compute_type=item.get('compute_type','float16'),local_files_only=True)))
    prior=None; pp=SRC/'prior.json'
    if pp.exists(): prior=TrackPrior(**json.loads(pp.read_text(encoding='utf-8')))
    cfg=ConsensusConfig(**config.get('consensus',{}))
    rows=list(csv.DictReader(FORMAT.open('r',encoding='utf-8',newline='')))
    if not rows or 'audio_filename' not in rows[0]: raise RuntimeError('invalid submission_format.csv')
    out=[]
    for row in rows:
        name=row['audio_filename']; audio=(CLIPS/name).resolve(); audio.relative_to(CLIPS.resolve())
        if not audio.is_file(): raise FileNotFoundError(audio)
        hs=[]
        for rank,(item,model) in enumerate(loaded):
            segments,_=model.transcribe(str(audio),beam_size=int(item.get('beam_size',5)),language=item.get('language'),vad_filter=bool(item.get('vad_filter',True)),condition_on_previous_text=False)
            text=' '.join(seg.text.strip() for seg in segments if seg.text.strip()).strip()
            if not text: raise RuntimeError(f"empty ASR output: {item['name']}")
            hs.append(Hypothesis(text=text,source=str(item['name']),rank=rank,reliability=float(item.get('reliability',1.0))))
        result=choose_consensus(TRACK,hs,prior=prior,config=cfg)
        out.append({'audio_filename':name,'transcript':result.text})
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    with OUTPUT.open('w',encoding='utf-8',newline='') as h:
        w=csv.DictWriter(h,fieldnames=['audio_filename','transcript']); w.writeheader(); w.writerows(out)
if __name__=='__main__': main()
