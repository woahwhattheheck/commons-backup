"use strict";
// Finite-host subset-sum fibers and minimal equal-sum obstruction supports.
// Supplied low-order sums are explicit premises and are not recomputed.
const VERSION="1.0.0",SCHEMA="commons.subset-sum-obstruction-index.v1";
const MAX_N=16,MAX_JSON=20000000;
function fail(s){throw new Error(s);}
function copy(x){return JSON.parse(JSON.stringify(x));}
function integer(x,name,lo,hi){if(!Number.isSafeInteger(x)||x<lo||x>hi)fail(name+" outside bounds");return x;}
function decimal(x,name,digits=130){
 if(typeof x==="bigint")x=x.toString();
 if(typeof x==="number"){integer(x,name,0,Number.MAX_SAFE_INTEGER);x=String(x);}
 if(typeof x!=="string"||!/^(0|[1-9][0-9]*)$/.test(x)||x.length>digits)fail(name+" requires canonical nonnegative decimal");
 return BigInt(x);
}
function pop(x){let n=0;for(;x;x&=x-1)n++;return n;}
function indices(mask,n){const a=[];for(let i=0;i<n;i++)if(mask&(1<<i))a.push(i);return a;}
function valuesInput(raw){
 if(!Array.isArray(raw)||raw.length>MAX_N)fail("at most 16 values required");
 const values=raw.map(x=>decimal(x,"value",128));let last=0n;
 for(const x of values){if(x<=last)fail("values must be strictly increasing and positive");last=x;}
 return values;
}
function compileSubsetObstructions(input,options={}){
 const start=Date.now();if(!input||typeof input!=="object")fail("input object required");
 const values=valuesInput(input.values),n=values.length,total=1<<n,full=total-1;
 const budget=options.collision_pair_budget===undefined?1000000:
  integer(options.collision_pair_budget,"collision_pair_budget",1,5000000);
 const sums=Array(total).fill(null),sizes=Array(total).fill(0),origins=Array(total).fill(0);
 const work={precomputed_rows_imported:0,literal_sums_assigned:0,new_subset_additions:0,
  collision_pairs_examined:0,cancelled_support_equality_checks:0,
  downward_classification_checks:0,maximality_extension_checks:0,
  old_pair_or_triple_additions:0,old_B3_or_field_evaluations:0};
 if(input.precomputed_sums!==undefined){
  if(!Array.isArray(input.precomputed_sums)||input.precomputed_sums.length>total)fail("precomputed row shape");
  const through=integer(input.precomputed_through,"precomputed_through",0,n);
  for(const r of input.precomputed_sums){
   const s=integer(r.mask,"precomputed mask",0,full);
   if(pop(s)>through||sums[s]!==null)fail("duplicate or out-of-degree precomputed row");
   sums[s]=decimal(r.sum,"precomputed sum");origins[s]=1;work.precomputed_rows_imported++;
  }
  for(let s=0;s<total;s++)if(pop(s)<=through&&sums[s]===null)fail("complete declared low-order sum layer required");
 }
 for(let s=0;s<total;s++){
  sizes[s]=pop(s);
  if(s===0){
   if(sums[s]!==null&&sums[s]!==0n)fail("empty sum premise mismatch");
   if(sums[s]===null){sums[s]=0n;work.literal_sums_assigned++;}
  }else if(sizes[s]===1){
   const v=31-Math.clz32(s);
   if(sums[s]!==null&&sums[s]!==values[v])fail("singleton premise mismatch");
   if(sums[s]===null){sums[s]=values[v];work.literal_sums_assigned++;}
  }else if(sums[s]===null){
   const bit=s&-s,v=31-Math.clz32(bit);
   sums[s]=sums[s^bit]+values[v];origins[s]=2;work.new_subset_additions++;
  }
 }
 const grouped=new Map();
 for(let s=0;s<total;s++){const key=sums[s].toString();if(!grouped.has(key))grouped.set(key,[]);grouped.get(key).push(s);}
 const fibers=[...grouped].map(([sum,masks])=>({sum,masks})).sort((a,b)=>BigInt(a.sum)<BigInt(b.sum)?-1:1);
 const relations=Array(total).fill(null);
 for(const f of fibers)for(let i=0;i<f.masks.length;i++)for(let j=i+1;j<f.masks.length;j++){
  if(++work.collision_pairs_examined>budget)fail("collision-pair budget exceeded; no partial snapshot returned");
  const a=f.masks[i],b=f.masks[j];let left=a&~b,right=b&~a;
  if(left>right){const t=left;left=right;right=t;}
  if(!left||!right)fail("positive-sum premise inconsistent after cancellation");
  const support=left|right;
  if(!relations[support])relations[support]={support,left,right,fiber_pair_occurrences:0};
  const r=relations[support];r.fiber_pair_occurrences++;
  if(left<r.left||(left===r.left&&right<r.right)){r.left=left;r.right=right;}
 }
 const supportRows=[];
 for(let s=1;s<total;s++)if(relations[s]){
  const r=relations[s];
  if(sums[r.left]!==sums[r.right])fail("cancelled stored equality inconsistent with supplied sums");
  work.cancelled_support_equality_checks++;
  r.equal_sum=sums[r.left].toString();supportRows.push(r);
 }
 const bad=Array(total).fill(0),minimal=[],goodBySize=Array.from({length:n+1},()=>[]);
 goodBySize[0].push(0);
 for(let s=1;s<total;s++){
  for(let bits=s;bits;bits&=bits-1){
   const bit=bits&-bits;work.downward_classification_checks++;
   if(bad[s^bit]){bad[s]=bad[s^bit];break;}
  }
  if(!bad[s]&&relations[s]){bad[s]=s;minimal.push(s);}
  if(!bad[s])goodBySize[sizes[s]].push(s);
 }
 const maximal=[];
 for(let s=0;s<total;s++)if(!bad[s]){
  let canExtend=false;
  for(let bits=full^s;bits;bits&=bits-1){
   work.maximality_extension_checks++;
   if(!bad[s|(bits&-bits)]){canExtend=true;break;}
  }
  if(!canExtend)maximal.push(s);
 }
 let maximum=n;while(maximum>0&&!goodBySize[maximum].length)maximum--;
 const histogram=new Map();for(const f of fibers)histogram.set(f.masks.length,(histogram.get(f.masks.length)||0)+1);
 return {schema:SCHEMA,version:VERSION,values:values.map(String),provenance:copy(input.provenance||{}),
  inherited_sums:input.precomputed_sums===undefined?null:{through:input.precomputed_through,rows:copy(input.precomputed_sums),
   premise:"supplied sums imported without pair/triple arithmetic; empty and singleton identities checked"},
  sizes,subset_sums:sums.map(String),sum_origin_codes:origins,
  origin_encoding:{literal:0,inherited:1,new_addition:2},
  fibers,support_rows:supportRows,minimal_support_masks:minimal,bad_support_by_mask:bad,
  good_masks_by_size:goodBySize,maximal_good_masks:maximal,
  summary:{host_size:n,host_maximum:n?values[n-1].toString():null,subset_count:total,
   distinct_sums:fibers.length,collision_pairs:work.collision_pairs_examined,
   relation_supports:supportRows.length,minimal_relation_supports:minimal.length,
   good_counts_by_size:goodBySize.map(x=>x.length),good_subsets:goodBySize.reduce((a,x)=>a+x.length,0),
   maximum_good_size:maximum,maximum_good_count:goodBySize[maximum].length,
   first_maximum_mask:goodBySize[maximum][0],last_maximum_mask:goodBySize[maximum].at(-1),
   inclusion_maximal_good_count:maximal.length,
   fiber_multiplicity_histogram:[...histogram].sort((a,b)=>a[0]-b[0]).map(([multiplicity,fibers])=>({multiplicity,fibers}))},
  ordering:{subsets:"numeric bit mask",fibers:"increasing exact sum; masks increasing within fiber",
   witness:"one canonical left/right mask per support; common intersection cancelled",
   family:"all sum-distinct subfamilies of the supplied finite host, not all positive-integer sets"},
  construction:{...work,collision_pair_budget:budget,elapsed_ms_observation:Date.now()-start}};
}
function openSubsetObstructions(value){
 if(typeof value==="string"){if(value.length>MAX_JSON)fail("snapshot JSON limit");value=JSON.parse(value);}
 const text=JSON.stringify(value);if(text.length>MAX_JSON)fail("snapshot JSON limit");const s=JSON.parse(text);
 if(!s||s.schema!==SCHEMA||s.version!==VERSION)fail("unsupported snapshot");
 const values=valuesInput(s.values),n=values.length,total=1<<n,full=total-1;
 for(const name of ["sizes","subset_sums","sum_origin_codes","bad_support_by_mask"])
  if(!Array.isArray(s[name])||s[name].length!==total)fail("complete "+name+" required");
 for(let mask=0;mask<total;mask++){
  if(s.sizes[mask]!==pop(mask))fail("saved size mismatch");
  decimal(s.subset_sums[mask],"saved sum");integer(s.sum_origin_codes[mask],"origin code",0,2);
 }
 if(s.subset_sums[0]!=="0")fail("empty sum identity");
 for(let i=0;i<n;i++)if(s.subset_sums[1<<i]!==values[i].toString())fail("singleton identity");
 if(!Array.isArray(s.fibers))fail("fiber array required");
 const seen=Array(total).fill(false);let previous=-1n;
 for(const f of s.fibers){
  const sum=decimal(f.sum,"fiber sum");if(sum<=previous||!Array.isArray(f.masks)||!f.masks.length)fail("fiber ordering");
  previous=sum;let prior=-1;
  for(const mask of f.masks){
   integer(mask,"fiber mask",0,full);
   if(mask<=prior||seen[mask]||s.subset_sums[mask]!==f.sum)fail("fiber coverage/binding");
   prior=mask;seen[mask]=true;
  }
 }
 if(seen.some(x=>!x))fail("incomplete fiber coverage");
 if(!Array.isArray(s.support_rows)||!Array.isArray(s.minimal_support_masks))fail("support rows required");
 const relationMap=new Map();let old=0,witnessChecks=0;
 for(const r of s.support_rows){
  integer(r.support,"support",1,full);integer(r.left,"left",1,full);integer(r.right,"right",1,full);
  if(r.support<=old||r.left>=r.right||(r.left&r.right)!==0||(r.left|r.right)!==r.support||
    s.subset_sums[r.left]!==s.subset_sums[r.right]||r.equal_sum!==s.subset_sums[r.left])fail("saved relation witness");
  integer(r.fiber_pair_occurrences,"fiber pair occurrences",1,Number.MAX_SAFE_INTEGER);
  relationMap.set(r.support,r);old=r.support;witnessChecks++;
 }
 const minimalSet=new Set();old=0;
 for(const mask of s.minimal_support_masks){
  if(!relationMap.has(mask)||mask<=old)fail("minimal support reference");
  old=mask;minimalSet.add(mask);
 }
 if(!Array.isArray(s.good_masks_by_size)||s.good_masks_by_size.length!==n+1||
    !Array.isArray(s.maximal_good_masks))fail("good-family shape");
 const goodSeen=Array(total).fill(false);
 for(let size=0;size<=n;size++){
  const list=s.good_masks_by_size[size];if(!Array.isArray(list))fail("good size list");old=-1;
  for(const mask of list){
   integer(mask,"good mask",0,full);
   if(mask<=old||s.sizes[mask]!==size||s.bad_support_by_mask[mask]!==0)fail("good family binding");
   goodSeen[mask]=true;old=mask;
  }
 }
 for(let mask=0;mask<total;mask++){
  const witness=integer(s.bad_support_by_mask[mask],"bad support",0,full);
  if(witness&&(!minimalSet.has(witness)||(witness&mask)!==witness))fail("bad support reference");
  if(goodSeen[mask]!==!witness)fail("complete good-family coverage");
 }
 old=-1;for(const mask of s.maximal_good_masks){
  integer(mask,"maximal mask",0,full);
  if(mask<=old||!goodSeen[mask])fail("maximal family reference");old=mask;
 }
 const maximalSet=new Set(s.maximal_good_masks),cache=new Map();
 const stats={opened_subset_cells:total,opened_fibers:s.fibers.length,
  saved_relation_equalities_checked:witnessChecks,queries:0,
  family_filter_scans:0,family_filter_cache_hits:0,fiber_search_steps:0,
  fiber_masks_inspected:0,subset_masks_materialized:0,
  new_subset_additions:0,collision_pair_replays:0,obstruction_closure_replays:0,
  old_pair_or_triple_additions:0,old_B3_or_field_evaluations:0};
 function mask(x){return integer(x,"mask",0,full);}
 function describe(x){return {mask:x,indices:indices(x,n),values:indices(x,n).map(i=>s.values[i]),
  size:s.sizes[x],sum:s.subset_sums[x],sum_distinct:s.bad_support_by_mask[x]===0,
  obstruction_support:s.bad_support_by_mask[x]||null};}
 function witness(x){const r=relationMap.get(x);return r?{...copy(r),left_values:indices(r.left,n).map(i=>s.values[i]),
  right_values:indices(r.right,n).map(i=>s.values[i])}:null;}
 function filter(query={}){
  const size=query.size===undefined||query.size===null?null:integer(query.size,"size",0,n);
  const contains=query.contains===undefined?0:mask(query.contains),excludes=query.excludes===undefined?0:mask(query.excludes);
  const maximal=query.maximal===undefined?false:query.maximal;if(typeof maximal!=="boolean")fail("maximal must be Boolean");
  if(contains&excludes)fail("contains/excludes conflict");
  const q={size,contains,excludes,maximal},key=JSON.stringify(q);
  if(cache.has(key)){stats.family_filter_cache_hits++;return cache.get(key);}
  const list=[];
  for(let x=0;x<total;x++){stats.family_filter_scans++;
   if(goodSeen[x]&&(size===null||s.sizes[x]===size)&&(x&contains)===contains&&(x&excludes)===0&&(!maximal||maximalSet.has(x)))list.push(x);
  }
  const result={query:q,list};if(cache.size>=16)cache.delete(cache.keys().next().value);cache.set(key,result);return result;
 }
 function ordinal(x,max,allowEnd){integer(x,"ordinal",0,max);if(!allowEnd&&x===max)fail("ordinal outside family");return x;}
 function fiberIndex(sum){let lo=0,hi=s.fibers.length;while(lo<hi){stats.fiber_search_steps++;const mid=(lo+hi)>>1;
  if(BigInt(s.fibers[mid].sum)<sum)lo=mid+1;else hi=mid;}return lo;}
 return {
  summary(){stats.queries++;return copy(s.summary);},
  subset(x){stats.queries++;return describe(mask(x));},
  collision(x){stats.queries++;x=mask(x);return {host_mask:x,sum_distinct:!s.bad_support_by_mask[x],
    witness:witness(s.bad_support_by_mask[x])};},
  obstructionPage(start=0,limit=32){
   stats.queries++;integer(start,"start",0,s.minimal_support_masks.length);integer(limit,"limit",1,64);
   const end=Math.min(s.minimal_support_masks.length,start+limit);
   return {start,total:s.minimal_support_masks.length,rows:s.minimal_support_masks.slice(start,end).map(witness),
    next:end<s.minimal_support_masks.length?end:null};
  },
  fiber(sum,within=full){
   stats.queries++;const value=decimal(sum,"sum"),host=mask(within),i=fiberIndex(value);
   const f=i<s.fibers.length&&s.fibers[i].sum===value.toString()?s.fibers[i]:null,out=[];
   if(f)for(const x of f.masks){stats.fiber_masks_inspected++;if((x&host)===x)out.push(describe(x));}
   return {sum:value.toString(),within:host,count:out.length,subsets:out};
  },
  fibersPage(start=0,limit=32){
   stats.queries++;integer(start,"start",0,s.fibers.length);integer(limit,"limit",1,64);
   const end=Math.min(s.fibers.length,start+limit);
   return {start,total:s.fibers.length,rows:copy(s.fibers.slice(start,end)),next:end<s.fibers.length?end:null};
  },
  goodCount(query={}){stats.queries++;const f=filter(query);return {query:copy(f.query),count:f.list.length};},
  selectGood(query,rank){stats.queries++;const f=filter(query),r=ordinal(rank,f.list.length,false);
   return {query:copy(f.query),rank:r,subset:describe(f.list[r])};},
  rankGood(query,subset){
   stats.queries++;const f=filter(query),x=mask(subset);let lo=0,hi=f.list.length;
   while(lo<hi){const m=(lo+hi)>>1;if(f.list[m]<x)lo=m+1;else hi=m;}
   const found=lo<f.list.length&&f.list[lo]===x;
   return {query:copy(f.query),mask:x,found,rank:found?lo:null,insertion_rank:lo};
  },
  goodPage(query={},start=0,limit=32){
   stats.queries++;const f=filter(query),r=ordinal(start,f.list.length,true);integer(limit,"limit",1,64);
   const end=Math.min(f.list.length,r+limit);
   return {query:copy(f.query),start:r,total:f.list.length,rows:f.list.slice(r,end).map((x,i)=>({rank:r+i,subset:describe(x)})),
    next:end<f.list.length?end:null};
  },
  subsetSumsPage(within,start=0,limit=32){
   stats.queries++;const host=mask(within),bits=indices(host,n),count=1<<bits.length;
   integer(start,"start",0,count);integer(limit,"limit",1,64);const end=Math.min(count,start+limit),rows=[];
   for(let code=start;code<end;code++){
    let x=0;for(let i=0;i<bits.length;i++)if(code&(1<<i))x|=1<<bits[i];
    rows.push({rank:code,mask:x,sum:s.subset_sums[x]});stats.subset_masks_materialized++;
   }
   return {within:host,start,total:count,rows,next:end<count?end:null,order:"numeric submask"};
  },
  statistics(){return copy(stats);}
 };
}
module.exports={VERSION,compileSubsetObstructions,openSubsetObstructions};
