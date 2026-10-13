"use strict";
function assert(x,m){if(!x)throw new TypeError(m);}
function pop(x,work,key){let n=0;while(x){x&=x-1n;n++;if(work)work[key]++;}return n;}
function rankInt(s){assert(typeof s==="string"&&/^(0|[1-9][0-9]*)$/.test(s)&&s.length<=64,"canonical rank string required");return BigInt(s);}
function compile(input){
 const n=input.vertices.length;assert(n===16,"declared sixteen-vertex input required");
 const seenVertices=new Set(input.vertices.map(v=>v.source_id));assert(seenVertices.size===n,"duplicate source vertex");
 const work={savedPairCopies:0,localClassAssignments:0,subsetRows:0,supportUnions:0,supportPopcountSteps:0,histogramUpdates:0,budgetCells:0,newCoordinates:0,newChordLengths:0,rationalComparisons:0,oldPerimeterStates:0};
 const bySource=new Map(),pairKeys=new Set();
 for(const p of input.pairs){assert(Number.isInteger(p.i)&&Number.isInteger(p.j)&&0<=p.i&&p.i<p.j&&p.j<n,"invalid pair");const key=p.i+","+p.j;assert(!pairKeys.has(key),"duplicate pair");pairKeys.add(key);if(!bySource.has(p.source_class_id))bySource.set(p.source_class_id,{source_class_id:p.source_class_id,distance:p.distance,pairs:[]});bySource.get(p.source_class_id).pairs.push([p.i,p.j]);work.savedPairCopies++;}
 assert(pairKeys.size===n*(n-1)/2,"incomplete pair list");
 const sourceIds=Array.from(bySource.keys()).sort((a,b)=>a-b),classes=sourceIds.map((id,local)=>({local,...bySource.get(id)})),localOf=new Map(sourceIds.map((x,i)=>[x,i])),C=classes.length;
 const pairClass=Array.from({length:n},()=>Array(n).fill(-1));
 for(const p of input.pairs){const k=localOf.get(p.source_class_id);pairClass[p.i][p.j]=pairClass[p.j][p.i]=k;work.localClassAssignments++;}
 const total=1<<n,rows=Array(total),supports=Array(total),hist=Array.from({length:n+1},()=>Array(C+1).fill(0));
 rows[0]=[0,0,"0"];supports[0]=0n;hist[0][0]=1;work.subsetRows++;work.histogramUpdates++;
 for(let mask=1;mask<total;mask++){
  const bit=mask&-mask,v=31-Math.clz32(bit),rest=mask^bit;let support=supports[rest],uMask=rest;
  while(uMask){const ub=uMask&-uMask,u=31-Math.clz32(ub);support|=1n<<BigInt(pairClass[v][u]);uMask^=ub;work.supportUnions++;}
  const k=rows[rest][0]+1,d=pop(support,work,"supportPopcountSteps");supports[mask]=support;rows[mask]=[k,d,String(support)];hist[k][d]++;work.subsetRows++;work.histogramUpdates++;
 }
 const minima=hist.map((a,k)=>{const d=a.findIndex(x=>x>0);return {cardinality:k,minimum_distances:d,count:String(a[d])};});
 const budgets=[];
 for(let b=0;b<=C;b++){let maxK=-1,count=0;for(let k=0;k<=n;k++){let x=0;for(let d=0;d<=b;d++){x+=hist[k][d];work.budgetCells++;}if(x){maxK=k;count=x;}}budgets.push({budget:b,maximum_cardinality:maxK,minimum_deletions:n-maxK,count:String(count)});}
 return {schema:"commons.erdos89.subset_distance_support/v1",input_id:input.id,vertices:input.vertices.map(v=>({local:v.local,source_id:v.source_id})),classes,pair_class:pairClass,row_format:["cardinality","distinct_distances","decimal_local_distance_support"],row_order:"numeric vertex mask equals row index",rows,histogram:hist,minima,budgets,summary:{vertices:n,pairs:input.pairs.length,distance_classes:C,subsets:total},work};
}
function createReader(c,sourceClassCount){
 assert(c.schema==="commons.erdos89.subset_distance_support/v1","unrecognized certificate");
 const n=c.vertices.length,C=c.classes.length,total=c.rows.length,cache=new Map(),classOf=new Map(c.classes.map(x=>[x.source_class_id,x.local]));
 const work={conditionsBuilt:0,conditionHits:0,rowsScanned:0,supportReads:0,selectedRows:0,rankComparisons:0,materializedRows:0,marginalRows:0,marginalVertexChecks:0,marginalDistanceChecks:0,budgetLookups:0,newSubsetSupports:0,newCoordinates:0,newChordLengths:0,oldPerimeterStates:0};
 function ids(a,bound,name){assert(a===undefined||Array.isArray(a),name+" must be an array");const out=Array.from(new Set(a||[]));for(const v of out)assert(Number.isInteger(v)&&v>=0&&v<bound,"invalid "+name);return out.sort((x,y)=>x-y);}
 function int(v,d){if(v===undefined)return d;assert(Number.isSafeInteger(v),"safe integer bound required");return v;}
 function condition(q={}){
  const requiredVertices=ids(q.required_vertices,n,"required vertex"),forbiddenVertices=ids(q.forbidden_vertices,n,"forbidden vertex");
  const requiredDistances=ids(q.required_distance_ids,sourceClassCount,"required source distance"),forbiddenDistances=ids(q.forbidden_distance_ids,sourceClassCount,"forbidden source distance");
  const minK=Math.max(0,int(q.min_cardinality,0)),maxK=Math.min(n,int(q.max_cardinality,n)),minD=Math.max(0,int(q.min_distances,0)),maxD=Math.min(C,int(q.max_distances,C));
  const key=JSON.stringify([requiredVertices,forbiddenVertices,requiredDistances,forbiddenDistances,minK,maxK,minD,maxD]);
  if(cache.has(key)){work.conditionHits++;return cache.get(key).summary;}work.conditionsBuilt++;
  let requireMask=0,forbidMask=0,requireD=0n,forbidD=0n,missing=false;
  for(const v of requiredVertices)requireMask|=1<<v;for(const v of forbiddenVertices)forbidMask|=1<<v;
  for(const s of requiredDistances){if(!classOf.has(s))missing=true;else requireD|=1n<<BigInt(classOf.get(s));}
  for(const s of forbiddenDistances)if(classOf.has(s))forbidD|=1n<<BigInt(classOf.get(s));
  const masks=[],cardCounts=Array(n+1).fill(0),distanceCounts=Array(C+1).fill(0);
  if(!missing&&!(requireMask&forbidMask)&&!(requireD&forbidD)&&minK<=maxK&&minD<=maxD)for(let mask=0;mask<total;mask++){
   work.rowsScanned++;const row=c.rows[mask];if((mask&requireMask)!==requireMask||(mask&forbidMask)||row[0]<minK||row[0]>maxK||row[1]<minD||row[1]>maxD)continue;
   if(requireD||forbidD){const support=BigInt(row[2]);work.supportReads++;if((support&requireD)!==requireD||(support&forbidD))continue;}
   masks.push(mask);cardCounts[row[0]]++;distanceCounts[row[1]]++;work.selectedRows++;
  }
  let maximumCardinality=null,minimumDistances=null;for(let k=0;k<=n;k++)if(cardCounts[k])maximumCardinality=k;for(let d=0;d<=C;d++)if(distanceCounts[d]){minimumDistances=d;break;}
  const summary={key,count:String(masks.length),required_vertices:requiredVertices,forbidden_vertices:forbiddenVertices,required_distance_ids:requiredDistances,forbidden_distance_ids:forbiddenDistances,min_cardinality:minK,max_cardinality:maxK,min_distances:minD,max_distances:maxD,required_class_absent:missing,cardinality_counts:cardCounts.map(String),distance_counts:distanceCounts.map(String),maximum_cardinality:maximumCardinality,minimum_distances:minimumDistances};
  cache.set(key,{summary,masks});return summary;
 }
 function selection(q){const s=condition(q);return cache.get(s.key);}
 function materialize(mask){
  assert(Number.isInteger(mask)&&mask>=0&&mask<total,"invalid local vertex mask");work.materializedRows++;
  const row=c.rows[mask],support=BigInt(row[2]),vertices=[],distances=[];
  for(let i=0;i<n;i++)if(mask&(1<<i))vertices.push(c.vertices[i].source_id);
  for(let i=0;i<C;i++)if(support&(1n<<BigInt(i)))distances.push({local:i,source_class_id:c.classes[i].source_class_id,distance:c.classes[i].distance});
  return {mask,cardinality:row[0],distinct_distances:row[1],vertices,distance_support:row[2],distances};
 }
 function select(q){const s=selection(q),rank=rankInt(q.rank);if(rank>=BigInt(s.masks.length))return {status:"OUT_OF_RANGE",count:s.summary.count};return {status:"FOUND",rank:q.rank,count:s.summary.count,...materialize(s.masks[Number(rank)])};}
 function rank(q){
  const s=selection(q),mask=q.mask;assert(Number.isInteger(mask)&&mask>=0&&mask<total,"invalid local vertex mask");
  let a=0,b=s.masks.length;while(a<b){const mid=(a+b)>>1;work.rankComparisons++;if(s.masks[mid]<mask)a=mid+1;else b=mid;}
  return a<s.masks.length&&s.masks[a]===mask?{status:"FOUND",rank:String(a),count:s.summary.count,mask}:{status:"NOT_IN_CONDITION",count:s.summary.count,mask};
 }
 function page(q){
  const s=selection(q),start=rankInt(q.start),limit=q.limit;assert(Number.isInteger(limit)&&limit>=0&&limit<=256,"page limit must be 0..256");
  if(start>BigInt(s.masks.length))return {status:"OUT_OF_RANGE",count:s.summary.count,items:[]};
  const a=Number(start),end=Math.min(s.masks.length,a+limit);return {status:"OK",start:q.start,count:s.summary.count,items:s.masks.slice(a,end).map(materialize),next:String(end)};
 }
 function marginals(q){
  const s=selection(q),vertices=Array(n).fill(0),distances=Array(C).fill(0);
  for(const mask of s.masks){work.marginalRows++;const support=BigInt(c.rows[mask][2]);work.supportReads++;for(let i=0;i<n;i++){work.marginalVertexChecks++;if(mask&(1<<i))vertices[i]++;}for(let i=0;i<C;i++){work.marginalDistanceChecks++;if(support&(1n<<BigInt(i)))distances[i]++;}}
  return {count:s.summary.count,vertices:vertices.map((count,i)=>({local:i,source_id:c.vertices[i].source_id,count:String(count)})),distances:distances.map((count,i)=>({local:i,source_class_id:c.classes[i].source_class_id,count:String(count)}))};
 }
 function distanceBudget(q){assert(Number.isSafeInteger(q.budget),"safe integer distance budget required");work.budgetLookups++;if(q.budget<0)return {status:"INFEASIBLE",budget:q.budget,maximum_cardinality:null,minimum_deletions:null,count:"0"};const b=Math.min(C,q.budget);return {status:"FOUND",...c.budgets[b],requested_budget:q.budget};}
 return {summary:()=>({...c.summary,minima:c.minima,budgets:c.budgets}),condition,select,rank,page,marginals,distanceBudget,materialize:q=>materialize(q.mask),snapshot:()=>({conditions:Array.from(cache.values())}),work:()=>({...work})};
}
module.exports={compile,createReader};
