# Exact global vertex and edge patch planner

Issue: https://github.com/woahwhattheheck/commons/issues/14999

The planner in **global_patch_plan.py** enumerates every vertex and edge of a
uniform n by n by n Kuhn cube mesh, for n at least two. It selects a contained
patch for the appropriate accepted P4 or P5 local lift and supplies all geometry
needed to transfer that lift into the exact global cell order.

Its only local import is **kuhn.py**. It does not construct a local lift, solve a
coefficient system, run a local proof, or infer global pressure compatibility.
The existing local constructions and their credit remain in their original
modules and guides. This component establishes the patch embeddings and complete
target-star census; the global assembly and mesh-uniform norm theorem are separate.

## Produce a complete plan

Python 3.10+, standard library only, from the repository root:

~~~sh
python3 research/ridgway_freudenthal/global_patch_plan.py \
  --n=2 --degree=4 --output=global-patches-n2-p4.json

python3 research/ridgway_freudenthal/global_patch_plan.py \
  --n=3 --degree=5 --output=global-patches-n3-p5.json
~~~

Choose a new output path. The output file contains the complete plan. The CLI
prints a compact census after writing it; omitting the output option prints the
complete JSON to standard output. Invalid parameters, incomplete embeddings,
inconsistent stars, or output failures produce a nonzero exit with a concrete
error message.

Physical geometry is

    physical_position = origin + cell_size * lattice_position.

The defaults are origin (0,0,0) and cell_size 1/n, so the mesh fills the unit cube.
Both parameters use integers or exact rational strings. Floating-point API
inputs and booleans are rejected. A translated and scaled plan can be requested
with the following options, without changing the lattice census:

~~~sh
python3 research/ridgway_freudenthal/global_patch_plan.py \
  --n=3 --degree=5 --origin=-2,1/3,5/2 --cell-size=2/3 \
  --output=global-patches-affine.json
~~~

The reusable API is:

~~~python
from research.ridgway_freudenthal.global_patch_plan import construct, map_beta

plan = construct(3, degree=5)
patch = plan["edge_patches"][0]

global_cell, global_beta = map_beta(patch, local_cell=0, beta=(1, 2, 1, 0))
~~~

The degree chooses the local constructor arguments. The mesh and patch geometry
are shared by P4 and P5.

## Global and local ordering

Global lattice vertices are ordered lexicographically. Global cells follow
lexicographic cube origins, with the six positively ordered tetrahedra from
kuhn_tets() inside each cube. Equivalently, cube (i,j,k) starts at global cell
6*((i*n+j)*n+k). The mesh object stores the exact ordered vertex IDs of every cell.

Every mesh edge is obtained from a pair of vertices of an actual tetrahedron.
Its endpoints are ordered componentwise low to high; the displacement is one of
the seven nonzero vectors in {0,1} cubed. Global edge IDs follow the sorted pairs
of endpoint vertex IDs.

The reference_patches object contains one geometry template per used box shape.
Its lattice vertices are lexicographic, and its cells use the same cube-major
Kuhn ordering. Each target record provides:

| Field | Meaning |
| --- | --- |
| target_global_vertex_ids | Global target vertex, or canonical low/high edge endpoints |
| reference_patch | Key of the complete reference box geometry |
| patch_vertex_to_global_vertex | Map from the template vertex list to global mesh vertex IDs |
| local_cell_to_global_cell | Map from every transported local cell to its global cell ID |
| local_vertex_to_global_vertex_position | For each local cell, the global cell position of each of its four transported local vertices |
| physical_vertex_to_reference_vertex | Identity or swap of positions 1 and 2 used by the accepted transport |
| incident_local_cells | Complete reference target star, in local cell order |
| incident_global_cells | The same star mapped to global cells, retaining local order |
| global_incident_cells | Independently enumerated complete global star, sorted by global cell ID |
| target_vertex_positions_in_incident_local_cells | Target positions in each transported local star cell |
| target_vertex_positions_in_incident_global_cells | Corresponding positions in the ordered global cell |
| reference_target_to_canonical_target | Target endpoint permutation, including reversal under inversion |

Every local patch cell is matched to a global tetrahedron by its unordered
vertices. Its indexwise vertex permutation is then recorded explicitly.
The planner checks that all patch vertices and cells lie inside the mesh, that
no two local cells map to the same global cell, and that the reference target
star maps onto every actual global incident cell with no additions or omissions.

### Transfer a Bernstein label

Local operators already return positively ordered transported cells. Their
barycentric multi-indices must be transferred using that ordering, not by
repeating the transport's orientation swap.

For a local cell c, let position[i] be its
local_vertex_to_global_vertex_position row. The global multi-index is defined by

    global_beta[position[i]] = local_beta[i].

The map_beta helper performs this permutation and returns the global cell ID.
It works for any nonnegative integer multi-index, including pressure and
velocity labels. In particular, it does not assume that the local vertex order
equals the global kuhn_tets() order.

For an inverted edge, the second reference endpoint may be the physical
canonical low endpoint. The local lift's source-column order is inherited.
The reference_target_to_canonical_target field records this reversal without
reordering the source columns or changing their interpretation.

## Executable local-lift descriptors

Each patch includes:

- constructor: the existing module, function construct, and complete keyword
  arguments, including the selected degree and exact physical coordinates;
- constructor_argv: an executable Python CLI argument vector from the repository
  root;
- transport: the existing module, function transport, and complete transform
  keyword arguments for reuse of an accepted reference operator.

The planner does not execute any descriptor. An assembler can use an existing
reference operator through the transport descriptor:

~~~python
from importlib import import_module

description = patch["transport"]
transport = getattr(import_module(description["module"]), description["function"])
physical_operator = transport(accepted_reference, **description["kwargs"])
~~~

Select the accepted reference for the record's class and degree. Boundary
vertices have five reference classes; boundary crease edges have same and mixed
reference classes. Other orientations of the same local family share their
reference. Reuse those references rather than rebuilding one for each target.

The zero_source_image field records the already-established zero source images:
mixed-side boundary crease edges, mixed-side boundary crease vertices, and
mixed-side boundary corners. These targets are still enumerated and mapped in
full. Their zero source image does not justify dropping them from the census.

## Exact edge patch choices

Write an edge as low to high. The permutation P sends each reference coordinate
axis to the recorded global coordinate axis. Its cyclic choices are

    x: (0,1,2), y: (1,2,0), z: (2,0,1).

The table gives lattice-coordinate rules. Physical constructor arguments apply
the mesh origin and cell_size afterward.

| Class | Accepted module | Reference target and contained placement |
| --- | --- | --- |
| Body diagonal | body_diagonal_transport | Reference (0,0,0) to (1,1,1), shape (2,1,1). Central cube is low. Choose neighbor +x when low.x < n-1, otherwise -x. Constructor origin is the central cube lower corner. |
| Interior face diagonal | face_diagonal_transport | Fixed normal coordinate r is between 1 and n-1. Reference (1,0,0) to (1,1,1), shape (2,1,1), cyclic normal-axis permutation, origin low minus the normal unit vector. |
| Boundary face diagonal | boundary_face_diagonal_lift | Reference (0,0,0) to (0,1,1), shape (2,1,1). Sign is positive on a lower face and negative on an upper face. Origin is low for positive sign and high for negative sign. |
| Interior axial | axial_edge_lift | Reference (0,1,1) to (1,1,1), shape (1,2,2), cyclic tangent-axis permutation. Origin is low minus the two non-tangent unit vectors. |
| Boundary axial, inside one face | boundary_axial_edge_lift | Reference (1,0,0) to (1,1,0), shape (2,1,1). P=(remaining,tangent,normal). With sign from the normal face and first=low or high according to that sign, origin=first-sign*P(1,0,0). |
| Boundary crease axial | boundary_crease_edge_lift | Sort the two normal axes. P=(firstNormal,tangent,secondNormal); sign comes from the first normal side. Reference (0,0,z) to (0,1,z), with z=0 for equal sides and z=1 otherwise. Origin=first-sign*P(0,0,z). |

For the negative body-neighbor transport, the reference zero maps to low+(1,1,1)
before physical scaling, exactly as body_diagonal_transport specifies. The
constructor origin remains low; these are distinct quantities.

A full inversion preserves the Kuhn triangulation. For all families, an odd
coordinate permutation or a negative global sign can change orientation. The
planner uses determinant sign*det(P), swapping local vertices 1 and 2 exactly
when it is negative. This matches the existing transport modules.

The two-cube extent is why n must be at least two. Every other placement starts
at a boundary or straddles an interior lattice coordinate; each reference extent
therefore lies completely inside the mesh.

## Exact vertex patch choices

An interior vertex uses shape (2,2,2), center (1,1,1), and

    lattice_position = vertex + reference_position - center.

Boundary vertices use the geometry and orientation enumeration from
boundary_vertex_lift.py:

| Reference class | Shape | Center | Reference boundary sides |
| --- | --- | --- | --- |
| face | (1,2,2) | (0,1,1) | x lower |
| crease_same | (1,1,2) | (0,0,1) | x lower, y lower |
| crease_mixed | (1,1,2) | (0,1,1) | x lower, y upper |
| corner_same | (2,1,1) | (0,0,0) | x lower, y lower, z lower |
| corner_mixed | (2,1,1) | (0,0,1) | x lower, y lower, z upper |

The same cyclic permutations and full inversion generate the existing 26
orientation names. A record selects the name from the target's actual boundary
planes and uses

    lattice_position = vertex + sign*P(reference_position-center).

The planner mirrors only these small geometric definitions, avoiding an import
of the local-lift construction graph. The accepted
[boundary-vertex guide](BOUNDARY_VERTEX_LIFT.md) retains the source-image and
coefficient arguments; the [interior-vertex guide](INTERIOR_VERTEX_LIFT.md)
retains the interior construction.

## Complete census

The mesh has 6*n^3 tetrahedra, (n+1)^3 vertices, and
7*n^3+9*n^2+3*n edges.

| Vertex class | General count | n=2 | n=3 |
| --- | ---: | ---: | ---: |
| Interior | (n-1)^3 | 1 | 8 |
| Face | 6*(n-1)^2 | 6 | 24 |
| Same-side crease | 6*(n-1) | 6 | 12 |
| Mixed-side crease | 6*(n-1) | 6 | 12 |
| Same-side corner | 2 | 2 | 2 |
| Mixed-side corner | 6 | 6 | 6 |
| Total | (n+1)^3 | 27 | 64 |

| Edge class | General count | n=2 | n=3 |
| --- | ---: | ---: | ---: |
| Body diagonal | n^3 | 8 | 27 |
| Interior face diagonal | 3*n^2*(n-1) | 12 | 54 |
| Boundary face diagonal | 6*n^2 | 24 | 54 |
| Interior axial | 3*n*(n-1)^2 | 6 | 36 |
| Boundary axial inside one face | 12*n*(n-1) | 24 | 72 |
| Same-side boundary crease | 6*n | 12 | 18 |
| Mixed-side boundary crease | 6*n | 12 | 18 |
| Total | 7*n^3+9*n^2+3*n | 98 | 279 |

The largest patch has 48 cells. Every boundary-vertex orientation occurs already
at n=2. Both negative and positive transports are needed there, so the complete
small mesh is a useful executable product for an assembler.

## Existing constructions retained

The edge descriptors use the accepted
[body-diagonal](BODY_DIAGONAL_TRANSPORT.md),
[interior face-diagonal](FACE_DIAGONAL_TRANSPORT.md),
[boundary face-diagonal](BOUNDARY_FACE_DIAGONAL_LIFT.md),
[interior axial](AXIAL_EDGE_LIFT.md),
[boundary axial](BOUNDARY_AXIAL_EDGE_LIFT.md), and
[boundary crease](BOUNDARY_CREASE_EDGE_LIFT.md) lifts. Their operator coefficients,
compatibility conditions, and local bounds are not replaced by this planner.

A full global construction must still consume a compatible pressure,
apply its assembled corrections in the required order, preserve shared
Bernstein coefficients, and establish the global bound. A successful plan
establishes that every selected local patch and target star has an exact,
contained address in the mesh.
