"use strict";

/*
 * Exact finite triangular-lattice diameter families.
 * This module performs no I/O and uses no external dependencies.
 */
const LATTICE_DIAMETER_LIMITS = Object.freeze({
  max_points: 40,
  max_abs_coordinate: 1000000,
  max_squared_diameter: 12000000000000,
  max_hexagon_radius: 3,
  max_states: 100000,
  max_snapshot_chars: 16000000,
  max_page_size: 4096,
  max_decimal_digits: 13
});
const SNAPSHOT_SCHEMA = "commons.lattice_diameter_family/v1";

function need(ok, message) { if (!ok) throw new TypeError(message); }
function integer(x, lo, hi, name) {
  need(Number.isSafeInteger(x) && x >= lo && x <= hi, name + " is outside its integer range");
  return x;
}
function decimal(x, name) {
  if (typeof x === "bigint") { need(x >= 0n && x <= (1n<<40n), name + " is outside the finite-family range"); return x; }
  if (typeof x === "number") { need(Number.isSafeInteger(x) && x >= 0, name + " must be exact"); return BigInt(x); }
  need(typeof x === "string" && x.length<=LATTICE_DIAMETER_LIMITS.max_decimal_digits && /^(0|[1-9][0-9]*)$/.test(x), name + " must be a bounded canonical nonnegative decimal");
  return BigInt(x);
}
function copy(x) { return JSON.parse(JSON.stringify(x)); }
function pop(x) { let n=0; while(x) { x &= x-1n; n++; } return n; }
function labels(mask, bits) { const a=[]; for(let i=0;i<bits.length;i++) if(mask&bits[i]) a.push(i); return a; }
function pointsInput(input) {
  need(Array.isArray(input) && input.length<=LATTICE_DIAMETER_LIMITS.max_points, "points must be an array within the point cap");
  const seen=new Set();
  return input.map((p,i)=>{
    need(Array.isArray(p)&&p.length===2, "each point must have exactly two axial coordinates");
    const a=integer(p[0],-LATTICE_DIAMETER_LIMITS.max_abs_coordinate,LATTICE_DIAMETER_LIMITS.max_abs_coordinate,"coordinate");
    const b=integer(p[1],-LATTICE_DIAMETER_LIMITS.max_abs_coordinate,LATTICE_DIAMETER_LIMITS.max_abs_coordinate,"coordinate");
    const key=a+","+b; need(!seen.has(key), "duplicate lattice point at index "+i); seen.add(key);
    return [a,b];
  });
}
function cappedIntegerOptions(options) {
  need(options && typeof options==="object" && !Array.isArray(options), "options must be an object");
  return {
    max_states:integer(options.max_states===undefined?LATTICE_DIAMETER_LIMITS.max_states:options.max_states,1,LATTICE_DIAMETER_LIMITS.max_states,"max_states")
  };
}

/** The labels follow increasing first coordinate, then increasing second coordinate. */
function triangularHexagon(radius) {
  integer(radius,0,LATTICE_DIAMETER_LIMITS.max_hexagon_radius,"radius");
  const points=[];
  for(let a=-radius;a<=radius;a++) for(let b=-radius;b<=radius;b++)
    if(Math.abs(a+b)<=radius) points.push([a,b]);
  return {kind:"axial_hexagon",radius,points};
}

/**
 * Construct all exact pair distances and a complete unit-triangle ledger once,
 * then solve the maximum-clique recurrence with memoization. A state cap is an
 * unfinished computation, never an infeasibility or optimality certificate.
 */
function compileLatticeDiameterFamily(input, options={}) {
  need(input && typeof input==="object", "input must be an object");
  const points=pointsInput(input.points);
  const cap=integer(input.squared_diameter,0,LATTICE_DIAMETER_LIMITS.max_squared_diameter,"squared_diameter");
  const limits=cappedIntegerOptions(options), n=points.length;
  const bits=Array.from({length:n},(_,i)=>1n<<BigInt(i)), full=(1n<<BigInt(n))-1n;
  const adj=Array(n).fill(0n), unit=Array(n).fill(0n);
  const pairs=[], triangles=[], matrix=Array.from({length:n},()=>Array(n).fill(0));
  const counters={
    pair_distance_evaluations:0, compatibility_edges:0, unit_edges:0,
    unit_triangle_candidates:0, unit_triangles:0,
    memo_hits:0, states_entered:0, completed_states:0,
    universal_vertex_tests:0, forced_states:0, branch_states:0,
    coloring_calls:0, coloring_vertex_placements:0, coloring_classes:0,
    pruned_exclude_branches:0
  };
  for(let i=0;i<n;i++) for(let j=i+1;j<n;j++) {
    const a=points[i][0]-points[j][0], b=points[i][1]-points[j][1];
    const d=a*a+a*b+b*b;
    need(Number.isSafeInteger(d)&&d>=1, "distance arithmetic escaped its exact contract");
    counters.pair_distance_evaluations++;
    matrix[i][j]=matrix[j][i]=d;
    pairs.push([i,j,d]);
    if(d<=cap) {adj[i]|=bits[j];adj[j]|=bits[i];counters.compatibility_edges++;}
    if(d===1) {unit[i]|=bits[j];unit[j]|=bits[i];counters.unit_edges++;}
  }
  for(let i=0;i<n;i++) for(let j=i+1;j<n;j++) if(unit[i]&bits[j]) {
    const common=unit[i]&unit[j];
    for(let k=j+1;k<n;k++) {
      counters.unit_triangle_candidates++;
      if(common&bits[k]) triangles.push([i,j,k]);
    }
  }
  counters.unit_triangles=triangles.length;
  const rows=[], memo=new Map(), active=[];
  function finish(mask,row) {
    const id=rows.length;
    const completed={id,mask:mask.toString(),...row};
    rows.push(completed);memo.set(mask,id);counters.completed_states++;
    return id;
  }
  function colors(mask) {
    counters.coloring_calls++;
    const classes=[];let left=mask;
    while(left) {
      let available=left, group=0n;
      for(let i=0;i<n&&available;i++) if(available&bits[i]) {
        group|=bits[i];left&=~bits[i];
        available&=~(bits[i]|adj[i]);
        counters.coloring_vertex_placements++;
      }
      need(group!==0n, "internal empty color class");
      classes.push(group.toString());counters.coloring_classes++;
    }
    return classes;
  }
  function solve(mask) {
    if(memo.has(mask)) {counters.memo_hits++;return memo.get(mask);}
    if(counters.states_entered>=limits.max_states) {
      const error=new RangeError("maximum-clique state cap reached; computation unfinished");
      error.code="STATE_CAP";
      error.partial={
        status:"INCOMPLETE",points:copy(points),squared_diameter:cap,
        pair_distances:copy(pairs),unit_triangles:copy(triangles),
        adjacency_masks:adj.map(String),completed_nodes:copy(rows),
        pending_masks:active.map(String).concat([mask.toString()]),counters:copy(counters)
      };
      throw error;
    }
    counters.states_entered++;active.push(mask);
    if(mask===0n) {
      const id=finish(mask,{kind:"empty",omega:0,count:"1"});
      active.pop();return id;
    }
    let forced=0n, pivot=-1, bestDegree=-1;
    for(let i=0;i<n;i++) if(mask&bits[i]) {
      counters.universal_vertex_tests++;
      const neighbors=adj[i]&mask, degree=pop(neighbors);
      if(neighbors===(mask&~bits[i])) forced|=bits[i];
      if(degree>bestDegree) {bestDegree=degree;pivot=i;}
    }
    if(forced) {
      counters.forced_states++;
      const child=solve(mask&~forced), c=rows[child];
      const id=finish(mask,{kind:"forced",forced_mask:forced.toString(),child,
        omega:pop(forced)+c.omega,count:c.count});
      active.pop();return id;
    }
    counters.branch_states++;
    const includeMask=mask&adj[pivot], excludeMask=mask&~bits[pivot];
    const includeChild=solve(includeMask), inc=rows[includeChild];
    const includeOmega=1+inc.omega, classes=colors(excludeMask), upper=classes.length;
    let excludeChild=null, omega=includeOmega, count=BigInt(inc.count), optimal=["include"];
    if(upper<includeOmega) {
      counters.pruned_exclude_branches++;
    } else {
      excludeChild=solve(excludeMask);
      const exc=rows[excludeChild];
      omega=Math.max(includeOmega,exc.omega);
      optimal=[];
      count=0n;
      if(includeOmega===omega) {optimal.push("include");count+=BigInt(inc.count);}
      if(exc.omega===omega) {optimal.push("exclude");count+=BigInt(exc.count);}
    }
    const id=finish(mask,{
      kind:"branch",vertex:pivot,include_child:includeChild,exclude_child:excludeChild,
      exclude_color_classes:classes,exclude_upper_bound:upper,
      exclude_pruned:excludeChild===null,optimal_branches:optimal,
      omega,count:count.toString()
    });
    active.pop();return id;
  }
  const root=solve(full);
  const snapshot={
    schema:SNAPSHOT_SCHEMA,
    points:copy(points),squared_diameter:cap,
    geometry:{
      coordinate_convention:"(a,b) maps to (a+b/2,sqrt(3)*b/2)",
      squared_norm:"a*a+a*b+b*b",
      pair_order:"increasing i, then increasing j, i<j",
      pair_distances:pairs,adjacency_masks:adj.map(String),
      unit_triangles:triangles
    },
    proof:{
      method:"maximum-clique forced-universal and include/exclude recurrence",
      family_order:"include-first proof-DAG order; not lexicographic vertex order",
      root,node_count:rows.length,nodes:rows,
      maximum_cardinality:rows[root].omega,maximum_subset_count:rows[root].count
    },
    compilation:{status:"COMPLETE",limits,counters}
  };
  const serialized=JSON.stringify(snapshot);
  if(serialized.length>LATTICE_DIAMETER_LIMITS.max_snapshot_chars) {
    const error=new RangeError("snapshot character cap reached");
    error.code="SNAPSHOT_CAP";error.completed_snapshot=snapshot;throw error;
  }
  return {snapshot,summary:{
    point_count:n,squared_diameter:cap,
    maximum_cardinality:rows[root].omega,maximum_subset_count:rows[root].count,
    proof_nodes:rows.length,pair_records:pairs.length,unit_triangles:triangles.length,
    snapshot_chars:serialized.length,counters:copy(counters)
  }};
}

/**
 * Restore the finite combinatorial proof and index.
 * Pair distances and completeness of the triangle ledger are identified input
 * premises. The reader does not recompute squared norms or rebuild that ledger.
 */
function openRetainedLatticeDiameterFamily(saved) {
  let serialized;
  if(typeof saved==="string") {
    need(saved.length<=LATTICE_DIAMETER_LIMITS.max_snapshot_chars,"snapshot exceeds character cap");
    serialized=saved;
  } else {
    serialized=JSON.stringify(saved);
    need(typeof serialized==="string"&&serialized.length<=LATTICE_DIAMETER_LIMITS.max_snapshot_chars,"invalid snapshot");
  }
  const data=JSON.parse(serialized);
  need(data && data.schema===SNAPSHOT_SCHEMA,"unsupported snapshot schema");
  const points=pointsInput(data.points), n=points.length;
  const cap=integer(data.squared_diameter,0,LATTICE_DIAMETER_LIMITS.max_squared_diameter,"squared_diameter");
  const bits=Array.from({length:n},(_,i)=>1n<<BigInt(i)),full=(1n<<BigInt(n))-1n;
  function maskValue(s,name) {const m=decimal(s,name);need((m&~full)===0n,name+" contains out-of-host bits");return m;}
  need(data.geometry&&Array.isArray(data.geometry.pair_distances),"missing pair distances");
  const pairRows=data.geometry.pair_distances;
  need(pairRows.length===n*(n-1)/2,"pair table length mismatch");
  const distance=Array.from({length:n},()=>Array(n).fill(0)),derivedAdj=Array(n).fill(0n);
  const statistics={
    loaded_pair_records:pairRows.length,loaded_triangle_records:0,loaded_proof_nodes:0,
    pair_record_checks:0,triangle_record_checks:0,proof_recurrence_checks:0,
    forced_vertex_checks:0,coloring_pair_checks:0,
    select_queries:0,select_node_visits:0,rank_queries:0,rank_node_visits:0,
    membership_queries:0,profile_queries:0,profile_pair_lookups:0,profile_triangle_checks:0,
    page_queries:0,page_rows:0,geometry_distance_evaluations:0,
    triangle_ledger_constructions:0,optimization_states:0
  };
  let pos=0;
  for(let i=0;i<n;i++) for(let j=i+1;j<n;j++) {
    const row=pairRows[pos++];
    need(Array.isArray(row)&&row.length===3&&row[0]===i&&row[1]===j,"pair order or endpoint mismatch");
    const d=integer(row[2],1,LATTICE_DIAMETER_LIMITS.max_squared_diameter,"retained squared distance");
    distance[i][j]=distance[j][i]=d;
    if(d<=cap) {derivedAdj[i]|=bits[j];derivedAdj[j]|=bits[i];}
    statistics.pair_record_checks++;
  }
  need(Array.isArray(data.geometry.adjacency_masks)&&data.geometry.adjacency_masks.length===n,"adjacency size mismatch");
  const adj=data.geometry.adjacency_masks.map((s,i)=>{const m=maskValue(s,"adjacency");need(m===derivedAdj[i],"adjacency disagrees with retained distances");return m;});
  need(Array.isArray(data.geometry.unit_triangles),"missing triangle ledger");
  const triangleRows=data.geometry.unit_triangles, triangleMasks=[];
  let previous=null;
  for(const row of triangleRows) {
    need(Array.isArray(row)&&row.length===3,"invalid triangle row");
    const [i,j,k]=row;
    integer(i,0,n-1,"triangle vertex");integer(j,0,n-1,"triangle vertex");integer(k,0,n-1,"triangle vertex");
    need(i<j&&j<k,"triangle labels must be strictly increasing");
    if(previous) need(i>previous[0]||(i===previous[0]&&(j>previous[1]||(j===previous[1]&&k>previous[2]))),"triangle rows not strictly ordered");
    need(distance[i][j]===1&&distance[i][k]===1&&distance[j][k]===1,"triangle is not unit in retained distances");
    triangleMasks.push(bits[i]|bits[j]|bits[k]);previous=row;
    statistics.triangle_record_checks++;
  }
  statistics.loaded_triangle_records=triangleRows.length;
  need(data.proof&&Array.isArray(data.proof.nodes),"missing proof DAG");
  const rows=data.proof.nodes;
  need(rows.length>=1&&rows.length<=LATTICE_DIAMETER_LIMITS.max_states,"proof node cap");
  const masks=[], counts=[], seen=new Set();
  function child(id,parent) {integer(id,0,parent-1,"child id");return rows[id];}
  for(let id=0;id<rows.length;id++) {
    const row=rows[id];
    need(row&&row.id===id,"proof node id mismatch");
    const m=maskValue(row.mask,"node mask");
    need(!seen.has(m.toString()),"duplicate proof mask");seen.add(m.toString());masks.push(m);
    integer(row.omega,0,pop(m),"node omega");
    const cnt=decimal(row.count,"node count");need(cnt>=1n,"node count must be positive");counts.push(cnt);
    if(row.kind==="empty") {
      need(m===0n&&row.omega===0&&cnt===1n,"invalid empty node");
    } else if(row.kind==="forced") {
      const u=maskValue(row.forced_mask,"forced mask");
      need(u!==0n&&(u&~m)===0n,"invalid forced mask");
      const c=child(row.child,id);
      need(masks[row.child]===(m&~u),"forced child mask mismatch");
      for(let i=0;i<n;i++) if(u&bits[i]) {
        need((adj[i]&m)===(m&~bits[i]),"forced vertex is not universal");
        statistics.forced_vertex_checks++;
      }
      need(row.omega===pop(u)+c.omega&&cnt===counts[row.child],"forced recurrence mismatch");
    } else if(row.kind==="branch") {
      const v=integer(row.vertex,0,n-1,"pivot");
      need((m&bits[v])!==0n,"pivot is not present");
      const inc=child(row.include_child,id);
      need(masks[row.include_child]===(m&adj[v]),"include child mask mismatch");
      const exclude=m&~bits[v];
      need(Array.isArray(row.exclude_color_classes),"missing coloring evidence");
      let union=0n;
      for(const raw of row.exclude_color_classes) {
        const group=maskValue(raw,"color class");
        need(group!==0n&&(group&~exclude)===0n&&(group&union)===0n,"invalid color class partition");
        const vertices=labels(group,bits);
        for(let a=0;a<vertices.length;a++) for(let b=a+1;b<vertices.length;b++) {
          need((adj[vertices[a]]&bits[vertices[b]])===0n,"color class contains a compatible pair");
          statistics.coloring_pair_checks++;
        }
        union|=group;
      }
      need(union===exclude&&row.exclude_upper_bound===row.exclude_color_classes.length,"coloring coverage or bound mismatch");
      const iomega=1+inc.omega;
      let omega=iomega,count=counts[row.include_child],optimal=["include"];
      if(row.exclude_pruned===true) {
        need(row.exclude_child===null&&row.exclude_upper_bound<iomega,"pruning does not have a strict bound");
      } else {
        need(row.exclude_pruned===false,"invalid prune marker");
        const exc=child(row.exclude_child,id);
        need(masks[row.exclude_child]===exclude,"exclude child mask mismatch");
        omega=Math.max(iomega,exc.omega);count=0n;optimal=[];
        if(iomega===omega) {optimal.push("include");count+=counts[row.include_child];}
        if(exc.omega===omega) {optimal.push("exclude");count+=counts[row.exclude_child];}
      }
      need(row.omega===omega&&cnt===count&&JSON.stringify(row.optimal_branches)===JSON.stringify(optimal),"branch recurrence mismatch");
    } else throw new TypeError("unknown proof node kind");
    statistics.proof_recurrence_checks++;
  }
  const root=integer(data.proof.root,0,rows.length-1,"root");
  need(masks[root]===full&&data.proof.node_count===rows.length,"root or node count mismatch");
  need(data.proof.maximum_cardinality===rows[root].omega&&decimal(data.proof.maximum_subset_count,"root count")===counts[root],"summary mismatch");
  statistics.loaded_proof_nodes=rows.length;
  const omega=rows[root].omega,total=counts[root];

  function subsetMask(vertices) {
    need(Array.isArray(vertices),"vertices must be an array");
    let m=0n;for(const v of vertices) {
      integer(v,0,n-1,"vertex");need((m&bits[v])===0n,"duplicate selected vertex");m|=bits[v];
    }
    return m;
  }
  function atRank(rank, counted=true) {
    const original=decimal(rank,"rank");need(original<total,"rank outside maximum family");
    if(counted) statistics.select_queries++;
    let q=original,id=root,selected=0n;
    while(true) {
      statistics.select_node_visits++;
      const row=rows[id];
      if(row.kind==="empty") break;
      if(row.kind==="forced") {selected|=BigInt(row.forced_mask);id=row.child;continue;}
      const include=row.optimal_branches.includes("include");
      const incCount=include?counts[row.include_child]:0n;
      if(q<incCount) {selected|=bits[row.vertex];id=row.include_child;}
      else {q-=incCount;need(row.optimal_branches.includes("exclude"),"internal select exhausted branches");id=row.exclude_child;}
    }
    need(q===0n,"internal residual rank");
    const vertices=labels(selected,bits);
    return {rank:original.toString(),vertices,coordinates:vertices.map(i=>points[i].slice()),cardinality:vertices.length};
  }
  function indexOf(vertices) {
    statistics.rank_queries++;
    let selected=subsetMask(vertices),q=0n,id=root;
    need(pop(selected)===omega,"subset cardinality is not maximum");
    while(true) {
      statistics.rank_node_visits++;
      const row=rows[id];
      need((selected&~masks[id])===0n,"subset escapes a proof branch");
      if(row.kind==="empty") {need(selected===0n,"nonempty terminal subset");break;}
      if(row.kind==="forced") {
        const forced=BigInt(row.forced_mask);
        need((selected&forced)===forced,"maximum subset omits a forced vertex");
        selected&=~forced;id=row.child;continue;
      }
      if(selected&bits[row.vertex]) {
        need(row.optimal_branches.includes("include"),"included pivot is not an optimal branch");
        selected&=~bits[row.vertex];id=row.include_child;
      } else {
        need(row.optimal_branches.includes("exclude"),"excluded pivot is not an optimal branch");
        if(row.optimal_branches.includes("include")) q+=counts[row.include_child];
        id=row.exclude_child;
      }
    }
    return q.toString();
  }
  function profile(vertices) {
    statistics.profile_queries++;
    const mask=subsetMask(vertices), ordered=labels(mask,bits);
    let minimum=null,diameter=0,unitPairs=0;
    for(let i=0;i<ordered.length;i++) for(let j=i+1;j<ordered.length;j++) {
      const d=distance[ordered[i]][ordered[j]];
      statistics.profile_pair_lookups++;
      minimum=minimum===null?d:Math.min(minimum,d);diameter=Math.max(diameter,d);
      if(d===1) unitPairs++;
    }
    const triangleIds=[];
    for(let i=0;i<triangleMasks.length;i++) {
      statistics.profile_triangle_checks++;
      if((mask&triangleMasks[i])===triangleMasks[i]) triangleIds.push(i);
    }
    return {
      vertices:ordered,cardinality:ordered.length,
      minimum_squared_distance:minimum,diameter_squared:diameter,
      within_diameter_cap:diameter<=cap,
      has_minimum_distance_one:minimum===1,
      unit_pair_count:unitPairs,unit_triangle_count:triangleIds.length,unit_triangle_ids:triangleIds
    };
  }
  return Object.freeze({
    summary() {return {
      point_count:n,squared_diameter:cap,maximum_cardinality:omega,maximum_subset_count:total.toString(),
      proof_nodes:rows.length,pair_records:pairRows.length,unit_triangles:triangleRows.length,
      family_order:data.proof.family_order,
      geometry_premise:"retained exact pair distances and complete unit-triangle ledger"
    };},
    select(rank) {return atRank(rank);},
    rank(vertices) {return indexOf(vertices);},
    membership(vertices) {
      statistics.membership_queries++;
      const mask=subsetMask(vertices),vs=labels(mask,bits);
      for(let i=0;i<vs.length;i++) for(let j=i+1;j<vs.length;j++)
        if(!(adj[vs[i]]&bits[vs[j]])) return {feasible:false,maximum:false,incompatible_pair:[vs[i],vs[j]]};
      return {feasible:true,maximum:vs.length===omega,rank:vs.length===omega?indexOf(vs):null};
    },
    profile,
    page(start=0,limit=100,include_profiles=false) {
      const begin=decimal(start,"page start");need(begin<=total,"page start beyond family");
      integer(limit,0,LATTICE_DIAMETER_LIMITS.max_page_size,"page limit");
      need(typeof include_profiles==="boolean","include_profiles must be boolean");
      statistics.page_queries++;
      const out=[],end=begin+BigInt(limit)<total?begin+BigInt(limit):total;
      for(let r=begin;r<end;r++) {
        const value=atRank(r);
        if(include_profiles) value.profile=profile(value.vertices);
        out.push(value);statistics.page_rows++;
      }
      return {start:begin.toString(),total:total.toString(),rows:out,next:end<total?end.toString():null};
    },
    unitTriangle(id) {
      integer(id,0,triangleRows.length-1,"triangle id");
      const vertices=triangleRows[id].slice();
      return {id,vertices,coordinates:vertices.map(i=>points[i].slice())};
    },
    proofNode(id) {integer(id,0,rows.length-1,"proof node id");return copy(rows[id]);},
    snapshot() {return copy(data);},
    statistics() {return copy(statistics);}
  });
}
module.exports={LATTICE_DIAMETER_LIMITS,triangularHexagon,compileLatticeDiameterFamily,openRetainedLatticeDiameterFamily};
