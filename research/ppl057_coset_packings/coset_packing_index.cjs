"use strict";
const VERSION="1.0.0",SCHEMA="commons.finite-coset-packings.v1",MAX_JSON=24000000;
function fail(s){throw new Error(s);}
function copy(x){return JSON.parse(JSON.stringify(x));}
function integer(x,name,lo,hi){if(!Number.isSafeInteger(x)||x<lo||x>hi)fail(name+" outside bounds");return x;}
function nat(x,name){
 if(typeof x==="bigint")x=x.toString();
 if(typeof x==="number"){integer(x,name,0,Number.MAX_SAFE_INTEGER);x=String(x);}
 if(typeof x!=="string"||!/^(0|[1-9][0-9]*)$/.test(x)||x.length>100)fail(name+" requires canonical nonnegative decimal");
 return BigInt(x);
}
function pop(mask){let n=0;for(;mask;mask&=mask-1)n++;return n;}
function members(mask,n){const out=[];for(let i=0;i<n;i++)if(mask&(1<<i))out.push(i);return out;}
function gcd(a,b){while(b){const t=a%b;a=b;b=t;}return a;}
function signature(code,indices,radix){
 const counts=[];let k=0,coverage=0,maxGcd=0,pair=null,t=code;
 for(let i=0;i<indices.length;i++){const c=t%radix;t=Math.floor(t/radix);counts.push(c);k+=c;}
 if(t)fail("signature exceeds dimensions");
 const N=radix-1;
 for(let i=0;i<indices.length;i++)coverage+=counts[i]*(N/indices[i]);
 if(k>=2)for(let i=0;i<indices.length;i++)if(counts[i])for(let j=i;j<indices.length;j++){
  if(!counts[j]||(i===j&&counts[i]<2))continue;
  const g=gcd(indices[i],indices[j]);if(g>maxGcd){maxGcd=g;pair=[indices[i],indices[j]];}
 }
 return {code,counts,cosets:k,covered_elements:coverage,max_pair_index_gcd:k>=2?maxGcd:null,
  index_pair:pair,sun_condition:k>=2?maxGcd>=k:null};
}
function makeGroup(raw){
 if(!raw||typeof raw!=="object")fail("group input required");
 if(raw.dihedral_rotation!==undefined){
  const m=integer(raw.dihedral_rotation,"dihedral rotation order",2,6),N=2*m;
  const table=Array.from({length:N},(_,x)=>Array.from({length:N},(_,y)=>{
   const a=Math.floor(x/2),b=x%2,c=Math.floor(y/2),d=y%2;
   return 2*((a+(b?-c:c)+m)%m)+(b^d);
  }));
  return {order:N,identity:0,table,description:{kind:"dihedral",rotation_order:m,
   elements:"2*a+b",product:"(a,b)(c,d)=(a+(-1)^b*c mod m,b xor d)"}};
 }
 if(!Array.isArray(raw.table)||!raw.table.length||raw.table.length>12)fail("Cayley table order1..12 required");
 const N=raw.table.length,id=integer(raw.identity,"identity",0,N-1);
 const table=raw.table.map(row=>{if(!Array.isArray(row)||row.length!==N)fail("square Cayley table required");return row.map(x=>integer(x,"product",0,N-1));});
 return {order:N,identity:id,table,description:copy(raw.description||{kind:"supplied Cayley table"})};
}
function compileCosetPackings(input,options={}){
 const started=Date.now();if(!input||typeof input!=="object")fail("input object required");
 const group=makeGroup(input.group),N=group.order,id=group.identity,T=group.table,total=1<<N,full=total-1;
 const cellBudget=options.coefficient_budget===undefined?1000000:integer(options.coefficient_budget,"coefficient_budget",1,1500000);
 const visitBudget=options.visit_budget===undefined?10000000:integer(options.visit_budget,"visit_budget",1,20000000);
 const work={group_products_materialized:input.group.dihedral_rotation===undefined?0:N*N,
  identity_checks:0,inverse_candidates:0,associativity_checks:0,subgroup_candidates:0,subgroup_product_checks:0,
  left_translate_products:0,packing_states:total,coset_branch_candidates:0,coefficient_visits:0,
  coefficient_cells:0,individual_packings_enumerated:0,old_group_or_coset_evaluations:0};
 const inverse=[];
 for(let a=0;a<N;a++){
  work.identity_checks+=2;if(T[id][a]!==a||T[a][id]!==a)fail("identity violation");
  let inv=-1;for(let b=0;b<N;b++){work.inverse_candidates++;if(T[a][b]===id&&T[b][a]===id){inv=b;break;}}
  if(inv<0)fail("inverse absent");inverse.push(inv);
 }
 for(let a=0;a<N;a++)for(let b=0;b<N;b++)for(let c=0;c<N;c++){
  work.associativity_checks++;if(T[T[a][b]][c]!==T[a][T[b][c]])fail("associativity violation");
 }
 const subgroups=[],candidateRows=[];
 for(let mask=1;mask<total;mask++)if(mask&(1<<id)){
  work.subgroup_candidates++;const set=members(mask,N);let escape=null;
  outer:for(const a of set)for(const b of set){
   work.subgroup_product_checks++;const product=T[a][b];
   if(!(mask&(1<<product))){escape={a,b,product};break outer;}
  }
  candidateRows.push({mask,subgroup:escape===null,escape});
  if(escape===null){if(N%set.length)fail("subgroup order does not divide group order");
   subgroups.push({mask,order:set.length,index:N/set.length,elements:set,left_translate_masks:[]});}
 }
 const cosetMap=new Map();
 for(const H of subgroups)for(let a=0;a<N;a++){
  let mask=0;for(const h of H.elements){mask|=1<<T[a][h];work.left_translate_products++;}
  H.left_translate_masks.push(mask);
  const prior=cosetMap.get(mask);
  if(prior){if(prior.subgroup_mask!==H.mask)fail("same coset set attributed to different subgroups");}
  else cosetMap.set(mask,{mask,subgroup_mask:H.mask,index:H.index,representative:a,elements:members(mask,N)});
 }
 const cosets=[...cosetMap.values()].sort((a,b)=>a.mask-b.mask),
  indices=[...new Set(subgroups.map(H=>H.index))].sort((a,b)=>a-b),radix=N+1,
  weights=indices.map((_,i)=>radix**i),indexPosition=new Map(indices.map((v,i)=>[v,i]));
 if(!Number.isSafeInteger(radix**indices.length))fail("signature encoding overflow");
 const byElement=Array.from({length:N},()=>[]);
 for(const C of cosets){C.index_position=indexPosition.get(C.index);for(const a of C.elements)byElement[a].push(C);}
 const polys=Array(total);polys[0]=new Map([[0,1n]]);work.coefficient_cells=1;
 function add(row,code,value){
  if(++work.coefficient_visits>visitBudget)fail("coefficient visit budget exceeded; no partial snapshot returned");
  if(!row.has(code)){
   if(++work.coefficient_cells>cellBudget)fail("coefficient cell budget exceeded; no partial snapshot returned");
   row.set(code,value);
  }else row.set(code,row.get(code)+value);
 }
 for(let S=1;S<total;S++){
  const bit=S&-S,v=31-Math.clz32(bit),row=new Map();
  for(const [code,count]of polys[S^bit])add(row,code,count);
  for(const C of byElement[v]){
   work.coset_branch_candidates++;if((C.mask&S)!==C.mask)continue;
   const weight=weights[C.index_position];
   for(const [code,count]of polys[S^C.mask])add(row,code+weight,count);
  }
  polys[S]=row;
 }
 const fullRows=[...polys[full]].sort((a,b)=>a[0]-b[0]),profiles=fullRows.map(([code,count])=>({...signature(code,indices,radix),count:count.toString()}));
 const countByK=Array(N+1).fill(0n),countByCoverage=Array(N+1).fill(0n);
 for(const r of profiles){countByK[r.cosets]+=BigInt(r.count);countByCoverage[r.covered_elements]+=BigInt(r.count);}
 return {schema:SCHEMA,version:VERSION,group:{...group,inverse},provenance:copy(input.provenance||{}),
  subgroup_candidates:candidateRows,subgroups,cosets,indices,radix,weights,
  polynomials:polys.map(row=>[...row].sort((a,b)=>a[0]-b[0]).map(([code,c])=>[code,c.toString()])),
  full_profiles:profiles,
  summary:{group_order:N,subgroups:subgroups.length,left_cosets:cosets.length,available_masks:total,
   index_types:indices,coefficient_cells:work.coefficient_cells,full_signature_count:profiles.length,
   total_packings:fullRows.reduce((a,row)=>a+row[1],0n).toString(),
   full_covers:countByCoverage[N].toString(),counts_by_coset_number:countByK.map(String),
   counts_by_covered_elements:countByCoverage.map(String),sun_violation_profiles:profiles.filter(r=>r.sun_condition===false)},
  ordering:{signature:"radix code increasing",within_signature:"least available element: uncovered branch first, then containing cosets in increasing mask order",
   families:"unlabelled sets of distinct disjoint left coset sets; no covering requirement"},
  construction:{...work,coefficient_budget:cellBudget,visit_budget:visitBudget,elapsed_ms_observation:Date.now()-started}};
}
function openCosetPackings(raw){
 if(typeof raw==="string"){if(raw.length>MAX_JSON)fail("snapshot JSON limit");raw=JSON.parse(raw);}
 const text=JSON.stringify(raw);if(text.length>MAX_JSON)fail("snapshot JSON limit");const s=JSON.parse(text);
 if(s.schema!==SCHEMA||s.version!==VERSION)fail("unsupported snapshot");
 const N=integer(s.group&&s.group.order,"group order",1,12),total=1<<N,full=total-1,
  id=integer(s.group.identity,"identity",0,N-1),radix=N+1;
 if(s.radix!==radix||!Array.isArray(s.indices)||!s.indices.length||!Array.isArray(s.weights))fail("index encoding");
 let prior=0;for(let i=0;i<s.indices.length;i++){
  const x=integer(s.indices[i],"index",1,N);if(x<=prior||N%x||s.weights[i]!==radix**i)fail("index/weight mismatch");prior=x;
 }
 const maxCode=radix**s.indices.length-1;
 if(!Array.isArray(s.group.table)||s.group.table.length!==N||!Array.isArray(s.group.inverse)||s.group.inverse.length!==N)fail("saved group shape");
 for(const row of s.group.table){if(!Array.isArray(row)||row.length!==N)fail("saved table row");for(const x of row)integer(x,"saved product",0,N-1);}
 for(const x of s.group.inverse)integer(x,"saved inverse",0,N-1);
 const stats={opened_polynomial_cells:0,saved_escape_checks:0,queries:0,saved_coefficient_lookups:0,
  navigation_branches:0,profile_evaluations:0,aggregate_coefficient_visits:0,
  group_products_rebuilt:0,subgroup_closure_replays:0,coset_translate_replays:0,polynomial_recurrences:0};
 const subgroupMap=new Map(),cosetMap=new Map(),byElement=Array.from({length:N},()=>[]);
 if(!Array.isArray(s.subgroups)||!Array.isArray(s.cosets)||!Array.isArray(s.subgroup_candidates))fail("group records");
 prior=0;for(const H of s.subgroups){
  integer(H.mask,"subgroup mask",1,full);if(H.mask<=prior||!(H.mask&(1<<id))||H.order!==pop(H.mask)||H.index*H.order!==N)fail("subgroup row");
  if(JSON.stringify(H.elements)!==JSON.stringify(members(H.mask,N))||!Array.isArray(H.left_translate_masks)||H.left_translate_masks.length!==N)fail("subgroup elements/translates");
  prior=H.mask;subgroupMap.set(H.mask,H);
 }
 const candidateSet=new Set();
 for(const r of s.subgroup_candidates){
  integer(r.mask,"candidate mask",1,full);if(!(r.mask&(1<<id))||candidateSet.has(r.mask)||typeof r.subgroup!=="boolean")fail("candidate coverage");
  candidateSet.add(r.mask);
  if(r.subgroup){if(!subgroupMap.has(r.mask)||r.escape!==null)fail("accepted candidate binding");}
  else{
   const e=r.escape;if(!e)fail("escape witness missing");
   integer(e.a,"escape a",0,N-1);integer(e.b,"escape b",0,N-1);integer(e.product,"escape product",0,N-1);
   if(!(r.mask&(1<<e.a))||!(r.mask&(1<<e.b))||(r.mask&(1<<e.product))||s.group.table[e.a][e.b]!==e.product)fail("escape witness invalid");
   stats.saved_escape_checks++;
  }
 }
 if(candidateSet.size!==total/2)fail("all identity-containing candidates required");
 prior=0;for(const C of s.cosets){
  integer(C.mask,"coset mask",1,full);const H=subgroupMap.get(C.subgroup_mask);
  integer(C.representative,"representative",0,N-1);integer(C.index_position,"index position",0,s.indices.length-1);
  if(C.mask<=prior||!H||C.index!==H.index||C.index!==s.indices[C.index_position]||pop(C.mask)!==H.order||
   !(C.mask&(1<<C.representative))||H.left_translate_masks[C.representative]!==C.mask||
   JSON.stringify(C.elements)!==JSON.stringify(members(C.mask,N)))fail("coset binding");
  prior=C.mask;cosetMap.set(C.mask,C);for(const a of C.elements)byElement[a].push(C);
 }
 for(const H of s.subgroups)for(const mask of H.left_translate_masks){
  const C=cosetMap.get(mask);if(!C||C.subgroup_mask!==H.mask)fail("translate reference");
 }
 if(!Array.isArray(s.polynomials)||s.polynomials.length!==total)fail("complete polynomials required");
 const tables=s.polynomials.map((rows,S)=>{
  if(!Array.isArray(rows)||!rows.length)fail("polynomial rows");const tab=new Map();let old=-1;
  for(const row of rows){
   if(!Array.isArray(row)||row.length!==2)fail("coefficient cell");
   const code=integer(row[0],"signature code",0,maxCode),c=nat(row[1],"coefficient");
   if(code<=old||c===0n||signature(code,s.indices,radix).covered_elements>pop(S))fail("coefficient support");
   tab.set(code,c);old=code;stats.opened_polynomial_cells++;
  }
  if(tab.get(0)!==1n)fail("empty packing identity");return tab;
 });
 function mask(x){return integer(x,"available mask",0,full);}
 function encode(counts){
  if(!Array.isArray(counts)||counts.length!==s.indices.length)fail("signature vector length");
  let code=0;for(let i=0;i<counts.length;i++)code+=integer(counts[i],"index multiplicity",0,N)*s.weights[i];
  return code;
 }
 function profile(code){stats.profile_evaluations++;return signature(code,s.indices,radix);}
 function count(S,code){stats.saved_coefficient_lookups++;return tables[S].get(code)||0n;}
 function branches(S,code){
  if(!S)return [];
  const bit=S&-S,v=31-Math.clz32(bit),out=[{coset:null,next:S^bit,code,count:count(S^bit,code)}];
  const counts=profile(code).counts;
  for(const C of byElement[v])if((C.mask&S)===C.mask&&counts[C.index_position]>0){
   const nextCode=code-s.weights[C.index_position];out.push({coset:C.mask,next:S^C.mask,code:nextCode,count:count(S^C.mask,nextCode)});
  }
  return out;
 }
 function select(S,code,rank){
  const initial=rank,amount=count(S,code);if(rank>=amount)fail("rank outside signature family");
  const chosen=[],trace=[];let at=S,key=code;
  while(at){
   let found=false,skipped=0n;
   for(const b of branches(at,key)){
    stats.navigation_branches++;
    if(rank>=b.count){rank-=b.count;skipped+=b.count;continue;}
    trace.push({available:at,signature:key,coset:b.coset,next:b.next,next_signature:b.code,
     skipped:skipped.toString(),branch_count:b.count.toString(),residual_rank:rank.toString()});
    if(b.coset!==null)chosen.push(copy(cosetMap.get(b.coset)));at=b.next;key=b.code;found=true;break;
   }
   if(!found)fail("saved polynomial has no selected branch");
  }
  if(key!==0||rank!==0n)fail("terminal signature mismatch");
  let covered=0;for(const C of chosen)covered|=C.mask;
  return {available:S,signature:profile(code),rank:initial.toString(),family_count:amount.toString(),
   cosets:chosen,covered_mask:covered,uncovered:members(S^covered,N),trace};
 }
 function filtered(S,covers){
  const rows=[];
  for(const [code,c]of tables[S]){stats.aggregate_coefficient_visits++;
   if(!covers||profile(code).covered_elements===pop(S))rows.push([code,c]);}
  return rows;
 }
 function selectAll(S,rank,covers){
  const rows=filtered(S,covers),amount=rows.reduce((a,r)=>a+r[1],0n),original=rank;
  if(rank>=amount)fail("aggregate rank outside family");
  for(const [code,c]of rows){if(rank>=c){rank-=c;continue;}
   return {aggregate_rank:original.toString(),aggregate_count:amount.toString(),covers,selected:select(S,code,rank)};}
  fail("aggregate selection failed");
 }
 function prefix(S,code,decisions){
  if(!Array.isArray(decisions)||decisions.length>N)fail("decision prefix limit");
  let at=S,key=code,offset=0n;const trace=[];
  for(const chosen of decisions){
   if(!at)fail("decision after terminal");
   if(chosen!==null)integer(chosen,"chosen coset",1,full);
   let branch=null,skipped=0n;
   for(const b of branches(at,key)){stats.navigation_branches++;if(b.coset===chosen){branch=b;break;}skipped+=b.count;}
   if(!branch)fail("not a permitted canonical decision");
   offset+=skipped;trace.push({available:at,signature:key,coset:chosen,skipped:skipped.toString()});at=branch.next;key=branch.code;
  }
  const c=count(at,key);return {available:S,signature:profile(code),decisions:decisions.slice(),remaining:at,
   remaining_signature:profile(key),count:c.toString(),first_rank:c?offset.toString():null,trace};
 }
 return {
  summary(){stats.queries++;return copy(s.summary);},
  subgroupPage(start=0,limit=32){stats.queries++;integer(start,"start",0,s.subgroups.length);integer(limit,"limit",1,64);
   const end=Math.min(s.subgroups.length,start+limit);return {start,total:s.subgroups.length,rows:copy(s.subgroups.slice(start,end)),next:end<s.subgroups.length?end:null};},
  cosetPage(start=0,limit=32){stats.queries++;integer(start,"start",0,s.cosets.length);integer(limit,"limit",1,64);
   const end=Math.min(s.cosets.length,start+limit);return {start,total:s.cosets.length,rows:copy(s.cosets.slice(start,end)),next:end<s.cosets.length?end:null};},
  candidatePage(start=0,limit=32){stats.queries++;integer(start,"start",0,s.subgroup_candidates.length);integer(limit,"limit",1,64);
   const end=Math.min(s.subgroup_candidates.length,start+limit);return {start,total:s.subgroup_candidates.length,rows:copy(s.subgroup_candidates.slice(start,end)),next:end<s.subgroup_candidates.length?end:null};},
  profilePage(available,start=0,limit=32){
   stats.queries++;const S=mask(available),rows=s.polynomials[S];integer(start,"start",0,rows.length);integer(limit,"limit",1,64);
   const end=Math.min(rows.length,start+limit);return {available:S,start,total:rows.length,
    rows:rows.slice(start,end).map(([code,c])=>({...profile(code),count:c})),next:end<rows.length?end:null};
  },
  count(available,counts){stats.queries++;const S=mask(available),code=encode(counts);return {available:S,signature:profile(code),count:count(S,code).toString()};},
  totalCount(available,covers=false){
   stats.queries++;if(typeof covers!=="boolean")fail("covers Boolean required");const S=mask(available);
   return {available:S,covers,count:filtered(S,covers).reduce((a,r)=>a+r[1],0n).toString()};
  },
  select(available,counts,rank){stats.queries++;return select(mask(available),encode(counts),nat(rank,"rank"));},
  selectAll(available,rank,covers=false){stats.queries++;if(typeof covers!=="boolean")fail("covers Boolean required");return selectAll(mask(available),nat(rank,"rank"),covers);},
  prefix(available,counts,decisions){stats.queries++;return prefix(mask(available),encode(counts),decisions);},
  rank(available,cosetMasks){
   stats.queries++;const S=mask(available);if(!Array.isArray(cosetMasks)||cosetMasks.length>N)fail("coset list limit");
   const chosen=new Map(),counts=Array(s.indices.length).fill(0);let union=0;
   for(const m of cosetMasks){integer(m,"coset mask",1,full);const C=cosetMap.get(m);
    if(!C||(m&S)!==m||(m&union)||chosen.has(m))fail("distinct disjoint contained cosets required");
    chosen.set(m,C);union|=m;counts[C.index_position]++;}
   const decisions=[];let at=S;
   while(at){const bit=at&-at;let C=null;for(const value of chosen.values())if(value.mask&bit){C=value;break;}
    if(C){decisions.push(C.mask);at^=C.mask;chosen.delete(C.mask);}else{decisions.push(null);at^=bit;}}
   const r=prefix(S,encode(counts),decisions);
   if(r.count!=="1"||r.remaining!==0)fail("rank terminal mismatch");
   return {available:S,signature:r.signature,rank:r.first_rank,canonical_decisions:decisions,trace:r.trace};
  },
  pageAll(available,start=0,limit=8,covers=false){
   stats.queries++;if(typeof covers!=="boolean")fail("covers Boolean required");const S=mask(available),r=nat(start,"start");
   integer(limit,"limit",1,32);const amount=filtered(S,covers).reduce((a,x)=>a+x[1],0n);if(r>amount)fail("page start outside family");
   const rows=[];let at=r;for(let i=0;i<limit&&at<amount;i++,at++)rows.push(selectAll(S,at,covers));
   return {available:S,covers,start:r.toString(),count:amount.toString(),rows,next:at<amount?at.toString():null};
  },
  statistics(){return copy(stats);}
 };
}
module.exports={VERSION,compileCosetPackings,openCosetPackings};
