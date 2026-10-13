"use strict";
// Restricted sums of distinct selected values must avoid the complete ambient affine host.
function integer(x,name,a,b){if(!Number.isSafeInteger(x)||x<a||x>b)throw new RangeError(name);return x;}
function signed(x,name){if(typeof x==="bigint")return x;if(typeof x!=="string"||!/^(-?[1-9][0-9]*|0)$/.test(x))throw new TypeError(name);return BigInt(x);}
function compile(input){
 const H=input.host,L=input.limits||{};
 if(!Array.isArray(H)||!H.length)throw new TypeError("host");
 const n=integer(H.length,"host size",1,Math.min(24,L.max_host||24)),full=(1<<n)-1,index=new Map();
 H.forEach((a,i)=>{integer(a,"host value",-1000000,1000000);if(i&&a<=H[i-1])throw new Error("host order");index.set(a,i);});
 const bins=input.binomial_rows,cums=input.binomial_cumulative;
 if(!Array.isArray(bins)||bins.length<=n||!Array.isArray(cums)||cums.length<=n)throw new Error("binomial premises");
 for(let f=0;f<=n;f++){if(bins[f].length!==f+1||cums[f].length!==f+2||cums[f][0]!=="0")throw new Error("binomial shape");for(const x of bins[f].concat(cums[f]))if(typeof x!=="string"||!/^(0|[1-9][0-9]*)$/.test(x)||!Number.isSafeInteger(Number(x)))throw new TypeError("coefficient premise");}
 const work={inherited_pairs_examined:0,diagonal_pairs_omitted:0,distinct_pairs_consumed:0,critical_subtractions:0,edge_witnesses:0,adjacency_insertions:0,state_key_vertex_probes:0,dag_nodes:0,coefficient_cells:0,cumulative_cells:0,binomial_coefficient_copies:0,binomial_cumulative_copies:0,new_coefficient_additions:0,new_cumulative_additions:0,pair_sum_additions:0,pascal_recurrence_operations:0};
 const maps=new Map(),pairs=[];
 for(const f of input.sum_fibers){
  integer(f.sum,"sum premise",-2000000,2000000);
  for(const p of f.pairs){work.inherited_pairs_examined++;const i=index.get(p.a),j=index.get(p.b);if(i===undefined||j===undefined||i>j)throw new Error("pair premise indices");
   if(i===j){work.diagonal_pairs_omitted++;continue;}
   if(p.mask!==((1<<i)|(1<<j)))throw new Error("pair mask premise");
   const id=pairs.length;pairs.push({id,i,j,a:p.a,b:p.b,sum:f.sum,mask:p.mask});work.distinct_pairs_consumed++;
   for(let k=0;k<n;k++){
    const t=H[k]-f.sum;work.critical_subtractions++;
    if(!maps.has(t)){if(maps.size+1>=(L.max_graphs||256))throw new RangeError("graph cap");maps.set(t,{ratio:t,adjacency:Array(n).fill(0),edges:[]});}
    const g=maps.get(t);if(g.adjacency[i]&(1<<j))throw new Error("duplicate inherited pair");
    if(work.edge_witnesses>=(L.max_witnesses||20000))throw new RangeError("witness cap");
    g.adjacency[i]|=1<<j;g.adjacency[j]|=1<<i;work.adjacency_insertions+=2;
    g.edges.push({pair_id:id,i,j,mask:p.mask,target_index:k,target:H[k]});work.edge_witnesses++;
   }
  }
 }
 const graphs=Array.from(maps.values()).sort((a,b)=>a.ratio-b.ratio);
 graphs.push({ratio:null,adjacency:Array(n).fill(0),edges:[]});
 const nodes=[],memo=new Map();
 function state(mask,adj){
  let rest=mask,key=String(mask),count=0,edge=false;
  while(rest){const b=rest&-rest,i=31-Math.clz32(b),a=adj[i]&mask;key+=","+a;count++;if(a)edge=true;rest^=b;work.state_key_vertex_probes++;}
  if(memo.has(key))return memo.get(key);
  const v=mask?31-Math.clz32(mask&-mask):null,without=mask?(mask&~(1<<v)):0;
  let exclude=null,include=null,coefficients,cumulative,kind;
  if(mask){exclude=state(without,adj);include=edge?state(without&~adj[v],adj):exclude;}
  if(!edge){coefficients=bins[count].map(Number);cumulative=cums[count].slice(1).map(Number);work.binomial_coefficient_copies+=count+1;work.binomial_cumulative_copies+=count+1;kind="binomial_premise";}
  else{
   const a=nodes[exclude].coefficients,b=nodes[include].coefficients,len=Math.max(a.length,b.length+1),out=Array(len).fill(0);
   for(let k=0;k<a.length;k++){out[k]+=a[k];work.new_coefficient_additions++;}
   for(let k=0;k<b.length;k++){out[k+1]+=b[k];work.new_coefficient_additions++;}
   coefficients=out;let sum=0;cumulative=out.map(x=>{sum+=x;work.new_cumulative_additions++;return sum;});kind="independent_set_recurrence";
  }
  if(nodes.length>=(L.max_nodes||100000))throw new RangeError("node cap");
  if(work.coefficient_cells+coefficients.length>(L.max_coefficient_cells||2000000))throw new RangeError("coefficient cap");
  work.coefficient_cells+=coefficients.length;work.cumulative_cells+=cumulative.length;work.dag_nodes++;
  const id=nodes.length;nodes.push({id,mask,vertex:v,exclude,include,kind,coefficients,cumulative});memo.set(key,id);return id;
 }
 const byRatio={},profiles=new Map();
 for(let id=0;id<graphs.length;id++){
  const g=graphs[id];g.id=id;g.root=state(full,g.adjacency);const node=nodes[g.root];
  g.total=node.cumulative[node.cumulative.length-1];g.maximum_size=node.coefficients.length-1;g.maximum_count=node.coefficients[g.maximum_size];
  if(g.ratio!==null)byRatio[String(g.ratio)]=id;
  const key=g.maximum_size+","+g.maximum_count+","+g.total;if(!profiles.has(key))profiles.set(key,{key,maximum_size:g.maximum_size,maximum_count:g.maximum_count,total:g.total,graph_ids:[]});profiles.get(key).graph_ids.push(id);
 }
 const min=Math.min(...graphs.map(g=>g.maximum_size));
 return {format:"affine-restricted-sum-avoiding-v1",host:H.slice(),provenance:input.provenance,pairs,graphs,ratio_to_graph:byRatio,generic_graph:graphs.length-1,nodes,profiles:Array.from(profiles.values()),summary:{host_size:n,critical_graphs:graphs.length-1,generic_graph:graphs.length-1,critical_ratios:graphs.slice(0,-1).map(g=>g.ratio),distinct_pairs:pairs.length,edge_witnesses:work.edge_witnesses,node_count:nodes.length,profile_count:profiles.size,smallest_maximum:min,graphs_attaining_smallest_maximum:graphs.filter(g=>g.maximum_size===min).map(g=>g.id),graph_summaries:graphs.map(g=>({id:g.id,ratio:g.ratio,edges:g.edges.length,total:g.total,maximum_size:g.maximum_size,maximum_count:g.maximum_count}))},construction_work:work};
}
function openIndex(data){
 if(data.format!=="affine-restricted-sum-avoiding-v1"||!Array.isArray(data.graphs)||!data.host.length)throw new Error("snapshot shape");
 const n=data.host.length,full=(1<<n)-1;
 const work={parameter_divisions:0,parameter_remainders:0,coefficient_lookups:0,dag_steps:0,membership_edge_scans:0,mask_bit_checks:0,affine_multiplications:0,affine_additions:0,critical_subtractions:0,pair_sum_additions:0,graph_reconstructions:0,coefficient_recurrence_operations:0};
 function resolve(p={}){
  const scale=signed(p.scale===undefined?"1":p.scale,"scale"),shift=signed(p.shift===undefined?"0":p.shift,"shift");if(scale===0n)throw new RangeError("nonzero scale required");
  const q=shift/scale,r=shift%scale;work.parameter_divisions++;work.parameter_remainders++;
  const id=r===0n&&Object.prototype.hasOwnProperty.call(data.ratio_to_graph,String(q))?data.ratio_to_graph[String(q)]:data.generic_graph;
  return {scale,shift,graph:data.graphs[id],parameters:{scale:String(scale),shift:String(shift),integral_ratio:r===0n,ratio:r===0n?String(q):null,graph_id:id}};
 }
 function bounds(o={}){const lo=o.min_size===undefined?0:integer(o.min_size,"min_size",0,n),hi=o.max_size===undefined?n:integer(o.max_size,"max_size",0,n);if(lo>hi)throw new RangeError("inverted size range");return[lo,hi];}
 function count(id,lo,hi){const c=data.nodes[id].cumulative;if(hi<0||lo>=c.length||lo>hi)return 0;lo=Math.max(0,lo);hi=Math.min(c.length-1,hi);work.coefficient_lookups++;let a=c[hi];if(lo){a-=c[lo-1];work.coefficient_lookups++;}return a;}
 function value(x,z){work.affine_multiplications++;work.affine_additions++;return String(z.scale*BigInt(x)+z.shift);}
 function decode(mask,z){const indices=[];for(let i=0;i<n;i++){work.mask_bit_checks++;if(mask&(1<<i))indices.push(i);}return {mask,size:indices.length,indices,base_values:indices.map(i=>data.host[i]),affine_values:indices.map(i=>value(data.host[i],z))};}
 function bad(mask,z){integer(mask,"subset mask",0,full);for(const e of z.graph.edges){work.membership_edge_scans++;if((mask&e.mask)===e.mask){const pair=data.pairs[e.pair_id];return {pair_id:e.pair_id,base_pair:[pair.a,pair.b],base_target:e.target,affine_pair:[value(pair.a,z),value(pair.b,z)],affine_target:value(e.target,z)};}}return null;}
 function select(p,rank,o={}){
  const z=resolve(p),[lo,hi]=bounds(o),total=count(z.graph.root,lo,hi);integer(rank,"rank",0,total-1);
  let left=rank,id=z.graph.root,used=0,mask=0;const trace=[];
  while(data.nodes[id].mask){const a=data.nodes[id],skip=count(a.exclude,lo-used,hi-used);work.dag_steps++;
   if(left<skip){trace.push({node:id,vertex:a.vertex,include:false,excluded_branch_count:skip,remaining_rank:left});id=a.exclude;}
   else{left-=skip;mask|=1<<a.vertex;used++;trace.push({node:id,vertex:a.vertex,include:true,excluded_branch_count:skip,remaining_rank:left});id=a.include;}
  }
  return {parameters:z.parameters,rank,min_size:lo,max_size:hi,total,...decode(mask,z),trace};
 }
 function rank(p,mask,o={}){
  const z=resolve(p),[lo,hi]=bounds(o),witness=bad(mask,z);if(witness)return {parameters:z.parameters,member:false,reason:"restricted_sum_in_ambient",witness};
  let id=z.graph.root,used=0,r=0;const trace=[];
  while(data.nodes[id].mask){const a=data.nodes[id];work.dag_steps++;work.mask_bit_checks++;const yes=(mask&(1<<a.vertex))!==0;let skipped=0;if(yes){skipped=count(a.exclude,lo-used,hi-used);r+=skipped;used++;}
   trace.push({node:id,vertex:a.vertex,include:yes,skipped,rank_prefix:r});id=yes?a.include:a.exclude;
  }
  if(used<lo||used>hi)return {parameters:z.parameters,member:false,reason:"size",size:used,min_size:lo,max_size:hi};
  return {parameters:z.parameters,member:true,rank:r,size:used,min_size:lo,max_size:hi,total:count(z.graph.root,lo,hi),trace};
 }
 return {
  summary:()=>data.summary,profiles:()=>data.profiles,
  graph:p=>{const z=resolve(p);return {parameters:z.parameters,graph:z.graph,pairs:z.graph.edges.map(e=>({edge:e,pair:data.pairs[e.pair_id]})),coefficients:data.nodes[z.graph.root].coefficients};},
  family:(p,o={})=>{const z=resolve(p),[lo,hi]=bounds(o);return {parameters:z.parameters,min_size:lo,max_size:hi,count:count(z.graph.root,lo,hi),maximum_size:z.graph.maximum_size,maximum_count:z.graph.maximum_count};},
  select,rank,
  page:(p,start,limit,o={})=>{const z=resolve(p),[lo,hi]=bounds(o),total=count(z.graph.root,lo,hi);integer(start,"start",0,total);integer(limit,"limit",0,10000);const items=[];for(let i=start;i<Math.min(total,start+limit);i++)items.push(select(p,i,o));return {parameters:z.parameters,start,next:start+items.length,total,items};},
  membership:(p,mask)=>{const z=resolve(p),witness=bad(mask,z);return {parameters:z.parameters,member:witness===null,witness,...decode(mask,z)};},
  work:()=>({...work})
 };
}
module.exports={compile,openIndex};
