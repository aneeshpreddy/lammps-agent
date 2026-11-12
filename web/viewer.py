"""3D views of LAMMPS DATA FILEs for the AtomForge page, with 3Dmol.js (bundled and inlined, so it works offline).

A data file becomes a *scene*: PDB text (elements from the Masses section, nearest standard atomic mass;
bonds from the Bonds section, except bonds longer than 3 Å, which cross a periodic boundary and would be
drawn across the box), the LAMMPS atom IDs, the colours of the elements present and the 12 edges of the
periodic cell. html() draws a scene with the full toolbar (results and validation pages); showcase() draws
one without controls, on a transparent background (landing page). Streamlit serves .js as text/plain with
nosniff, so the library is inlined rather than served as a static file.
"""
from __future__ import annotations

import functools
import itertools
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
COLOURS = {"H": "#f4f6fa", "C": "#909aa8", "N": "#4a6cf7", "O": "#f2453d", "Na": "#ab5cf2", "Mg": "#8aff00",
           "Al": "#bfa6a6", "Si": "#f0c8a0", "S": "#ffff30", "Cl": "#1ff01f", "K": "#8f40d4", "Ca": "#3ddc4f",
           "Fe": "#e06633", "X": "#ff1493"}      # Jmol/CPK colours (the convention chemists read), H and C lifted for a dark background
JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "3Dmol-min.js")


def element(mass: float) -> str:
    e, m = min(MASSES.items(), key=lambda kv: abs(kv[1] - mass))
    return e if abs(m - mass) < 0.6 else "X"


def scene(path: str) -> dict:
    """{"pdb", "ids", "colours", "edges", "atoms", "elements"} for a data file (coordinates shifted to the box origin)."""
    m = build_model(parse_file(path), "full")
    el = {t: element(m.masses.get(t, 0.0)) for t in range(1, m.n_atom_types + 1)}
    xyz = m.xyz - (m.cell.origin if m.cell is not None else 0.0)
    lines, edges = [], []
    if m.cell is not None:
        H = np.asarray(m.cell.H, dtype=float)
        a, b, c = (H[:, i] for i in range(3))
        ang = lambda u, v: np.degrees(np.arccos(np.dot(u, v) / np.linalg.norm(u) / np.linalg.norm(v)))  # noqa: E731
        lines.append(f"CRYST1{np.linalg.norm(a):9.3f}{np.linalg.norm(b):9.3f}{np.linalg.norm(c):9.3f}"
                     f"{ang(b, c):7.2f}{ang(a, c):7.2f}{ang(a, b):7.2f} P 1           1")
        corners = {k: sum((v for v, on in zip((a, b, c), k) if on), np.zeros(3)) for k in itertools.product((0, 1), repeat=3)}
        for k in corners:
            for i in range(3):
                if k[i] == 0:
                    k2 = tuple(1 if j == i else k[j] for j in range(3))
                    edges.append([[round(float(x), 3) for x in corners[k]], [round(float(x), 3) for x in corners[k2]]])
    serial, names = {}, []
    for i, (aid, t) in enumerate(zip(m.ids, m.types)):
        s = i + 1
        serial[int(aid)] = s
        e = el[int(t)]
        names.append(e)
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
    present = sorted(set(names), key=lambda e: list(COLOURS).index(e) if e in COLOURS else 99)
    q = [round(float(x), 6) for x in m.q] if getattr(m, "q", None) is not None else []
    return {"pdb": "\n".join(lines), "ids": [int(a) for a in m.ids], "colours": {e: COLOURS.get(e, COLOURS["X"]) for e in present},
            "edges": edges, "atoms": len(names), "elements": {e: names.count(e) for e in present},
            "q": q, "type": [int(t) for t in m.types], "tnames": {str(k): v for k, v in (m.type_names or {}).items()}}


@functools.lru_cache(maxsize=1)
def _lib() -> str:
    return open(JS).read()


# Shared JavaScript: styles, periodic box as cylinders (visible at any zoom), initial camera.
_CORE = """
const IONS = %(ions)s;
function styleFor(rep, e, c) {
  if (rep === "st") return {stick: {radius: 0.16, color: c}};
  if (rep === "sp") return {sphere: {scale: 0.9, color: c}};
  if (rep === "ln") return {line: {color: c, linewidth: 1.5}};
  if (rep === "at") return {sphere: {scale: 0.3, color: c}};
  if (rep === "rich") return {stick: {radius: 0.26, color: c}, sphere: {scale: 0.34, color: c}};
  return {stick: {radius: 0.13, color: c}, sphere: {scale: 0.24, color: c}};
}
function applyStyle(v, S, rep, hideH) {
  v.setStyle({}, {});
  for (const e in S.colours) {
    let s = styleFor(rep, e, S.colours[e]);
    if (hideH && e === "H") s = {};
    v.setStyle({elem: e}, s);
    if (IONS.includes(e)) v.setStyle({elem: e, bonds: 0}, {sphere: {scale: rep === "sp" ? 0.9 : rep === "rich" ? 0.55 : 0.42, color: S.colours[e]}});
  }
}
function fmtQ(q) {                              // charge as in the file, with a real minus sign
  if (q === undefined || q === null) return "";
  const t = Math.abs(q).toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  return (q > 0 ? "+" : q < 0 ? "\u2212" : "") + t + " e";
}
function hoverHTML(S, i, elem) {                  // element, force-field type, LAMMPS atom ID and charge of atom i
  const t = S.type ? S.type[i] : null, name = t !== null && S.tnames ? S.tnames[String(t)] : null;
  let top = "<b>" + elem + "</b>" + (t !== null && t !== undefined ? " · type " + (name ? name + " (" + t + ")" : t) : "");
  let bot = "atom ID " + S.ids[i] + (S.q && S.q.length ? " · charge <b>" + fmtQ(S.q[i]) + "</b>" : "");
  return top + "<br>" + bot;
}
function boxShapes(v, S, colour) {
  if (!S.edges.length) return [];
  const span = Math.max(...S.edges.flat().flat()) - Math.min(...S.edges.flat().flat());
  const r = Math.max(0.035, span * 0.0016);
  return S.edges.map(([p, q]) => v.addCylinder({start: {x: p[0], y: p[1], z: p[2]}, end: {x: q[0], y: q[1], z: q[2]},
    radius: r, color: colour, fromCap: 1, toCap: 1, opacity: 0.9}));
}
function frame(v, tilt, zf) {
  v.zoomTo({});                                 // the atoms only: not the box, not the vacuum above a slab
  if (tilt) { v.rotate(-18, {x: 1, y: 0, z: 0}); v.rotate(24, {x: 0, y: 1, z: 0}); v.zoomTo({}); }
  v.zoom(zf || 1.0);
  v.setSlab(-1000, 1000);                       // never clip a long chain while rotating
}
"""


def html(path: str, height: int = 460, bg: str = "#0a1222", box: str = "#5aa9ff", border: str = "#1f3358",
         toolbar: bool = True, panel: str = "#111a2b", text: str = "#e6edf7", muted: str = "#8b9bb4",
         accent: str = "#38bdf8", spin: bool = False) -> str:
    """The interactive viewer: toolbar (reset, fit, zoom, view along x/y/z, spin, box, labels, hydrogens,
    representation, PNG), element legend, orientation axes and hover (element and LAMMPS atom ID)."""
    S = scene(path)
    legend = "".join(f"<span class='lg'><i style='background:{c}'></i>{e}</span>" for e, c in S["colours"].items())
    label_note = ("element labels on every non-hydrogen atom" if S["atoms"] <= 600 else
                  "element labels on the ions (a structure this large has too many atoms to label legibly)")
    bar = f"""<div class="tb">
  <button onclick="resetView()" title="Back to the original orientation and zoom">↺ Reset</button>
  <button onclick="fit()" title="Fit the structure to the view, keeping the orientation">⤢ Fit</button>
  <button onclick="v.zoom(1.25, 150)" title="Zoom in">＋</button>
  <button onclick="v.zoom(0.8, 150)" title="Zoom out">－</button>
  <span class="sep"></span>
  <button onclick="along('x')" title="Look along the x axis">x</button>
  <button onclick="along('y')" title="Look along the y axis">y</button>
  <button onclick="along('z')" title="Look along the z axis">z</button>
  <span class="sep"></span>
  <button id="b_spin" onclick="toggleSpin()" title="Rotate continuously">⟳ Rotate</button>
  <button id="b_box" class="on" onclick="toggleBox()" title="Show or hide the periodic box">▢ Box</button>
  <button id="b_lab" onclick="toggleLabels()" title="Show {label_note}">Aa Labels</button>
  <button id="b_h" onclick="toggleH()" title="Show or hide hydrogen atoms">H</button>
  <select id="rep" onchange="restyle()" title="Representation">
    <option value="bs">Ball and stick</option><option value="st">Sticks</option>
    <option value="sp">Space filling</option><option value="ln">Lines</option><option value="at">Atoms only (no bonds)</option></select>
  <span class="grow"></span>
  <button onclick="png()" title="Save the current view as a PNG image">⬇ PNG</button>
</div>""" if toolbar else ""
    return f"""<style>
body {{margin:0; font-family:"Inter",-apple-system,"Segoe UI",Roboto,sans-serif;}}
.wrap {{position:relative; width:100%; height:{height}px; border-radius:14px; overflow:hidden; border:1px solid {border}; background:{bg};}}
#v {{position:absolute; inset:0;}}
.tb {{position:absolute; z-index:5; top:10px; left:10px; right:10px; display:flex; gap:5px; align-items:center; flex-wrap:wrap;}}
.tb button, .tb select {{background:{panel}e6; color:{text}; border:1px solid {border}; border-radius:8px; padding:5px 9px;
  font-size:12px; cursor:pointer; backdrop-filter:blur(6px); font-family:inherit;}}
.tb button:hover, .tb select:hover {{border-color:{accent};}}
.tb button.on {{border-color:{accent}; color:{accent};}}
.tb .sep {{width:1px; height:20px; background:{border}; margin:0 2px;}} .tb .grow {{flex:1;}}
.legend {{position:absolute; z-index:5; left:10px; bottom:10px; display:flex; gap:10px; flex-wrap:wrap; padding:5px 10px;
  background:{panel}cc; border:1px solid {border}; border-radius:8px; font-size:12px; color:{muted};}}
.lg i {{display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; vertical-align:-1px;}}
.axes {{position:absolute; z-index:5; right:12px; bottom:12px; width:74px; height:74px; border-radius:50%;
  background:{panel}aa; border:1px solid {border};}}
.hover {{position:absolute; z-index:6; right:96px; bottom:12px; padding:6px 11px; font-size:12px; line-height:1.5; color:{text};
  background:{panel}f0; border:1px solid {accent}88; border-radius:8px; display:none; font-variant-numeric:tabular-nums;}}
</style>
<div class="wrap">{bar}<div id="v"></div><div class="legend">{legend}</div>
<svg class="axes" viewBox="-37 -37 74 74"><g id="ax"></g></svg><div class="hover" id="hv"></div></div>
<script>{_lib()}</script>
<script>
{_CORE % {"ions": json.dumps(list(IONS))}}
const S = {json.dumps(S)};
const v = $3Dmol.createViewer("v", {{backgroundColor: "{bg}", antialias: true}});
const m = v.addModel(S.pdb, "pdb", {{keepH: true}});
let hideH = false, boxOn = true, spinning = {str(spin).lower()}, labelsOn = false, shapes = [];
const rep = () => (document.getElementById("rep") || {{value: "bs"}}).value;
function restyle() {{ applyStyle(v, S, rep(), hideH); v.render(); }}
function fit() {{ v.zoomTo({{}}); v.setSlab(-1000, 1000); v.render(); }}
function resetView() {{ v.setView(homeView); v.render(); }}
function along(ax) {{
  v.setView(topView); if (ax === "x") v.rotate(90, {{x: 0, y: 1, z: 0}}); if (ax === "y") v.rotate(-90, {{x: 1, y: 0, z: 0}});
  fit(); }}
function toggleSpin() {{ spinning = !spinning; v.spin(spinning ? "y" : false, 0.45);
  const b = document.getElementById("b_spin"); if (b) b.classList.toggle("on", spinning); }}
function toggleBox() {{ boxOn = !boxOn;
  if (boxOn) shapes = boxShapes(v, S, "{box}"); else {{ shapes.forEach(s => v.removeShape(s)); shapes = []; }}
  document.getElementById("b_box").classList.toggle("on", boxOn); v.render(); }}
function toggleH() {{ hideH = !hideH; document.getElementById("b_h").classList.toggle("on", hideH);
  document.getElementById("b_h").textContent = hideH ? "H hidden" : "H"; restyle(); }}
function toggleLabels() {{
  labelsOn = !labelsOn; v.removeAllLabels();
  if (labelsOn) {{
    const sel = S.atoms <= 600 ? {{not: {{elem: "H"}}}} : {{elem: IONS}};
    for (const a of m.selectedAtoms(sel)) v.addLabel(a.elem, {{position: {{x: a.x, y: a.y, z: a.z}}, fontSize: 10, fontColor: "white",
      backgroundColor: "{panel}", backgroundOpacity: 0.65, borderThickness: 0, inFront: true, alignment: "center"}});
  }}
  document.getElementById("b_lab").classList.toggle("on", labelsOn); v.render(); }}
function png() {{ const a = document.createElement("a"); a.href = v.pngURI(); a.download = "structure.png";
  document.body.appendChild(a); a.click(); a.remove(); }}
const hv = document.getElementById("hv");
v.setHoverable({{}}, true, function (atom) {{ hv.style.display = "block"; hv.innerHTML = hoverHTML(S, atom.index, atom.elem); }},
  function () {{ hv.style.display = "none"; }});
v.setHoverDuration(60);
// orientation axes: the x, y, z directions of the box frame, rotated with the view (quaternion from getView)
const AX = [["x", [1, 0, 0], "#f87171"], ["y", [0, 1, 0], "#4ade80"], ["z", [0, 0, 1], "#60a5fa"]];
function rot(q, p) {{
  const [x, y, z, w] = q, [px, py, pz] = p;
  const ix = w * px + y * pz - z * py, iy = w * py + z * px - x * pz, iz = w * pz + x * py - y * px, iw = -x * px - y * py - z * pz;
  return [ix * w + iw * -x + iy * -z - iz * -y, iy * w + iw * -y + iz * -x - ix * -z, iz * w + iw * -z + ix * -y - iy * -x];
}}
let lastQ = "";
function drawAxes() {{
  const view = v.getView(), q = view.slice(4, 8), key = q.map(n => n.toFixed(4)).join();
  if (key !== lastQ) {{
    lastQ = key;
    const parts = AX.map(([n, p, c]) => [n, rot(q, p), c]).sort((a, b) => a[1][2] - b[1][2]);
    document.getElementById("ax").innerHTML = parts.map(([n, r, c]) =>
      `<line x1="0" y1="0" x2="${{r[0] * 24}}" y2="${{-r[1] * 24}}" stroke="${{c}}" stroke-width="2.4" stroke-linecap="round"/>` +
      `<text x="${{r[0] * 31}}" y="${{-r[1] * 31 + 3.5}}" fill="${{c}}" font-size="10" font-weight="700" text-anchor="middle">${{n}}</text>`).join("");
  }}
  requestAnimationFrame(drawAxes);
}}
applyStyle(v, S, "bs", false);
frame(v, false); const topView = v.getView();
frame(v, true); const homeView = v.getView();
shapes = boxShapes(v, S, "{box}");
v.render(); drawAxes();
if (spinning && !matchMedia("(prefers-reduced-motion: reduce)").matches) {{ v.spin("y", 0.45);
  const b = document.getElementById("b_spin"); if (b) b.classList.add("on"); }}
</script>"""


def showcase(S: dict, height: int, bg: str = "#05070c", box: str = "#38bdf8", spin_speed: float = 0.35,
             tilt: bool = True, interactive: bool = False, ao: bool = False, particles: int = 0,
             accent: str = "#38bdf8", zoom: float = 0.95, show_box: bool = True) -> str:
    """A scene with no controls (landing page and illustrations), on a solid background that matches the page.
    `particles` > 0 draws a faint, purely decorative field of drifting glow points over it. Rotation and drift
    stop when the visitor prefers reduced motion, and pause while the view is scrolled out of sight. Ambient
    occlusion (`ao`) is for still images only: it is too heavy for a page with several live views."""
    return f"""<style>html, body {{margin:0; background:{bg}; overflow:hidden;}}
#v {{position:relative; width:100%; height:{height}px;}}
#p {{position:absolute; inset:0; width:100%; height:{height}px; pointer-events:none; z-index:3;}}
#hv {{position:absolute; z-index:6; right:10px; bottom:10px; padding:6px 11px; font:12px/1.5 "Inter",-apple-system,sans-serif;
  color:#e6edf7; background:#111827f0; border:1px solid {accent}88; border-radius:8px; display:none;}}</style>
<div id="v"></div><canvas id="p"></canvas><div id="hv"></div>
<script>{_lib()}</script>
<script>
{_CORE % {"ions": json.dumps(list(IONS))}}
const S = {json.dumps(S)};
const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
const v = $3Dmol.createViewer("v", {{backgroundColor: "{bg}", antialias: true, nomouse: {str(not interactive).lower()}
  {", ambientOcclusion: {strength: 0.9, radius: 6}" if ao else ""}}});
v.addModel(S.pdb, "pdb", {{keepH: true}});
applyStyle(v, S, "rich", false);
if ({str(interactive).lower()}) {{
  const hv = document.getElementById("hv");
  v.setHoverable({{}}, true, (atom) => {{ hv.style.display = "block"; hv.innerHTML = hoverHTML(S, atom.index, atom.elem); }},
                 () => {{ hv.style.display = "none"; }});
  v.setHoverDuration(60);
}}
frame(v, {str(tilt).lower()}, {zoom});
{'boxShapes(v, S, "' + box + '");' if show_box else ''}
v.render();
let visible = true, looping = false;
const spinOn = () => {{ if (!still && {spin_speed} > 0) v.spin("y", {spin_speed}); }};
spinOn();
const N = {particles}, cv = document.getElementById("p"), cx = cv.getContext("2d");
if (N > 0) {{
  const dpr = window.devicePixelRatio || 1;
  const fitCanvas = () => {{ cv.width = cv.clientWidth * dpr; cv.height = cv.clientHeight * dpr; }};
  fitCanvas(); addEventListener("resize", fitCanvas);
  const P = Array.from({{length: N}}, () => ({{x: Math.random(), y: Math.random(), r: 0.6 + Math.random() * 1.8,
    vx: (Math.random() - .5) * 0.00012, vy: -0.00004 - Math.random() * 0.00012, a: 0.15 + Math.random() * 0.45, t: Math.random() * 6.3}}));
  const draw = () => {{
    cx.clearRect(0, 0, cv.width, cv.height);
    for (const q of P) {{
      if (!still) {{ q.x += q.vx; q.y += q.vy; q.t += 0.01; if (q.y < -0.02) {{ q.y = 1.02; q.x = Math.random(); }} }}
      const g = cx.createRadialGradient(q.x * cv.width, q.y * cv.height, 0, q.x * cv.width, q.y * cv.height, q.r * 4 * dpr);
      const al = q.a * (0.65 + 0.35 * Math.sin(q.t));
      g.addColorStop(0, `rgba(170, 220, 255, ${{al}})`); g.addColorStop(1, "rgba(56, 189, 248, 0)");
      cx.fillStyle = g; cx.beginPath(); cx.arc(q.x * cv.width, q.y * cv.height, q.r * 4 * dpr, 0, 6.29); cx.fill();
    }}
    if (!still && visible) requestAnimationFrame(draw); else looping = false;
  }};
  looping = true; draw();
  window.restartParticles = () => {{ if (!looping && !still) {{ looping = true; draw(); }} }};
}}
new IntersectionObserver(([e]) => {{        // pause everything while the view is off screen
  visible = e.isIntersecting;
  if (visible) {{ spinOn(); if (window.restartParticles) window.restartParticles(); }} else v.spin(false);
}}).observe(document.getElementById("v"));
window.ready = true;
</script>"""
