"use strict";
// Exact finite simultaneous extensions; inherited prefix membership is an input premise.
function pop(m){let n=0;for(;m;m&=m-1)n++;return n;}
function first(m){return 31-Math.clz32(m&-m);}
function assert(ok,msg){if(!ok)throw new TypeError(msg);}
function checkedMask(m,n){assert(Number.isSafeInteger(m)&&m>=0&&m<(1<<n),"mask outside declared labels");return m;}
function labels(m,n){const a=[];for(let i=0;i<n;i++)if(m&(1<<i))a.push(i);return a;}
function makeSolver(adj,weights,seed,work){
 const nodes=new Map(seed.map(x=>[x.mask,x]));
 function solve(mask){
  if(nodes.has(mask)){work.savedNodeHits++;return nodes.get(mask);}
  if(mask===0){const z={mask:0,pivot:null,exclude:null,include:null,counts:[1],best:["0"],ties:[1]};nodes.set(0,z);work.newNodes++;return z;}
  const v=first(mask),low=mask&~(1<<v),high=low&~adj[v],a=solve(low),b=solve(high);
  const length=Math.max(a.counts.length,b.counts.length+1),counts=[],best=[],ties=[];
  for(let k=0;k<length;k++){
   const ca=a.counts[k]||0,cb=k?b.counts[k-1]||0:0;
   counts[k]=ca+cb;
   const wa=ca?BigInt(a.best[k]):null,wb=cb?BigInt(weights[v])+BigInt(b.best[k-1]):null;
   if(wa===null&&wb===null){best[k]=null;ties[k]=0;}
   else if(wb===null||(wa!==null&&wa>wb)){best[k]=String(wa);ties[k]=a.ties[k];}
   else if(wa===null||wb>wa){best[k]=String(wb);ties[k]=b.ties[k-1];}
   else{best[k]=String(wa);ties[k]=a.ties[k]+b.ties[k-1];}
   work.coefficientCells++;
  }
  const r={mask,pivot:v,exclude:low,include:high,counts,best,ties};nodes.set(mask,r);work.newNodes++;return r;
 }
 return {solve,nodes};
}
function construct(input){
 const n=input.candidates.length;
 assert(n>=1&&n<=20&&input.denominator==="2","one to twenty denominator-two candidates required");
 const a=input.candidates.map(x=>BigInt(x.numerator));
 for(let i=0;i<n;i++)assert(a[i]>0n&&(i===0||a[i]>a[i-1]),"candidates must be strictly increasing positive integers");
 const adj=Array(n).fill(0),pairs=[];
 const work={newPairDistances:0,inheritedPairWitnesses:0,conflictEdges:0,weightProductFactors:0,weightDivisions:0,newNodes:0,savedNodeHits:0,coefficientCells:0};
 const old=input.inherited_obstruction;
 assert(old.left_label===4&&old.right_label===5&&a[4]===87n&&a[5]===88n&&old.scaled_distance==="1","inherited obstruction identity mismatch");
 for(let i=0;i<n;i++)for(let j=i+1;j<n;j++){
  let row;
  if(i===old.left_label&&j===old.right_label){
   row={left:i,right:j,conflict:true,provenance:"inherited",nearest_multiplier:old.positive_multiplier,scaled_distance:old.scaled_distance};
   work.inheritedPairWitnesses++;
  }else{
   const q=a[j]/a[i],r=a[j]%a[i],upper=a[i]-r,takeFloor=r<=upper;
   row={left:i,right:j,conflict:(takeFloor?r:upper)<2n,provenance:"new",quotient:String(q),remainder:String(r),nearest_multiplier:String(takeFloor?q:q+1n),scaled_distance:String(takeFloor?r:upper)};
   work.newPairDistances++;
  }
  if(row.conflict){adj[i]|=1<<j;adj[j]|=1<<i;work.conflictEdges++;}
  pairs.push(row);
 }
 let D=1n;for(const x of a){D*=x;work.weightProductFactors++;}
 const weights=a.map(x=>{work.weightDivisions++;return String(2n*D/x);});
 const solver=makeSolver(adj,weights,[],work),full=(1<<n)-1,root=solver.solve(full);
 return {schema:"commons.erdos143.simultaneous_extensions/v1",input_id:input.id,denominator:"2",candidates:input.candidates,prefix_numerators:input.prefix_numerators,adjacency:adj,pairs,weight_denominator:String(D),weights,root_mask:full,root,nodes:Array.from(solver.nodes.values()),work,scope:"Only simultaneous subsets of the supplied individually compatible candidates; prefix membership is inherited."};
}
function createReader(certificate){
 assert(certificate.schema==="commons.erdos143.simultaneous_extensions/v1","unrecognized certificate");
 const c=certificate,n=c.candidates.length,full=c.root_mask,weights=c.weights;
 const work={newNodes:0,savedNodeHits:0,coefficientCells:0,conditionsBuilt:0,conditionHits:0,requiredAdjacencyReads:0,requiredWeightAdds:0,selectionBranches:0,rankingBranches:0,rowsMaterialized:0,marginalConditions:0,newPairDistances:0,newWeightProducts:0};
 const solver=makeSolver(c.adjacency,weights,c.nodes,work),conditions=new Map();
 function condition(required=0,excluded=0){
  checkedMask(required,n);checkedMask(excluded,n);const key=required+":"+excluded;
  if(conditions.has(key)){work.conditionHits++;return conditions.get(key);}
  work.conditionsBuilt++;let reason=required&excluded?"required-excluded overlap":null,ban=required|excluded,W=0n;
  for(let v=0;v<n;v++)if(required&(1<<v)){
   work.requiredAdjacencyReads++;if(c.adjacency[v]&required)reason="required conflict";
   ban|=c.adjacency[v];W+=BigInt(weights[v]);work.requiredWeightAdds++;
  }
  const base=pop(required),available=full&~ban,node=reason?null:solver.solve(available);
  const counts=Array(n+1).fill(0),best=Array(n+1).fill(null),ties=Array(n+1).fill(0);
  if(node)for(let k=0;k<node.counts.length;k++)if(node.counts[k]){counts[k+base]=node.counts[k];best[k+base]=String(W+BigInt(node.best[k]));ties[k+base]=node.ties[k];}
  const maxSize=counts.reduce((r,x,k)=>x?k:r,-1),total=counts.reduce((s,x)=>s+x,0);
  let global=null,globalSizes=[],globalTies=0;
  for(let k=0;k<=n;k++)if(best[k]!==null){
   const w=BigInt(best[k]);
   if(global===null||w>global){global=w;globalSizes=[k];globalTies=ties[k];}
   else if(w===global){globalSizes.push(k);globalTies+=ties[k];}
  }
  const r={key,required,excluded,available,required_size:base,required_weight:String(W),reason,counts,best,ties,total,max_size:maxSize,max_size_count:maxSize<0?0:counts[maxSize],global_best:global===null?null:String(global),global_best_sizes:globalSizes,global_best_ties:globalTies,weight_denominator:c.weight_denominator};
  conditions.set(key,r);return r;
 }
 function args(q){
  const x=condition(q.required||0,q.excluded||0);
  assert(Number.isSafeInteger(q.size)&&q.size>=0&&q.size<=n,"invalid cardinality");
  return x;
 }
 function branches(node,k,optimal){
  const low=solver.solve(node.exclude),high=solver.solve(node.include);
  let l=low.counts[k]||0,h=k?high.counts[k-1]||0:0;
  if(optimal){
   const target=node.best[k];
   l=l&&low.best[k]===target?low.ties[k]:0;
   h=h&&String(BigInt(weights[node.pivot])+BigInt(high.best[k-1]))===target?high.ties[k-1]:0;
  }
  return {l,h};
 }
 function materialize(mask){
  work.rowsMaterialized++;const ids=labels(mask,n);let w=0n;for(const v of ids)w+=BigInt(weights[v]);
  return {mask,labels:ids,numerators:ids.map(v=>c.candidates[v].numerator),denominator:"2",size:ids.length,added_reciprocal_sum:{numerator:String(w),denominator:c.weight_denominator}};
 }
 function select(q){
  const x=args(q),optimal=q.optimal===true,total=optimal?x.ties[q.size]:x.counts[q.size];
  assert(Number.isSafeInteger(q.rank)&&q.rank>=0,"rank must be a nonnegative safe integer");
  if(q.rank>=total)return {status:"OUT_OF_RANGE",total};
  let rank=q.rank,mask=x.available,out=x.required,k=q.size-x.required_size;
  while(mask){
   const node=solver.solve(mask),b=branches(node,k,optimal);work.selectionBranches++;
   if(rank<b.l)mask=node.exclude;
   else{rank-=b.l;out|=1<<node.pivot;k--;mask=node.include;}
  }
  return {status:"FOUND",rank:q.rank,total,optimal,...materialize(out)};
 }
 function rank(q){
  const x=args(q),m=checkedMask(q.mask,n),optimal=q.optimal===true,total=optimal?x.ties[q.size]:x.counts[q.size];
  if(x.reason||pop(m)!==q.size||(m&x.required)!==x.required||(m&x.excluded)||((m&~x.required)&~x.available))return {status:"NOT_IN_FAMILY",total};
  for(const v of labels(m,n))if(c.adjacency[v]&m)return {status:"NOT_IN_FAMILY",total};
  let mask=x.available,k=q.size-x.required_size,r=0;
  while(mask){
   const node=solver.solve(mask),b=branches(node,k,optimal);work.rankingBranches++;
   if(m&(1<<node.pivot)){if(!b.h)return {status:"NOT_IN_FAMILY",total};r+=b.l;k--;mask=node.include;}
   else{if(!b.l)return {status:"NOT_IN_FAMILY",total};mask=node.exclude;}
  }
  return {status:"FOUND",rank:r,total,optimal,mask:m};
 }
 function page(q){
  args(q);assert(Number.isSafeInteger(q.start)&&q.start>=0&&Number.isSafeInteger(q.limit)&&q.limit>=0&&q.limit<=10000,"invalid bounded page");
  const x=condition(q.required||0,q.excluded||0),total=q.optimal===true?x.ties[q.size]:x.counts[q.size],rows=[];
  for(let r=q.start;r<Math.min(total,q.start+q.limit);r++)rows.push(select({...q,rank:r}));
  return {total,start:q.start,returned:rows.length,rows};
 }
 function marginals(q){
  const x=args(q);const rows=[];
  for(let v=0;v<n;v++){
   work.marginalConditions++;
   const y=condition(x.required|(1<<v),x.excluded);
   const count=y.counts[q.size];
   const optimalCount=count&&y.best[q.size]===x.best[q.size]?y.ties[q.size]:0;
   rows.push({label:v,count,optimal_count:optimalCount});
  }
  return {size:q.size,total:x.counts[q.size],optimal_total:x.ties[q.size],rows};
 }
 return {condition,select,rank,page,marginals,summary:()=>({n,conflict_edges:c.work.conflictEdges,pair_records:c.pairs.length,saved_nodes:c.nodes.length,order:"label bitvector lexicographic with 0 before 1",full:condition()}),work:()=>({...work}),snapshot:()=>({nodes:Array.from(solver.nodes.values()),conditions:Array.from(conditions.values())})};
}
module.exports={construct,createReader};
