#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("sealchain", HERE / "sealchain.py")
assert SPEC and SPEC.loader
sc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sc
SPEC.loader.exec_module(sc)

CHAINLOCK_STUB = r'''
import hashlib, json
from pathlib import Path

def _sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _read_jsonl(path):
    out=[]
    for line in Path(path).read_text().splitlines():
        if line.strip(): out.append(json.loads(line))
    return out

def _seed(value, label):
    if isinstance(value, bool) or value is None: raise ValueError(label)
    return str(value)
def _strict_int(value, label, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum): raise ValueError(label)
    return value

def _derived_outcome(row, index):
    if row.get('status') != 'DONE': raise ValueError('not done')
    seat=_strict_int(row.get('seat'), 'seat')
    if seat not in (0,1): raise ValueError('seat')
    rewards=row.get('rewards')
    if not isinstance(rewards,list) or len(rewards)!=2: raise ValueError('rewards')
    a,b=map(float,rewards)
    if seat==0: cand,opp=a,b
    else: cand,opp=b,a
    return seat,cand,opp,cand-opp

def bind_results(*, candidate_path, engine_path, opponent_root, rows):
    c=_sha(candidate_path); e=_sha(engine_path)
    opps={}
    ledger=[]
    pairs={}
    for i,row in enumerate(rows):
        seat,cand,opp,margin=_derived_outcome(row,i)
        art=row['opponent_artifact']; sha=_sha(Path(opponent_root)/art); opps[art]=sha
        seed=_seed(row['environment_seed'],'seed')
        rep=_strict_int(row.get('replicate',0),'rep',minimum=0)
        key=(seed,sha,rep); pairs.setdefault(key,set()).add(seat)
        ledger.append({'environment_seed': seed if 'replicate' not in row else f'{seed}::replicate={rep}',
            'opponent_sha256':sha,'seat':seat,'candidate_score':cand,'opponent_score':opp,
            'status':'DONE','source_result_sha256':hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest()})
    if not pairs or any(v!={0,1} for v in pairs.values()): raise ValueError('incomplete')
    analyzer=[{'seed':r['environment_seed'],'opponent':r['opponent_sha256'],'seat':r['seat'],
               'margin':r['candidate_score']-r['opponent_score']} for r in ledger]
    receipt={'verdict':'PASS','score_ceiling_applied':False,'candidate':{'sha256':c},'engine':{'sha256':e},
             'opponents':[{'artifact':k,'sha256':v} for k,v in sorted(opps.items())],
             'rows':len(ledger),'paired_cells':len(pairs),
             'panel_sha256':hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest()}
    return {'rows':ledger}, analyzer, receipt
'''

QUIETBOX_STUB = r'''
import hashlib, json
from pathlib import Path

def load_jsonl(path, margin_field, key_fields):
    out={}
    for line in Path(path).read_text().splitlines():
        r=json.loads(line); k=(r['opponent'],r['seed'],r['seat'],r.get('replicate',0))
        if k in out: raise ValueError('dup')
        out[k]=r
    return out

def evaluate(quiet, loaded, **kwargs):
    missing=set(quiet)-set(loaded); extra=set(loaded)-set(quiet)
    common=set(quiet)&set(loaded)
    ds=[loaded[k]['margin']-quiet[k]['margin'] for k in common]
    ma=max([abs(x) for x in ds],default=999999)
    mean=sum(abs(x) for x in ds)/len(ds) if ds else 999999
    bias=sum(ds)/len(ds) if ds else 999999
    seats={k[2] for k in common}
    failures=[]
    if missing or extra: failures.append('coverage')
    if len(common)<kwargs['min_pairs']: failures.append('pairs')
    if kwargs['require_both_seats'] and len(seats)<2: failures.append('seats')
    if ma>kwargs['max_abs_drift']: failures.append('max drift')
    if mean>kwargs['max_mean_abs_drift']: failures.append('mean drift')
    if abs(bias)>kwargs['max_mean_bias']: failures.append('bias')
    return {'certified':not failures,'failures':failures,'aligned_pairs':len(common),'max_abs_drift':ma,
            'mean_abs_drift':mean,'mean_signed_bias':bias}
def sha256_file(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
'''

SPECTRUM_STUB = r'''
def validate_panel(raw):
    if raw.get('schema')!='titan.gauntlet.panel.v1': raise ValueError('schema')
    return raw

def analyze(panel, results):
    rows=panel['opponents']; resolved=[r for r in rows if r['status']=='resolved']
    ids={r['id'] for r in rows}; rid={r['opponent_id'] for r in results['rows']}
    auth=len(rows)==panel['expected_labels'] and len(resolved)==len(rows) and ids==rid
    fam={r['family'] for r in resolved}; src={r['source_id'] for r in resolved}
    games=sum(x['wins']+x['losses']+x['draws'] for x in results['rows'])
    mm=sum(x['margin_sum'] for x in results['rows'])/games if games else 0
    return {'authoritative_family_weighting':auth,'blocking_reasons':[] if auth else ['incomplete'],
            'panel':{'observed_labels':len(rows),'unique_families':len(fam),'unique_sources':len(src),
                     'unresolved_labels':[r['id'] for r in rows if r['status']!='resolved']},
            'results':{'family_balanced':{'mean_margin_per_game':mm}}}
'''

COHORT_STUB = r'''
def audit(raw):
    dirty=raw.get('force_dirty',False)
    return {'mode':'planned_paired','coverage_complete':not dirty,'runtime_clean':not dirty,
            'complete_pairs':2,'expected_games':4,'observed_games':4}
'''


class SealchainTests(unittest.TestCase):
    def setUp(self):
        self.old_pins=copy.deepcopy(sc.AUTHORITY_PINS)
        self.td=tempfile.TemporaryDirectory()
        self.root=Path(self.td.name)
        self.v4=self.root/'v4'
        stubs={'chainlock':CHAINLOCK_STUB,'quietbox':QUIETBOX_STUB,'spectrum':SPECTRUM_STUB,'cohort':COHORT_STUB}
        for name,pin in sc.AUTHORITY_PINS.items():
            path=self.v4/pin['path']; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(stubs[name])
            sc.AUTHORITY_PINS[name]['git_blob']=sc._git_blob_id(path.read_bytes())
        self.candidate=self.root/'candidate.py'; self.candidate.write_text('candidate\n')
        self.engine=self.root/'engine.py'; self.engine.write_text('engine\n')
        self.opps=self.root/'opponents'; self.opps.mkdir()
        (self.opps/'a.py').write_text('a\n'); (self.opps/'b.py').write_text('b\n')
        self.quiet=self.root/'quiet.jsonl'; self.loaded=self.root/'loaded.jsonl'
        q=[
            {'environment_seed':1,'opponent_artifact':'a.py','seat':0,'status':'DONE','rewards':[100,0]},
            {'environment_seed':1,'opponent_artifact':'a.py','seat':1,'status':'DONE','rewards':[0,100]},
            {'environment_seed':2,'opponent_artifact':'b.py','seat':0,'status':'DONE','rewards':[40,0]},
            {'environment_seed':2,'opponent_artifact':'b.py','seat':1,'status':'DONE','rewards':[0,40]},
        ]
        l=[dict(r) for r in q]
        for r in l:
            seat=r['seat']; r['rewards']=list(r['rewards']); r['rewards'][seat]+=5
        self.write_jsonl(self.quiet,q); self.write_jsonl(self.loaded,l)
        self.panel=self.root/'panel.json'
        self.write_panel([
            {'id':'a.py','kind':'real_policy','family':'fam-a','source_id':'src-a','status':'resolved'},
            {'id':'b.py','kind':'real_policy','family':'fam-b','source_id':'src-b','status':'resolved'},
        ])

    def tearDown(self):
        sc.AUTHORITY_PINS.clear(); sc.AUTHORITY_PINS.update(self.old_pins)
        self.td.cleanup()

    @staticmethod
    def write_jsonl(path, rows): path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    def write_panel(self, opponents):
        self.panel.write_text(json.dumps({'schema':'titan.gauntlet.panel.v1','expected_labels':len(opponents),'opponents':opponents}))
    def certify(self, cohort=None):
        return sc.certify(v4_root=self.v4,candidate=self.candidate,engine=self.engine,opponent_root=self.opps,
            quiet_results=self.quiet,loaded_results=self.loaded,panel_path=self.panel,cohort_input=cohort)

    def test_happy_chain_admits(self):
        r=self.certify(); self.assertTrue(r['admitted']); self.assertTrue(r['quietbox']['certified'])
        self.assertTrue(r['spectrum']['authoritative_family_weighting']); self.assertFalse(r['cohort']['applicable'])

    def test_authority_source_drift_blocks_before_import(self):
        (self.v4/sc.AUTHORITY_PINS['quietbox']['path']).write_text('tampered\n')
        with self.assertRaisesRegex(sc.SealError,'source drift'): self.certify()

    def test_loaded_contention_drift_blocks(self):
        rows=[json.loads(x) for x in self.loaded.read_text().splitlines()]
        for r in rows: r['rewards'][r['seat']]+=1000
        self.write_jsonl(self.loaded,rows)
        with self.assertRaisesRegex(sc.SealError,'QUIETBOX contention certificate failed'): self.certify()

    def test_missing_loaded_coordinate_blocks(self):
        rows=[json.loads(x) for x in self.loaded.read_text().splitlines()][:-2]
        self.write_jsonl(self.loaded,rows)
        with self.assertRaises(sc.SealError): self.certify()

    def test_unresolved_panel_identity_blocks(self):
        self.write_panel([
            {'id':'a.py','kind':'real_policy','family':'fam-a','source_id':'src-a','status':'resolved'},
            {'id':'b.py','kind':'unknown','family':None,'source_id':None,'status':'unresolved'},
        ])
        with self.assertRaisesRegex(sc.SealError,'unresolved'): self.certify()

    def test_panel_artifact_set_mismatch_blocks(self):
        self.write_panel([{'id':'a.py','kind':'real_policy','family':'fam-a','source_id':'src-a','status':'resolved'}])
        with self.assertRaisesRegex(sc.SealError,'panel/opponent artifact mismatch'): self.certify()

    def test_identical_bytes_cannot_claim_two_source_identities(self):
        (self.opps/'b.py').write_text((self.opps/'a.py').read_text())
        with self.assertRaisesRegex(sc.SealError,'identical opponent bytes'): self.certify()

    def test_one_source_id_cannot_map_to_multiple_digests(self):
        self.write_panel([
            {'id':'a.py','kind':'real_policy','family':'fam','source_id':'same','status':'resolved'},
            {'id':'b.py','kind':'real_policy','family':'fam','source_id':'same','status':'resolved'},
        ])
        with self.assertRaisesRegex(sc.SealError,'maps to multiple exact opponent digests'): self.certify()

    def make_cohort(self, *, candidate_sha=None, engine_sha=None, dirty=False):
        csha=candidate_sha or hashlib.sha256(self.candidate.read_bytes()).hexdigest()
        esha=engine_sha or hashlib.sha256(self.engine.read_bytes()).hexdigest()
        asha=hashlib.sha256((self.opps/'a.py').read_bytes()).hexdigest()
        path=self.root/'cohort.json'
        path.write_text(json.dumps({'schema':'titan.gauntlet.paired.v1','artifacts':{'baseline':'0'*64,'candidate':csha},
            'engine_sha256':esha,'cells':[{'opponent_sha256':asha}], 'force_dirty':dirty}))
        return path

    def test_compatible_cohort_packet_is_composed(self):
        r=self.certify(self.make_cohort()); self.assertTrue(r['cohort']['applicable']); self.assertTrue(r['cohort']['runtime_clean'])

    def test_cohort_candidate_mismatch_blocks(self):
        with self.assertRaisesRegex(sc.SealError,'candidate artifact'): self.certify(self.make_cohort(candidate_sha='f'*64))

    def test_dirty_cohort_blocks(self):
        with self.assertRaisesRegex(sc.SealError,'incomplete, failed, or contains fallbacks'):
            self.certify(self.make_cohort(dirty=True))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(sc.SealError,'duplicate JSON key'):
            sc.loads_strict('{"a":1,"a":2}','x')

    def test_spectrum_aggregate_preserves_large_exact_integer(self):
        rows=[{'environment_seed':1,'opponent_artifact':'a.py','seat':0,'status':'DONE',
               'rewards':[9007199254740993,0]}]
        grouped=sc._aggregate_spectrum_results(type('C',(),{'_derived_outcome':staticmethod(lambda row,index:(0,row['rewards'][0],0,row['rewards'][0]))}), rows)
        self.assertEqual(9007199254740993, grouped['rows'][0]['margin_sum'])
        self.assertIs(type(grouped['rows'][0]['margin_sum']), int)

    def test_bool_seat_rejected_by_chainlock(self):
        rows=[json.loads(x) for x in self.quiet.read_text().splitlines()]; rows[0]['seat']=True; self.write_jsonl(self.quiet,rows)
        with self.assertRaisesRegex(sc.SealError,'CHAINLOCK rejected'): self.certify()


if __name__=='__main__': unittest.main()
