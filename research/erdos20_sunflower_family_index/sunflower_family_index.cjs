"use strict";
function natural(x,name){if(!Number.isSafeInteger(x)||x<0)throw new TypeError(name);return x;}
function bitCount(x){let n=0;for(;x;x&=x-1)n++;return n;}
function compile(input){
  const edges=input.edges,m=edges.length,vertices=input.vertices;
  if(input.sunflower_members!==3||m<1||m>input.limits.max_edges||vertices.length>24)throw new RangeError("declared scope");
  const vm=new Map(vertices.map((v,i)=>[v,i]));
  const masks=edges.map(e=>{if(e.length!==3||new Set(e).size!==3||e.some(v=>!vm.has(v)))throw new TypeError("edge");return e.reduce((mask,v)=>mask|1<<vm.get(v),0);});
  if(new Set(masks).size!==m)throw new TypeError("duplicate edge");
  const work={literal_edge_masks:m,triples_examined:0,pair_intersections:0,patterns:0,normalization_calls:0,dominance_checks:0,states:0,node_intern_hits:0,nodes:2,coefficient_cells:2,coefficient_additions:0,binomial_copies:0,pascal_recurrence_operations:0,old_k4_computations:0};
  const patterns=[];
  for(let i=0;i<m;i++)for(let j=i+1;j<m;j++)for(let k=j+1;k<m;k++){
    work.triples_examined++;work.pair_intersections+=3;
    const a=masks[i]&masks[j],b=masks[i]&masks[k],c=masks[j]&masks[k];
    if(a===b&&b===c){patterns.push({id:patterns.length,edge_indices:[i,j,k],edge_mask:(1<<i)|(1<<j)|(1<<k),kernel_mask:a,kernel:vertices.filter((v,q)=>a&(1<<q)),petals:[i,j,k].map(t=>vertices.filter((v,q)=>(masks[t]&~a)&(1<<q)))});work.patterns++;if(patterns.length>input.limits.max_patterns)throw new RangeError("pattern cap");}
  }
  const nodes=[{id:0,variable:m,lo:0,hi:0,coefficients:[0],total:0},{id:1,variable:m,lo:1,hi:1,coefficients:[1],total:1}],memo=new Map(),intern=new Map(),freeMemo=new Map();
  function addNode(pos,lo,hi,coeff){
    const key=pos+","+lo+","+hi;
    if(intern.has(key)){work.node_intern_hits++;return intern.get(key);}
    if(nodes.length>=input.limits.max_nodes)throw new RangeError("node cap");
    work.coefficient_cells+=coeff.length;if(work.coefficient_cells>input.limits.max_coefficient_cells)throw new RangeError("coefficient cap");
    const id=nodes.length;nodes.push({id,variable:pos,lo,hi,coefficients:coeff,total:coeff.reduce((a,b)=>a+b,0)});intern.set(key,id);work.nodes++;return id;
  }
  function free(pos){
    if(pos===m)return 1;if(freeMemo.has(pos))return freeMemo.get(pos);
    const child=free(pos+1),row=input.binomial_rows[m-pos];
    if(!Array.isArray(row)||row.length!==m-pos+1)throw new TypeError("binomial premise");
    const coeff=row.map(v=>natural(Number(v),"binomial coefficient"));work.binomial_copies+=coeff.length;
    const id=addNode(pos,child,child,coeff);freeMemo.set(pos,id);return id;
  }
  function normalize(clauses){
    work.normalization_calls++;
    const sorted=[...new Set(clauses)].sort((a,b)=>bitCount(a)-bitCount(b)||a-b),out=[];
    for(const c of sorted){let dominated=false;for(const a of out){work.dominance_checks++;if((a&c)===a){dominated=true;break;}}if(!dominated)out.push(c);}
    return out.sort((a,b)=>a-b);
  }
  function solve(pos,clauses){
    if(clauses.includes(0))return 0;if(!clauses.length)return free(pos);if(pos===m)return 1;
    const key=pos+"|"+clauses.join(",");if(memo.has(key))return memo.get(key);
    work.states++;if(work.states>input.limits.max_states)throw new RangeError("state cap");
    const bit=1<<pos;
    const lo=solve(pos+1,normalize(clauses.filter(c=>!(c&bit))));
    const hi=solve(pos+1,normalize(clauses.map(c=>c&~bit)));
    const a=nodes[lo].coefficients,b=nodes[hi].coefficients,coeff=Array(m-pos+1).fill(0);
    for(let k=0;k<coeff.length;k++){coeff[k]=(a[k]||0)+(k?b[k-1]||0:0);work.coefficient_additions++;}
    const id=addNode(pos,lo,hi,coeff);memo.set(key,id);return id;
  }
  const root=solve(0,normalize(patterns.map(p=>p.edge_mask))),co=nodes[root].coefficients;
  let maximum=co.length-1;while(maximum>0&&!co[maximum])maximum--;
  const kernels={};for(const p of patterns)kernels[p.kernel.length]=(kernels[p.kernel.length]||0)+1;
  return {format:"sunflower-family-index-v1",vertices:vertices.slice(),edges:edges.map(e=>e.slice()),edge_vertex_masks:masks,patterns,nodes,root,limits:{...input.limits},provenance:input.provenance,summary:{members:m,patterns:patterns.length,kernel_size_counts:kernels,total:nodes[root].total,coefficients:co,maximum,maximum_count:co[maximum]},construction_work:work};
}
function openIndex(data,caches){
  if(data.format!=="sunflower-family-index-v1")throw new TypeError("format");
  const m=data.edges.length,full=2**m-1,nodes=data.nodes;
  if(m<1||m>24||!Array.isArray(nodes)||!nodes[data.root])throw new TypeError("shape");
  const conditions=new Map(),work={conditions_built:0,condition_cache_hits:0,condition_node_visits:0,condition_coefficients:0,condition_additions:0,base_coefficient_reads:0,rank_steps:0,selection_steps:0,membership_pattern_scans:0,materialized_edges:0,sunflower_intersections:0,base_dag_constructions:0};
  function maskValue(v){if(typeof v==="string"&&!/^\d+$/.test(v))throw new TypeError("mask");const n=typeof v==="string"?Number(v):v;natural(n,"mask");if(n>full)throw new RangeError("mask");return n;}
  if(caches){
    if(caches.format!=="sunflower-reader-caches-v1"||JSON.stringify(caches.edges)!==JSON.stringify(data.edges))throw new TypeError("cache input");
    for(const c of caches.conditions)conditions.set(c.key,c);
  }
  function condition(required=0,excluded=0){
    required=maskValue(required);excluded=maskValue(excluded);if(required&excluded)throw new RangeError("contradictory condition");
    const key=required+","+excluded;if(conditions.has(key)){work.condition_cache_hits++;return conditions.get(key);}
    work.conditions_built++;const values={};
    function visit(id){
      if(values[id])return values[id];
      work.condition_node_visits++;let result;
      if(id<2)result=[id];
      else{
        const node=nodes[id],bit=1<<node.variable,tail=(2**m-1)^(2**node.variable-1);
        if(((required|excluded)&tail)===0){work.base_coefficient_reads+=node.coefficients.length;result=node.coefficients.slice();}
        else{
          const low=required&bit?[0]:visit(node.lo),high=excluded&bit?[0]:visit(node.hi);
          result=Array(m-node.variable+1).fill(0);
          for(let k=0;k<result.length;k++){result[k]=(low[k]||0)+(k?high[k-1]||0:0);work.condition_additions++;}
        }
      }
      values[id]=result;work.condition_coefficients+=result.length;return result;
    }
    const coefficients=visit(data.root),c={key,required,excluded,coefficients,total:coefficients.reduce((a,b)=>a+b,0),node_coefficients:values};conditions.set(key,c);return c;
  }
  function coefficients(id,con){
    if(con.node_coefficients[id])return con.node_coefficients[id];
    if(id<2)return [id];
    const node=nodes[id],tail=full^(2**node.variable-1);
    if(((con.required|con.excluded)&tail)!==0)throw new Error("missing conditional coefficient");
    work.base_coefficient_reads+=node.coefficients.length;return node.coefficients;
  }
  function rangeCount(id,con,used,min,max){
    const co=coefficients(id,con);let t=0;
    for(let k=Math.max(0,min-used);k<=Math.min(co.length-1,max-used);k++)t+=co[k];return t;
  }
  function bounds(options={}){
    const min=options.min_size===undefined?0:natural(options.min_size,"min size"),max=options.max_size===undefined?m:natural(options.max_size,"max size");
    if(min>max||max>m)throw new RangeError("size range");return {min,max,required:options.required===undefined?0:options.required,excluded:options.excluded===undefined?0:options.excluded};
  }
  function family(options={}){
    const b=bounds(options),con=condition(b.required,b.excluded);
    return {required:con.required,excluded:con.excluded,min_size:b.min,max_size:b.max,count:con.coefficients.slice(b.min,b.max+1).reduce((a,v)=>a+v,0),coefficients:con.coefficients.slice()};
  }
  function membership(value){
    const mask=maskValue(value);
    for(const p of data.patterns){work.membership_pattern_scans++;if((mask&p.edge_mask)===p.edge_mask)return {valid:false,pattern_id:p.id,edge_indices:p.edge_indices,kernel:p.kernel,petals:p.petals};}
    return {valid:true,pattern_id:null};
  }
  function select(rank,options={}){
    natural(rank,"rank");const b=bounds(options),con=condition(b.required,b.excluded),total=rangeCount(data.root,con,0,b.min,b.max);
    if(rank>=total)throw new RangeError("rank");const original=rank;let id=data.root,mask=0,used=0;
    while(id>=2){
      work.selection_steps++;const node=nodes[id],bit=1<<node.variable;
      const lo=con.required&bit?0:rangeCount(node.lo,con,used,b.min,b.max);
      if(rank<lo)id=node.lo;else{rank-=lo;if(con.excluded&bit)throw new Error("excluded branch");mask|=bit;used++;id=node.hi;}
    }
    if(id!==1)throw new Error("invalid terminal");
    const indices=[];for(let i=0;i<m;i++)if(mask&(1<<i)){indices.push(i);work.materialized_edges++;}
    return {rank:original,mask,size:used,edge_indices:indices,edges:indices.map(i=>data.edges[i])};
  }
  function rank(value,options={}){
    const mask=maskValue(value),b=bounds(options),con=condition(b.required,b.excluded),size=bitCount(mask);
    if((mask&con.required)!==con.required||(mask&con.excluded)||size<b.min||size>b.max)return {member:false,rank:null};
    let id=data.root,used=0,result=0;
    while(id>=2){
      work.rank_steps++;const node=nodes[id],bit=1<<node.variable;
      if(mask&bit){if(!(con.required&bit))result+=rangeCount(node.lo,con,used,b.min,b.max);used++;id=node.hi;}
      else id=node.lo;
    }
    return id===1?{member:true,rank:result}:{member:false,rank:null};
  }
  function page(offset=0,limit=20,options={}){
    natural(offset,"offset");natural(limit,"limit");if(limit>data.limits.max_page)throw new RangeError("page cap");
    const f=family(options),items=[];for(let r=offset;r<Math.min(f.count,offset+limit);r++)items.push(select(r,options));return {count:f.count,offset,items};
  }
  return {summary:()=>({...data.summary,construction_work:data.construction_work}),family,select,rank,page,membership,
    obstruction:id=>{natural(id,"pattern id");if(!data.patterns[id])throw new RangeError("pattern id");return data.patterns[id];},
    conditions:()=>({format:"sunflower-reader-caches-v1",edges:data.edges,conditions:[...conditions.values()]}),
    work:()=>({...work})};
}
module.exports={compile,openIndex};
