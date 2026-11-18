"""Build a 2D Fluent ASCII quadrilateral mesh for a slip-wall duct."""
from pathlib import Path


def duct(path, nx=32, ny=8):
    def node(i, j):
        return j * (nx + 1) + i + 1

    def cell(i, j):
        return j * nx + i + 1

    zones = []
    interior = [(node(i,j+1),node(i,j),cell(i-1,j),cell(i,j))
                for j in range(ny) for i in range(1,nx)]
    interior += [(node(i,j),node(i+1,j),cell(i,j-1),cell(i,j))
                 for j in range(1,ny) for i in range(nx)]
    zones.append((2, 2, "interior", "internal", interior))
    zones.append((3, 10, "velocity-inlet", "inlet",
                  [(node(0,j),node(0,j+1),cell(0,j),0) for j in range(ny)]))
    zones.append((4, 5, "pressure-outlet", "outlet",
                  [(node(nx,j+1),node(nx,j),cell(nx-1,j),0) for j in range(ny)]))
    edges = [(node(i+1,0),node(i,0),cell(i,0),0) for i in range(nx)]
    edges += [(node(i,ny),node(i+1,ny),cell(i,ny-1),0) for i in range(nx)]
    zones.append((5, 7, "symmetry", "slip", edges))
    nn = (nx+1)*(ny+1)
    nf = sum(len(z[-1]) for z in zones)
    lines = ["(2 2)", f"(10 (0 1 {nn:x} 0 2))", f"(12 (0 1 {nx*ny:x} 0))",
             f"(13 (0 1 {nf:x} 0))", f"(10 (1 1 {nn:x} 1 2)("]
    lines += [f"{i/nx:.12g} {0.1*j/ny:.12g}" for j in range(ny+1) for i in range(nx+1)]
    lines += ["))", f"(12 (1 1 {nx*ny:x} 1 3))", "(45 (1 fluid duct)())"]
    first = 1
    for zone, kind, name, label, faces in zones:
        last = first + len(faces) - 1
        lines += [f"(13 ({zone:x} {first:x} {last:x} {kind:x} 2)("]
        lines += [" ".join(f"{v:x}" for v in (face[1],face[0],face[2],face[3])) for face in faces]
        lines += ["))", f"(45 ({zone} {name} {label})())"]
        first = last + 1
    Path(path).write_text("\n".join(lines)+"\n", encoding="ascii")
