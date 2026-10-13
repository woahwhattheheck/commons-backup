"use strict";
function consume(api,retain){
 const outputs=[],inverses=[],conditionReports=[];let serial=0;
 function call(method,args){const request={id:++serial,method,args};retain("pending",request);try{const response=api[method](...args);outputs.push({request,response});retain("outputs",outputs);retain("snapshot",api.snapshot());return response;}catch(e){retain("error",{request,name:e.name,message:e.message});retain("snapshot",api.snapshot());throw e;}}
 call("summary",[]);call("scoreGroups",[]);
 const conditions=[{}, {min_size:7,max_size:7},{min_size:6,max_size:6},{required:[1]},{forbidden:[1]},{required:[1,19]},{forbidden:[1,2,3,4]},{prefix_min:[{N:4,count:2}]},{prefix_min:[{N:4,count:2},{N:8,count:3},{N:12,count:4},{N:16,count:5}]},{prefix_min:[{N:4,count:5}]},{score_min:{num:"1",den:"1"}},{score_min:{num:"3",den:"2"}},{score_min:{num:"25",den:"13"},score_max:{num:"25",den:"13"}},{score_min:{num:"2",den:"1"}},{score_max:{num:"0",den:"1"}},{required:[1],forbidden:[1]},{min_size:8},{min_size:7,max_size:5}];
 const optima=[];
 for(const condition of conditions){const q=call("condition",[condition]);conditionReports.push({condition,count:q.count,size_counts:q.size_counts,maximum_score:q.maximum_score,maximum_score_count:q.maximum_score_ids.length});if(q.count){for(const rank of [...new Set([0,Math.floor(q.count/2),q.count-1])]){const row=call("select",[condition,rank]),back=call("rank",[condition,row.values]);inverses.push({kind:"family",condition,rank,row_id:row.row_id,returned:back.rank,match:rank===back.rank});}
 const count=q.maximum_score_ids.length;for(const rank of [...new Set([0,count-1])]){const row=call("optimumSelect",[condition,rank]),back=call("optimumRank",[condition,row.values]);inverses.push({kind:"finite-score",condition,rank,row_id:row.row_id,returned:back.rank,match:rank===back.rank});if(!Object.keys(condition).length)optima.push(row);}
 }}
 call("page",[{},0,32]);const total=conditionReports[0].count;call("page",[{},Math.max(0,total-32),32]);call("page",[{min_size:7,max_size:7},0,256]);call("optimumPage",[{},0,256]);call("page",[{},total,32]);call("page",[{},0,0]);
 for(const values of [[1,2,3,4],[1,2,3],[],optima[0].values])call("explain",[values]);
 call("rank",[{},[1,2,3,4]]);
 const result={schema:"commons.ordered_cap3_reader/v1",scope:"First conditional navigation of the new saved ordered-cap-three family; no old family, pair support, prefix profile or finite score reconstruction.",outputs,condition_reports:conditionReports,inverses,summary:{responses:outputs.length,inverse_checks:inverses.length,all_inverse_matches:inverses.every(x=>x.match),global_finite_score_maximizer:optima[0]},snapshot:api.snapshot()};
 retain("complete",result);return result;
}
module.exports={consume};
