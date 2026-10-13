'use strict';
// Exact unary Kleene-star lengths from an identified finite positive dictionary.
// One shortest-path compiler; saved-reader operations do not repeat it.
const SCHEMA='commons.unary_apery/v1';
const clone=x=>JSON.parse(JSON.stringify(x));
function nat(s,max=1200){if(typeof s!=='string'||!/^(0|[1-9][0-9]*)$/.test(s)||s.length>max)throw new TypeError('canonical nonnegative decimal string');return BigInt(s);}
function gcd(a,b){while(b){const t=a%b;a=b;b=t;}return a;}
function num(x,lo,hi){if(!Number.isSafeInteger(x)||x<lo||x>hi)throw new RangeError('integer range');return x;}
function compileUnary(input){
 if(!input||!input.premise||!Array.isArray(input.alphabet)||input.alphabet.length!==1||input.alphabet[0]!=='0'||!Array.isArray(input.lengths)||input.lengths.length<1||input.lengths.length>64)throw new TypeError('identified nonempty dictionary');
 const a=input.lengths.map(s=>nat(s,100));let previous=0n,g=0n;for(const x of a){if(x<=previous)throw new RangeError('strictly increasing positive lengths');previous=x;g=gcd(g,x);}
 const b=a.map(x=>x/g),mBig=b[0];if(mBig>4096n)throw new RangeError('normalized minimum at most 4096');const m=Number(mBig);if(m*a.length>262144)throw new RangeError('edge cap');
 const distance=Array(m).fill(null),parent=Array(m).fill(null),done=Array(m).fill(false),settled=[];
 const work={gcd_inputs:a.length,selection_candidates:0,edge_relaxations:0,successful_relaxations:0,certificate_edges:0,witness_products:0,integers_enumerated:0};
 distance[0]=0n;
 for(let step=0;step<m;step++){
  let u=-1;for(let r=0;r<m;r++){work.selection_candidates++;if(!done[r]&&distance[r]!==null&&(u<0||distance[r]<distance[u]))u=r;}
  if(u<0)throw new Error('normalized residue graph unexpectedly disconnected');
  done[u]=true;settled.push(u);
  for(let j=0;j<b.length;j++){const v=Number((BigInt(u)+b[j])%mBig),candidate=distance[u]+b[j];work.edge_relaxations++;
   if(distance[v]===null||candidate<distance[v]){distance[v]=candidate;parent[v]={residue:u,generator:j};work.successful_relaxations++;}}
 }
 const counts=Array(m);counts[0]=Array(a.length).fill(0n);
 for(const r of settled){if(r===0)continue;const p=parent[r];if(!p||!counts[p.residue])throw new Error('parent order');counts[r]=counts[p.residue].slice();counts[r][p.generator]++;}
 const rows=distance.map((d,r)=>{
  let value=0n;for(let j=0;j<b.length;j++){value+=counts[r][j]*b[j];work.witness_products++;}
  if(value!==d||d%mBig!==BigInt(r))throw new Error('residue witness mismatch');
  return {residue:r,distance:String(d),parent:parent[r],counts:counts[r].map(String),missing_count:String((d-BigInt(r))/mBig)};
 });
 const edges=[];for(let u=0;u<m;u++)for(let j=0;j<b.length;j++){
  const v=Number((BigInt(u)+b[j])%mBig),slack=distance[u]+b[j]-distance[v];if(slack<0n)throw new Error('negative certificate slack');
  edges.push([u,j,v,String(slack)]);work.certificate_edges++;
 }
 const maximum=distance.reduce((a,b)=>a>b?a:b),frobenius=maximum-mBig,conductor=frobenius+1n;
 const genus=rows.reduce((s,r)=>s+BigInt(r.missing_count),0n);
 return {schema:SCHEMA,input:clone(input),gcd:String(g),normalized_lengths:b.map(String),modulus:m,settled,rows,edges,
  normalized:{frobenius:String(frobenius),conductor:String(conductor),missing_count:String(genus)},work};
}
function openUnary(saved,options={}){
 const r=clone(saved);if(r.schema!==SCHEMA)throw new TypeError('schema');
 const baseG=nat(r.gcd,100),dilation=nat(options.dilation===undefined?'1':options.dilation,100);if(baseG===0n||dilation===0n)throw new RangeError('positive gcd/dilation');
 const g=baseG*dilation,m=num(r.modulus,1,4096),M=BigInt(m),a=r.input.lengths.map(x=>nat(x,100)*dilation),b=r.normalized_lengths.map(x=>nat(x,100));
 if(!Array.isArray(r.rows)||r.rows.length!==m||a.length!==b.length)throw new TypeError('shape');
 const distances=[],counts=[];for(let i=0;i<m;i++){const row=r.rows[i];if(row.residue!==i||row.counts.length!==a.length)throw new TypeError('row');distances.push(nat(row.distance));counts.push(row.counts.map(x=>nat(x)));}
 const genus=nat(r.normalized.missing_count),C=nat(r.normalized.conductor),F=BigInt(r.normalized.frobenius);
 const work={residue_count_terms:0,rank_search_steps:0,witness_products:0,saved_row_reads:0,shortest_path_relaxations:0,certificate_edges_rechecked:0};
 function representedUpTo(t){if(t<0n)return 0n;const q=t/g;let total=0n;for(const d of distances){work.residue_count_terms++;if(q>=d)total+=(q-d)/M+1n;}return total;}
 function missingUpTo(t){return t<0n?0n:t+1n-representedUpTo(t);}
 function membership(length){
  const n=nat(length);if(n%g!==0n)return {length,represented:false,reason:'not_divisible_by_gcd',gcd:String(g),remainder:String(n%g)};
  const q=n/g,residue=Number(q%M),d=distances[residue];work.saved_row_reads++;
  if(q<d)return {length,represented:false,reason:'below_apery_minimum',normalized_length:String(q),residue,minimum:String(d),deficit:String(d-q)};
  return {length,represented:true,normalized_length:String(q),residue,minimum:String(d),extra_minimum_generators:String((q-d)/M)};
 }
 function decompose(length){
  const result=membership(length);if(!result.represented)return result;
  const c=counts[result.residue].slice();c[0]+=BigInt(result.extra_minimum_generators);let total=0n;
  for(let j=0;j<c.length;j++){total+=c[j]*a[j];work.witness_products++;}
  if(total!==BigInt(length))throw new Error('saved decomposition mismatch');
  return {...result,generator_lengths:a.map(String),multiplicities:c.map(String),number_of_dictionary_words:String(c.reduce((x,y)=>x+y,0n)),reconstructed_length:String(total)};
 }
 function summary(){return {alphabet:['0'],generator_lengths:a.map(String),dilation:String(dilation),gcd:String(g),modulus:m,
  complement_finite:g===1n,frobenius:g===1n?String(F):null,conductor:g===1n?String(C):null,missing_count:g===1n?String(genus):null,
  normalized:{frobenius:String(F),conductor:String(C),missing_count:String(genus)},empty_word_represented:true};}
 function count(length){const t=nat(length),represented=representedUpTo(t);return {through:length,represented:String(represented),missing:String(t+1n-represented),domain:'all nonnegative lengths, including zero'};}
 function interval(lo,hi){const l=nat(lo),h=nat(hi);if(l>h)throw new RangeError('interval');const represented=representedUpTo(h)-representedUpTo(l-1n);return {lo,hi,represented:String(represented),missing:String(h-l+1n-represented)};}
 function select(kind,rank){
  const k=nat(rank);if(kind==='missing'&&g===1n&&k>=genus)throw new RangeError('missing rank');
  let lo=0n,hi=kind==='represented'?g*M*k:g===1n?F:g*(k+1n),steps=0;
  if(String(hi).length>1200)throw new RangeError('selected length search exceeds 1200-digit cap');
  const total=t=>kind==='represented'?representedUpTo(t):missingUpTo(t);
  while(lo<hi){const mid=(lo+hi)/2n;if(total(mid)>k)hi=mid;else lo=mid+1n;steps++;work.rank_search_steps++;}
  const before=total(lo-1n),through=total(lo);if(before!==k||through!==k+1n)throw new Error('rank boundary');
  return {kind,rank,length:String(lo),before_count:String(before),through_count:String(through),search_steps:steps,membership:membership(String(lo))};
 }
 function rank(kind,length){const n=nat(length),mem=membership(length);if(mem.represented!==(kind==='represented'))throw new RangeError('wrong family');return {kind,length,rank:String(kind==='represented'?representedUpTo(n-1n):missingUpTo(n-1n)),membership:mem};}
 function pageMissing(start,limit){let k=nat(start);num(limit,0,256);if(g===1n&&k>genus)throw new RangeError('page start');const rows=[];while(rows.length<limit&&(g!==1n||k<genus))rows.push(select('missing',String(k++)));return {start,total:g===1n?String(genus):null,next:g===1n&&k===genus?null:String(k),rows};}
 function gapRuns(){const runs=[];for(let i=0;i<m;i++){const d=distances[i],n=(d-BigInt(i))/M;work.saved_row_reads++;if(n)runs.push({residue:i,first:String(g*BigInt(i)),step:String(g*M),count:String(n),last:String(g*(d-M))});}
  return {finite_runs:runs,additional_infinite_family:g===1n?null:{predicate:'n mod gcd != 0',gcd:String(g)}};}
 function pageRows(start,limit){num(start,0,m);num(limit,0,256);return clone(r.rows.slice(start,start+limit));}
 return {summary,membership,decompose,count,interval,
  selectMissing:k=>select('missing',k),selectRepresented:k=>select('represented',k),
  rankMissing:n=>rank('missing',n),rankRepresented:n=>rank('represented',n),
  pageMissing,gapRuns,pageRows,work:()=>clone(work),snapshot:()=>clone(r)};
}
module.exports={SCHEMA,compileUnary,openUnary};
