"use strict";
function run(reader, record) {
  let id=0; const inverseMatches=[];
  function query(method,args){
    const request={id:++id,method,args};
    record({phase:"before",request});
    const response=reader[method](...args);
    record({phase:"after",request,response,caches:reader.caches(),work:reader.work()});
    return response;
  }
  query("summary",[]);
  const families=[
    {mode:"triangular",masks:[511,508,1,0,257,341],last:"190"},
    {mode:"double_triangular",masks:[127,65,1,0,85],last:"75"}
  ];
  for(const f of families){
    query("collisions",[f.mode]);
    query("count",[f.mode,"-1"]);
    for(const mask of f.masks){
      query("condition",[f.mode,mask]);
      query("count",[f.mode,"10000000000000000000000000000000000000000",mask]);
      query("profile",[f.mode,f.last,mask]);
      if(mask!==0)for(const rank of ["0","10","1000000000000000000000000"]){
        const selected=query("select",[f.mode,rank,mask]);
        const ranked=query("rank",[f.mode,selected.value,mask]);
        inverseMatches.push({mode:f.mode,mask,requestedRank:rank,value:selected.value,
          returnedRank:ranked.rank,equal:ranked.rank===rank});
      }
    }
    query("window",[f.mode,"1000000000000000000000000000000","1000000000000000000000001000000"]);
    query("window",[f.mode,"0",f.last]);
  }
  return {schema:"ppl120.saved-reader/v1",queries:id,inverseMatches,work:reader.work(),caches:reader.caches()};
}
module.exports={run};
