"use strict";
function run(reader,retain){
 const outputs=[],inverses=[],conditions=[];
 function call(method,args){const id=outputs.length+1,request={id,method,args};retain("pending",request);retain("query_"+id+"_request",request);
  const response=reader[method](...args);retain("query_"+id+"_response",response);outputs.push({request,response});
  retain("latest_caches",reader.caches());retain("latest_work",reader.work());retain("completed",outputs.length);retain("pending",null);return response;}
 call("summary",[]);const profiles=call("profiles",[]);
 const filters=[{}, {x:[0,0]}, {z:[0,0]}, {w:[0,0]}, {x:[1,31],y:[1,31],z:[1,31],w:[1,31]},
  {n:[500,500]}, {n:[1000,1000]}, {n:[2000,2000]}, {n:[100,400],t:[4,8]},
  {t:[16,16]}, {y:[8,15],z:[16,23],w:[3,9]}, {x:[20,10]}, {n:[4000,5000]}, {x:[-10,0],w:[-5,5]}];
 for(const filter of filters){
  const c=call("condition",[filter]);conditions.push({filter,condition:c});
  call("count",[filter]);call("blocks",[filter]);
  if(c.count){for(const rank of [...new Set([0,Math.floor(c.count/2),c.count-1])]){
   const s=call("select",[filter,rank]),r=call("rank",[filter,s.tuple]);inverses.push({filter,rank,actual:r.rank,match:r.rank===rank});
   call("fiber",[s.n,s.t]);}
   call("page",[filter,Math.max(0,c.count-5),5]);}
 }
 call("image",[{w:[0,0]}]);call("image",[{n:[100,400],t:[4,8]}]);call("image",[{x:[20,10]}]);
 call("image",[{w:[0,0]}]);
 const occupied=profiles.joint;
 for(const index of [...new Set([0,Math.floor(occupied.length/2),occupied.length-1])])call("fiber",occupied[index].slice(0,2));
 call("fiber",[-1,0]);call("fiber",[0,-1]);
 return {schema:"ppl006.saved-reader/v1",outputs,conditions,inverses,work:reader.work(),caches:reader.caches(),
  summary:{outputs:outputs.length,inverses:inverses.length,allInverseMatches:inverses.every(x=>x.match),conditions:conditions.length}};
}
module.exports={run};
