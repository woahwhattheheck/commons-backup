"use strict";
const copy=x=>JSON.parse(JSON.stringify(x));
function nat(x,name,lo,hi){if(!Number.isSafeInteger(x)||x<lo||x>hi)throw new RangeError(name);return x;}
function compile(input){
 const p=input.primes,g=input.gaps,N=p.length;
 if(!Array.isArray(p)||N<3||N>4096||!Array.isArray(g)||g.length!==N-1)throw new Error("bounded prime/gap premise");
 for(let i=0;i<N;i++){nat(p[i],"prime",2,10000000);if(i&&p[i]<=p[i-1])throw new Error("increasing list");}
 for(let i=0;i<g.length;i++)if(g[i].n!==i||g[i].prime!==p[i]||g[i].next_prime!==p[i+1]||!Number.isSafeInteger(g[i].gap)||g[i].gap<1||g[i].gap>10000000)throw new Error("saved gap alignment");
 const work={gap_equality_comparisons:0,runs_created:0,start_records:0,histogram_cells:0,new_gap_subtractions:0,prime_tests:0,sieve_steps:0,old_threshold_merges:0,old_normalized_ordering:0};
 const runs=[],starts=[],ap_prefix=[0],non_ap_prefix=[0],length_histogram={};
 let a=0;function close(b){const length=b-a+2,id=runs.length,step=g[a].gap;const run={id,first_edge:a,last_edge:b,first_index:a,last_index:b+1,length,step};runs.push(run);work.runs_created++;
   for(let i=a;i<=b&&i<N-2;i++){const good=Math.max(0,b-i),total=N-i-2;starts.push({first_index:i,run_id:id,last_ap_index:b+1,step});ap_prefix.push(ap_prefix.at(-1)+good);non_ap_prefix.push(non_ap_prefix.at(-1)+total-good);work.start_records++;}
   for(let k=3;k<=length;k++){length_histogram[k]=(length_histogram[k]||0)+length-k+1;work.histogram_cells++;}
 }
 for(let i=1;i<g.length;i++){work.gap_equality_comparisons++;if(g[i].gap!==g[i-1].gap){close(i-1);a=i;}}
 close(g.length-1);
 return {schema:"consecutive-prime-ap/v1",primes:p.slice(),gaps:copy(g),provenance:copy(input.provenance),runs,starts,ap_prefix,non_ap_prefix,length_histogram,maximum_equal_gap_length:Math.max(...runs.map(r=>r.length)),ap_blocks:ap_prefix.at(-1),non_ap_blocks:non_ap_prefix.at(-1),work};
}
function openIndex(snapshot){
 const S=copy(snapshot),N=S.primes.length;
 if(S.schema!=="consecutive-prime-ap/v1"||N<3||N>4096||S.gaps.length!==N-1||S.starts.length!==N-2||S.ap_prefix.length!==N-1||S.non_ap_prefix.length!==N-1)throw new Error("saved shape");
 let edge=0;for(let i=0;i<S.runs.length;i++){const r=S.runs[i];if(r.id!==i||r.first_edge!==edge||r.last_edge<edge||r.first_index!==edge||r.last_index!==r.last_edge+1||r.length!==r.last_index-r.first_index+1)throw new Error("saved run coverage");edge=r.last_edge+1;}if(edge!==N-1)throw new Error("incomplete run partition");
 S.starts.forEach((r,i)=>{const u=S.runs[r.run_id];if(r.first_index!==i||!u||i<u.first_edge||i>u.last_edge||r.last_ap_index!==u.last_index||r.step!==u.step)throw new Error("saved start links");});
 const work={queries:0,condition_builds:0,condition_cache_hits:0,saved_start_scans:0,range_count_evaluations:0,prime_bound_comparisons:0,selection_steps:0,rank_lookups:0,classifications:0,unequal_gap_witnesses:0,saved_run_gap_records_returned:0,new_gap_subtractions:0,new_gap_equality_comparisons:0,run_reconstruction:0,prime_tests:0,sieve_steps:0,old_threshold_merges:0,old_normalized_ordering:0};
 const cache=new Map();
 function family(q={}){
  const kind=q.kind??"ap";if(kind!=="ap"&&kind!=="non_ap")throw new RangeError("kind");
  const first=nat(q.first_index??0,"first index",0,N-1);let last=nat(q.last_index??N-1,"last index",-1,N-1);
  const min=nat(q.min_length??3,"minimum length",3,N),max=nat(q.max_length??N,"maximum length",min,N);
  if(kind==="non_ap"&&((q.min_step!==undefined&&q.min_step!==1)||(q.max_step!==undefined&&q.max_step!==10000000)))throw new Error("step filters apply only to APs");
  const d0=nat(q.min_step??1,"minimum step",1,10000000),d1=nat(q.max_step??10000000,"maximum step",d0,10000000);
  if(q.x!==undefined){nat(q.x,"prime cutoff",0,1000000000);let l=0,h=N;while(l<h){const m=(l+h)>>1;work.prime_bound_comparisons++;if(S.primes[m]<=q.x)l=m+1;else h=m;}last=Math.min(last,l-1);}
  const condition={kind,first_index:first,last_index:last,min_length:min,max_length:max,min_step:d0,max_step:d1},key=JSON.stringify(condition);
  if(cache.has(key)){work.condition_cache_hits++;return cache.get(key);}if(cache.size>=32)throw new Error("32-condition limit");
  const rows=[],prefix=[0];let longest=0;
  for(let i=first;i<=Math.min(last,N-3);i++){work.saved_start_scans++;const s=S.starts[i];let lo=i+min-1,hi=Math.min(last,i+max-1);
   if(kind==="ap"){hi=Math.min(hi,s.last_ap_index);if(s.step<d0||s.step>d1)hi=lo-1;}else lo=Math.max(lo,s.last_ap_index+1);
   const count=Math.max(0,hi-lo+1);work.range_count_evaluations++;rows.push({first_index:i,first_end:lo,last_end:hi,count});prefix.push(prefix.at(-1)+count);if(count)longest=Math.max(longest,hi-i+1);
  }
  const f={condition,rows,prefix,count:prefix.at(-1),longest};cache.set(key,f);work.condition_builds++;return f;
 }
 function block(i,j){
  nat(i,"first index",0,N-3);nat(j,"last index",i+2,N-1);const s=S.starts[i],ap=j<=s.last_ap_index;work.classifications++;
  const out={first_index:i,last_index:j,length:j-i+1,first_prime:S.primes[i],last_prime:S.primes[j],ap,run_id:s.run_id,step:ap?s.step:null};
  if(!ap){const b=s.last_ap_index;out.first_unequal_gap_witness={left_edge:b-1,right_edge:b,left_gap:S.gaps[b-1].gap,right_gap:S.gaps[b].gap};work.unequal_gap_witnesses++;}
  return out;
 }
 function select(f,k){
  nat(k,"rank",0,f.count-1);let l=0,h=f.rows.length;while(l<h){const m=(l+h)>>1;work.selection_steps++;if(f.prefix[m+1]<=k)l=m+1;else h=m;}
  const r=f.rows[l];return {rank:k,...block(r.first_index,r.first_end+k-f.prefix[l])};
 }
 function rank(f,i,j){nat(i,"first index",0,N-3);nat(j,"last index",i+2,N-1);work.rank_lookups++;const at=i-f.condition.first_index,r=f.rows[at];if(!r||r.first_index!==i||j<r.first_end||j>r.last_end)return {member:false,rank:null};return {member:true,rank:f.prefix[at]+j-r.first_end};}
 function query(q){
  work.queries++;let out;
  if(q.op==="summary")out={schema:S.schema,prime_count:N,last_prime:S.primes.at(-1),runs:S.runs.length,start_records:S.starts.length,ap_blocks:S.ap_blocks,non_ap_blocks:S.non_ap_blocks,length_histogram:S.length_histogram,maximum_equal_gap_length:S.maximum_equal_gap_length,construction_work:S.work};
  else if(q.op==="classify")out=block(q.first_index,q.last_index);
  else if(q.op==="run"){const r=S.runs[nat(q.id,"run id",0,S.runs.length-1)];out={...r,gaps:S.gaps.slice(r.first_edge,r.last_edge+1)};work.saved_run_gap_records_returned+=out.gaps.length;}
  else if(q.op==="runs"){const min=nat(q.min_length??3,"run minimum length",2,N);out=S.runs.filter(r=>r.length>=min);}
  else if(q.op==="conditions")out=[...cache.values()].map(f=>({condition:f.condition,count:f.count,longest:f.longest}));
  else {const f=family(q.condition);
   if(q.op==="family")out={condition:f.condition,count:f.count,longest:f.longest};
   else if(q.op==="condition_rows")out=f;
   else if(q.op==="select")out=select(f,q.rank);
   else if(q.op==="rank")out=rank(f,q.first_index,q.last_index);
   else if(q.op==="page"){const offset=nat(q.offset??0,"offset",0,f.count),limit=nat(q.limit??20,"limit",0,512),end=Math.min(f.count,offset+limit);out={count:f.count,offset,next:end<f.count?end:null,blocks:Array.from({length:end-offset},(_,i)=>select(f,offset+i))};}
   else throw new Error("unknown operation");
  }return copy(out);
 }
 return {query,work:()=>copy(work)};
}
module.exports={compile,openIndex};
