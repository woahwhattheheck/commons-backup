"use strict";
function consume(api,retain){
 const outputs=[],inverse=[],traceChecks=[];let i=0;
 function call(method,args){const request={id:++i,method,args};retain("pending",request);try{const response=api[method](...args);outputs.push({request,response});retain("outputs",outputs);retain("snapshot",api.snapshot());return response;}catch(e){retain("error",{request,name:e.name,message:e.message});retain("snapshot",api.snapshot());throw e;}}
 const summary=call("summary",[]),lower=call("lowerBound",[]);
 const conditions=[{},...Array.from({length:8},(_,final_mask)=>({final_mask})),{min_edges:3,max_edges:3},{max_edges:4},{max_edges:6},{min_edges:8,max_edges:10},{zero_code:0},{one_code:0},{require_final:1,forbid_final:1},{require_final:1},{forbid_final:1},{min_edges:10,max_edges:5},{min_edges:-4,max_edges:-1}];
 const counts=[],allSelected=[];
 for(const condition of conditions){const q=call("condition",[condition]);counts.push({condition,count:q.count});if(q.count){for(const rank of [...new Set([0,Math.floor(q.count/2),q.count-1])]){const row=call("select",[condition,rank]),back=call("rank",[condition,row.table_code,row.final_mask]);inverse.push({condition,rank,table_code:row.table_code,final_mask:row.final_mask,returned_rank:back.rank,match:back.rank===rank});if(Object.keys(condition).length===0)allSelected.push(row);}}}
 call("page",[{},0,32]);call("page",[{},Math.max(0,summary.separating_machines-32),32]);call("page",[{min_edges:3,max_edges:3},0,128]);call("page",[{},summary.separating_machines,32]);call("page",[{},0,0]);call("rank",[{},0,0]);
 for(const row of allSelected){const result=call("trace",[row.table_code,row.final_mask]);traceChecks.push(result.saved_endpoints_match&&result.separates);}
 for(const code of [...new Set(allSelected.map(x=>x.zero_code))])call("relationPower",[code]);
 const first=allSelected[0];
 for(const condition of [{zero_code:first.zero_code},{one_code:first.one_code},{zero_code:first.zero_code,one_code:first.one_code}]){const q=call("condition",[condition]);counts.push({condition,count:q.count});if(q.count){const row=call("select",[condition,q.count-1]),back=call("rank",[condition,row.table_code,row.final_mask]);inverse.push({condition,rank:q.count-1,table_code:row.table_code,final_mask:row.final_mask,returned_rank:back.rank,match:back.rank===q.count-1});}}
 const result={schema:"commons.nfa_pair212_reader/v1",scope:"First actual navigation of the saved new word-pair endpoint catalogue; no constructor or old DFA/power replay.",outputs,condition_counts:counts,inverses:inverse,trace_matches:traceChecks,summary:{responses:outputs.length,inverse_checks:inverse.length,all_inverse_matches:inverse.every(x=>x.match),all_trace_matches:traceChecks.every(Boolean),lower_all_equal:lower.all_equal},snapshot:api.snapshot()};
 retain("complete",result);return result;
}
module.exports={consume};
