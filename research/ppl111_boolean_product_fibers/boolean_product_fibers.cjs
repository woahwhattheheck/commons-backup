'use strict';
const SCHEMA='commons.boolean_product_fibers/v1';
const LIMITS=Object.freeze({rows:20,columns:20,block:5,states:100000,arcs:500000,coefficients:1500000,queryCells:200000,page:128});
const clone=x=>JSON.parse(JSON.stringify(x));
function int(x,lo,hi,name){if(!Number.isSafeInteger(x)||x<lo||x>hi)throw new RangeError(name+' out of range');return x;}
function rankNumber(x,name){if(typeof x!=='string'||!/^(0|[1-9][0-9]*)$/.test(x)||x.length>8)throw new TypeError(name+' must be a bounded decimal string');return int(Number(x),0,2**LIMITS.columns,name);}
function contract(input){
 if(!input||!Array.isArray(input.matrix)||!input.matrix.length)throw new TypeError('matrix required');
 const m=int(input.matrix.length,1,LIMITS.rows,'rows'),n=typeof input.matrix[0]==='string'?input.matrix[0].length:0;
 int(n,1,LIMITS.columns,'columns');
 for(const row of input.matrix)if(typeof row!=='string'||row.length!==n||!/^[01]+$/.test(row))throw new TypeError('rectangular binary row strings required');
 const b=int(input.block_size,1,LIMITS.block,'block_size');return {m,n,b};
}
function buildIndex(input){
 const {m,n,b}=contract(input),columns=Array(n).fill(0);
 for(let i=0;i<m;i++)for(let j=0;j<n;j++)if(input.matrix[i][j]==='1')columns[j]|=2**i;
 const blocks=[],layers=[{processed:0,states:[{output:0,counts:[1]}]}],transitions=[];
 const work={matrix_entries_read:m*n,block_table_entries:0,block_or_operations:0,transition_or_operations:0,coefficient_additions:0,states:1,arcs:0,coefficient_cells:1,input_vectors_enumerated:0};
 for(let offset=0;offset<n;offset+=b){
  const width=Math.min(b,n-offset),size=2**width,outputs=Array(size).fill(0),weights=Array(size).fill(0);
  for(let x=1;x<size;x++){const low=x&-x,j=31-Math.clz32(low);outputs[x]=outputs[x-low]|columns[offset+j];weights[x]=weights[x-low]+1;work.block_or_operations++;}
  const block={offset,width,outputs,weights};blocks.push(block);work.block_table_entries+=size;
  const prev=layers[layers.length-1],processed=offset+width,map=new Map(),raw=[];
  for(const state of prev.states){
   const row=[];
   for(let choice=0;choice<size;choice++){
    const output=state.output|outputs[choice];work.transition_or_operations++;
    if(!map.has(output))map.set(output,Array(processed+1).fill(0));
    const counts=map.get(output);
    for(let k=0;k<state.counts.length;k++)if(state.counts[k]){counts[k+weights[choice]]+=state.counts[k];work.coefficient_additions++;}
    row.push(output);work.arcs++;
    if(work.arcs>LIMITS.arcs)throw new RangeError('arc budget exceeded');
   }
   raw.push(row);
  }
  const values=[...map.keys()].sort((a,b)=>a-b),ids=new Map(values.map((x,i)=>[x,i]));
  const states=values.map(output=>({output,counts:map.get(output)}));
  work.states+=states.length;work.coefficient_cells+=states.length*(processed+1);
  if(work.states>LIMITS.states||work.coefficient_cells>LIMITS.coefficients)throw new RangeError('layer budget exceeded');
  transitions.push(raw.map(row=>row.map(x=>ids.get(x))));layers.push({processed,states});
 }
 return {schema:SCHEMA,input:{matrix:input.matrix.slice(),block_size:b},rows:m,columns:n,blocks,layers,transitions,construction_work:work,
  conventions:{product:'OR over AND; output bit i is row i',input:'bit j is column j',fiber_order:'lexicographic numerical block choices, block 0 first',coefficients:'ordinary counts by input Hamming weight; no color or symmetry quotient'}};
}
function openIndex(snapshot){
 const data=clone(snapshot);
 if(data.schema!==SCHEMA)throw new TypeError('schema mismatch');
 const {m,n,b}=contract(data.input),B=Math.ceil(n/b);
 if(data.rows!==m||data.columns!==n||data.blocks.length!==B||data.layers.length!==B+1||data.transitions.length!==B)throw new TypeError('dimensions mismatch');
 let stateTotal=0,cellTotal=0,arcTotal=0;
 for(let i=0;i<=B;i++){
  const layer=data.layers[i],processed=Math.min(i*b,n);if(layer.processed!==processed||!Array.isArray(layer.states)||!layer.states.length)throw new TypeError('layer shape');
  let old=-1;
  for(const s of layer.states){
   int(s.output,0,2**m-1,'output');if(s.output<=old)throw new TypeError('output order');old=s.output;
   if(!Array.isArray(s.counts)||s.counts.length!==processed+1)throw new TypeError('coefficient shape');
   s.counts.forEach(x=>int(x,0,2**n,'coefficient'));
   stateTotal++;cellTotal+=s.counts.length;
  }
  if(i<B){
   const block=data.blocks[i],width=Math.min(b,n-i*b),size=2**width,edges=data.transitions[i];
   if(block.offset!==i*b||block.width!==width||block.outputs.length!==size||block.weights.length!==size||edges.length!==layer.states.length)throw new TypeError('block shape');
   block.outputs.forEach(x=>int(x,0,2**m-1,'block output'));block.weights.forEach(x=>int(x,0,width,'block weight'));
   for(const row of edges){if(!Array.isArray(row)||row.length!==size)throw new TypeError('arc row shape');for(const to of row)int(to,0,data.layers[i+1].states.length-1,'arc target');arcTotal+=row.length;}
  }
 }
 if(data.layers[0].states.length!==1||data.layers[0].states[0].output!==0||JSON.stringify(data.layers[0].states[0].counts)!=='[1]')throw new TypeError('initial state');
 if(stateTotal>LIMITS.states||cellTotal>LIMITS.coefficients||arcTotal>LIMITS.arcs)throw new RangeError('snapshot budget exceeded');
 const last=data.layers[B].states,finalIds=new Map(last.map((s,i)=>[s.output,i])),memo=new Map();
 const work={saved_states_indexed:stateTotal,saved_coefficients_indexed:cellTotal,saved_arcs_indexed:arcTotal,queries:0,block_table_lookups:0,query_or_operations:0,saved_arc_lookups:0,conditional_cells:0,conditional_cache_hits:0,conditional_additions:0,input_vectors_enumerated:0,matrix_entries_read:0,block_tables_rebuilt:0,layer_coefficients_rebuilt:0};
 function mask(x,bits,name){return int(x,0,2**bits-1,name);}
 function weight(w){if(w!==null)int(w,0,n,'weight');return w;}
 function bits(x,len){return Array.from({length:len},(_,i)=>(x>>i)&1).join('');}
 function product(v){
  let output=0;const choices=[];
  for(const block of data.blocks){const c=(v>>block.offset)&(2**block.width-1);choices.push(c);work.block_table_lookups++;output|=block.outputs[c];work.query_or_operations++;}
  return {input:v,input_bits:bits(v,n),output,output_bits:bits(output,m),block_choices:choices};
 }
 function count(goal,w){const i=finalIds.get(goal);if(i===undefined)return 0;return w===null?last[i].counts.reduce((a,b)=>a+b,0):last[i].counts[w];}
 function suffix(goal,i,state,remaining){
  const key=[goal,i,state,remaining===null?'*':remaining].join(':');
  if(memo.has(key)){work.conditional_cache_hits++;return memo.get(key);}
  if(memo.size>=LIMITS.queryCells)throw new RangeError('conditional cell budget exceeded');
  let value=0;const row=data.layers[i].states[state];
  if((row.output&~goal)!==0||(remaining!==null&&(remaining<0||remaining>n-data.layers[i].processed)))value=0;
  else if(i===B)value=row.output===goal&&(remaining===null||remaining===0)?1:0;
  else{
   const edges=data.transitions[i][state],block=data.blocks[i];
   for(let c=0;c<edges.length;c++){work.saved_arc_lookups++;value+=suffix(goal,i+1,edges[c],remaining===null?null:remaining-block.weights[c]);work.conditional_additions++;}
  }
  if(memo.size>=LIMITS.queryCells)throw new RangeError('conditional cell budget exceeded');
  memo.set(key,value);work.conditional_cells++;return value;
 }
 function select(goal,j,w){
  const total=count(goal,w);if(j<0||j>=total)throw new RangeError('rank outside fiber');
  let state=0,remaining=w,v=0;const trace=[];
  for(let i=0;i<B;i++){
   const block=data.blocks[i],edges=data.transitions[i][state];let selected=false;
   for(let c=0;c<edges.length;c++){
    const nextRemaining=remaining===null?null:remaining-block.weights[c];work.saved_arc_lookups++;
    const ways=suffix(goal,i+1,edges[c],nextRemaining);
    if(j>=ways){j-=ways;continue;}
    trace.push({stage:i,state,choice:c,next_state:edges[c],suffix_count:ways,residual_rank:j});
    v+=c*2**block.offset;state=edges[c];remaining=nextRemaining;selected=true;break;
   }
   if(!selected)throw new Error('snapshot count/arc mismatch');
  }
  return {input:v,input_bits:bits(v,n),output:goal,output_bits:bits(goal,m),trace};
 }
 return Object.freeze({
  summary(){work.queries++;return {rows:m,columns:n,block_size:b,blocks:B,inputs:2**n,distinct_outputs:last.length,layer_state_counts:data.layers.map(l=>l.states.length),construction_work:clone(data.construction_work)};},
  matrix(){work.queries++;return clone(data.input);},
  profiles(){work.queries++;return last.map(s=>({output:s.output,output_bits:bits(s.output,m),counts:s.counts.slice(),total:s.counts.reduce((a,b)=>a+b,0),minimum_weight:s.counts.findIndex(x=>x>0)}));},
  block(index){work.queries++;int(index,0,B-1,'block');return clone(data.blocks[index]);},
  product(v){work.queries++;return product(mask(v,n,'input'));},
  fiberCount(goal,w=null){work.queries++;mask(goal,m,'output');weight(w);return {output:goal,weight:w,count:count(goal,w)};},
  fiberSelect(goal,rank,w=null){work.queries++;mask(goal,m,'output');weight(w);const j=rankNumber(rank,'rank');return {rank,weight:w,...select(goal,j,w)};},
  fiberRank(goal,v,w=null){
   work.queries++;mask(goal,m,'output');mask(v,n,'input');weight(w);
   let state=0,remaining=w,j=0;const trace=[];
   for(let i=0;i<B;i++){
    const block=data.blocks[i],choice=(v>>block.offset)&(2**block.width-1),edges=data.transitions[i][state];
    for(let c=0;c<choice;c++){work.saved_arc_lookups++;j+=suffix(goal,i+1,edges[c],remaining===null?null:remaining-block.weights[c]);}
    work.saved_arc_lookups++;trace.push({stage:i,state,choice,next_state:edges[choice]});
    state=edges[choice];if(remaining!==null)remaining-=block.weights[choice];
   }
   const matches=data.layers[B].states[state].output===goal&&(remaining===null||remaining===0);
   return {output:goal,input:v,weight:w,rank:matches?String(j):null,trace};
  },
  fiberPage(goal,start='0',limit=16,w=null){
   work.queries++;mask(goal,m,'output');weight(w);const j=rankNumber(start,'start');int(limit,0,LIMITS.page,'limit');
   const total=count(goal,w);if(j>total)throw new RangeError('page start exceeds fiber');
   const rows=[];for(let r=j;r<total&&rows.length<limit;r++)rows.push({rank:String(r),...select(goal,r,w)});
   return {output:goal,weight:w,start,total,rows};
  },
  stream(){
   let round=0,lastReply=null;
   return Object.freeze({submit(v){work.queries++;mask(v,n,'input');const result={round:round+1,...product(v)};round++;lastReply=result;return clone(result);},
    state(){return {round,last_reply:clone(lastReply)};}});
  },
  conditionalTable(){return {cells:[...memo.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([key,value])=>({key,value})),semantics:'goal:layer:state:remaining; * means any weight'};},
  work(){return clone(work);}
 });
}
module.exports={SCHEMA,LIMITS,buildIndex,openIndex};
