"use strict";
// Exact finite navigation of consecutive-prime blocks from saved raw gaps.
function integer(x,name,min,max){if(!Number.isSafeInteger(x)||x<min||x>max)throw new RangeError(name);return x;}
function copy(x){return JSON.parse(JSON.stringify(x));}
function count(L,a,b){const v=Math.min(L,b),u=v-a+1;return u<=0?0:u*(L+1)-(a+v)*u/2;}
function compile(input){
 const p=input.primes, rows=input.imported_rows;
 if(!Array.isArray(p)||p.length<3||p.length>4096)throw new RangeError("3..4096 primes");
 for(let i=0;i<p.length;i++){integer(p[i],"prime",2,10000000);if(i&&p[i]<=p[i-1])throw new Error("increasing premise");}
 if(!Array.isArray(rows)||rows.length!==p.length-3)throw new Error("imported coverage");
 const work={imported_gap_records:rows.length,new_initial_gap_subtractions:2,old_gap_subtractions:0,group_insertions:0,union_merges:0,root_snapshots:0,prime_tests:0,sieve_steps:0,old_normalized_comparisons:0};
 const gaps=[{n:0,prime:p[0],next_prime:p[1],gap:p[1]-p[0],origin:"new_initial"},{n:1,prime:p[1],next_prime:p[2],gap:p[2]-p[1],origin:"new_initial"}];
 for(let j=0;j<rows.length;j++){const r=rows[j],n=j+2;if(r.n!==n||r.prime!==p[n]||r.next_prime!==p[n+1])throw new Error("literal row alignment");integer(r.gap,"saved positive gap",1,10000000);gaps.push({...r,origin:"imported"});}
 const by=new Map();for(const e of gaps){if(!by.has(e.gap))by.set(e.gap,[]);by.get(e.gap).push(e.n);work.group_insertions++;}
 const values=[...by.keys()].sort((a,b)=>b-a),N=p.length,ds=Array.from({length:N},(_,i)=>i),ids=ds.slice(),nodes=p.map((v,i)=>({id:i,first:i,last:i,length:1,left:null,right:null,edge:null,gap:null}));
 const find=i=>{while(ds[i]!==i){ds[i]=ds[ds[i]];i=ds[i];}return i;};
 const levels=[];
 function snapshot(gap,added){
   const roots=[];for(let i=0;i<N;){const n=nodes[ids[find(i)]];roots.push(n.id);i=n.last+1;work.root_snapshots++;}
   const prefix=[0];let longest=0;for(const id of roots){const L=nodes[id].length;prefix.push(prefix.at(-1)+count(L,1,N));longest=Math.max(longest,L);}
   levels.push({id:levels.length,min_active_gap:gap,added_edges:added,roots,block_prefix:prefix,blocks:prefix.at(-1),components:roots.length,longest});
 }
 snapshot(null,[]);
 for(const gap of values){
   const edges=by.get(gap);
   for(const edge of edges){const a=find(edge),b=find(edge+1);if(a===b)throw new Error("chain cycle");
     const l=nodes[ids[a]],r=nodes[ids[b]];if(l.last+1!==r.first)throw new Error("nonadjacent merge");
     const node={id:nodes.length,first:l.first,last:r.last,length:l.length+r.length,left:l.id,right:r.id,edge,gap};
     nodes.push(node);ds[b]=a;ids[a]=node.id;work.union_merges++;
   }snapshot(gap,edges.slice());
 }
 return {schema:"consecutive-prime-blocks/v1",primes:p.slice(),gaps,nodes,levels,provenance:copy(input.provenance),work};
}
function openIndex(saved){
 const S=copy(saved),N=S.primes.length;
 if(S.schema!=="consecutive-prime-blocks/v1"||N<3||N>4096||S.gaps.length!==N-1||S.nodes.length!==2*N-1)throw new Error("shape");
 for(let i=0;i<S.gaps.length;i++)if(S.gaps[i].n!==i||S.gaps[i].prime!==S.primes[i]||S.gaps[i].next_prime!==S.primes[i+1])throw new Error("saved endpoints");
 for(let i=0;i<S.nodes.length;i++){const n=S.nodes[i];if(n.id!==i||n.length!==n.last-n.first+1)throw new Error("node shape");if(i>=N){const l=S.nodes[n.left],r=S.nodes[n.right];if(!l||!r||n.left>=i||n.right>=i||l.last+1!==r.first||l.first!==n.first||r.last!==n.last||n.edge!==l.last||n.gap!==S.gaps[n.edge].gap)throw new Error("saved merge links");}}
 for(let j=0;j<S.levels.length;j++){const l=S.levels[j];if(l.id!==j||l.roots.length!==l.components||l.block_prefix.length!==l.components+1||l.block_prefix[0]!==0||l.block_prefix.at(-1)!==l.blocks)throw new Error("saved phase");let at=0;for(const id of l.roots){const n=S.nodes[id];if(!n||n.first!==at)throw new Error("saved partition");at=n.last+1;}if(at!==N)throw new Error("partition end");}
 const work={queries:0,condition_builds:0,condition_cache_hits:0,phase_comparisons:0,saved_component_scans:0,condition_count_formulas:0,prime_bound_comparisons:0,selection_steps:0,rank_count_formulas:0,saved_gap_records_returned:0,new_gap_subtractions:0,union_merges:0,level_reconstructions:0,old_normalized_comparisons:0,prime_tests:0,sieve_steps:0};
 const cache=new Map();
 function family(q={}){
   let t=q.threshold??{n:0,d:1};if(typeof t==="number")t={n:t,d:1};
   const num=integer(t.n,"threshold numerator",0,1000000000),den=integer(t.d??1,"threshold denominator",1,1000000);
   let first=integer(q.first_index??0,"first index",0,N-1),last=integer(q.last_index??N-1,"last index",-1,N-1);
   const a=integer(q.min_length??1,"minimum length",1,N),b=integer(q.max_length??N,"maximum length",1,N);if(b<a)throw new RangeError("length interval");
   if(q.x!==undefined){integer(q.x,"prime cutoff",0,1000000000);let lo=0,hi=N;while(lo<hi){const mid=(lo+hi)>>1;work.prime_bound_comparisons++;if(S.primes[mid]<=q.x)lo=mid+1;else hi=mid;}last=Math.min(last,lo-1);}
   const key=JSON.stringify([num,den,first,last,a,b]);if(cache.has(key)){work.condition_cache_hits++;return cache.get(key);}
   if(cache.size>=32)throw new RangeError("at most 32 distinct conditions");
   let phase=0;for(let j=1;j<S.levels.length;j++){work.phase_comparisons++;if(S.levels[j].min_active_gap*den>num)phase=j;else break;}
   const components=[],prefix=[0];let longest=0;
   for(const id of S.levels[phase].roots){work.saved_component_scans++;const node=S.nodes[id],l=Math.max(first,node.first),r=Math.min(last,node.last);if(l>r)continue;const length=r-l+1,total=count(length,a,b);work.condition_count_formulas++;components.push({node:id,first:l,last:r,length,blocks:total});prefix.push(prefix.at(-1)+total);longest=Math.max(longest,length);}
   const f={condition:{threshold:{n:num,d:den},first_index:first,last_index:last,min_length:a,max_length:b},phase,components,prefix,blocks:prefix.at(-1),longest};cache.set(key,f);work.condition_builds++;return f;
 }
 function block(first,last,withEdges=false){
   integer(first,"block first",0,N-1);integer(last,"block last",first,N-1);
   const b={first_index:first,last_index:last,length:last-first+1,first_prime:S.primes[first],last_prime:S.primes[last]};
   if(withEdges){b.internal_gaps=S.gaps.slice(first,last);work.saved_gap_records_returned+=b.internal_gaps.length;b.left_boundary=first?S.gaps[first-1]:null;b.right_boundary=last<N-1?S.gaps[last]:null;}
   return b;
 }
 function select(f,rank){
   integer(rank,"rank",0,f.blocks-1);let lo=0,hi=f.components.length;
   while(lo<hi){const mid=(lo+hi)>>1;work.selection_steps++;if(f.prefix[mid+1]<=rank)lo=mid+1;else hi=mid;}
   const c=f.components[lo],v=rank-f.prefix[lo],a=f.condition.min_length,b=f.condition.max_length,L=c.length;
   let l=0,h=L;while(l<h){const m=(l+h)>>1;work.selection_steps++;if(count(L,a,b)-count(L-m-1,a,b)<=v)l=m+1;else h=m;}
   const before=count(L,a,b)-count(L-l,a,b),length=a+v-before;
   return {...block(c.first+l,c.first+l+length-1),rank};
 }
 function rank(f,first,last){
   integer(first,"first",0,N-1);integer(last,"last",first,N-1);const length=last-first+1;
   if(length<f.condition.min_length||length>f.condition.max_length)return {member:false,rank:null};
   for(let j=0;j<f.components.length;j++){const c=f.components[j];if(first>=c.first&&last<=c.last){work.rank_count_formulas+=2;return {member:true,rank:f.prefix[j]+count(c.length,f.condition.min_length,f.condition.max_length)-count(c.last-first+1,f.condition.min_length,f.condition.max_length)+length-f.condition.min_length};}}
   return {member:false,rank:null};
 }
 function query(q){
   work.queries++;let out;
   if(q.op==="summary")out={schema:S.schema,prime_count:N,last_prime:S.primes.at(-1),gaps:S.gaps.length,nodes:S.nodes.length,levels:S.levels.map(l=>({id:l.id,min_active_gap:l.min_active_gap,components:l.components,blocks:l.blocks,longest:l.longest})),construction_work:S.work};
   else if(q.op==="node")out=S.nodes[integer(q.id,"node id",0,S.nodes.length-1)];
   else if(q.op==="phase")out=S.levels[integer(q.id,"phase id",0,S.levels.length-1)];
   else if(q.op==="block")out=block(q.first_index,q.last_index,true);
   else if(q.op==="conditions")out=[...cache.values()].map(f=>({condition:f.condition,phase:f.phase,blocks:f.blocks,components:f.components.length,longest:f.longest}));
   else {const f=family(q.condition);
     if(q.op==="family")out={condition:f.condition,phase:f.phase,blocks:f.blocks,components:f.components.length,longest:f.longest};
     else if(q.op==="components")out={condition:f.condition,phase:f.phase,blocks:f.blocks,longest:f.longest,components:f.components,prefix:f.prefix};
     else if(q.op==="select")out=select(f,q.rank);
     else if(q.op==="rank")out=rank(f,q.first_index,q.last_index);
     else if(q.op==="page"){const offset=integer(q.offset??0,"offset",0,f.blocks),limit=integer(q.limit??20,"limit",0,512),end=Math.min(f.blocks,offset+limit);out={total:f.blocks,offset,next:end<f.blocks?end:null,rows:Array.from({length:end-offset},(_,i)=>select(f,offset+i))};}
     else throw new Error("unknown query");
   }return copy(out);
 }
 return {query,work:()=>copy(work)};
}
module.exports={compile,openIndex};
