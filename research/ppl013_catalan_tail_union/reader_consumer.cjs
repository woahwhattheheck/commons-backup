"use strict";
function run(reader,retain){
 const outputs=[],inverses=[],conditions=[],aliasChecks=[];
 function call(method,args){const id=outputs.length+1,request={id,method,args};retain("pending",request);retain("query_"+id+"_request",request);
  const response=reader[method](...args);retain("query_"+id+"_response",response);outputs.push({request,response});
  retain("latest_caches",reader.caches());retain("latest_work",reader.work());retain("completed",outputs.length);retain("pending",null);return response;}
 call("summary",[]);
 const masks=[127,1,2,3,5,42,85,0],huge="1"+"0".repeat(100);
 for(const mask of masks){
  const c=call("condition",[mask]);conditions.push(c);call("prefix",[mask]);
  call("countLeq",[mask,"4"]);call("countLeq",[mask,"34"]);call("countWindow",[mask,"35","45"]);
  if(c.infinite){
   const ranks=[...new Set(["0",String(Math.floor(c.prefixCount/2)),String(c.prefixCount-1),String(c.prefixCount),String(c.prefixCount+7),huge])];
   for(const rank of ranks){const s=call("select",[mask,rank]),a=s.target.canonical,r=call("rankSymbolic",[mask,a.primeIndex,a.catalanIndex]);
    inverses.push({mask,rank,actual:r.rank,match:r.rank===rank});
    if(BigInt(rank)<=BigInt(c.prefixCount+7)){const v=call("materialize",[mask,rank]),f=call("fiberValue",[mask,v.target.value]);
     inverses.push({mask,rank,actual:f.rank,match:f.rank===rank,kind:"decimal"});}}
  }
 }
 for(const index of [16,128,512,1000]){
  const c=call("catalan",[index]);const rank=call("rankSymbolic",[127,0,String(index)]).rank;
  const v=call("materialize",[127,rank]);call("fiberValue",[127,v.target.value]);call("countLeq",[127,v.target.value]);
  call("countWindow",[127,(BigInt(v.target.value)-2n).toString(),(BigInt(v.target.value)+2n).toString()]);
 }
 for(const threshold of ["1"+"0".repeat(100),"1"+"0".repeat(400)])for(const mask of [127,42,0])call("countLeq",[mask,threshold]);
 call("countWindow",[127,"100","1"]);call("fiberValue",[127,"4"]);
 for(const p of [0,6]){const a=call("rankSymbolic",[127,p,"0"]),b=call("rankSymbolic",[127,p,"1"]);aliasChecks.push({primeIndex:p,rank0:a.rank,rank1:b.rank,same:a.rank===b.rank});}
 return {schema:"ppl013.saved-reader/v1",outputs,conditions,inverses,aliasChecks,work:reader.work(),caches:reader.caches(),
  summary:{outputs:outputs.length,inverses:inverses.length,allInverseMatches:inverses.every(x=>x.match),conditions:conditions.length,
   aliasChecks:aliasChecks.length,allAliasMatches:aliasChecks.every(x=>x.same),hugeSymbolicRank:huge}};
}
module.exports={run};
