"use strict";
// Green 62: fixed-modulus product fibers and target-specific deletion families.
// Prime/completeness and supplied binomial rows are explicit input premises.
function integer(x,name,min,max){if(!Number.isSafeInteger(x)||x<min||x>max)throw new RangeError(name);return x;}
function decimal(x,name){if(typeof x!=="string"||!/^(0|[1-9][0-9]*)$/.test(x))throw new TypeError(name);return BigInt(x);}
function compile(input){
 const p=integer(input.modulus,"modulus",3,100000), primes=input.primes;
 if(!Array.isArray(primes)||!primes.length)throw new TypeError("nonempty prime premise");
 const m=primes.length,L=input.limits||{};
 integer(m,"prime cap",1,L.max_primes||128);
 if(p>(L.max_modulus||100000))throw new RangeError("modulus cap");
 primes.forEach((v,i)=>{integer(v,"prime value",2,p-1);if(i&&v<=primes[i-1])throw new Error("strict prime order");});
 if(m*(m+1)/2>(L.max_pair_products||20000))throw new RangeError("pair cap");
 const bin=input.binomial_rows,bc=input.binomial_cumulative;
 if(!Array.isArray(bin)||!Array.isArray(bc)||bin.length<=m||bc.length<=m)throw new Error("binomial premises missing");
 for(let f=0;f<=m;f++){if(bin[f].length!==f+1||bc[f].length!==f+2||bc[f][0]!=="0")throw new Error("binomial row shape");for(const v of bin[f])decimal(v,"binomial");for(const v of bc[f])decimal(v,"cumulative");}
 const work={pair_products:0,pair_remainders:0,pair_quotients:0,matching_incidence_checks:0,coefficient_cells:0,cumulative_cells:0,binomial_coefficient_copies:0,binomial_cumulative_copies:0,shifted_zero_cells:0,edge_weighted_additions:0,new_cumulative_additions:0,incidence_coefficient_additions:0,primality_tests:0,sieve_operations:0,pascal_recurrence_operations:0};
 const pairs=[],fibers=Array.from({length:p-1},(_,i)=>({target:i+1,pair_ids:[],edge_pair_ids:[],loop_pair_ids:[],unused:[],groups:[],states:[],root:null,ordered_representations:0}));
 for(let i=0;i<m;i++)for(let j=i;j<m;j++){
  const product=primes[i]*primes[j],target=product%p,quotient=Math.floor(product/p);
  work.pair_products++;work.pair_remainders++;work.pair_quotients++;
  if(target===0)throw new Error("prime-modulus premise violated by zero product");
  const id=pairs.length,row={id,i,j,product,target,quotient,ordered_weight:i===j?1:2};
  pairs.push(row);const f=fibers[target-1];f.pair_ids.push(id);f.ordered_representations+=row.ordered_weight;
  (i===j?f.loop_pair_ids:f.edge_pair_ids).push(id);
 }
 const nodes=[],memo=new Map();
 function state(e,l,f){
  const key=e+","+l+","+f;if(memo.has(key))return memo.get(key);
  if(nodes.length>=(L.max_states||10000))throw new RangeError("state cap");
  let child=null;
  if(e)child=state(e-1,l,f);else if(l)child=state(0,l-1,f);else if(f)child=state(0,0,f-1);
  const degree=2*e+l+f,need=degree+1;
  if(work.coefficient_cells+need>(L.max_coefficient_cells||200000))throw new RangeError("coefficient cap");
  let coeff,cumulative,kind;
  if(!e){
   coeff=Array(l).fill("0").concat(bin[f]);cumulative=Array(l).fill("0").concat(bc[f].slice(1));
   work.binomial_coefficient_copies+=f+1;work.binomial_cumulative_copies+=f+1;work.shifted_zero_cells+=2*l;
   kind="shifted_binomial_premise";
  }else{
   const a=nodes[child].coefficients.map(BigInt),out=Array(need).fill(0n);
   for(let k=0;k<a.length;k++){out[k+1]+=2n*a[k];out[k+2]+=a[k];work.edge_weighted_additions+=2;}
   coeff=out.map(String);let sum=0n;cumulative=out.map(v=>{sum+=v;work.new_cumulative_additions++;return String(sum);});kind="edge_recurrence";
  }
  work.coefficient_cells+=need;work.cumulative_cells+=need;
  const id=nodes.length;nodes.push({id,key,e,l,f,degree,child,kind,coefficients:coeff,cumulative});memo.set(key,id);return id;
 }
 const profiles=new Map(),incidence=Array(m+1).fill(0n);
 for(const f of fibers){
  const seen=new Set();
  for(const id of f.pair_ids){const q=pairs[id];for(const i of q.i===q.j?[q.i]:[q.i,q.j]){work.matching_incidence_checks++;if(seen.has(i))throw new Error("fiber is not matching plus loops");seen.add(i);}}
  for(let i=0;i<m;i++)if(!seen.has(i))f.unused.push(i);
  for(const id of f.edge_pair_ids){const q=pairs[id];f.groups.push({kind:"edge",indices:[q.i,q.j],pair_id:id});}
  for(const id of f.loop_pair_ids){const q=pairs[id];f.groups.push({kind:"loop",indices:[q.i],pair_id:id});}
  for(const i of f.unused)f.groups.push({kind:"free",indices:[i]});
  let e=f.edge_pair_ids.length,l=f.loop_pair_ids.length,v=f.unused.length;
  f.root=state(e,l,v);f.states.push(f.root);
  for(const g of f.groups){if(g.kind==="edge")e--;else if(g.kind==="loop")l--;else v--;f.states.push(state(e,l,v));}
  f.minimum_deletions=f.edge_pair_ids.length+f.loop_pair_ids.length;
  f.minimum_count=nodes[f.root].coefficients[f.minimum_deletions];
  f.total_blocking_deletions=nodes[f.root].cumulative[m];
  const key=nodes[f.root].key;if(!profiles.has(key))profiles.set(key,{key,edges:f.edge_pair_ids.length,loops:f.loop_pair_ids.length,free:f.unused.length,targets:[]});profiles.get(key).targets.push(f.target);
  for(let k=0;k<=m;k++){incidence[k]+=BigInt(nodes[f.root].coefficients[k]);work.incidence_coefficient_additions++;}
 }
 const min=Math.min(...fibers.map(f=>f.minimum_deletions)),max=Math.max(...fibers.map(f=>f.minimum_deletions));
 const summary={modulus:p,prime_count:m,unordered_pairs:pairs.length,ordered_pairs:m*m,covered_targets:fibers.filter(f=>f.pair_ids.length).length,uncovered_targets:fibers.filter(f=>!f.pair_ids.length).map(f=>f.target),profile_count:profiles.size,state_count:nodes.length,minimum_deletion_range:[min,max],least_resilient_targets:fibers.filter(f=>f.minimum_deletions===min).map(f=>f.target),most_resilient_targets:fibers.filter(f=>f.minimum_deletions===max).map(f=>f.target),target_deletion_incidences_by_size:incidence.map(String)};
 return {format:"green62-prime-deletion-v1",modulus:p,primes:primes.slice(),provenance:input.provenance,pairs,fibers,nodes,profiles:Array.from(profiles.values()),summary,construction_work:work};
}
function openIndex(data){
 if(data.format!=="green62-prime-deletion-v1"||data.fibers.length!==data.modulus-1)throw new Error("snapshot shape");
 const m=data.primes.length,maskLimit=1n<<BigInt(m);
 const work={coefficient_lookups:0,group_steps:0,pair_scans:0,bit_checks:0,mask_decodes:0,modular_products:0,coefficient_recurrence_operations:0};
 function fiber(t){integer(t,"target",1,data.modulus-1);return data.fibers[t-1];}
 function bounds(o={}){const lo=o.min_deletions===undefined?0:integer(o.min_deletions,"min_deletions",0,m),hi=o.max_deletions===undefined?m:integer(o.max_deletions,"max_deletions",0,m);if(lo>hi)throw new RangeError("inverted deletion range");return[lo,hi];}
 function count(id,lo,hi){const n=data.nodes[id];if(hi<0||lo>n.degree||lo>hi)return 0n;lo=Math.max(lo,0);hi=Math.min(hi,n.degree);work.coefficient_lookups++;let z=BigInt(n.cumulative[hi]);if(lo>0){work.coefficient_lookups++;z-=BigInt(n.cumulative[lo-1]);}return z;}
 function mask(x){const v=typeof x==="bigint"?x:decimal(x,"deleted mask");if(v<0n||v>=maskLimit)throw new RangeError("deleted mask outside host");return v;}
 function bit(v,i){work.bit_checks++;return (v&(1n<<BigInt(i)))!==0n;}
 function decode(v){work.mask_decodes++;const indices=[];for(let i=0;i<m;i++)if(bit(v,i))indices.push(i);return {deleted_mask:String(v),deleted_indices:indices,deleted_primes:indices.map(i=>data.primes[i]),deletion_count:indices.length};}
 function choices(g){if(g.kind==="edge")return[[g.indices[0]],[g.indices[1]],g.indices];if(g.kind==="loop")return[g.indices];return[[],g.indices];}
 function select(t,r,o={}){
  const f=fiber(t),[lo,hi]=bounds(o),rank=typeof r==="bigint"?r:decimal(r,"rank"),total=count(f.root,lo,hi);
  if(rank<0n||rank>=total)throw new RangeError("rank outside family");
  let left=rank,used=0,v=0n;const trace=[];
  for(let j=0;j<f.groups.length;j++){
   work.group_steps++;const g=f.groups[j],cs=choices(g),counts=[];let chosen=-1;
   for(let a=0;a<cs.length;a++){
    const c=count(f.states[j+1],lo-used-cs[a].length,hi-used-cs[a].length);counts.push(String(c));
    if(left<c){chosen=a;for(const i of cs[a])v|=1n<<BigInt(i);used+=cs[a].length;break;}left-=c;
   }
   if(chosen<0)throw new Error("saved coefficient selection mismatch");
   trace.push({group:j,kind:g.kind,choice:chosen,counts_through_choice:counts,remaining_rank:String(left)});
  }
  return {target:t,rank:String(rank),min_deletions:lo,max_deletions:hi,total:String(total),...decode(v),trace};
 }
 function rank(t,x,o={}){
  const f=fiber(t),[lo,hi]=bounds(o),v=mask(x);let used=0,r=0n;const trace=[];
  for(let j=0;j<f.groups.length;j++){
   work.group_steps++;const g=f.groups[j],selected=g.indices.filter(i=>bit(v,i)),cs=choices(g);
   const a=cs.findIndex(c=>c.length===selected.length&&c.every((i,k)=>i===selected[k]));
   if(a<0)return {target:t,member:false,reason:"surviving_pair",group:j,pair:data.pairs[g.pair_id]};
   let skipped=0n;for(let k=0;k<a;k++)skipped+=count(f.states[j+1],lo-used-cs[k].length,hi-used-cs[k].length);
   r+=skipped;used+=selected.length;trace.push({group:j,choice:a,skipped:String(skipped),rank_prefix:String(r)});
  }
  if(used<lo||used>hi)return {target:t,member:false,reason:"deletion_count",deletion_count:used,min_deletions:lo,max_deletions:hi};
  return {target:t,member:true,rank:String(r),total:String(count(f.root,lo,hi)),deletion_count:used,min_deletions:lo,max_deletions:hi,trace};
 }
 function coverage(x){
  const v=mask(x),rows=[];let covered=0,ordered=0,unordered=0;
  for(const f of data.fibers){let u=0,z=0,first=null;for(const id of f.pair_ids){work.pair_scans++;const q=data.pairs[id];if(!bit(v,q.i)&&!bit(v,q.j)){u++;z+=q.ordered_weight;if(first===null)first=id;}}if(u)covered++;ordered+=z;unordered+=u;rows.push({target:f.target,unordered:u,ordered:z,first_surviving_pair:first});}
  return {...decode(v),covered_targets:covered,uncovered_targets:rows.filter(r=>!r.unordered).map(r=>r.target),surviving_unordered_pairs:unordered,surviving_ordered_pairs:ordered,rows};
 }
 return {
  summary:()=>data.summary,
  profiles:()=>data.profiles,
  fiber:t=>{const f=fiber(t);return {...f,pairs:f.pair_ids.map(id=>data.pairs[id]),coefficients:data.nodes[f.root].coefficients};},
  family:(t,o={})=>{const f=fiber(t),[lo,hi]=bounds(o);return {target:t,min_deletions:lo,max_deletions:hi,count:String(count(f.root,lo,hi)),minimum_deletions:f.minimum_deletions,minimum_count:f.minimum_count};},
  select,rank,coverage,
  page:(t,start,limit,o={})=>{integer(limit,"page limit",0,10000);let r=typeof start==="bigint"?start:decimal(start,"start"),[lo,hi]=bounds(o),total=count(fiber(t).root,lo,hi);if(r<0n||r>total)throw new RangeError("page start");const items=[];for(let i=0;i<limit&&r<total;i++,r++)items.push(select(t,r,o));return {target:t,start:String(start),next:String(r),total:String(total),items};},
  work:()=>({...work})
 };
}
module.exports={compile,openIndex};
