"""3D view of a LAMMPS DATA FILE for the AtomForge page: data file -> PDB text -> 3Dmol.js (bundled, works offline).

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


def to_pdb(path: str, ids: list = None) -> str:
    """PDB text of the data file; if `ids` is a list, the LAMMPS atom IDs are appended to it in PDB order."""
    m = build_model(parse_file(path), "full")
    if ids is not None:
        ids.extend(int(a) for a in m.ids)
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


COLOURS = {"H": "#eef2f8", "C": "#8d99ae", "N": "#5b8cff", "O": "#ff5a5a", "Na": "#7fdcff", "Mg": "#7dffb3",
           "Al": "#d4a5a5", "Si": "#f2c57c", "S": "#ffe14d", "Cl": "#5cff8f", "K": "#d58cff", "Ca": "#a6ec6f",
           "Fe": "#e0773d", "X": "#ff3df5"}       # readable on a dark background; the legend shows the same colours


def html(path: str, height: int = 460, spin: bool = False, bg: str = "#0a1222", box: str = "#5aa9ff",
         border: str = "#1f3358", toolbar: bool = True, panel: str = "#111a2b", text: str = "#e6edf7",
         muted: str = "#8b9bb4", accent: str = "#38bdf8") -> str:
    """A self-contained HTML snippet (3Dmol.js inlined) showing the structure with its periodic cell, with an
    optional toolbar: fit, zoom, spin, periodic box, hide hydrogens, representation, hover info, PNG export."""
    ids = []
    pdb_text = to_pdb(path, ids)
    present = sorted({ln[76:78].strip() for ln in pdb_text.splitlines() if ln.startswith("HETATM")},
                     key=lambda e: list(COLOURS).index(e) if e in COLOURS else 99)
    colours = {e: COLOURS.get(e, COLOURS["X"]) for e in present}
    legend = "".join(f"<span class='lg'><i style='background:{c}'></i>{e}</span>" for e, c in colours.items())
    bar = f"""<div class="tb">
  <button onclick="fit()" title="Fit the structure to the view">⤢ Fit</button>
  <button onclick="v.zoom(1.25, 150)" title="Zoom in">＋</button>
  <button onclick="v.zoom(0.8, 150)" title="Zoom out">－</button>
  <span class="sep"></span>
  <button id="b_spin" onclick="toggleSpin()" title="Rotate continuously">⟳ Spin</button>
  <button id="b_box" class="on" onclick="toggleBox()" title="Show or hide the periodic box">▢ Box</button>
  <button id="b_h" onclick="toggleH()" title="Show or hide hydrogen atoms">H</button>
  <select id="rep" onchange="applyStyle()" title="Representation">
    <option value="bs">Ball and stick</option><option value="st">Sticks</option>
    <option value="sp">Space filling</option><option value="ln">Lines</option></select>
  <span class="grow"></span>
  <button onclick="png()" title="Save the current view as a PNG image">⬇ PNG</button>
</div>""" if toolbar else ""
    return f"""<style>
body {{margin:0; font-family:-apple-system,"Inter","Segoe UI",Roboto,sans-serif;}}
.wrap {{position:relative; width:100%; height:{height}px; border-radius:12px; overflow:hidden; border:1px solid {border}; background:{bg};}}
#v {{position:absolute; inset:0;}}
.tb {{position:absolute; z-index:5; top:10px; left:10px; right:10px; display:flex; gap:6px; align-items:center; flex-wrap:wrap;}}
.tb button, .tb select {{background:{panel}e6; color:{text}; border:1px solid {border}; border-radius:8px; padding:5px 10px;
  font-size:12.5px; cursor:pointer; backdrop-filter:blur(4px);}}
.tb button:hover, .tb select:hover {{border-color:{accent};}}
.tb button.on {{border-color:{accent}; color:{accent};}}
.tb .sep {{width:1px; height:20px; background:{border}; margin:0 2px;}} .tb .grow {{flex:1;}}
.legend {{position:absolute; z-index:5; left:10px; bottom:10px; display:flex; gap:10px; flex-wrap:wrap; padding:5px 10px;
  background:{panel}cc; border:1px solid {border}; border-radius:8px; font-size:12px; color:{muted};}}
.lg i {{display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; vertical-align:-1px;}}
.hover {{position:absolute; z-index:6; right:10px; bottom:10px; padding:5px 10px; font-size:12px; color:{text};
  background:{panel}e6; border:1px solid {border}; border-radius:8px; display:none;}}
</style>
<div class="wrap">{bar}<div id="v"></div><div class="legend">{legend}</div><div class="hover" id="hv"></div></div>
<script>{open(JS).read()}</script>
<script>
const v = $3Dmol.createViewer("v", {{backgroundColor: "{bg}"}});
const m = v.addModel({json.dumps(pdb_text)}, "pdb");
const C = {json.dumps(colours)}, IDS = {json.dumps(ids)}, IONS = {json.dumps(list(IONS))};
let hideH = false, boxOn = true, spinning = {str(spin).lower()};
function applyStyle() {{
  const rep = (document.getElementById("rep") || {{value: "bs"}}).value;
  v.setStyle({{}}, {{}});
  for (const e in C) {{
    let s;
    if (rep === "bs") s = {{stick: {{radius: 0.14, color: C[e]}}, sphere: {{scale: 0.22, color: C[e]}}}};
    else if (rep === "st") s = {{stick: {{radius: 0.17, color: C[e]}}}};
    else if (rep === "sp") s = {{sphere: {{scale: 0.85, color: C[e]}}}};
    else s = {{line: {{color: C[e]}}}};
    if (hideH && e === "H") s = {{}};
    v.setStyle({{elem: e}}, s);
    if (IONS.includes(e)) v.setStyle({{elem: e, bonds: 0}}, {{sphere: {{scale: rep === "sp" ? 0.85 : 0.45, color: C[e]}}}});
  }}
  v.render();
}}
function fit() {{ v.zoomTo(); v.render(); }}
function toggleSpin() {{ spinning = !spinning; v.spin(spinning ? "y" : false, 0.5);
  const b = document.getElementById("b_spin"); if (b) b.classList.toggle("on", spinning); }}
function toggleBox() {{ boxOn = !boxOn;
  try {{ boxOn ? v.addUnitCell(m, {{box: {{color: "{box}"}}}}) : v.removeUnitCell(m); }} catch (e) {{}}
  document.getElementById("b_box").classList.toggle("on", boxOn); v.render(); }}
function toggleH() {{ hideH = !hideH; document.getElementById("b_h").classList.toggle("on", hideH);
  document.getElementById("b_h").textContent = hideH ? "H hidden" : "H"; applyStyle(); }}
function png() {{ const a = document.createElement("a"); a.href = v.pngURI(); a.download = "structure.png";
  document.body.appendChild(a); a.click(); a.remove(); }}
const hv = document.getElementById("hv");
v.setHoverable({{}}, true, function (atom) {{
  hv.style.display = "block"; hv.textContent = atom.elem + " · atom ID " + IDS[atom.index]; }},   // view coordinates are shifted to the box origin
  function () {{ hv.style.display = "none"; }});
v.setHoverDuration(80);
applyStyle();
v.zoomTo();                       // fit the atoms, not the vacuum above a slab
try {{ v.addUnitCell(m, {{box: {{color: "{box}"}}}}); }} catch (e) {{}}
v.render(); if (spinning) {{ v.spin("y", 0.5); const b = document.getElementById("b_spin"); if (b) b.classList.add("on"); }}
</script>"""
