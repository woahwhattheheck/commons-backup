"use strict";
function pc(n){let r=0;for(;n;n&=n-1)r++;return r;}
function clone(x){return JSON.parse(JSON.stringify(x));}
function num(x,lo,hi,name){if(!Number.isInteger(x)||x<lo||x>hi)throw new RangeError(name);return x;}
function mul(A,B,w){w.newBooleanProducts++;return A.map(x=>{let z=0;for(let j=0;j<3;j++)if(x&(1<<j)){z|=B[j];w.newProductRowUnions++;}return z;});}
function apply(s,R,w){let x=0;for(let j=0;j<3;j++)if(s&(1<<j)){x|=R[j];w.endpointRowUnions++;}return x;}
function choices(w,x,c){const a=[];for(let f=0;f<8;f++)if((f&w)&&!(f&x)&&(f&c.require_final)===c.require_final&&!(f&c.forbid_final)&&(c.final_mask===null||f===c.final_mask))a.push(f);return a;}
function compile(input){
 if(input.schema!=="commons.nfa_pair212_input/v1"||input.relations.length!==512)throw new TypeError("complete input required");
 const work={copiedRelations:512,copiedPowerMatrices:2048,newBooleanProducts:0,newProductRowUnions:0,endpointTables:0,endpointRowUnions:0,finalMasksInspected:0,oldPowerProducts:0,oldDfaEvaluations:0,expandedSymbols:0};
 const powers=[],edgeCounts=[],lower=[];
 for(let i=0;i<512;i++){const r=input.relations[i];if(r.code!==i)throw new TypeError("relation order");for(const k of["rows","p2","p4","p16","p64"])if(!Array.isArray(r[k])||r[k].length!==3||r[k].some(x=>!Number.isInteger(x)||x<0||x>7))throw new TypeError("rows");
  const p128=mul(r.p64,r.p64,work),p20=mul(r.p4,r.p16,work),p84=mul(p20,r.p64,work),p212=mul(p84,p128,work);
  powers.push({code:i,p128,p20,p84,p212});edgeCounts.push(r.rows.reduce((a,b)=>a+pc(b),0));
  if(r.rows[2]===0&&!(r.rows[0]&4)&&!(r.rows[1]&4)){const difference=r.p2.map((x,j)=>x^p212[j]);lower.push({code:i,rows:r.rows.slice(),p2:r.p2.slice(),p212:p212.slice(),difference,equal:difference.every(x=>x===0)});}
 }
 const endpointHex=[],hist=Array(64).fill(0),finalCounts=Array(8).fill(0),edgeHistogram=Array(19).fill(0);let tables=0,machines=0;
 for(let b=0;b<512;b++)for(let a=0;a<512;a++){
  const w=apply(powers[a].p212[0],input.relations[b].p2,work),x=apply(input.relations[a].p2[0],powers[b].p212,work),byte=w+8*x;
  endpointHex.push(byte.toString(16).padStart(2,"0"));hist[byte]++;let n=0;for(let f=0;f<8;f++){work.finalMasksInspected++;if((f&w)&&!(f&x)){finalCounts[f]++;n++;}}
  if(n)tables++;machines+=n;edgeHistogram[edgeCounts[a]+edgeCounts[b]]+=n;work.endpointTables++;
 }
 if(lower.length!==16)throw new Error("embedded two-state coverage");
 return{schema:"commons.nfa_pair212_catalogue/v1",input_source:clone(input.source_atlas),inherited_dfa:clone(input.inherited_dfa),states:3,initial_state:0,acceptance:"existential,accept first word and reject second,epsilon-free labelled catalogue",table_order:"zero_relation_code + 512*one_relation_code; accepting mask ascending within table",endpoint_encoding:"two lowercase hex digits per table; byte=first_terminal_mask+8*second_terminal_mask",endpoint_hex:endpointHex.join(""),new_powers:powers,relation_edges:edgeCounts,endpoint_histogram:hist,final_mask_counts:finalCounts,edge_histogram:edgeHistogram,lower_two_state:{records:lower,all_equal:lower.every(r=>r.equal)},summary:{tables:262144,full_machines:2097152,separating_tables:tables,separating_machines:machines,inherited_dfa_minimum:input.inherited_dfa.minimum,nfa_minimum:lower.every(r=>r.equal)&&machines>0?3:null,finite_ratio:lower.every(r=>r.equal)&&machines>0?"4/3":null},work};
}
function open(cert,input){
 if(cert.schema!=="commons.nfa_pair212_catalogue/v1"||cert.endpoint_hex.length!==524288||!/^[0-9a-f]+$/.test(cert.endpoint_hex))throw new TypeError("complete endpoint encoding");
 const cache=new Map(),work={conditions:0,conditionHits:0,endpointRowsScanned:0,finalMaskChecks:0,selectionRows:0,rankRows:0,traceRowUnions:0,newPowerProducts:0,oldDfaEvaluations:0,expandedSymbols:0};
 function row(code){const x=parseInt(cert.endpoint_hex.slice(2*code,2*code+2),16);return[x&7,x>>3];}
 function condition(raw={}){
  const c={zero_code:raw.zero_code===undefined?null:num(raw.zero_code,0,511,"zero code"),one_code:raw.one_code===undefined?null:num(raw.one_code,0,511,"one code"),final_mask:raw.final_mask===undefined?null:num(raw.final_mask,0,7,"final mask"),require_final:num(raw.require_final??0,0,7,"require final"),forbid_final:num(raw.forbid_final??0,0,7,"forbid final"),min_edges:raw.min_edges??0,max_edges:raw.max_edges??18};
  if(!Number.isInteger(c.min_edges)||!Number.isInteger(c.max_edges))throw new TypeError("integer edge bounds");const key=JSON.stringify(c);if(cache.has(key)){work.conditionHits++;return cache.get(key);}if(cache.size>=64)throw new RangeError("condition cache bound");
  const blocks=Array(1024).fill(0);let count=0;
  for(let code=0;code<262144;code++){work.endpointRowsScanned++;const a=code%512,b=Math.floor(code/512),edges=cert.relation_edges[a]+cert.relation_edges[b];if((c.zero_code!==null&&a!==c.zero_code)||(c.one_code!==null&&b!==c.one_code)||edges<c.min_edges||edges>c.max_edges)continue;const[w,x]=row(code),fs=choices(w,x,c);work.finalMaskChecks+=8;count+=fs.length;blocks[Math.floor(code/256)]+=fs.length;}
  const prefix=[0];for(const x of blocks)prefix.push(prefix.at(-1)+x);const z={key,condition:c,count,blocks,prefix};cache.set(key,z);work.conditions++;return z;
 }
 function matching(code,c){const a=code%512,b=Math.floor(code/512),edges=cert.relation_edges[a]+cert.relation_edges[b];if((c.zero_code!==null&&a!==c.zero_code)||(c.one_code!==null&&b!==c.one_code)||edges<c.min_edges||edges>c.max_edges)return[];const[w,x]=row(code);work.finalMaskChecks+=8;return choices(w,x,c);}
 function describe(code,f){const a=code%512,b=Math.floor(code/512),[w,x]=row(code);return{table_code:code,zero_code:a,one_code:b,initial_state:0,final_mask:f,zero_rows:input.relations[a].rows.slice(),one_rows:input.relations[b].rows.slice(),first_terminal_mask:w,second_terminal_mask:x,edges:cert.relation_edges[a]+cert.relation_edges[b],separates:!!(w&f)&&!(x&f)};}
 function select(c,r){const q=condition(c);num(r,0,q.count-1,"rank out of range");let lo=0,hi=1024;while(lo+1<hi){const mid=(lo+hi)>>1;if(q.prefix[mid]<=r)lo=mid;else hi=mid;}let rem=r-q.prefix[lo];for(let code=lo*256;code<lo*256+256;code++){work.selectionRows++;const fs=matching(code,q.condition);if(rem<fs.length)return{rank:r,...describe(code,fs[rem])};rem-=fs.length;}throw new Error("select accounting");}
 function rank(c,code,f){num(code,0,262143,"table code");num(f,0,7,"final mask");const q=condition(c),fs=matching(code,q.condition),at=fs.indexOf(f);if(at<0)return{table_code:code,final_mask:f,rank:null};const block=Math.floor(code/256);let r=q.prefix[block]+at;for(let k=block*256;k<code;k++){work.rankRows++;r+=matching(k,q.condition).length;}return{table_code:code,final_mask:f,rank:r};}
 function trace(code,f){num(code,0,262143,"table code");num(f,0,7,"final mask");const d=describe(code,f),a=d.zero_code,b=d.one_code,midW=cert.new_powers[a].p212[0],midX=input.relations[a].p2[0];
  function ap(s,R){let v=0;for(let j=0;j<3;j++)if(s&(1<<j)){v|=R[j];work.traceRowUnions++;}return v;}
  const w=ap(midW,input.relations[b].p2),x=ap(midX,cert.new_powers[b].p212);return{...d,first_run_masks:[1,midW,w],second_run_masks:[1,midX,x],saved_endpoints_match:w===d.first_terminal_mask&&x===d.second_terminal_mask};}
 return{summary:()=>clone(cert.summary),lowerBound:()=>clone(cert.lower_two_state),relationPower:code=>clone(cert.new_powers[num(code,0,511,"relation code")]),condition:c=>clone(condition(c)),select,rank,trace,page:(c,start,limit=32)=>{const q=condition(c);num(start,0,q.count,"start rank");num(limit,0,128,"page limit");const n=Math.min(limit,q.count-start),rows=[];for(let j=0;j<n;j++)rows.push(select(c,start+j));return{start,count:n,total:q.count,next:start+n<q.count?start+n:null,rows};},work:()=>clone(work),snapshot:()=>({conditions:[...cache.values()].map(clone),work:clone(work)})};
}
module.exports={compile,open};
