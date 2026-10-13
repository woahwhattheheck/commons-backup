from pathlib import Path
import random,json,hashlib
import sys
root=Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True)
def make(name,n,h,nd,seed,split=False):
 r=random.Random(seed); arcs={}
 # Bidirected ring plus skip chords; integer metrics force shortest-path ties.
 for u in range(n):
  for hop in (1,2):
   v=(u+hop)%n
   for a,b in ((u,v),(v,u)):
    arcs[a,b]={'id':len(arcs),'from':a,'to':b,'metric':1 if split else r.randint(1,4),'capacity':r.choice([7,10,30,100])}
 links=[]
 for i,(key,row) in enumerate(sorted(arcs.items())):row['id']=i;links.append(row)
 demands=[]
 for d in range(nd):
  s=r.randrange(n);t=(s+r.randrange(1,n))%n
  demands.append({'s':s,'t':t,'v':[r.choice([0,1,3,10,20,55]) for _ in range(h)]})
 interventions=[]
 for t in range(h):
  removed=[]
  if t%4==1:
   removed=[e['id'] for e in links if abs(e['from']-e['to'])==2]
  elif t%4==2:
   # Isolate a node never demanded to exercise unreachable segment queries.
   isolated=n-1
   if any(d['s']==isolated or d['t']==isolated for d in demands):
    for d in demands:
     if d['s']==isolated:d['s']=0
     if d['t']==isolated:d['t']=1
     if d['s']==d['t']:d['t']=(d['s']+1)%(n-1)
   removed=[e['id'] for e in links if isolated in (e['from'],e['to'])]
  interventions.append({'t':t,'links':removed})
 p=root/name;p.mkdir(parents=True,exist_ok=True)
 for fn,obj in {'network.json':{'nodes':[{'id':i} for i in range(n)],'links':links},'traffic.json':{'num_time_slots':h,'demands':demands},'scenario.json':{'max_segments':4,'interventions':interventions,'budget':[{'t':t,'value':nd*6 if t else 0} for t in range(h)]}}.items():
  (p/fn).write_text(json.dumps(obj,sort_keys=True)+'\n')
for k in range(12):make(f'case-{k:02}',6+k%5,1+k%5,2+k%6,88450+k,k%2==0)
make('bench-small',8,4,8,99951,True)
make('bench-large',36,12,32,99953,True)
print('generated',len(list(root.iterdir())))
