"use strict";
// Finite sum/product images. Pair images include diagonal pairs.
// No I/O; BigInt arithmetic is confined to compilation and requested query output.
const SCHEMA="commons.sum_product_subsets/v1";
const LIMITS=Object.freeze({host:20,digits:128,rows:250000,page:64,json_chars:12000000});
function fail(s){throw new Error(s);}
function integer(v){if(typeof v==="number"){if(!Number.isSafeInteger(v))fail("safe integer required");v=String(v);}
 if(typeof v!=="string"||! /^-?(0|[1-9][0-9]*)$/.test(v)||v.replace("-","").length>LIMITS.digits)fail("bounded decimal integer required");
 return BigInt(v).toString();}
function nat(v,max,name){if(!Number.isSafeInteger(v)||v<0||v>max)fail(name+" out of range");return v;}
function choose(n,k){let r=1;for(let i=1;i<=k;i++)r=r*(n-k+i)/i;return Math.round(r);}
function pop(n){let c=0;while(n){n&=n-1;c++;}return c;}
function copy(x){return JSON.parse(JSON.stringify(x));}
function input(host,k){
 if(!Array.isArray(host)||host.length>LIMITS.host)fail("host limit");
 const h=host.map(integer),b=h.map(BigInt);
 for(let i=1;i<b.length;i++)if(b[i-1]>=b[i])fail("host must be strictly increasing; duplicate entries are not multiplicities");
 nat(k,h.length,"cardinality");if(choose(h.length,k)>LIMITS.rows)fail("subset budget");
 return {h,b,k};
}
function compile(host,k){
 const {h,b}=input(host,k),n=h.length;
 const sums=[],products=[],sumMap=new Map(),productMap=new Map(),pairs=[],pairAt=Array.from({length:n},()=>Array(n));
 const stats={pair_additions:0,pair_multiplications:0,recursive_nodes:0,subset_rows:0,pair_insertions:0,pair_removals:0,histogram_rows:0};
 function intern(v,a,m){const s=v.toString();if(!m.has(s)){m.set(s,a.length);a.push(s);}return m.get(s);}
 for(let i=0;i<n;i++)for(let j=i;j<n;j++){
  const si=intern(b[i]+b[j],sums,sumMap),pi=intern(b[i]*b[j],products,productMap);
  stats.pair_additions++;stats.pair_multiplications++;
  pairAt[i][j]=pairAt[j][i]=pairs.length;pairs.push([i,j,(1<<i)|(1<<j),si,pi]);
 }
 // Sort retained value tables once and remap the dense indices.
 function sorted(a){const o=a.map((x,i)=>[BigInt(x),i]).sort((x,y)=>x[0]<y[0]?-1:x[0]>y[0]?1:0),r=[];
  o.forEach((x,i)=>r[x[1]]=i);return {values:o.map(x=>x[0].toString()),remap:r};}
 const ss=sorted(sums),pp=sorted(products);
 for(const p of pairs){p[3]=ss.remap[p[3]];p[4]=pp.remap[p[4]];}
 const sc=new Int32Array(sums.length),pc=new Int32Array(products.length),selected=[],rows=[],hist=new Map();
 let sn=0,pn=0,best=Infinity,winners=[];
 function visit(start,mask){
  stats.recursive_nodes++;
  if(selected.length===k){
   const id=rows.length;rows.push([mask,sn,pn]);stats.subset_rows++;
   const key=sn+","+pn;hist.set(key,(hist.get(key)||0)+1);
   const z=Math.max(sn,pn);if(z<best){best=z;winners=[id];}else if(z===best)winners.push(id);
   return;
  }
  const remaining=k-selected.length;
  for(let i=start;i<=n-remaining;i++){
   const ids=[pairAt[i][i],...selected.map(j=>pairAt[j][i])];
   for(const id of ids){const p=pairs[id];if(sc[p[3]]++===0)sn++;if(pc[p[4]]++===0)pn++;stats.pair_insertions++;}
   selected.push(i);visit(i+1,mask|(1<<i));selected.pop();
   for(const id of ids){const p=pairs[id];if(--sc[p[3]]===0)sn--;if(--pc[p[4]]===0)pn--;stats.pair_removals++;}
  }
 }
 visit(0,0);
 const histogram=[...hist].map(([key,c])=>[...key.split(",").map(Number),c]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
 const pareto=[];let minP=Infinity;
 for(const z of histogram)if(z[1]<minP){pareto.push(z.slice());minP=z[1];}
 stats.histogram_rows=histogram.length;
 return {schema:SCHEMA,host:h,k,ordering:"lexicographic increasing host-index tuples; zero-based ranks",
  pair_columns:["i","j","mask","sum_id","product_id"],row_columns:["mask","sum_count","product_count"],
  sum_values:ss.values,product_values:pp.values,pairs,rows,histogram,pareto,
  minimax:{value:best,row_ids:winners},stats};
}
function open(saved){
 let s;
 if(typeof saved==="string"){if(saved.length>LIMITS.json_chars)fail("snapshot size");s=JSON.parse(saved);}
 else {const t=JSON.stringify(saved);if(t.length>LIMITS.json_chars)fail("snapshot size");s=JSON.parse(t);}
 if(!s||s.schema!==SCHEMA)fail("snapshot schema");
 const {h,k}=input(s.host,s.k),n=h.length,maskLimit=(1<<n)-1,expected=choose(n,k),pairN=n*(n+1)/2;
 if(!Array.isArray(s.rows)||s.rows.length!==expected||!Array.isArray(s.pairs)||s.pairs.length!==pairN)fail("snapshot dimensions");
 for(const name of ["sum_values","product_values"]){
  const a=s[name];if(!Array.isArray(a)||a.length>pairN)fail("value table");let prev=null;
  for(const x of a){if(typeof x!=="string"||! /^-?(0|[1-9][0-9]*)$/.test(x)||x.replace("-","").length>2*LIMITS.digits+1)fail("value entry");
   const b=BigInt(x);if(b.toString()!==x||(prev!==null&&b<=prev))fail("value ordering");prev=b;}
 }
 let at=0;
 for(let i=0;i<n;i++)for(let j=i;j<n;j++){
  const p=s.pairs[at++];if(!Array.isArray(p)||p.length!==5||p[0]!==i||p[1]!==j||p[2]!==((1<<i)|(1<<j)))fail("pair structure");
  nat(p[3],s.sum_values.length-1,"sum id");nat(p[4],s.product_values.length-1,"product id");
 }
 const map=new Map();let prevIndices=null;
 function indices(mask){const a=[];for(let i=0;i<n;i++)if(mask&(1<<i))a.push(i);return a;}
 for(let r=0;r<s.rows.length;r++){
  const x=s.rows[r];if(!Array.isArray(x)||x.length!==3)fail("row");
  nat(x[0],maskLimit,"mask");if(pop(x[0])!==k||map.has(x[0]))fail("mask cardinality/duplicate");
  nat(x[1],k*(k+1)/2,"sum count");nat(x[2],k*(k+1)/2,"product count");
  const is=indices(x[0]);if(prevIndices){let d=0;while(d<k&&is[d]===prevIndices[d])d++;if(d===k||is[d]<prevIndices[d])fail("row order");}prevIndices=is;
  map.set(x[0],r);
 }
 function histCheck(a,name){if(!Array.isArray(a)||a.length>s.rows.length)fail(name);let prev=null;
  for(const x of a){if(!Array.isArray(x)||x.length!==3)fail(name);nat(x[0],k*(k+1)/2,name);nat(x[1],k*(k+1)/2,name);nat(x[2],s.rows.length,name);if(x[2]===0)fail(name);
   if(prev&&(x[0]<prev[0]||(x[0]===prev[0]&&x[1]<=prev[1])))fail(name+" ordering");prev=x;}}
 histCheck(s.histogram,"histogram");histCheck(s.pareto,"pareto");
 if(s.histogram.reduce((a,x)=>a+x[2],0)!==s.rows.length)fail("histogram partition size");
 nat(s.minimax.value,k*(k+1)/2,"minimum");
 function rowIds(a){if(!Array.isArray(a)||a.length>s.rows.length)fail("row ids");let p=-1;for(const x of a){nat(x,s.rows.length-1,"row id");if(x<=p)fail("row-id order");p=x;}}
 rowIds(s.minimax.row_ids);
 const stats={rows_indexed:s.rows.length,queries:0,rows_scanned:0,pairs_scanned:0,fibers_returned:0,pair_arithmetic:0,subset_enumerations:0,image_count_recomputations:0};
 function record(id){nat(id,s.rows.length-1,"rank");const r=s.rows[id],is=indices(r[0]);return {rank:id,mask:r[0],indices:is,values:is.map(i=>h[i]),sum_count:r[1],product_count:r[2],objective:Math.max(r[1],r[2])};}
 function pageIds(ids,start=0,limit=64){nat(start,ids.length,"start");nat(limit,LIMITS.page,"page size");return {total:ids.length,start,items:ids.slice(start,start+limit).map(record),next:start+limit<ids.length?start+limit:null};}
 function maskFromValues(values){
  if(!Array.isArray(values)||values.length!==k)fail("subset cardinality");
  let mask=0,prev=-1;
  for(const v of values){const i=h.indexOf(integer(v));if(i<0||i<=prev)fail("subset must follow increasing host order");mask|=1<<i;prev=i;}
  return mask;
 }
 function makeSlice(ids,criteria){return {schema:"commons.sum_product_slice/v1",host:h.slice(),k,criteria:copy(criteria),row_ids:ids};}
 function openSlice(savedSlice){
  const z=copy(savedSlice);if(z.schema!=="commons.sum_product_slice/v1"||z.k!==k||JSON.stringify(z.host)!==JSON.stringify(h))fail("slice binding");
  rowIds(z.row_ids);
  return {summary(){stats.queries++;return {count:z.row_ids.length,criteria:copy(z.criteria)};},
   page(start=0,limit=64){stats.queries++;return pageIds(z.row_ids,start,limit);},
   select(rank){stats.queries++;nat(rank,z.row_ids.length-1,"slice rank");return {slice_rank:rank,...record(z.row_ids[rank])};},
   rank(values){stats.queries++;const global=map.get(maskFromValues(values));let lo=0,hi=z.row_ids.length;while(lo<hi){const m=(lo+hi)>>1;if(z.row_ids[m]<global)lo=m+1;else hi=m;}return lo<z.row_ids.length&&z.row_ids[lo]===global?lo:null;},
   snapshot(){return copy(z);}
  };
 }
 const api={
  summary(){stats.queries++;return {host:h.slice(),cardinality:k,subsets:s.rows.length,host_pairs:s.pairs.length,
   host_sum_values:s.sum_values.length,host_product_values:s.product_values.length,histogram_rows:s.histogram.length,
   pareto:copy(s.pareto),minimax:{value:s.minimax.value,count:s.minimax.row_ids.length},constructor_stats:copy(s.stats)};},
  select(rank){stats.queries++;return record(rank);},
  rank(values){stats.queries++;return map.get(maskFromValues(values));},
  page(start=0,limit=64){stats.queries++;nat(start,s.rows.length,"start");nat(limit,LIMITS.page,"page size");
   return {total:s.rows.length,start,items:s.rows.slice(start,start+limit).map((_,i)=>record(start+i)),next:start+limit<s.rows.length?start+limit:null};},
  histogram(start=0,limit=64){stats.queries++;nat(start,s.histogram.length,"start");nat(limit,LIMITS.page,"page size");return {total:s.histogram.length,start,rows:copy(s.histogram.slice(start,start+limit)),next:start+limit<s.histogram.length?start+limit:null};},
  minimizers(){stats.queries++;return makeSlice(s.minimax.row_ids.slice(),{minimax:true});},
  filter(criteria={}){
   stats.queries++;const allowed=["sum_min","sum_max","product_min","product_max","objective_max","contains","excludes","pareto"];
   if(!criteria||typeof criteria!=="object"||Array.isArray(criteria)||Object.keys(criteria).some(x=>!allowed.includes(x)))fail("filter contract");
   const c=copy(criteria),cap=k*(k+1)/2;
   for(const key of ["sum_min","sum_max","product_min","product_max","objective_max"])if(c[key]!==undefined)nat(c[key],cap,key);
   if(c.pareto!==undefined&&typeof c.pareto!=="boolean")fail("pareto flag");
   function indexMask(a){if(a===undefined)return 0;if(!Array.isArray(a)||a.length>n)fail("index filter");let m=0;for(const i of a){nat(i,n-1,"host index");if(m&(1<<i))fail("duplicate index");m|=1<<i;}return m;}
   const incl=indexMask(c.contains),excl=indexMask(c.excludes),ps=new Set(s.pareto.map(x=>x[0]+","+x[1])),ids=[];
   for(let id=0;id<s.rows.length;id++){stats.rows_scanned++;const [mask,a,b]=s.rows[id];
    if((mask&incl)!==incl||(mask&excl)!==0)continue;
    if(c.sum_min!==undefined&&a<c.sum_min||c.sum_max!==undefined&&a>c.sum_max||c.product_min!==undefined&&b<c.product_min||c.product_max!==undefined&&b>c.product_max||c.objective_max!==undefined&&Math.max(a,b)>c.objective_max)continue;
    if(c.pareto&&!ps.has(a+","+b))continue;ids.push(id);}
   return makeSlice(ids,c);
  },
  openSlice,
  fibers(rank,kind){
   stats.queries++;nat(rank,s.rows.length-1,"rank");if(kind!=="sum"&&kind!=="product")fail("fiber kind");
   const mask=s.rows[rank][0],column=kind==="sum"?3:4,table=kind==="sum"?s.sum_values:s.product_values,groups=new Map();
   for(let id=0;id<s.pairs.length;id++){stats.pairs_scanned++;const p=s.pairs[id];if((mask&p[2])!==p[2])continue;
    const key=p[column];if(!groups.has(key))groups.set(key,{value:table[key],pair_ids:[],ordered_multiplicity:0});
    const g=groups.get(key);g.pair_ids.push(id);g.ordered_multiplicity+=p[0]===p[1]?1:2;}
   const fibers=[...groups].sort((a,b)=>a[0]-b[0]).map(x=>x[1]);stats.fibers_returned+=fibers.length;
   return {rank,kind,subset:record(rank),fiber_count:fibers.length,ordered_pairs:fibers.reduce((a,x)=>a+x.ordered_multiplicity,0),
    ordered_energy:fibers.reduce((a,x)=>a+x.ordered_multiplicity*x.ordered_multiplicity,0),fibers};
  },
  pairPage(start=0,limit=64){stats.queries++;nat(start,s.pairs.length,"start");nat(limit,LIMITS.page,"page size");
   return {total:s.pairs.length,start,rows:s.pairs.slice(start,start+limit).map((p,i)=>({id:start+i,indices:p.slice(0,2),values:[h[p[0]],h[p[1]]],sum:s.sum_values[p[3]],product:s.product_values[p[4]]})),next:start+limit<s.pairs.length?start+limit:null};},
  stats(){return copy(stats);},
  snapshot(){return copy(s);}
 };
 return api;
}
module.exports={compile,open,LIMITS,SCHEMA};
