'use strict';
function big(x,name){if(typeof x==='number'&&!Number.isSafeInteger(x))throw new TypeError(name+' must be exact');if(typeof x!=='number'&&typeof x!=='bigint'&&!(typeof x==='string'&&/^\d+$/.test(x)))throw new TypeError(name+' must be an integer');const v=BigInt(x);if(v<0n)throw new RangeError(name+' negative');return v;}
function compile(input){
 const alphabet=input.alphabet,N=input.max_length,limits=input.limits||{};
 if(!Array.isArray(alphabet)||alphabet.length!==3||alphabet.some((a,i)=>!Number.isSafeInteger(a)||(i&&a<=alphabet[i-1]))||!Number.isSafeInteger(N)||N<1||N>11)throw new TypeError('Input alphabet/length');
 const work={determinants:0,determinant_cache_hits:0,condensation_numerators:0,exact_divisions:0,nodes:0,append_attempts:0,window_checks:0,completion_additions:0,old_determinants:0};
 const records=[{code:'',order:0,value:'1',parents:[]}],lookup=new Map([['',0]]),nodes=[],byDepth=Array(N+1).fill(0),rejections=Array.from({length:N+1},()=>({total:0,orders:{}}));
 function det(code){
  if(lookup.has(code)){work.determinant_cache_hits++;return lookup.get(code);}
  const order=(code.length+1)/2;let value,parents=[];
  if(code.length===1)value=BigInt(alphabet[Number(code)]);
  else{
   const left=det(code.slice(0,-2)),middle=det(code.slice(1,-1)),right=det(code.slice(2)),denominator=code.length===3?0:det(code.slice(2,-2));
   const a=BigInt(records[left].value),b=BigInt(records[middle].value),c=BigInt(records[right].value),d=BigInt(records[denominator].value);
   if(d===0n)throw new Error('Nonzero-minor precondition violated');
   const numerator=a*c-b*b;work.condensation_numerators++;
   if(numerator%d!==0n)throw new Error('Nonintegral condensation');
   value=numerator/d;work.exact_divisions++;parents=[left,middle,right,denominator];
  }
  const id=records.length;records.push({code,order,value:String(value),parents});lookup.set(code,id);work.determinants++;
  if(records.length>(limits.max_determinants||250000))throw new RangeError('Determinant budget');
  return id;
 }
 function build(code){
  const id=nodes.length,node={code,branches:[],completions:'0'};nodes.push(node);work.nodes++;byDepth[code.length]++;
  if(nodes.length>(limits.max_nodes||300000))throw new RangeError('Node budget');
  if(code.length===N){node.completions='1';return id;}
  let total=0n;
  for(let symbol=0;symbol<3;symbol++){
   work.append_attempts++;const next=code+symbol;let zero=null;const checked=[];
   for(let order=1;2*order-1<=next.length;order++){
    const shift=next.length-(2*order-1),record=det(next.slice(shift));work.window_checks++;checked.push(record);
    if(records[record].value==='0'){zero={record,order,shift};break;}
   }
   if(zero){node.branches.push({symbol,target:null,checked,zero});rejections[next.length].total++;rejections[next.length].orders[zero.order]=(rejections[next.length].orders[zero.order]||0)+1;}
   else {const target=build(next);node.branches.push({symbol,target,checked,zero:null});total+=BigInt(nodes[target].completions);work.completion_additions++;}
  }
  node.completions=String(total);return id;
 }
 const root=build('');
 return{schema:'integer-hankel-prefix-index-v1',input,alphabet,max_length:N,root,nodes,determinants:records,summary:{alphabet,max_length:N,prefix_counts:byDepth,full_words:nodes[root].completions,nodes:nodes.length,determinant_records:records.length,zero_records:records.filter(r=>r.value==='0').length,rejections},work};
}
function openIndex(saved){
 if(saved.schema!=='integer-hankel-prefix-index-v1')throw new TypeError('Snapshot schema');
 const alphabet=saved.alphabet,N=saved.max_length,work={branch_reads:0,completion_reads:0,rank_additions:0,selected_words:0,determinant_record_reads:0,matrix_entries:0,marginal_node_scans:0,marginal_additions:0,new_determinants:0,new_divisions:0};
 function encode(word){if(!Array.isArray(word)||word.length>N||word.some(x=>!alphabet.includes(x)))throw new TypeError('Finite alphabet word');return word.map(x=>String(alphabet.indexOf(x))).join('');}
 function decode(code){return [...code].map(x=>alphabet[Number(x)]);}
 function record(id){if(!Number.isSafeInteger(id)||id<0||id>=saved.determinants.length)throw new RangeError('Record id');work.determinant_record_reads++;const r=saved.determinants[id];return{id,...r,word:decode(r.code)};}
 function zeroCertificate(z){const r=record(z.record),matrix=[];for(let i=0;i<z.order;i++){const row=[];for(let j=0;j<z.order;j++){row.push(r.word[i+j]);work.matrix_entries++;}matrix.push(row);}return{...z,determinant:r,matrix};}
 function walk(code){
  let node=saved.root;
  for(let at=0;at<code.length;at++){const b=saved.nodes[node].branches[Number(code[at])];work.branch_reads++;if(b.target===null)return{valid:false,rejected_at:at+1,node,branch:b};node=b.target;}
  return{valid:true,node};
 }
 function prefix(word=[]){const code=encode(word),w=walk(code);if(!w.valid)return{prefix:word,valid:false,count:'0',rejected_at:w.rejected_at,zero:zeroCertificate(w.branch.zero)};work.completion_reads++;return{prefix:word,valid:true,node:w.node,count:saved.nodes[w.node].completions,full:word.length===N};}
 function select(rank,pre=[]){
  let r=big(rank,'rank');const original=r,code0=encode(pre),start=walk(code0);
  if(!start.valid)throw new RangeError('Rejected prefix');
  let id=start.node,code=code0;work.completion_reads++;const total=BigInt(saved.nodes[id].completions);
  if(r>=total)throw new RangeError('Rank outside completions');const trace=[];
  while(code.length<N){let found=false;for(const b of saved.nodes[id].branches){work.branch_reads++;if(b.target===null)continue;const n=BigInt(saved.nodes[b.target].completions);work.completion_reads++;if(r>=n){r-=n;continue;}trace.push({position:code.length,symbol:alphabet[b.symbol],child:b.target,block_count:String(n),remaining_rank:String(r)});code+=b.symbol;id=b.target;found=true;break;}if(!found)throw new Error('Saved selection missing');}
  work.selected_words++;return{prefix:pre,rank:String(original),count:String(total),word:decode(code),node:id,trace};
 }
 function rank(word,pre=[]){
  const code=encode(word),p=encode(pre);if(code.length!==N||!code.startsWith(p))throw new TypeError('Full completion word');
  const start=walk(p);if(!start.valid)return{rank:null,reason:'rejected_prefix'};let id=start.node,r=0n;
  for(let at=p.length;at<N;at++){const symbol=Number(code[at]);for(let j=0;j<symbol;j++){const b=saved.nodes[id].branches[j];work.branch_reads++;if(b.target!==null){r+=BigInt(saved.nodes[b.target].completions);work.completion_reads++;work.rank_additions++;}}
   const b=saved.nodes[id].branches[symbol];work.branch_reads++;if(b.target===null)return{rank:null,rejected_at:at+1,zero:zeroCertificate(b.zero)};id=b.target;
  }
  return{rank:String(r),node:id,prefix:pre,word};
 }
 function page(start,limit,pre=[]){let at=big(start,'start');if(!Number.isSafeInteger(limit)||limit<0||limit>100)throw new RangeError('Page limit');const p=prefix(pre),n=BigInt(p.count);if(at>n)throw new RangeError('Page start');const rows=[];for(;at<n&&rows.length<limit;at++)rows.push(select(String(at),pre));return{start:String(big(start,'start')),count:p.count,rows,next:at<n?String(at):null};}
 function check(word){return prefix(word);}
 function determinantPage(start,limit){if(!Number.isSafeInteger(start)||!Number.isSafeInteger(limit)||start<0||limit<0||limit>1000||start>saved.determinants.length)throw new RangeError('Record page');const end=Math.min(start+limit,saved.determinants.length);return{start,records:Array.from({length:end-start},(_,i)=>record(start+i)),next:end<saved.determinants.length?end:null};}
 function marginals(pre=[]){
  const p=prefix(pre),code=encode(pre),table=Array.from({length:N},()=>Array(3).fill(0n));
  if(!p.valid)return{prefix:pre,count:'0',positions:table.map((counts,position)=>({position,counts:counts.map(String)}))};
  const total=BigInt(p.count);for(let i=0;i<code.length;i++)table[i][Number(code[i])]=total;
  for(const node of saved.nodes){work.marginal_node_scans++;if(node.code.length<code.length||node.code.length>=N||!node.code.startsWith(code))continue;for(const b of node.branches){if(b.target!==null){table[node.code.length][b.symbol]+=BigInt(saved.nodes[b.target].completions);work.completion_reads++;work.marginal_additions++;}}}
  return{prefix:pre,count:p.count,positions:table.map((counts,position)=>({position,counts:counts.map(String)}))};
 }
 return{summary:()=>saved.summary,prefix,count:(pre=[])=>prefix(pre).count,select,rank,page,check,determinantPage,marginals,work:()=>({...work})};
}
module.exports={compile,openIndex};
