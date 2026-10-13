"use strict";

/**
 * Exact implicit Ramsey colorings from a sum-free XOR difference partition.
 * The source-backed Greenwood-Gleason normalization is a convenience input;
 * the generic compiler's finite certificate does not need a field theorem.
 * See RAMSEY_PRODUCT_API.md for classical attribution and problem status.
 */
const XOR_RAMSEY_LIMITS=Object.freeze({
  max_bits_per_symbol:6,
  max_dimension:128,
  max_vertex_bits:512,
  max_base_edges:2016,
  max_palette_witnesses:1953,
  max_product_colors:4096,
  max_snapshot_chars:4000000,
  max_provenance_chars:65536,
  max_decimal_digits:350,
  max_page_rows:128
});
const SCHEMA="commons.xor_ramsey_product/v1";
const COMPLETE="EXACT_TRIANGLE_FREE_PRODUCT";
function fail(s){throw new RangeError(s);}
function int(x,name,lo,hi){
  if(!Number.isSafeInteger(x)||x<lo||x>hi)fail(name+" must be a safe integer in ["+lo+","+hi+"]");
  return x;
}
function obj(x,name){if(!x||typeof x!=="object"||Array.isArray(x))fail(name+" must be an object");return x;}
function arr(x,name,n){if(!Array.isArray(x)||(n!==undefined&&x.length!==n))fail(name+" must be an array"+(n===undefined?"":" of length "+n));return x;}
function clone(x){return JSON.parse(JSON.stringify(x));}
function detached(x,name,cap){
  const s=typeof x==="string"?x:JSON.stringify(obj(x,name));
  if(s.length>cap)fail(name+" exceeds its character limit");
  return JSON.parse(s);
}
function decimal(x,name){
  if(typeof x!=="string"||x.length>XOR_RAMSEY_LIMITS.max_decimal_digits||!/^(0|[1-9][0-9]*)$/.test(x))fail(name+" must be a bounded canonical nonnegative decimal string");
  return BigInt(x);
}
function big(x,name,exclusive){
  let n;
  if(typeof x==="bigint")n=x;
  else if(typeof x==="number"){if(!Number.isSafeInteger(x))fail(name+" Number must be a safe integer");n=BigInt(x);}
  else n=decimal(x,name);
  if(n<0n||(exclusive!==undefined&&n>=exclusive))fail(name+" is outside its range");
  return n;
}
function lowerBudget(x,name,cap){return x===undefined?cap:int(x,name,0,cap);}
function newWork(){
  return {palette_entries:0,sum_free_witnesses:0,base_edges:0,base_neighbor_entries:0,
    product_power_steps:0,product_color_rows:0,product_vertices_enumerated:0,
    product_edges_enumerated:0,base_triangles_enumerated:0,product_triangles_enumerated:0,
    full_field_tables_built:0,primality_or_irreducibility_tests:0,primitive_generator_searches:0};
}

/**
 * Greenwood-Gleason (1955), Theorem 4:
 * x^4-x-1=0 over F2, with the displayed cube subgroup.
 * Codes are polynomial coefficient bits, a normalization chosen here.
 * Only ten multiplication-by-x reductions are performed.
 */
function makeGreenwoodGleasonPalette(){
  const polynomialMask=19,subgroup=[1,8,12,10,15],cosets=[subgroup.slice()],steps=[];
  for(let stage=0;stage<2;stage++){
    const next=[];
    for(let i=0;i<5;i++){
      const input=cosets[stage][i],shifted=input<<1,reduce=(shifted&16)!==0;
      const output=reduce?shifted^polynomialMask:shifted;
      steps.push({stage:stage+1,subgroup_index:i,input,shifted,
        reduction_applied:reduce,polynomial_mask:polynomialMask,output});
      next.push(output);
    }
    cosets.push(next);
  }
  return {
    schema:"commons.greenwood_gleason_palette/v1",
    bits_per_symbol:4,
    polynomial:"x^4-x-1 over F2",
    polynomial_mask:polynomialMask,
    code_convention:"coefficient bits of 1,x,x^2,x^3",
    source_subgroup_polynomials:["1","x^3","x^3+x^2","x^3+x","x^3+x^2+x+1"],
    source_subgroup_codes:subgroup,
    ordered_cosets:cosets,
    difference_classes:cosets.map(a=>a.slice().sort((x,y)=>x-y)),
    multiplication_by_x_steps:steps,
    work:{multiplication_by_x_steps:steps.length,conditional_polynomial_reductions:steps.filter(r=>r.reduction_applied).length,full_field_tables_built:0,
      irreducibility_or_primitivity_tests:0},
    source:{authors:["R. E. Greenwood","A. M. Gleason"],
      title:"Combinatorial Relations and Chromatic Graphs",
      journal:"Canadian Journal of Mathematics",volume:7,year:1955,pages:"1–7",
      doi:"10.4153/CJM-1955-001-4",locator:"Section 4, Theorem 4, printed pages 4–5"}
  };
}

function compileXorRamseyProduct(input){
  obj(input,"input");
  const bits=int(input.bits_per_symbol,"bits_per_symbol",1,XOR_RAMSEY_LIMITS.max_bits_per_symbol);
  const B=1<<bits,dimension=int(input.dimension,"dimension",1,XOR_RAMSEY_LIMITS.max_dimension);
  if(bits*dimension>XOR_RAMSEY_LIMITS.max_vertex_bits)fail("product vertex bit length exceeds its cap");
  const provenance=obj(detached(input.provenance,"provenance",XOR_RAMSEY_LIMITS.max_provenance_chars),"provenance");
  const supplied=arr(input.difference_classes,"difference_classes");
  int(supplied.length,"number of nonempty difference classes",1,B-1);
  const C=supplied.length,classes=[],classOf=new Array(B).fill(-1),work=newWork();
  for(let c=0;c<C;c++){
    const d=arr(supplied[c],"difference class");
    int(d.length,"difference class size",1,B-1);
    const copy=d.map(x=>int(x,"nonzero difference",1,B-1)).sort((x,y)=>x-y);
    for(const x of copy){
      if(classOf[x]!==-1)fail("difference classes must partition nonzero symbols without repetitions");
      classOf[x]=c;work.palette_entries++;
    }
    classes.push(copy);
  }
  for(let x=1;x<B;x++)if(classOf[x]===-1)fail("difference classes must cover all nonzero symbols");
  const neededWitnesses=classes.reduce((s,a)=>s+a.length*(a.length-1)/2,0);
  const neededEdges=B*(B-1)/2,neededColors=dimension*C;
  const witnessBudget=lowerBudget(input.max_palette_witnesses,"max_palette_witnesses",XOR_RAMSEY_LIMITS.max_palette_witnesses);
  const edgeBudget=lowerBudget(input.max_base_edges,"max_base_edges",XOR_RAMSEY_LIMITS.max_base_edges);
  const colorBudget=lowerBudget(input.max_product_colors,"max_product_colors",XOR_RAMSEY_LIMITS.max_product_colors);
  if(neededWitnesses>witnessBudget||neededEdges>edgeBudget||neededColors>colorBudget){
    return {schema:SCHEMA,status:"INCOMPLETE_BUDGET",snapshot:null,work,
      stop:{stage:"preflight",required_palette_witnesses:neededWitnesses,allowed_palette_witnesses:witnessBudget,
        required_base_edges:neededEdges,allowed_base_edges:edgeBudget,
        required_product_colors:neededColors,allowed_product_colors:colorBudget}};
  }
  const witnesses=[],violations=[];
  for(let c=0;c<C;c++){
    const a=classes[c];
    for(let i=0;i<a.length;i++)for(let j=i+1;j<a.length;j++){
      const xor=a[i]^a[j],row={rank:witnesses.length,local_color:c,left_index:i,right_index:j,
        left:a[i],right:a[j],xor,target_color:classOf[xor]};
      witnesses.push(row);work.sum_free_witnesses++;
      if(row.target_color===c)violations.push(row);
    }
  }
  if(violations.length)return {schema:SCHEMA,status:"NOT_TRIANGLE_FREE_PALETTE",snapshot:null,
    bits_per_symbol:bits,difference_classes:classes,sum_free_witnesses:witnesses,violations,work};
  const edges=Array.from({length:C},()=>[]);
  const neighbors=Array.from({length:C},()=>Array.from({length:B},()=>[]));
  for(let a=0;a<B;a++)for(let b=a+1;b<B;b++){
    const difference=a^b,c=classOf[difference];
    edges[c].push({rank:edges[c].length,local_color:c,first:a,second:b,difference});
    neighbors[c][a].push(b);neighbors[c][b].push(a);
    work.base_edges++;work.base_neighbor_entries+=2;
  }
  for(const byVertex of neighbors)for(const row of byVertex)row.sort((a,b)=>a-b);
  const powers=[1n],base=BigInt(B);
  for(let i=1;i<=dimension;i++){powers.push(powers[i-1]*base);work.product_power_steps++;}
  const N=powers[dimension],rows=[];
  for(let j=0;j<dimension;j++){
    const suffix=dimension-j-1,T=powers[suffix],P=powers[j];
    for(let c=0;c<C;c++){
      const count=P*BigInt(edges[c].length)*T*T,degree=BigInt(classes[c].length)*T;
      rows.push({color:rows.length,coordinate:j,local_color:c,
        suffix_digits:suffix,prefix_count:P.toString(),tail_space:T.toString(),
        base_edge_count:edges[c].length,base_degree:classes[c].length,
        edge_count:count.toString(),neighbor_count:degree.toString()});
      work.product_color_rows++;
    }
  }
  const snapshot={
    schema:SCHEMA,status:COMPLETE,
    base:{bits_per_symbol:bits,symbol_count:B,color_count:C,
      addition:"bitwise XOR on coefficient labels",
      difference_classes:classes,color_by_difference:classOf,
      sum_free_witnesses:witnesses,edges_by_color:edges,neighbors_by_color:neighbors,
      provenance,
      summary:{edge_count:neededEdges,sum_free_witness_count:witnesses.length,
        class_sizes:classes.map(a=>a.length),edges_per_color:edges.map(a=>a.length)}},
    product:{dimension,vertex_bits:bits*dimension,vertex_count:N.toString(),color_count:neededColors,
      color_rule:"first differing coordinate with a separate copy of the base palette",
      vertex_order:"fixed-length base-B digits, most significant coordinate first",
      powers:powers.map(x=>x.toString()),color_rows:rows},
    summary:{symbol_count:B,base_colors:C,dimension,vertex_count:N.toString(),
      color_count:neededColors,edge_count:(N*(N-1n)/2n).toString(),
      neighbors_per_vertex:(N-1n).toString(),monochromatic_triangle_free:true,
      ramsey_parameter:neededColors,ramsey_lower_bound:(N+1n).toString(),
      lower_bound_scope:"explicit classical-family construction; no new Ramsey record or asymptotic result",
      storage:"base certificates and product count tables, without enumerated product vertices or edges"},
    work,limits:clone(XOR_RAMSEY_LIMITS)
  };
  const chars=JSON.stringify(snapshot).length;
  if(chars>XOR_RAMSEY_LIMITS.max_snapshot_chars)return {schema:SCHEMA,status:"INCOMPLETE_BUDGET",snapshot:null,work,
    stop:{stage:"snapshot",actual_chars:chars,allowed_chars:XOR_RAMSEY_LIMITS.max_snapshot_chars}};
  return {schema:SCHEMA,status:COMPLETE,summary:clone(snapshot.summary),snapshot,work:clone(work),snapshot_chars:chars};
}

function openRetainedXorRamseyProduct(value){
  const s=detached(value,"snapshot",XOR_RAMSEY_LIMITS.max_snapshot_chars);
  if(s.schema!==SCHEMA||s.status!==COMPLETE)fail("a complete retained product index is required");
  const b=obj(s.base,"base"),p=obj(s.product,"product");
  const bits=int(b.bits_per_symbol,"base bits",1,XOR_RAMSEY_LIMITS.max_bits_per_symbol);
  const B=1<<bits,C=int(b.color_count,"base color count",1,B-1),base=BigInt(B);
  const dimension=int(p.dimension,"dimension",1,XOR_RAMSEY_LIMITS.max_dimension);
  if(b.symbol_count!==B||p.vertex_bits!==bits*dimension||bits*dimension>XOR_RAMSEY_LIMITS.max_vertex_bits)fail("inconsistent product dimensions");
  const totalColors=dimension*C;
  if(p.color_count!==totalColors||totalColors>XOR_RAMSEY_LIMITS.max_product_colors)fail("invalid product color count");
  obj(detached(b.provenance,"base provenance",XOR_RAMSEY_LIMITS.max_provenance_chars),"base provenance");
  if(b.addition!=="bitwise XOR on coefficient labels" ||
    p.color_rule!=="first differing coordinate with a separate copy of the base palette" ||
    p.vertex_order!=="fixed-length base-B digits, most significant coordinate first")fail("unsupported saved coloring convention");
  const classes=arr(b.difference_classes,"difference_classes",C),classOf=arr(b.color_by_difference,"color_by_difference",B);
  const stats={loaded_palette_entries:0,saved_sum_free_arithmetic_checks:0,saved_base_edge_checks:0,
    saved_neighbor_entry_checks:0,saved_power_checks:0,saved_color_count_checks:0,
    queries:0,summary_queries:0,palette_queries:0,color_queries:0,edge_color_queries:0,
    edge_rank_queries:0,edge_select_queries:0,neighbor_rank_queries:0,neighbor_select_queries:0,
    triangle_queries:0,vertex_encode_queries:0,vertex_decode_queries:0,page_queries:0,
    page_rows_returned:0,first_difference_lookups:0,edge_selections:0,neighbor_selections:0,
    vertex_digits_encoded:0,vertex_digits_decoded:0,
    palette_constructions:0,base_edge_pair_enumerations:0,base_triangle_enumerations:0,
    product_vertex_enumerations:0,product_edge_enumerations:0,product_triangle_enumerations:0,
    product_count_table_constructions:0,field_operations:0};
  if(classOf[0]!==-1)fail("zero has no edge color");
  const seen=new Array(B).fill(false);
  for(let c=0;c<C;c++){
    const a=arr(classes[c],"class");int(a.length,"class size",1,B-1);
    for(let i=0;i<a.length;i++){
      const x=int(a[i],"saved difference",1,B-1);
      if((i&&x<=a[i-1])||seen[x]||classOf[x]!==c)fail("invalid saved difference partition");
      seen[x]=true;stats.loaded_palette_entries++;
    }
  }
  for(let x=1;x<B;x++)if(!seen[x])fail("missing saved difference");
  const neededWitnesses=classes.reduce((a,z)=>a+z.length*(z.length-1)/2,0);
  const witnesses=arr(b.sum_free_witnesses,"sum_free_witnesses",neededWitnesses),witnessLookup=new Map();
  let wrank=0;
  for(let c=0;c<C;c++)for(let i=0;i<classes[c].length;i++)for(let j=i+1;j<classes[c].length;j++){
    const r=obj(witnesses[wrank],"sum-free witness"),x=classes[c][i],y=classes[c][j],z=x^y;
    if(r.rank!==wrank||r.local_color!==c||r.left_index!==i||r.right_index!==j||
      r.left!==x||r.right!==y||r.xor!==z||r.target_color!==classOf[z]||r.target_color===c)fail("invalid saved sum-free witness");
    witnessLookup.set(c+":"+x+":"+y,r);wrank++;stats.saved_sum_free_arithmetic_checks++;
  }
  const edges=arr(b.edges_by_color,"edges_by_color",C),edgeRank=Array.from({length:B},()=>new Array(B).fill(-1));
  let allEdges=0;
  for(let c=0;c<C;c++){
    const a=arr(edges[c],"base edge family",B*classes[c].length/2);
    let previous=-1;
    for(let i=0;i<a.length;i++){
      const r=obj(a[i],"base edge"),x=int(r.first,"base first vertex",0,B-1),y=int(r.second,"base second vertex",0,B-1);
      const code=x*B+y;
      if(x>=y||code<=previous||r.rank!==i||r.local_color!==c||r.difference!==(x^y)||
        classOf[x^y]!==c||edgeRank[x][y]!==-1)fail("invalid saved base edge");
      edgeRank[x][y]=edgeRank[y][x]=i;previous=code;allEdges++;stats.saved_base_edge_checks++;
    }
  }
  if(allEdges!==B*(B-1)/2)fail("saved base edges do not cover the complete graph");
  const neighbors=arr(b.neighbors_by_color,"neighbors_by_color",C);
  const neighborRank=Array.from({length:C},()=>Array.from({length:B},()=>new Array(B).fill(-1)));
  for(let c=0;c<C;c++){
    arr(neighbors[c],"base neighborhood family",B);
    for(let x=0;x<B;x++){
      const row=arr(neighbors[c][x],"base neighborhood",classes[c].length);
      for(let i=0;i<row.length;i++){
        const y=int(row[i],"base neighbor",0,B-1);
        if(y===x||(i&&y<=row[i-1])||classOf[x^y]!==c||edgeRank[x][y]===-1)fail("invalid saved base neighbor");
        neighborRank[c][x][y]=i;stats.saved_neighbor_entry_checks++;
      }
    }
  }
  const powers=arr(p.powers,"powers",dimension+1).map((x,i)=>decimal(x,"saved power "+i));
  if(powers[0]!==1n)fail("first saved power must be one");
  for(let i=1;i<=dimension;i++){
    if(powers[i]!==powers[i-1]*base)fail("inconsistent saved power");
    stats.saved_power_checks++;
  }
  const N=powers[dimension];
  if(decimal(p.vertex_count,"vertex count")!==N)fail("vertex count disagrees with saved powers");
  const colorRows=arr(p.color_rows,"color_rows",totalColors),edgeCounts=[],degrees=[];
  let edgeTotal=0n,degreeTotal=0n;
  for(let g=0;g<totalColors;g++){
    const r=obj(colorRows[g],"product color row"),j=Math.floor(g/C),c=g%C,suffix=dimension-j-1,T=powers[suffix],P=powers[j];
    const E=P*BigInt(edges[c].length)*T*T,D=BigInt(classes[c].length)*T;
    if(r.color!==g||r.coordinate!==j||r.local_color!==c||r.suffix_digits!==suffix||
      decimal(r.prefix_count,"prefix count")!==P||decimal(r.tail_space,"tail space")!==T||
      r.base_edge_count!==edges[c].length||r.base_degree!==classes[c].length||
      decimal(r.edge_count,"color edge count")!==E||decimal(r.neighbor_count,"color neighbor count")!==D)fail("invalid saved product color row");
    edgeCounts.push(E);degrees.push(D);edgeTotal+=E;degreeTotal+=D;stats.saved_color_count_checks++;
  }
  const summary=obj(s.summary,"summary");
  if(summary.symbol_count!==B||summary.base_colors!==C||summary.dimension!==dimension||summary.color_count!==totalColors||
    decimal(summary.vertex_count,"summary vertices")!==N||decimal(summary.edge_count,"summary edges")!==N*(N-1n)/2n||
    decimal(summary.neighbors_per_vertex,"summary degree")!==N-1n||summary.monochromatic_triangle_free!==true||
    summary.ramsey_parameter!==totalColors||decimal(summary.ramsey_lower_bound,"Ramsey lower bound")!==N+1n||
    edgeTotal!==N*(N-1n)/2n||degreeTotal!==N-1n)fail("inconsistent finite summary");
  obj(b.summary,"base summary");
  if(b.summary.edge_count!==allEdges||b.summary.sum_free_witness_count!==neededWitnesses||
    JSON.stringify(b.summary.class_sizes)!==JSON.stringify(classes.map(a=>a.length))||
    JSON.stringify(b.summary.edges_per_color)!==JSON.stringify(edges.map(a=>a.length)))fail("inconsistent base summary");

  function query(kind){stats.queries++;stats[kind]++;}
  function vertex(x,name){return big(x,name,N);}
  function color(x){return int(x,"color",0,totalColors-1);}
  function localColor(x){return int(x,"local color",0,C-1);}
  function firstDifference(x,y){
    if(x===y)fail("an edge requires two distinct vertices");
    const suffix=Math.floor(((x^y).toString(2).length-1)/bits);
    const coordinate=dimension-suffix-1,T=powers[suffix];
    const a=Number((x/T)%base),b=Number((y/T)%base),c=classOf[a^b];
    stats.first_difference_lookups++;
    return {color:coordinate*C+c,coordinate,local_color:c,suffix_digits:suffix,
      tail:T,first_symbol:a,second_symbol:b,base_difference:a^b};
  }
  function colorDescription(x,y){
    const r=firstDifference(x,y);
    return {vertices:[x.toString(),y.toString()],color:r.color,coordinate:r.coordinate,
      local_color:r.local_color,symbols:[r.first_symbol,r.second_symbol],base_difference:r.base_difference};
  }
  function selectEdgeCore(g,rank){
    const row=colorRows[g],T=powers[row.suffix_digits],E=BigInt(row.base_edge_count);
    let qrank=rank;
    const rightTail=qrank%T;qrank/=T;
    const leftTail=qrank%T;qrank/=T;
    const baseRank=Number(qrank%E),prefix=qrank/E,r=edges[row.local_color][baseRank];
    const x=(prefix*base+BigInt(r.first))*T+leftTail,y=(prefix*base+BigInt(r.second))*T+rightTail;
    stats.edge_selections++;
    return {color:g,rank:rank.toString(),vertices:[x.toString(),y.toString()],
      coordinate:row.coordinate,local_color:row.local_color,
      prefix:prefix.toString(),base_edge_rank:baseRank,base_edge:[r.first,r.second],
      tails:[leftTail.toString(),rightTail.toString()]};
  }
  function rankEdgeCore(x,y){
    let reversed=false;if(x>y){const z=x;x=y;y=z;reversed=true;}
    const r=firstDifference(x,y),T=r.tail,E=BigInt(edges[r.local_color].length);
    const prefix=x/(T*base),a=r.first_symbol,b=r.second_symbol,baseRank=edgeRank[a][b];
    const left=x%T,right=y%T,rank=(((prefix*E+BigInt(baseRank))*T+left)*T+right);
    return {color:r.color,rank:rank.toString(),vertices:[x.toString(),y.toString()],
      input_reversed:reversed,coordinate:r.coordinate,local_color:r.local_color,
      prefix:prefix.toString(),base_edge_rank:baseRank,base_edge:[a,b],
      tails:[left.toString(),right.toString()]};
  }
  function selectNeighborCore(x,g,rank){
    const row=colorRows[g],T=powers[row.suffix_digits],a=Number((x/T)%base),prefix=x/(T*base);
    const i=Number(rank/T),tail=rank%T,b=neighbors[row.local_color][a][i];
    const y=(prefix*base+BigInt(b))*T+tail;stats.neighbor_selections++;
    return {vertex:x.toString(),color:g,rank:rank.toString(),neighbor:y.toString(),
      coordinate:row.coordinate,local_color:row.local_color,base_symbols:[a,b],
      base_neighbor_rank:i,prefix:prefix.toString(),tail:tail.toString()};
  }
  function pageBounds(options,size){
    if(options===undefined)options={};obj(options,"page options");
    const start=options.start===undefined?0n:big(options.start,"page start");
    if(start>size)fail("page start exceeds family size");
    const limit=options.limit===undefined?XOR_RAMSEY_LIMITS.max_page_rows:
      int(options.limit,"page limit",1,XOR_RAMSEY_LIMITS.max_page_rows);
    const stop=start+BigInt(limit)<size?start+BigInt(limit):size;
    return {start,stop,size};
  }
  function generatedPage(options,size,select){
    const b=pageBounds(options,size),records=[];
    for(let rank=b.start;rank<b.stop;rank++)records.push(select(rank));
    stats.page_queries++;stats.page_rows_returned+=records.length;
    return {start:b.start.toString(),count:records.length,total:b.size.toString(),
      next_start:b.stop<b.size?b.stop.toString():null,records};
  }
  function savedPage(rows,options){
    return generatedPage(options,BigInt(rows.length),rank=>clone(rows[Number(rank)]));
  }
  const api={
    summary(){query("summary_queries");return clone(s.summary);},
    source(){query("summary_queries");return clone(b.provenance);},
    basePalette(){query("palette_queries");return clone({bits_per_symbol:bits,difference_classes:classes,color_by_difference:classOf,summary:b.summary});},
    baseWitnessPage(options){query("palette_queries");return savedPage(witnesses,options);},
    baseEdgePage(c,options){query("palette_queries");return {local_color:localColor(c),...savedPage(edges[c],options)};},
    baseNeighbors(c,x){query("palette_queries");localColor(c);int(x,"base vertex",0,B-1);return neighbors[c][x].slice();},
    colorSummary(g){query("color_queries");return clone(colorRows[color(g)]);},
    colorPage(options){query("color_queries");return savedPage(colorRows,options);},
    edgeColor(x,y){query("edge_color_queries");return colorDescription(vertex(x,"first vertex"),vertex(y,"second vertex"));},
    rankEdge(x,y){query("edge_rank_queries");return rankEdgeCore(vertex(x,"first vertex"),vertex(y,"second vertex"));},
    selectEdge(g,rank){query("edge_select_queries");g=color(g);return selectEdgeCore(g,big(rank,"edge rank",edgeCounts[g]));},
    edgePage(g,options){query("edge_select_queries");g=color(g);return {color:g,...generatedPage(options,edgeCounts[g],r=>selectEdgeCore(g,r))};},
    selectNeighbor(x,g,rank){query("neighbor_select_queries");x=vertex(x,"vertex");g=color(g);return selectNeighborCore(x,g,big(rank,"neighbor rank",degrees[g]));},
    neighborPage(x,g,options){query("neighbor_select_queries");x=vertex(x,"vertex");g=color(g);return {vertex:x.toString(),color:g,...generatedPage(options,degrees[g],r=>selectNeighborCore(x,g,r))};},
    rankNeighbor(x,y){
      query("neighbor_rank_queries");x=vertex(x,"vertex");y=vertex(y,"neighbor");
      const r=firstDifference(x,y),i=neighborRank[r.local_color][r.first_symbol][r.second_symbol],rank=BigInt(i)*r.tail+y%r.tail;
      return {vertex:x.toString(),neighbor:y.toString(),color:r.color,rank:rank.toString(),
        coordinate:r.coordinate,local_color:r.local_color,base_neighbor_rank:i};
    },
    encodeVertex(digits){
      query("vertex_encode_queries");arr(digits,"vertex digits",dimension);let x=0n;
      for(const d of digits){x=x*base+BigInt(int(d,"vertex digit",0,B-1));stats.vertex_digits_encoded++;}
      return x.toString();
    },
    decodeVertex(value){
      query("vertex_decode_queries");let x=vertex(value,"vertex");const digits=new Array(dimension);
      for(let j=dimension-1;j>=0;j--){digits[j]=Number(x%base);x/=base;stats.vertex_digits_decoded++;}
      return digits;
    },
    triangleCertificate(values){
      query("triangle_queries");arr(values,"triangle vertices",3);
      const v=values.map((x,i)=>vertex(x,"triangle vertex "+i));
      if(v[0]===v[1]||v[0]===v[2]||v[1]===v[2])fail("a triangle requires three distinct vertices");
      const pairs=[[0,1],[0,2],[1,2]],erows=pairs.map(([i,j])=>({pair:[i,j],...colorDescription(v[i],v[j])}));
      const j=Math.min(...erows.map(r=>r.coordinate)),T=powers[dimension-j-1],symbols=v.map(x=>Number((x/T)%base));
      let evidence;
      if(new Set(symbols).size===2){
        const within=pairs.find(([a,b])=>symbols[a]===symbols[b]);
        const inside=erows.find(r=>r.pair[0]===within[0]&&r.pair[1]===within[1]);
        const crossing=erows.filter(r=>r!==inside);
        evidence={kind:"two_symbols_at_first_split",coordinate:j,symbols,within_pair:within,
          within_coordinate:inside.coordinate,crossing_coordinates:crossing.map(r=>r.coordinate),
          reason:"the within-pair edge uses a later coordinate, whose color palette is disjoint"};
      }else{
        const colors=erows.map(r=>r.local_color);
        if(new Set(colors).size===3)evidence={kind:"three_distinct_base_colors",coordinate:j,symbols,base_colors:colors};
        else{
          const repeated=pairs.find(([a,b])=>colors[a]===colors[b]);
          const r1=erows[repeated[0]],r2=erows[repeated[1]];
          const a=Math.min(r1.base_difference,r2.base_difference),b=Math.max(r1.base_difference,r2.base_difference);
          const witness=witnessLookup.get(r1.local_color+":"+a+":"+b);
          if(!witness)throw new Error("missing retained sum-free triangle witness");
          evidence={kind:"saved_sum_free_witness",coordinate:j,symbols,base_colors:colors,witness:clone(witness)};
        }
      }
      const monochromatic=erows.every(r=>r.color===erows[0].color);
      if(monochromatic)throw new Error("retained triangle-free certificate was contradicted");
      return {vertices:v.map(x=>x.toString()),edges:erows,monochromatic:false,evidence};
    },
    snapshot(){return clone(s);},
    statistics(){return clone(stats);}
  };
  return Object.freeze(api);
}

module.exports={XOR_RAMSEY_LIMITS,makeGreenwoodGleasonPalette,compileXorRamseyProduct,openRetainedXorRamseyProduct};
