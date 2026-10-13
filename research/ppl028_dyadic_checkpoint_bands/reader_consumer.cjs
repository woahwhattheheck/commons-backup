"use strict";
function run(reader,c,bank){
 const responses=[],inverseChecks=[],found=[];
 function call(method,args={}){
  const id=responses.length+1;bank("pending",{id,method,args});bank("query_"+id+"_request",{method,args});
  const response=reader[method](args);bank("query_"+id+"_response",response);responses.push({id,method,args,response});
  bank("latest_caches",reader.snapshot());bank("latest_work",reader.work());bank("completed",id);bank("pending",null);return response;
 }
 const lower=()=>Array(10).fill(0),upper=()=>Array(10).fill(3);
 function coordinate(name,i,b){const min=lower(),max=upper();min[i]=b;max[i]=b;return {name,min_bands:min,max_bands:max};}
 const threshold=c.cells[1].lower,lowHighMin=lower(),lowHighMax=upper();lowHighMin[9]=3;lowHighMax[0]=1;
 const conflictMin=lower(),conflictMax=upper();conflictMin[4]=2;conflictMax[4]=1;
 const queries=[
  {name:"full"},coordinate("initialBand0",0,0),coordinate("finalBand1",9,1),
  {name:"allBand2",min_bands:Array(10).fill(2),max_bands:Array(10).fill(2)},
  {name:"initialLowFinalHigh",min_bands:lowHighMin,max_bands:lowHighMax},
  coordinate("time8Band2",4,2),
  {name:"parameterMiddle",lower:"1"+"0".repeat(200),upper:"1"+"0".repeat(300)},
  {name:"beforeFirstEvent",lower:String(BigInt(threshold)-1n),upper:String(BigInt(threshold)-1n)},
  {name:"atFirstEvent",lower:threshold,upper:threshold},
  {name:"reversedParameterRange",lower:"11",upper:"10"},
  {name:"allBand3",min_bands:Array(10).fill(3)},
  {name:"incompatibleBands",min_bands:conflictMin,max_bands:conflictMax}
 ];
 const summary=call("summary"),conditions=[];
 for(const q of queries){
  const x=call("condition",q);conditions.push({name:q.name,...x});const count=BigInt(x.count);
  if(count){
   const ranks=Array.from(new Set(["0",String(count/2n),String(count-1n)]));
   for(const rank of ranks){
    const s=call("select",{...q,rank});found.push({condition:q.name,parameter:s.parameter,seed:s.seed});
    const a=call("rank",{...q,parameter:s.parameter}),b=call("rank",{...q,seed:s.seed});
    inverseChecks.push({select_id:responses.length-2,parameter_rank_id:responses.length-1,seed_rank_id:responses.length,expected:rank,parameter_match:a.status==="FOUND"&&a.rank===rank,seed_match:b.status==="FOUND"&&b.rank===rank});
   }
   call("select",{...q,rank:x.count});
  }else call("select",{...q,rank:"0"});
 }
 const selectedParameters=Array.from(new Set(["1",threshold,String(BigInt(threshold)-1n),c.parameter_upper,found.find(x=>x.condition==="allBand2").parameter,found.find(x=>x.condition==="allBand3").parameter]));
 const states=[];
 for(const parameter of selectedParameters){
  states.push(call("state",{parameter}));
  for(const at_least_band of [1,2,3])call("firstCheckpoint",{parameter,at_least_band});
  call("firstCheckpoint",{parameter,at_least_band:3,include_initial:true});
 }
 const marginals=[call("marginals",queries[0]),call("marginals",queries[3]),call("marginals",queries[6])];
 call("rank",{seed:c.residue}); // original seed is outside declared t>=1 window
 call("rank",{seed:String(BigInt(c.residue)+1n)}); // wrong full-cylinder residue
 const result={schema:"commons.ppl028.band_reader/v1",summary,conditions,states,marginals,responses,inverse_checks:inverseChecks,caches:reader.snapshot(),work:reader.work()};
 bank("final_result",result);return result;
}
module.exports={run};
