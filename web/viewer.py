"""3D view of a LAMMPS DATA FILE for the demo page: data file -> PDB text -> 3Dmol.js (bundled, works offline).

Elements come from the Masses section (nearest standard atomic mass); bonds from the Bonds section, except
bonds longer than 3 Å, which cross a periodic boundary and would be drawn across the box.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from validator.model import build_model  # noqa: E402
from validator.parser import parse_file  # noqa: E402

MASSES = {"H": 1.008, "C": 12.011, "N": 14.007, "O": 15.999, "Na": 22.990, "Mg": 24.305, "Al": 26.982,
          "Si": 28.086, "S": 32.06, "Cl": 35.45, "K": 39.098, "Ca": 40.078, "Fe": 55.845}
IONS = ("Na", "K", "Ca", "Mg")
JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "3Dmol-min.js")


def element(mass: float) -> str:
    e, m = min(MASSES.items(), key=lambda kv: abs(kv[1] - mass))
    return e if abs(m - mass) < 0.6 else "X"


def to_pdb(path: str) -> str:
    m = build_model(parse_file(path), "full")
    el = {t: element(m.masses.get(t, 0.0)) for t in range(1, m.n_atom_types + 1)}
    xyz = m.xyz - (m.cell.origin if m.cell is not None else 0.0)
    lines = []
    if m.cell is not None:
        a, b, c = (m.cell.H[:, i] for i in range(3))
        ang = lambda u, v: np.degrees(np.arccos(np.dot(u, v) / np.linalg.norm(u) / np.linalg.norm(v)))  # noqa: E731
        lines.append(f"CRYST1{np.linalg.norm(a):9.3f}{np.linalg.norm(b):9.3f}{np.linalg.norm(c):9.3f}"
                     f"{ang(b, c):7.2f}{ang(a, c):7.2f}{ang(a, b):7.2f} P 1           1")
    serial = {}
    for i, (aid, t) in enumerate(zip(m.ids, m.types)):
        s = i + 1
        serial[int(aid)] = s
        e = el[int(t)]
        x, y, z = xyz[i]
        lines.append(f"HETATM{s % 100000:5d} {e:<4s} MOL A   1    {x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00          {e:>2s}")
    bonds = {}
    top = m.topology.get("Bonds")
    if top is not None:
        for a1, a2 in top.atoms:
            i, j = serial.get(int(a1)), serial.get(int(a2))
            if i and j and np.linalg.norm(xyz[i - 1] - xyz[j - 1]) <= 3.0:
                bonds.setdefault(i, []).append(j)
                bonds.setdefault(j, []).append(i)
    for i in sorted(bonds):
        nb = bonds[i]
        for k in range(0, len(nb), 4):
            lines.append("CONECT" + f"{i:5d}" + "".join(f"{j:5d}" for j in nb[k:k + 4]))
    lines.append("END")
    return "\n".join(lines)


def html(path: str, height: int = 460, spin: bool = False, bg: str = "#0a1222", box: str = "#5aa9ff",
         border: str = "#1f3358") -> str:
    """A self-contained HTML snippet (3Dmol.js inlined) showing the structure with its periodic cell."""
    pdb = json.dumps(to_pdb(path))
    ions = json.dumps(list(IONS))
    return f"""<div id="v" style="width:100%;height:{height}px;position:relative;border-radius:10px;overflow:hidden;border:1px solid {border}"></div>
<script>{open(JS).read()}</script>
<script>
const v = $3Dmol.createViewer("v", {{backgroundColor: "{bg}"}});
v.addModel({pdb}, "pdb");
v.setStyle({{}}, {{stick: {{radius: 0.14}}, sphere: {{scale: 0.22}}}});
v.setStyle({{elem: {ions}}}, {{sphere: {{scale: 0.45}}}});
const ionColour = {{Na: "#9fe3ff", K: "#ffb3e6", Ca: "#c6f7a1", Mg: "#a8ffcf"}};   // readable on a dark background
for (const e in ionColour) v.setStyle({{elem: e, bonds: 0}}, {{sphere: {{scale: 0.45, color: ionColour[e]}}}});
v.zoomTo();                       // fit the atoms, not the vacuum above a slab
try {{ v.addUnitCell(v.getModel(), {{box: {{color: "{box}"}}}}); }} catch (e) {{}}
v.render(); {"v.spin('y', 0.4);" if spin else ""}
</script>"""
