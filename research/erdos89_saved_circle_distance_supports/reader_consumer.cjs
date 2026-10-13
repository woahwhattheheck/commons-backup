"use strict";
function run(reader,c,sourceClassCount,bank){
 const responses=[],inverseChecks=[],optimalPages=[],conditionSummaries=[];
 function call(method,args={}){
  const id=responses.length+1;bank("pending",{id,method,args});bank("query_"+id+"_request",{method,args});
  const response=reader[method](args);bank("query_"+id+"_response",response);responses.push({id,method,args,response});
  bank("latest_caches",reader.snapshot());bank("latest_work",reader.work());bank("completed",id);bank("pending",null);return response;
 }
 const summary=call("summary");
 function navigation(name,q,completePage){
  const x=call("condition",q);conditionSummaries.push({name,...x});const count=BigInt(x.count);
  if(completePage){const p=call("page",{...q,start:"0",limit:256});optimalPages.push({name,complete:BigInt(p.items.length)===count,...p});}
  if(count){
   for(const rank of Array.from(new Set(["0",String(count/2n),String(count-1n)]))){
    const a=call("select",{...q,rank}),selectId=responses.length,b=call("rank",{...q,mask:a.mask});
    inverseChecks.push({name,select_id:selectId,rank_id:responses.length,expected:rank,match:b.status==="FOUND"&&b.rank===rank});
   }
  }
  call("select",{...q,rank:x.count});return x;
 }
 for(const x of c.minima)navigation("minimumAtK"+x.cardinality,{min_cardinality:x.cardinality,max_cardinality:x.cardinality,min_distances:x.minimum_distances,max_distances:x.minimum_distances},true);
 const used=new Set(c.classes.map(x=>x.source_class_id));let absent=0;while(absent<sourceClassCount&&used.has(absent))absent++;
 if(absent===sourceClassCount)throw Error("declared absent-class query unavailable");
 const first=c.classes[0].source_class_id,last=c.classes[c.classes.length-1].source_class_id;
 const cases=[
  ["full",{}],["requireVertex0",{required_vertices:[0]}],["forbidVertex0",{forbidden_vertices:[0]}],
  ["requireShortestHostClass",{required_distance_ids:[first]}],["forbidShortestHostClass",{forbidden_distance_ids:[first]}],
  ["requireLongestHostClass",{required_distance_ids:[last]}],["requireBothExtremeClasses",{required_distance_ids:[first,last]}],
  ["allEightVertexSubsets",{min_cardinality:8,max_cardinality:8}],["distanceBudget9",{max_distances:9}],
  ["requireOriginal0And32",{required_vertices:[0,8]}],["absentRequiredClass",{required_distance_ids:[absent]}],
  ["conflictingVertices",{required_vertices:[0],forbidden_vertices:[0]}],
  ["conflictingDistances",{required_distance_ids:[first],forbidden_distance_ids:[first]}],
  ["reversedCardinality",{min_cardinality:7,max_cardinality:6}],["negativeDistanceBudget",{max_distances:-1}]
 ];
 for(const [name,q] of cases)navigation(name,q,false);
 const budgets=[];for(const budget of [-1,0,1,5,8,9,12,13,51,52,100])budgets.push(call("distanceBudget",{budget}));
 const k8=c.minima[8],marginals=[
  call("marginals",{}),
  call("marginals",{required_distance_ids:[first]}),
  call("marginals",{min_cardinality:8,max_cardinality:8,min_distances:k8.minimum_distances,max_distances:k8.minimum_distances})
 ];
 call("rank",{min_cardinality:8,max_cardinality:8,mask:0});
 call("page",{min_cardinality:8,max_cardinality:8,start:"12870",limit:10});
 call("page",{min_cardinality:8,max_cardinality:8,start:"12871",limit:10});
 const result={schema:"commons.erdos89.subset_distance_reader/v1",summary,conditions:conditionSummaries,optimal_pages:optimalPages,budgets,marginals,responses,inverse_checks:inverseChecks,caches:reader.snapshot(),work:reader.work(),query_conventions:{required_distances:"source IDs from the full saved 757-class metric",absent_source_class:absent,numeric_mask_order:true}};
 bank("final_result",result);return result;
}
module.exports={run};
