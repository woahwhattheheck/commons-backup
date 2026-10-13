"use strict";

/*
 * Finite labelled Seidel-switch families avoiding monochromatic K4.
 * Vertex 0 is fixed to switch bit 0; no graph-isomorphism quotient.
 * Pure CommonJS. No I/O, dependencies, random choices or native hooks.
 */
const SEIDEL_SWITCH_LIMITS=Object.freeze({
  max_vertices:17,max_switches:65536,max_input_edges:512,
  max_page_size:64,max_condition_bits:64,max_condition_edges:256,
  max_cube_visits:20000000,max_profile_cells:11000000,
  max_snapshot_characters:8000000
});
const SCHEMA="commons.seidel_k4_switch_family/v1";
const PALEY_SOURCE="https://arxiv.org/pdf/math/0605252";
const PAIR_POSITIONS=Object.freeze([[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]].map(Object.freeze));

function fail(message){throw new Error(message);}
function integer(value,min,max,label){
  let n;
  if(typeof value==="number"&&Number.isSafeInteger(value))n=value;
  else if(typeof value==="bigint"){
    if(value<BigInt(min)||value>BigInt(max))fail(label+" is outside its finite range.");
    n=Number(value);
  }else if(typeof value==="string"&&/^(0|[1-9][0-9]*)$/.test(value)&&value.length<=8)n=Number(value);
  else fail(label+" must be an exact bounded nonnegative integer.");
  if(n<min||n>max)fail(label+" is outside its finite range.");
  return n;
}
function copy(value){return JSON.parse(JSON.stringify(value));}
function same(a,b){return JSON.stringify(a)===JSON.stringify(b);}
function choose4(n){return n<4?0:n*(n-1)*(n-2)*(n-3)/24;}
function bit(code,vertex){return vertex===0?0:(code>>>(vertex-1))&1;}
function weight(code){let x=code,n=0;while(x){x&=x-1;n++;}return n;}
function edge(rows,u,v){return (rows[u]>>>v)&1;}
function workRecord(){
  return {
    paley_square_evaluations:0,paley_pair_evaluations:0,
    normalized_input_edges:0,compiled_quadruples:0,base_edge_reads:0,triangle_xors:0,
    switchable_quadruples:0,compiled_cubes:0,cube_assignment_visits:0,
    classified_switches:0,first_bad_assignments:0,compiler_calls:0,
    loaded_quadruple_rows:0,loaded_cube_rows:0,loaded_switch_rows:0,
    loader_adjacency_cells:0,loader_first_witness_checks:0,
    condition_code_visits:0,condition_tests:0,condition_views:0,
    select_queries:0,rank_queries:0,membership_queries:0,
    obstruction_queries:0,obstruction_edge_evaluations:0,
    graph_queries:0,graph_edge_evaluations:0,
    profile_queries:0,profile_bit_cells:0,profile_edge_cells:0,
    page_rows:0
  };
}
function graphInput(input,w){
  if(!input||typeof input!=="object"||Array.isArray(input))fail("A graph input object is required.");
  const n=integer(input.order,1,SEIDEL_SWITCH_LIMITS.max_vertices,"graph order");
  if(!Array.isArray(input.red_edges)||input.red_edges.length>SEIDEL_SWITCH_LIMITS.max_input_edges)
    fail("The red-edge input exceeds its finite record bound.");
  const seen=new Set(),red=[];
  for(const pair of input.red_edges){
    if(!Array.isArray(pair)||pair.length!==2)fail("Each red edge has two vertices.");
    let u=integer(pair[0],0,n-1,"edge endpoint"),v=integer(pair[1],0,n-1,"edge endpoint");
    if(u===v)fail("Loops are outside the graph contract.");
    if(u>v)[u,v]=[v,u];
    const key=u+","+v;
    if(!seen.has(key)){seen.add(key);red.push([u,v]);}
  }
  red.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  const rows=Array(n).fill(0);
  for(const [u,v]of red){rows[u]|=1<<v;rows[v]|=1<<u;w.normalized_input_edges++;}
  const provenance=input.provenance===undefined?"caller_supplied_labelled_graph":input.provenance;
  if(typeof provenance!=="string"||provenance.length>4096)fail("Graph provenance must be a bounded string.");
  let details=input.source_details===undefined?null:copy(input.source_details);
  if(JSON.stringify(details).length>16384)fail("Source details exceed the finite metadata bound.");
  return {order:n,red_edges:red,adjacency_masks:rows,provenance,source_details:details};
}
function paleyPrimeGraph(prime){
  const q=integer(prime,5,17,"Paley prime");
  if(![5,13,17].includes(q))fail("This prime-field convenience constructor supports exactly 5, 13 and 17.");
  const images=[],squares=new Set(),w=workRecord();
  for(let a=1;a<=(q-1)/2;a++){const r=a*a%q;images.push([a,r]);squares.add(r);w.paley_square_evaluations++;}
  const residues=[...squares].sort((a,b)=>a-b),red=[];
  for(let u=0;u<q;u++)for(let v=u+1;v<q;v++){
    w.paley_pair_evaluations++;
    if(squares.has((v-u)%q))red.push([u,v]);
  }
  return {
    order:q,red_edges:red,
    provenance:"Paley prime-field graph from Lim-Praeger, Introduction: "+PALEY_SOURCE,
    source_details:{family:"Paley prime-field graph",prime:q,
      vertex_labels:"0 through q-1",red:"nonzero square differences modulo q",
      blue:"all other unordered distinct pairs",square_images:images,nonzero_squares:residues,
      prime_contract:"The convenience interface supports the fixed primes 5, 13 and 17 only; it is not a general prime-power field constructor.",
      construction_work:w}
  };
}
function histogram(values){
  const h=new Map();for(const value of values)h.set(value,(h.get(value)||0)+1);
  return [...h].sort((a,b)=>a[0]-b[0]).map(([monochromatic_quadruples,switches])=>({monochromatic_quadruples,switches}));
}
function compileSeidelK4Family(input){
  const w=workRecord(),g=graphInput(input,w),n=g.order,variables=n-1,total=1<<variables,all=total-1;
  const quadruples=[],cubes=[];
  for(let a=0;a<n;a++)for(let b=a+1;b<n;b++)for(let c=b+1;c<n;c++)for(let d=c+1;d<n;d++){
    const vertices=[a,b,c,d],e=PAIR_POSITIONS.map(([i,j])=>edge(g.adjacency_masks,vertices[i],vertices[j]));
    const parities=[e[0]^e[1]^e[3],e[0]^e[2]^e[4],e[1]^e[2]^e[5],e[3]^e[4]^e[5]];
    const color=parities.every(t=>t===parities[0])?parities[0]:null;
    const row={vertices,base_edge_bits:e,triangle_parities:parities,monochromatic_color:color,cube_ids:[]};
    const qid=quadruples.length;
    w.compiled_quadruples++;w.base_edge_reads+=6;w.triangle_xors+=8;
    if(color!==null){
      w.switchable_quadruples++;
      for(const phase of(a===0?[0]:[0,1])){
        const local=[phase,phase^e[0]^color,phase^e[1]^color,phase^e[2]^color];
        let mask=0,required=0;
        for(let i=0;i<4;i++)if(vertices[i]!==0){
          const position=1<<(vertices[i]-1);mask|=position;if(local[i])required|=position;
        }
        row.cube_ids.push(cubes.length);
        cubes.push({quadruple:qid,color,mask,required,local_bits:local});
        w.compiled_cubes++;
      }
    }
    quadruples.push(row);
  }
  const first=Array(total).fill(-1),counts=Array(total).fill(0);
  for(let cid=0;cid<cubes.length;cid++){
    const cube=cubes[cid],free=all^cube.mask;
    let sub=free;
    for(;;){
      const code=cube.required|sub;
      w.cube_assignment_visits++;
      if(w.cube_assignment_visits>SEIDEL_SWITCH_LIMITS.max_cube_visits)fail("Forbidden-cube expansion exceeds its finite work cap.");
      counts[code]++;
      if(first[code]===-1){first[code]=cid;w.first_bad_assignments++;}
      if(sub===0)break;
      sub=(sub-1)&free;
    }
  }
  const good=[],sizes=Array(n).fill(0);
  for(let code=0;code<total;code++){
    w.classified_switches++;
    if(first[code]===-1){good.push(code);sizes[weight(code)]++;}
  }
  w.compiler_calls++;
  const result={
    schema:SCHEMA,graph:g,fixed_vertex:0,fixed_switch_bit:0,
    variable_vertices:Array.from({length:variables},(_,i)=>i+1),
    code_order:"increasing unsigned integer code; vertex v>=1 has weight 2^(v-1)",
    edge_colors:{blue:0,red:1},total_switches:total,
    quadruple_edge_order:PAIR_POSITIONS.map(p=>p.slice()),
    quadruple_triangle_order:[[0,1,2],[0,1,3],[0,2,3],[1,2,3]],
    quadruples,forbidden_cubes:cubes,
    classification:{first_cube_by_code:first,monochromatic_quadruple_count_by_code:counts,
      admissible_codes:good,admissible_count:good.length,excluded_count:total-good.length,
      admissible_size_histogram:sizes,monochromatic_count_histogram:histogram(counts)},
    construction_work:w
  };
  if(JSON.stringify(result).length>SEIDEL_SWITCH_LIMITS.max_snapshot_characters)fail("The complete snapshot exceeds the finite size cap.");
  return result;
}
function rootConditions(){return {bits:[[0,0]],edges:[],conflicts:[]};}
function appendConditions(previous,input,n){
  if(input===undefined)input={};
  if(!input||typeof input!=="object"||Array.isArray(input))fail("Conditions must be an object with bits and/or edges.");
  if(Object.keys(input).some(k=>!["bits","edges"].includes(k)))fail("Unknown condition key.");
  const rawBits=input.bits===undefined?[]:input.bits,rawEdges=input.edges===undefined?[]:input.edges;
  if(!Array.isArray(rawBits)||rawBits.length>SEIDEL_SWITCH_LIMITS.max_condition_bits||
     !Array.isArray(rawEdges)||rawEdges.length>SEIDEL_SWITCH_LIMITS.max_condition_edges)
    fail("A condition request exceeds its finite record bounds.");
  const bits=new Map(previous.bits.map(p=>[p[0],p[1]]));
  const edges=new Map(previous.edges.map(p=>[p[0]+","+p[1],p.slice()]));
  const conflicts=copy(previous.conflicts);
  for(const p of rawBits){
    if(!Array.isArray(p)||p.length!==2)fail("A bit condition is [vertex, bit].");
    const v=integer(p[0],0,n-1,"condition vertex"),b=integer(p[1],0,1,"switch bit");
    if(bits.has(v)&&bits.get(v)!==b)conflicts.push({kind:"bit",vertex:v,existing:bits.get(v),requested:b});
    else bits.set(v,b);
  }
  for(const p of rawEdges){
    if(!Array.isArray(p)||p.length!==3)fail("An edge condition is [u, v, color].");
    let u=integer(p[0],0,n-1,"condition endpoint"),v=integer(p[1],0,n-1,"condition endpoint");
    const color=integer(p[2],0,1,"edge color");
    if(u===v)fail("Diagonal edge conditions are outside the contract.");
    if(u>v)[u,v]=[v,u];
    const key=u+","+v;
    if(edges.has(key)&&edges.get(key)[2]!==color)conflicts.push({kind:"edge",vertices:[u,v],existing:edges.get(key)[2],requested:color});
    else edges.set(key,[u,v,color]);
  }
  return {bits:[...bits].sort((a,b)=>a[0]-b[0]),edges:[...edges.values()].sort((a,b)=>a[0]-b[0]||a[1]-b[1]),conflicts};
}
function openRetainedSeidelK4Family(retained){
  const body=typeof retained==="string"?retained:JSON.stringify(retained);
  if(typeof body!=="string"||body.length>SEIDEL_SWITCH_LIMITS.max_snapshot_characters)fail("A bounded complete snapshot is required.");
  const s=JSON.parse(body),w=workRecord();
  if(!s||s.schema!==SCHEMA)fail("Unknown Seidel family schema.");
  const n=integer(s.graph&&s.graph.order,1,SEIDEL_SWITCH_LIMITS.max_vertices,"retained graph order"),total=1<<(n-1),all=total-1;
  if(s.total_switches!==total||s.fixed_vertex!==0||s.fixed_switch_bit!==0)fail("Switch-universe convention mismatch.");
  if(s.code_order!=="increasing unsigned integer code; vertex v>=1 has weight 2^(v-1)"||!same(s.edge_colors,{blue:0,red:1}))fail("Retained code/color convention mismatch.");
  if(!same(s.variable_vertices,Array.from({length:n-1},(_,i)=>i+1))||!same(s.quadruple_edge_order,PAIR_POSITIONS)||
     !same(s.quadruple_triangle_order,[[0,1,2],[0,1,3],[0,2,3],[1,2,3]]))fail("Retained coordinate order mismatch.");
  const g=s.graph,rows=g.adjacency_masks;
  if(!Array.isArray(rows)||rows.length!==n||!Array.isArray(g.red_edges)||g.red_edges.length>n*(n-1)/2)
    fail("Incomplete graph representation.");
  const rowLimit=(1<<n)-1,edgeKeys=new Set();
  let previousEdge=-1;
  for(const p of g.red_edges){
    if(!Array.isArray(p)||p.length!==2)fail("Malformed retained red edge.");
    const u=integer(p[0],0,n-1,"red endpoint"),v=integer(p[1],u+1,n-1,"red endpoint"),code=u*n+v;
    if(code<=previousEdge)fail("Retained edges must be unique and sorted.");
    previousEdge=code;edgeKeys.add(code);
  }
  for(let u=0;u<n;u++){
    integer(rows[u],0,rowLimit,"adjacency mask");
    if(edge(rows,u,u))fail("Retained graph contains a loop.");
    for(let v=0;v<n;v++){
      w.loader_adjacency_cells++;
      if(edge(rows,u,v)!==edge(rows,v,u))fail("Retained graph is not symmetric.");
      if(u<v&&edge(rows,u,v)!==(edgeKeys.has(u*n+v)?1:0))fail("Retained edge representations disagree.");
    }
  }
  if(!Array.isArray(s.quadruples)||s.quadruples.length!==choose4(n)||!Array.isArray(s.forbidden_cubes)||
     s.forbidden_cubes.length>2*choose4(n))fail("Incomplete local-pattern arrays.");
  const quads=s.quadruples,cubes=s.forbidden_cubes,quadKeys=new Set(),cubeSeen=Array(cubes.length).fill(false);
  let previousQuad="";
  for(let qi=0;qi<quads.length;qi++){
    const q=quads[qi];
    if(!q||!Array.isArray(q.vertices)||q.vertices.length!==4||!Array.isArray(q.base_edge_bits)||q.base_edge_bits.length!==6||
       !Array.isArray(q.triangle_parities)||q.triangle_parities.length!==4||!Array.isArray(q.cube_ids))fail("Malformed quadruple row.");
    let last=-1;
    for(const v of q.vertices){integer(v,last+1,n-1,"quadruple vertex");last=v;}
    const key=q.vertices.map(v=>String(v).padStart(2,"0")).join(",");
    if(quadKeys.has(key)||(previousQuad&&key<=previousQuad))fail("Quadruple rows must be unique and lexicographic.");
    quadKeys.add(key);previousQuad=key;
    q.base_edge_bits.forEach(v=>integer(v,0,1,"base edge bit"));
    q.triangle_parities.forEach(v=>integer(v,0,1,"triangle parity"));
    if(q.monochromatic_color!==null)integer(q.monochromatic_color,0,1,"monochromatic color");
    const expected=q.monochromatic_color===null?0:(q.vertices[0]===0?1:2);
    if(q.cube_ids.length!==expected)fail("Quadruple cube cardinality mismatch.");
    let lastCube=-1;
    for(const id of q.cube_ids){
      integer(id,0,cubes.length-1,"cube reference");
      if(id<=lastCube||cubeSeen[id])fail("Cube references are repeated or unsorted.");
      if(!cubes[id]||cubes[id].quadruple!==qi)fail("Cube parent mismatch.");
      lastCube=id;cubeSeen[id]=true;
    }
    w.loaded_quadruple_rows++;
  }
  if(cubeSeen.some(v=>!v))fail("Unreferenced forbidden cube.");
  for(let ci=0;ci<cubes.length;ci++){
    const c=cubes[ci],qid=integer(c.quadruple,0,quads.length-1,"cube quadruple"),q=quads[qid];
    integer(c.color,0,1,"cube color");integer(c.mask,0,all,"cube mask");integer(c.required,0,all,"cube value");
    if(c.color!==q.monochromatic_color||(c.required&c.mask)!==c.required||!Array.isArray(c.local_bits)||c.local_bits.length!==4)
      fail("Malformed forbidden cube.");
    let mask=0,value=0;
    for(let i=0;i<4;i++){
      const b=integer(c.local_bits[i],0,1,"local switch bit"),v=q.vertices[i];
      if(v===0){if(b!==0)fail("Cube violates the fixed switch bit.");}
      else{const p=1<<(v-1);mask|=p;if(b)value|=p;}
    }
    if(mask!==c.mask||value!==c.required)fail("Cube coordinates disagree.");
    w.loaded_cube_rows++;
  }
  const cls=s.classification;
  if(!cls||!Array.isArray(cls.first_cube_by_code)||cls.first_cube_by_code.length!==total||
     !Array.isArray(cls.monochromatic_quadruple_count_by_code)||cls.monochromatic_quadruple_count_by_code.length!==total||
     !Array.isArray(cls.admissible_codes))fail("Incomplete switch classification.");
  const first=cls.first_cube_by_code,counts=cls.monochromatic_quadruple_count_by_code,good=[],sizes=Array(n).fill(0);
  for(let code=0;code<total;code++){
    const id=first[code],count=integer(counts[code],0,quads.length,"monochromatic quadruple count");
    if(id===-1){
      if(count!==0)fail("Admissible code has a positive obstruction count.");
      good.push(code);sizes[weight(code)]++;
    }else{
      integer(id,0,cubes.length-1,"first cube");
      if(count===0)fail("Excluded code lacks an obstruction count.");
      const c=cubes[id];w.loader_first_witness_checks++;
      if((code&c.mask)!==c.required)fail("First witness does not match its code.");
    }
    w.loaded_switch_rows++;
  }
  if(!same(good,cls.admissible_codes)||cls.admissible_count!==good.length||cls.excluded_count!==total-good.length||
     !same(sizes,cls.admissible_size_histogram)||!same(histogram(counts),cls.monochromatic_count_histogram))
    fail("Retained classification summaries disagree.");
  function codeValue(value){return integer(value,0,total-1,"switch code");}
  function selection(code,rank){
    return {rank,code,switched_vertices:Array.from({length:n-1},(_,i)=>i+1).filter(v=>bit(code,v)),
      switch_bits:Array.from({length:n},(_,v)=>bit(code,v)),selected_size:weight(code)};
  }
  function firstConditionFailure(code,conditions){
    if(conditions.conflicts.length)return {kind:"inconsistent_conditions",conflicts:copy(conditions.conflicts)};
    for(const [v,target]of conditions.bits){
      w.condition_tests++;const actual=bit(code,v);
      if(actual!==target)return {kind:"switch_bit",vertex:v,target,actual};
    }
    for(const [u,v,target]of conditions.edges){
      w.condition_tests++;const actual=edge(rows,u,v)^bit(code,u)^bit(code,v);
      if(actual!==target)return {kind:"edge_color",vertices:[u,v],target,actual};
    }
    return null;
  }
  function obstruction(code){
    w.obstruction_queries++;
    const cid=first[code];
    if(cid===-1)return null;
    const c=cubes[cid],q=quads[c.quadruple],edges=[];
    for(const [i,j]of PAIR_POSITIONS){
      const u=q.vertices[i],v=q.vertices[j],base=edge(rows,u,v),su=bit(code,u),sv=bit(code,v),color=base^su^sv;
      w.obstruction_edge_evaluations++;
      if(color!==c.color)fail("Queried obstruction fails the retained graph arithmetic.");
      edges.push({vertices:[u,v],base_color:base,switch_bits:[su,sv],switched_color:color});
    }
    return {code,first_cube:cid,quadruple:c.quadruple,vertices:q.vertices.slice(),color:c.color,
      cube_mask:c.mask,cube_required:c.required,monochromatic_quadruples:counts[code],edges};
  }
  function pageSlice(values,start,count,decorate){
    const a=integer(start,0,values.length,"page start"),limit=integer(count,0,64,"page size"),end=Math.min(a+limit,values.length),out=[];
    for(let i=a;i<end;i++){out.push(decorate(values[i],i));w.page_rows++;}
    return {start:a,end,total:values.length,rows:out,next_start:end<values.length?end:null};
  }
  function makeView(codes,conditions){
    return Object.freeze({
      summary(){return {schema:SCHEMA,vertices:n,total_switches:total,global_admissible_count:good.length,
        count:codes.length,conditions:copy(conditions),fixed_vertex:0,fixed_switch_bit:0,
        code_order:s.code_order,edge_colors:copy(s.edge_colors),
        scope:"labelled Seidel-switch family only; not arbitrary edge completions or graph-isomorphism classes",
        loader_assurance:"structural consistency and requested obstruction arithmetic; no Paley construction, local-pattern compilation or full cube expansion",
        construction_work:copy(s.construction_work)};},
      count(){return codes.length;},
      select(rank=0){
        if(!codes.length)fail("The current view has no admissible switch.");
        const r=integer(rank,0,codes.length-1,"family rank");w.select_queries++;return selection(codes[r],r);
      },
      rank(rawCode){
        const code=codeValue(rawCode);let lo=0,hi=codes.length;w.rank_queries++;
        while(lo<hi){const mid=(lo+hi)>>>1;if(codes[mid]<code)lo=mid+1;else hi=mid;}
        if(lo===codes.length||codes[lo]!==code)fail("The switch is not in this admissible view.");
        return {code,rank:lo};
      },
      page(start=0,count=16){return pageSlice(codes,start,count,(code,rank)=>selection(code,rank));},
      membership(rawCode){
        const code=codeValue(rawCode),failure=firstConditionFailure(code,conditions);w.membership_queries++;
        return {code,admissible_in_orbit:first[code]===-1,matches_conditions:failure===null,
          in_view:first[code]===-1&&failure===null,condition_failure:failure,
          obstruction:obstruction(code)};
      },
      obstruction(rawCode){return obstruction(codeValue(rawCode));},
      switchGraph(rawCode){
        const code=codeValue(rawCode),red=[],degrees=Array(n).fill(0);w.graph_queries++;
        for(let u=0;u<n;u++)for(let v=u+1;v<n;v++){
          w.graph_edge_evaluations++;
          if(edge(rows,u,v)^bit(code,u)^bit(code,v)){red.push([u,v]);degrees[u]++;degrees[v]++;}
        }
        return {code,order:n,red_edges:red,red_degrees:degrees,red_edge_count:red.length,
          blue_edge_count:n*(n-1)/2-red.length,admissible_in_orbit:first[code]===-1,
          matches_conditions:firstConditionFailure(code,conditions)===null};
      },
      condition(input){
        const next=appendConditions(conditions,input,n),selected=[];w.condition_views++;
        if(!next.conflicts.length)for(const code of codes){
          w.condition_code_visits++;
          if(firstConditionFailure(code,next)===null)selected.push(code);
        }
        return makeView(selected,next);
      },
      profile(){
        const pairCount=n*(n-1)/2;
        if((n+pairCount)*codes.length>SEIDEL_SWITCH_LIMITS.max_profile_cells)fail("Profile exceeds its finite arithmetic cap.");
        const ones=Array(n).fill(0),pairs=[];
        for(let u=0;u<n;u++)for(let v=u+1;v<n;v++)pairs.push({vertices:[u,v],red_count:0});
        for(const code of codes){
          for(let v=0;v<n;v++){ones[v]+=bit(code,v);w.profile_bit_cells++;}
          for(const row of pairs){const [u,v]=row.vertices;row.red_count+=edge(rows,u,v)^bit(code,u)^bit(code,v);w.profile_edge_cells++;}
        }
        w.profile_queries++;
        return {count:codes.length,
          bits:ones.map((one_count,vertex)=>({vertex,one_count,zero_count:codes.length-one_count,
            forced:codes.length===0?null:(one_count===0?0:one_count===codes.length?1:null)})),
          edges:pairs.map(row=>({...row,blue_count:codes.length-row.red_count,
            forced:codes.length===0?null:(row.red_count===0?0:row.red_count===codes.length?1:null)})),
          empty_view_semantics:"forced is null for every coordinate when the family is empty"};
      },
      quadruplePage(start=0,count=16){return pageSlice(quads,start,count,(row,index)=>({index,...copy(row)}));},
      cubePage(start=0,count=16){return pageSlice(cubes,start,count,(row,index)=>({index,...copy(row)}));},
      classificationPage(start=0,count=16){
        const a=integer(start,0,total,"classification start"),limit=integer(count,0,64,"page size"),end=Math.min(total,a+limit),out=[];
        for(let code=a;code<end;code++){out.push({code,admissible:first[code]===-1,
          first_cube:first[code]===-1?null:first[code],monochromatic_quadruples:counts[code]});w.page_rows++;}
        return {start:a,end,total,rows:out,next_start:end<total?end:null};
      },
      snapshot(){return copy(s);},
      work(){return copy(w);}
    });
  }
  return makeView(good,rootConditions());
}
module.exports={paleyPrimeGraph,compileSeidelK4Family,openRetainedSeidelK4Family,SEIDEL_SWITCH_LIMITS};
