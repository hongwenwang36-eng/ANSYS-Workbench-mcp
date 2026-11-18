"""Generate an original conformal fluid/solid channel mesh, all dimensions in m."""
from pathlib import Path


def generate(path, nx=40, fluid_rows=8, solid_rows=4):
    ny = fluid_rows + solid_rows
    node = lambda i,j: j*(nx+1)+i+1
    cell = lambda i,j: j*nx+i+1
    zones = [
        (9,3,"wall","interface",[(node(i+1,fluid_rows),node(i,fluid_rows),cell(i,fluid_rows-1),cell(i,fluid_rows)) for i in range(nx)]),
        (2,2,"interior","internal",[(node(i,j),node(i,j+1),cell(i-1,j),cell(i,j)) for j in range(ny) for i in range(1,nx)]
         + [(node(i+1,j),node(i,j),cell(i,j-1),cell(i,j)) for j in range(1,ny) if j != fluid_rows for i in range(nx)]),
        (3,10,"velocity-inlet","inlet",[(node(0,j+1),node(0,j),cell(0,j),0) for j in range(fluid_rows)]),
        (4,5,"pressure-outlet","outlet",[(node(nx,j),node(nx,j+1),cell(nx-1,j),0) for j in range(fluid_rows)]),
        (5,3,"wall","bottom",[(node(i,0),node(i+1,0),cell(i,0),0) for i in range(nx)]),
        (6,3,"wall","heated",[(node(i+1,ny),node(i,ny),cell(i,ny-1),0) for i in range(nx)]),
        (7,3,"wall","solid_ends",[(node(0,j+1),node(0,j),cell(0,j),0) for j in range(fluid_rows,ny)]
          + [(node(nx,j),node(nx,j+1),cell(nx-1,j),0) for j in range(fluid_rows,ny)])
    ]
    nn=(nx+1)*(ny+1)
    nf=sum(len(z[-1]) for z in zones)
    lines=["(2 2)",f"(10 (0 1 {nn:x} 0 2))",f"(12 (0 1 {nx*ny:x} 0))",f"(13 (0 1 {nf:x} 0))",f"(10 (1 1 {nn:x} 1 2)("]
    lines += [f"{0.1*i/nx:.12g} {0.002*j/fluid_rows:.12g}" for j in range(ny+1) for i in range(nx+1)]
    lines += ["))",f"(12 (1 1 {nx*fluid_rows:x} 1 3))",f"(12 (8 {nx*fluid_rows+1:x} {nx*ny:x} 1 3))","(45 (1 fluid channel)())","(45 (8 solid block)())"]
    first=1
    for zone,kind,name,label,faces in zones:
        last=first+len(faces)-1
        lines += [f"(13 ({zone:x} {first:x} {last:x} {kind:x} 2)("]
        lines += [" ".join(f"{v:x}" for v in f) for f in faces]
        lines += ["))", f"(45 ({zone} {name} {label})())"]
        first=last+1
    Path(path).write_text("\n".join(lines)+"\n",encoding="ascii")
