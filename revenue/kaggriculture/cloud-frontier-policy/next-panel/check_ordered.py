from pathlib import Path
import importlib.util,sys,json,copy,gzip
p=Path(__file__).resolve().parent
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
m=load('ordered',p/'ordered-shed-main.py');ev=load('ev',p.parent.parent/'cloud-eval/evaluate.py');engine,hashes=ev.get_engine(Path('engine'))
n=0;bad=[]
for name in ['route-baseline-development','route-baseline-development-extra']:
 for g in json.loads(gzip.decompress((p/'results'/(name+'.json.gz')).read_bytes()))['games']:
  seat=g['candidate_seat']
  for t in g['timeline']:
   farm=copy.deepcopy(t['farms'][seat]);priv=copy.deepcopy(t['private'][seat]);a=t['actions'][seat];acts=[a['farmer']]+a.get('hands',[]);pos=[farm['farmer']]+farm['hands'];proj,_=m._ordered_shed_projection(priv['shed'],priv['inventories'],pos,acts,farm['tiles'])
   for i,act in enumerate(acts):engine._apply_unit_action(farm,priv,i,act,len(farm['tiles']),t['step']//24,24,100)
   n+=1
   if proj!=priv['shed']:bad.append({'seed':g['seed'],'step':t['step'],'expected':priv['shed'],'projected':proj})
tiles=[[None]*10 for _ in range(10)];farm={'tiles':tiles,'farmer':[4,4],'hands':[[5,4]]};priv={'shed':{'WHEAT':10,'MILK':90},'inventories':[{}, {'MILK':10}],'seeds':{}};acts=[['PICKUP','WHEAT',10],['DROP']];proj,carry=m._ordered_shed_projection(priv['shed'],priv['inventories'],[farm['farmer']]+farm['hands'],acts,tiles)
for i,a in enumerate(acts):engine._apply_unit_action(farm,priv,i,a,10,0,24,100)
assert proj==priv['shed']=={'WHEAT':0,'MILK':100} and carry==priv['inventories']
result={'sampled_actual_observations':n,'shed_mismatches':bad,'legal_full_shed_case':{'projected':proj,'actual':priv['shed'],'carried':carry},'engine_hashes':hashes,'scope':'Shed transfer projection checked against actual full unit actions on existing observed snapshots; carry model covers transfers only, inherited production/consumption guard estimates remain.'}
(p/'results/ordered-shed-check.json').write_text(json.dumps(result,indent=2)+'\n');print(n,'snapshots',len(bad),'mismatches');print(bad[:2]);assert not bad
