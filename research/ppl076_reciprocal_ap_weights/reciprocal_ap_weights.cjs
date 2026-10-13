'use strict';
// PPL076: exact weighted navigation on an identified, already-compiled ZDD.
// No arithmetic-progression generation or old family-polynomial computation.
const SCHEMA='commons.saved_zdd_weights/v1', CONDITION='commons.saved_zdd_weight_condition/v1';
const copy=x=>JSON.parse(JSON.stringify(x));
const integer=(x,lo,hi,name)=>{if(!Number.isSafeInteger(x)||x<lo||x>hi)throw new TypeError(name);return x;};
function decimal(x,signed=false){if(typeof x!=='string'||!(signed?/^-?(0|[1-9][0-9]*)$/:/^(0|[1-9][0-9]*)$/).test(x)||x.length>2200)throw new TypeError('decimal string');return BigInt(x);}
function gcd(a,b){a=a<0n?-a:a;b=b<0n?-b:b;while(b){const t=a%b;a=b;b=t;}return a;}
function fraction(a,b){const g=gcd(a,b);return {numerator:String(a/g),denominator:String(b/g)};}
function graph(input){
 if(!input||typeof input.premise!=='object'||input.premise===null)throw new TypeError('identified premise required');
 const n=integer(input.n,0,64,'n');if(!Array.isArray(input.nodes)||input.nodes.length<2||input.nodes.length>50000)throw new RangeError('2..50000 nodes');
 const nodes=input.nodes.map((r,id)=>{if(!Array.isArray(r)||r.length!==3)throw new TypeError('node triple');const [v,l,h]=r;
  if(id<2){if(v!==0||l!==0||h!==0)throw new TypeError('terminal');}
  else{integer(v,1,n,'element');integer(l,0,id-1,'lo');integer(h,1,id-1,'hi');
   if(l>1&&input.nodes[l][0]>=v||h>1&&input.nodes[h][0]>=v)throw new TypeError('descending variables');}
  return r.slice();});
 if(!Array.isArray(input.roots)||input.roots.length>n+1)throw new TypeError('roots');
 const seen=new Set(),roots=input.roots.map(r=>{integer(r.n,0,n,'interval');integer(r.root,0,nodes.length-1,'root');if(seen.has(r.n)||nodes[r.root][0]>r.n)throw new TypeError('root');seen.add(r.n);return {n:r.n,root:r.root};});
 return {n,nodes,roots,premise:copy(input.premise)};
}
function mergeCell(lo,hi,w,work){
 work.comparisons++;const a=lo[0]===null?null:BigInt(lo[0]),b=hi[0]===null?null:BigInt(hi[0])+w;
 if(a===null&&b===null)return [null,'0',0];
 let mask=0,best;if(b===null||(a!==null&&a>b)){best=a;mask=1;}
 else if(a===null||b>a){best=b;mask=2;}else{best=a;mask=3;}
 const count=(mask&1?BigInt(lo[1]):0n)+(mask&2?BigInt(hi[1]):0n);
 return [String(best),String(count),mask];
}
function compileWeights(input){
 const g=graph(input);if(!Array.isArray(input.weights)||input.weights.length!==g.n)throw new TypeError('one weight per element');
 let scale=1n;const ws=input.weights.map((r,i)=>{if(r.element!==i+1||r.numerator.length>101||r.denominator.length>100)throw new TypeError('weight');
 const a=decimal(r.numerator,true),b=decimal(r.denominator);if(b<=0n)throw new RangeError('positive denominator');scale=scale/gcd(scale,b)*b;if(String(scale).length>2048)throw new RangeError('scale cap');return [a,b];});
 const units=['0',...ws.map(([a,b])=>String(a*(scale/b)))],table=[[null,'0',0],['0','1',0]],work={comparisons:0,weighted_cells:2,ap_constraints_constructed:0,old_polynomial_cells_computed:0,subsets_enumerated:0};
 for(let id=2;id<g.nodes.length;id++){const [v,l,h]=g.nodes[id];table.push(mergeCell(table[l],table[h],BigInt(units[v]),work));work.weighted_cells++;}
 return {schema:SCHEMA,...g,weights:copy(input.weights),scale:String(scale),units,table,work};
}
function openWeights(saved){
 const r=copy(saved);if(r.schema!==SCHEMA)throw new TypeError('schema');const g=graph(r),scale=decimal(r.scale);if(scale<=0n)throw new RangeError('scale');
 if(!Array.isArray(r.units)||r.units.length!==g.n+1||!Array.isArray(r.table)||r.table.length!==g.nodes.length)throw new TypeError('table shape');
 const units=r.units.map(x=>decimal(x,true));for(const c of r.table){if(!Array.isArray(c)||c.length!==3)throw new TypeError('cell');if(c[0]!==null)decimal(c[0],true);decimal(c[1]);integer(c[2],0,3,'choice mask');}
 const work={saved_node_visits:0,new_condition_cells:0,new_condition_comparisons:0,weighted_base_cells_recomputed:0,ap_constraints_constructed:0,old_polynomial_cells_computed:0};
 const roots=new Map(g.roots.map(x=>[x.n,x.root]));
 function root(n){integer(n,0,g.n,'n');if(!roots.has(n))throw new RangeError('root absent');return roots.get(n);}
 function score(c){return {feasible:c[0]!==null,maximum:c[0]===null?null:fraction(BigInt(c[0]),scale),scaled:c[0],count:c[1]};}
 function values(a,n){if(!Array.isArray(a))throw new TypeError('elements');let p=0;for(const v of a){integer(v,1,n,'element');if(v<=p)throw new TypeError('strict increasing elements');p=v;}return a;}
 const baseGetter=id=>{work.saved_node_visits++;return {id,cell:r.table[id],lo:g.nodes[id][1],hi:g.nodes[id][2]};};
 function view(n,key,get,restriction){
  const summary=()=>({n,...score(get(key).cell),restriction:copy(restriction)});
  function select(rank){let k=decimal(rank);const initial=k,top=get(key).cell;if(k>=BigInt(top[1]))throw new RangeError('rank');
   let cur=key;const chosen=[],trace=[];while(true){const row=get(cur);if(row.id<2){if(row.id!==1)throw new Error('infeasible terminal');break;}
    const [v]=g.nodes[row.id],mask=row.cell[2],lo=(mask&1)?BigInt(get(row.lo).cell[1]):0n;
    if(k<lo){trace.push({node:row.id,element:v,choice:0,skipped:'0',remaining_rank:String(k)});cur=row.lo;}
    else{if(!(mask&2))throw new Error('saved branch mismatch');k-=lo;chosen.push(v);trace.push({node:row.id,element:v,choice:1,skipped:String(lo),remaining_rank:String(k)});cur=row.hi;}
   }
   return {rank:String(initial),set:chosen.reverse(),...score(top),trace};
  }
  function rank(a){values(a,n);if(get(key).cell[0]===null)throw new RangeError('infeasible family');let p=a.length-1,k=0n,cur=key;const trace=[];
   while(true){const row=get(cur);if(row.id<2){if(row.id!==1||p!==-1)throw new RangeError('not an optimum member');break;}
    const v=g.nodes[row.id][0],mask=row.cell[2];if(p>=0&&a[p]>v)throw new RangeError('skipped element');
    if(p>=0&&a[p]===v){if(!(mask&2))throw new RangeError('nonoptimal include');const skipped=mask&1?BigInt(get(row.lo).cell[1]):0n;k+=skipped;p--;trace.push({node:row.id,choice:1,skipped:String(skipped)});cur=row.hi;}
    else{if(!(mask&1))throw new RangeError('nonoptimal exclude');trace.push({node:row.id,choice:0,skipped:'0'});cur=row.lo;}
   }return {rank:String(k),set:a.slice(),trace};
  }
  function page(start,limit){let k=decimal(start);integer(limit,0,256,'page limit');const total=BigInt(get(key).cell[1]);if(k>total)throw new RangeError('page start');
   const rows=[];while(k<total&&rows.length<limit)rows.push(select(String(k++)));return {total:String(total),start,next:k<total?String(k):null,rows};}
  return {summary,select,rank,page};
 }
 function at(n){return view(n,root(n),baseGetter,{required:[],forbidden:[]});}
 function condition(n,required=[],forbidden=[]){
  const start=root(n);values(required,n);values(forbidden,n);
  const req=required.reduce((m,v)=>m|(1n<<BigInt(v)),0n),ban=forbidden.reduce((m,v)=>m|(1n<<BigInt(v)),0n);
  if(req&ban)throw new RangeError('required and forbidden overlap');
  const rows=[],memo=new Map(),w={comparisons:0};
  function visit(id,remaining){
   const key=id+'|'+String(remaining);if(memo.has(key))return key;
   if(rows.length>=200000)throw new RangeError('condition row cap');
   let cell,lo=null,hi=null;const v=g.nodes[id][0];
   if(id<2){cell=id===1&&remaining===0n?['0','1',0]:[null,'0',0];}
   else if(remaining>>BigInt(v+1)){cell=[null,'0',0];}
   else{
    const bit=1n<<BigInt(v);let lc=[null,'0',0],hc=[null,'0',0];
    if(!(remaining&bit)){lo=visit(g.nodes[id][1],remaining);lc=rows[memo.get(lo)].cell;}
    if(!(ban&bit)){hi=visit(g.nodes[id][2],remaining&~bit);hc=rows[memo.get(hi)].cell;}
    cell=mergeCell(lc,hc,units[v],w);
   }
   memo.set(key,rows.length);rows.push({key,id,remaining:String(remaining),cell,lo,hi});return key;
  }
  const key=visit(start,req);work.new_condition_cells+=rows.length;work.new_condition_comparisons+=w.comparisons;
  const record={schema:CONDITION,n,root:key,required:required.slice(),forbidden:forbidden.slice(),rows,work:{cells:rows.length,comparisons:w.comparisons}};
  return {record:copy(record),navigation:openCondition(record)};
 }
 function openCondition(record){
  const c=copy(record);if(c.schema!==CONDITION)throw new TypeError('condition schema');root(c.n);values(c.required,c.n);values(c.forbidden,c.n);
  if(!Array.isArray(c.rows)||c.rows.length>200000)throw new TypeError('condition rows');const map=new Map();
  for(const row of c.rows){integer(row.id,0,g.nodes.length-1,'condition node');if(map.has(row.key)||!Array.isArray(row.cell)||row.cell.length!==3)throw new TypeError('condition row');if(row.cell[0]!==null)decimal(row.cell[0],true);decimal(row.cell[1]);integer(row.cell[2],0,3,'mask');map.set(row.key,row);}
  for(const row of c.rows)for(const child of [row.lo,row.hi])if(child!==null&&!map.has(child))throw new TypeError('missing condition child');
  if(!map.has(c.root))throw new TypeError('condition root');const get=k=>{work.saved_node_visits++;const x=map.get(k);if(!x)throw new Error('missing saved cell');return x;};
  return view(c.n,c.root,get,{required:c.required,forbidden:c.forbidden});
 }
 return {at,condition,openCondition,summary:()=>({n:g.n,nodes:g.nodes.length,scale:r.scale,roots:g.roots.map(x=>({n:x.n,...score(r.table[x.root])}))}),
  pageNodes:(start,limit)=>{integer(start,0,g.nodes.length,'start');integer(limit,0,256,'limit');return g.nodes.slice(start,start+limit).map((node,i)=>({id:start+i,node:node.slice(),cell:r.table[start+i].slice()}));},
  work:()=>copy(work),snapshot:()=>copy(r)};
}
module.exports={SCHEMA,CONDITION,compileWeights,openWeights};
