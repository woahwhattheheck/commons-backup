"use strict";
// Exact finite reciprocal subset sums; the supplied prime identities are premises.
const SCHEMA="reciprocal-subset-sums/v1";
const copy=x=>JSON.parse(JSON.stringify(x));
function fail(s){throw new TypeError(s);}
function integer(s,label,signed=false){if(typeof s!=="string"||s.length>2048||!(signed?/^(0|-?[1-9][0-9]*)$/:/^(0|[1-9][0-9]*)$/).test(s))fail(label+" must be a canonical decimal string");return BigInt(s);}
function natural(x,max,label){if(!Number.isSafeInteger(x)||x<0||x>max)fail(label+" outside its bound");return x;}
function gcd(a,b){a=a<0n?-a:a;while(b){const r=a%b;a=b;b=r;}return a;}
function rational(x){if(!x||typeof x!=="object")fail("rational object required");const n=integer(x.n,"numerator",true),d=integer(x.d,"denominator");if(d===0n)fail("zero denominator");return {n,d};}
function floorDiv(a,b){let q=a/b;if(a<0n&&a%b!==0n)q--;return q;}
function ceilDiv(a,b){return -floorDiv(-a,b);}
function fraction(n,d){const g=gcd(n,d);return {n:String(n/g),d:String(d/g)};}
function compile(input){
 if(!input||!Array.isArray(input.primes)||input.primes.length<1||input.primes.length>24)fail("one to 24 supplied primes required");
 const p=input.primes.map(x=>integer(x,"prime"));let last=1n;
 for(const x of p){if(x<=last||x>1000000n)fail("strictly increasing supplied primes between 2 and 1000000 required");last=x;}
 if(!input.provenance||typeof input.provenance!=="object")fail("identified prime premise required");
 const work={prime_product_multiplications:0,weight_divisions:0,half_sum_additions:0,sort_comparisons:0,primality_tests:0,old_valuation_work:0,old_product_table_work:0};
 let D=1n;const product_prefixes=["1"];for(const x of p){D*=x;work.prime_product_multiplications++;product_prefixes.push(String(D));}
 const weights=p.map(x=>{work.weight_divisions++;return D/x;});
 const split=Math.floor(p.length/2);
 const halves=[[0,split],[split,p.length]].map(([start,end])=>{
   let rows=[[0,0n]];
   for(let j=start;j<end;j++){const len=rows.length;for(let i=0;i<len;i++){rows.push([rows[i][0]+2**(j-start),rows[i][1]+weights[j]]);work.half_sum_additions++;}}
   rows.sort((a,b)=>{work.sort_comparisons++;return a[1]<b[1]?-1:a[1]>b[1]?1:0;});
   for(let i=1;i<rows.length;i++)if(rows[i-1][1]===rows[i][1])fail("supplied prime premise contradicts half-sum uniqueness");
   return {start,count:end-start,rows:rows.map(([mask,sum])=>[mask,String(sum)])};
 });
 return {schema:SCHEMA,primes:p.map(String),provenance:copy(input.provenance),denominator:String(D),weights:weights.map(String),product_prefixes,split,total_subsets:String(2**p.length),maximum_numerator:String(halves.reduce((s,h)=>s+BigInt(h.rows.at(-1)[1]),0n)),halves,work};
}
function openIndex(saved){
 if(!saved||saved.schema!==SCHEMA)fail("unsupported schema");
 const data=copy(saved),p=data.primes;if(!Array.isArray(p)||p.length<1||p.length>24)fail("bad prime count");
 let last=1n;for(const x of p){const q=integer(x,"prime");if(q<=last||q>1000000n)fail("bad supplied primes");last=q;}
 const D=integer(data.denominator,"denominator");if(D<2n)fail("bad denominator");
 const split=Math.floor(p.length/2);if(data.split!==split||data.total_subsets!==String(2**p.length))fail("bad subset metadata");
 if(!Array.isArray(data.weights)||data.weights.length!==p.length)fail("bad weights");data.weights.forEach(x=>integer(x,"weight"));
 if(!Array.isArray(data.halves)||data.halves.length!==2)fail("two halves required");
 const work={queries:0,rows_loaded:0,condition_rows_scanned:0,conditions_created:0,condition_cache_hits:0,threshold_scans:0,threshold_left_rows:0,pair_comparisons:0,count_cache_hits:0,bisection_steps:0,pair_search_steps:0,witness_pair_additions:0,rank_pair_additions:0,returned_records:0,prime_product_multiplications:0,weight_divisions:0,half_sum_additions:0,sort_comparisons:0,primality_tests:0,old_valuation_work:0,old_product_table_work:0};
 const halves=data.halves.map((h,k)=>{
  const start=k===0?0:split,count=k===0?split:p.length-split,len=2**count;
  if(h.start!==start||h.count!==count||!Array.isArray(h.rows)||h.rows.length!==len)fail("bad half dimensions");
  const byMask=new Array(len);let prev=-1n;
  const rows=h.rows.map((r,i)=>{if(!Array.isArray(r)||r.length!==2)fail("bad row");const mask=natural(r[0],len-1,"mask"),sum=integer(r[1],"sum");if(sum<=prev||byMask[mask]!==undefined)fail("bad order or repeated mask");prev=sum;const v={mask,sum,index:i};byMask[mask]=v;work.rows_loaded++;return v;});
  if(rows[0].mask!==0||rows[0].sum!==0n||rows.at(-1).mask!==len-1)fail("bad half endpoints");
  return {start,count,rows,byMask};
 });
 const maximum=integer(data.maximum_numerator,"maximum");if(halves[0].rows.at(-1).sum+halves[1].rows.at(-1).sum!==maximum)fail("bad maximum");
 const conditions=new Map(),conditionLimit=16;
 function normalize(f={}){
  if(!f||typeof f!=="object"||Array.isArray(f))fail("filter object required");
  for(const k of Object.keys(f))if(k!=="required"&&k!=="excluded")fail("unknown filter field");
  const list=(x,label)=>{if(x===undefined)return [];if(!Array.isArray(x))fail(label+" must be an array");return [...new Set(x.map(i=>natural(i,p.length-1,label)))].sort((a,b)=>a-b);};
  const required=list(f.required,"required index"),excluded=list(f.excluded,"excluded index");
  return {required,excluded};
 }
 function condition(f){
  const filter=normalize(f),key=JSON.stringify(filter);
  if(conditions.has(key)){work.condition_cache_hits++;return conditions.get(key);}
  if(conditions.size===conditionLimit)fail("at most 16 distinct conditions per reader");
  const conflict=filter.required.some(i=>filter.excluded.includes(i));
  const lists=halves.map(h=>{
   const req=filter.required.filter(i=>i>=h.start&&i<h.start+h.count).reduce((m,i)=>m+2**(i-h.start),0);
   const exc=filter.excluded.filter(i=>i>=h.start&&i<h.start+h.count).reduce((m,i)=>m+2**(i-h.start),0);
   if(conflict)return [];
   if(req===0&&exc===0)return h.rows;
   return h.rows.filter(r=>{work.condition_rows_scanned++;return (r.mask&req)===req&&(r.mask&exc)===0;});
  });
  const c={key,filter,lists,total:lists[0].length*lists[1].length,cache:new Map()};conditions.set(key,c);work.conditions_created++;return c;
 }
 function count(c,z,frontier=false){
  if(!frontier&&c.cache.has(String(z))){work.count_cache_hits++;return {count:c.cache.get(String(z))};}
  const [L,R]=c.lists;let j=R.length-1,total=0;const cuts=frontier?new Array(L.length).fill(0):null;
  work.threshold_scans++;
  for(let i=0;i<L.length;i++){work.threshold_left_rows++;while(j>=0){work.pair_comparisons++;if(L[i].sum+R[j].sum<=z)break;j--;}if(j<0)break;total+=j+1;if(cuts)cuts[i]=j+1;}
  if(c.cache.size>=512)c.cache.delete(c.cache.keys().next().value);c.cache.set(String(z),total);
  return {count:total,...(cuts?{cutoffs:cuts,left_indices:L.map(r=>r.index),right_indices:R.map(r=>r.index)}:{})};
 }
 function find(c,z){
  const [L,R]=c.lists;let i=0,j=R.length-1;
  while(i<L.length&&j>=0){work.pair_search_steps++;const sum=L[i].sum+R[j].sum;if(sum===z)return [L[i],R[j]];if(sum<z)i++;else j--;}
  return null;
 }
 function witness(pair){
  const [a,b]=pair,z=a.sum+b.sum;work.witness_pair_additions++;
  const mask=a.mask+b.mask*2**split,indices=[];for(let i=0;i<p.length;i++)if(mask&2**i)indices.push(i);
  const gap=D-z,m=gap>0n&&D%gap===0n?D/gap:null;work.returned_records++;
  return {mask,indices,primes:indices.map(i=>p[i]),cardinality:indices.length,left_row:a.index,right_row:b.index,numerator:String(z),denominator:String(D),sum:fraction(z,D),gap:fraction(gap,D),primary_pseudoperfect_denominator:m!==null&&m>=2n?String(m):null};
 }
 function select(c,rank){
  natural(rank,c.total-1,"rank");if(c.total===0)fail("empty family");
  const [L,R]=c.lists;let lo=L[0].sum+R[0].sum,hi=L.at(-1).sum+R.at(-1).sum;const bounds=[String(lo),String(hi)],steps=[];
  while(lo<hi){const mid=(lo+hi)/2n,n=count(c,mid).count;steps.push([String(mid),n]);work.bisection_steps++;if(n<=rank)lo=mid+1n;else hi=mid;}
  const pair=find(c,lo);if(!pair)fail("saved tables contradict selection");return {rank,filter:c.filter,total:c.total,...witness(pair),selection:{initial_bounds:bounds,steps}};
 }
 function maskPair(indices){
  if(!Array.isArray(indices))fail("indices required");const clean=[...new Set(indices.map(i=>natural(i,p.length-1,"index")))].sort((a,b)=>a-b);
  let a=0,b=0;for(const i of clean)if(i<split)a+=2**i;else b+=2**(i-split);
  return {indices:clean,pair:[halves[0].byMask[a],halves[1].byMask[b]]};
 }
 function query(q){
  if(!q||typeof q!=="object")fail("query required");work.queries++;
  if(q.op==="summary")return {schema:SCHEMA,prime_count:p.length,primes:p,total_subsets:data.total_subsets,half_rows:halves.map(h=>h.rows.length),denominator:String(D),maximum:fraction(maximum,D),construction_work:data.work,order:"Increasing exact reciprocal sum; zero-based ranks."};
  if(q.op==="half"){const side=natural(q.side,1,"side"),start=natural(q.start??0,halves[side].rows.length,"start"),limit=natural(q.limit??20,100,"limit");return {side,start,rows:data.halves[side].rows.slice(start,start+limit)};}
  if(q.op==="conditions")return [...conditions.values()].map(c=>({filter:c.filter,total:c.total,left_indices:c.lists[0].map(r=>r.index),right_indices:c.lists[1].map(r=>r.index),cached_counts:[...c.cache].map(([z,n])=>[z,n])}));
  const c=condition(q.filter);
  if(q.op==="family")return {filter:c.filter,total:c.total,half_rows:c.lists.map(r=>r.length)};
  if(q.op==="range"){
   const a=rational(q.lower),b=rational(q.upper);if(a.n*b.d>b.n*a.d)fail("reversed interval");
   const low=ceilDiv(a.n*D,a.d),high=floorDiv(b.n*D,b.d);
   const below=count(c,low-1n,q.frontier===true),through=count(c,high,q.frontier===true);
   return {filter:c.filter,lower:q.lower,upper:q.upper,integer_bounds:[String(low),String(high)],count:through.count-below.count,below,through};
  }
  if(q.op==="select")return select(c,q.rank);
  if(q.op==="rank"){
   const v=maskPair(q.indices),allowed=c.filter.required.every(i=>v.indices.includes(i))&&!c.filter.excluded.some(i=>v.indices.includes(i));
   if(!allowed)return {status:"outside_filter",filter:c.filter,indices:v.indices};
   const z=v.pair[0].sum+v.pair[1].sum;work.rank_pair_additions++;return {status:"found",rank:count(c,z-1n).count,filter:c.filter,total:c.total,...witness(v.pair)};
  }
  if(q.op==="target"){
   const m=integer(q.m,"m");if(m<2n)fail("m must be at least 2");
   if(D%m!==0n)return {status:"absent",reason:"reduced target denominator does not divide supplied common denominator",m:String(m),filter:c.filter};
   const z=D-D/m,pair=find(c,z);return pair?{status:"found",m:String(m),filter:c.filter,rank:count(c,z-1n).count,...witness(pair)}:{status:"absent",reason:"no half-pair at target",m:String(m),filter:c.filter};
  }
  if(q.op==="locate"){
   const f=rational(q.value),z=floorDiv(f.n*D,f.d),exact=f.n*D%f.d===0n;
   const less=count(c,exact?z-1n:z).count,pair=exact?find(c,z):null;
   return {filter:c.filter,value:q.value,less,equal:pair?1:0,greater:c.total-less-(pair?1:0),witness:pair?witness(pair):null};
  }
  fail("unknown operation");
 }
 return Object.freeze({query,stats:()=>({...work,condition_count:conditions.size,cached_thresholds:[...conditions.values()].reduce((s,c)=>s+c.cache.size,0)})});
}
module.exports={compile,openIndex};
