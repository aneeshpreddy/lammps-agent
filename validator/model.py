"""Typed arrays built from a ParsedFile that has passed Tier 0.

Only called after Tier 0 succeeds, so every token is known to be well-formed. Type names are
taken from the declared configuration, or else from the `# name` comments on Masses rows
(EMC and msi2lmp both write them) — see OD-J.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from .geometry import Cell
from .parser import ATOM_STYLE_COLUMNS, ParsedFile, decimals

TOPOLOGY_ARITY = {"Bonds": 2, "Angles": 3, "Dihedrals": 4, "Impropers": 4}


@dataclass
class Topology:
    ids: np.ndarray        # entry IDs
    types: np.ndarray
    atoms: np.ndarray      # (n, arity) atom IDs
    linenos: List[int]


@dataclass
class Model:
    atom_style: str
    ids: np.ndarray
    types: np.ndarray
    mol: Optional[np.ndarray]
    q: Optional[np.ndarray]
    xyz: np.ndarray
    image: Optional[np.ndarray]
    atom_linenos: List[int]
    cell: Optional[Cell]
    n_atom_types: int
    masses: Dict[int, float] = field(default_factory=dict)       # last value per type
    mass_rows: Dict[int, int] = field(default_factory=dict)      # number of rows per type
    type_names: Dict[int, str] = field(default_factory=dict)
    topology: Dict[str, Topology] = field(default_factory=dict)
    velocities: Optional[np.ndarray] = None
    velocity_ids: Optional[np.ndarray] = None
    q_decimals: int = 0
    xyz_decimals: int = 0
    box_decimals: int = 0

    @property
    def natoms(self) -> int:
        return len(self.ids)

    def index_of(self) -> Dict[int, int]:
        return {int(a): i for i, a in enumerate(self.ids)}

    def element_of_type(self, element_map: Dict[str, str]) -> Dict[int, Optional[str]]:
        return {t: element_map.get(self.type_names.get(t, ""), None) for t in range(1, self.n_atom_types + 1)}


def build_model(pf: ParsedFile, atom_style: str, periodic=(True, True, True),
                type_names: Optional[Dict[int, str]] = None) -> Model:
    cols = ATOM_STYLE_COLUMNS[atom_style]
    k = len(cols)
    sec = pf.section("Atoms")
    rows = sec.rows if sec else []
    ids, types, mol, q, xyz, img, lines = [], [], [], [], [], [], []
    qdec = xdec = 0
    ci = {c: i for i, c in enumerate(cols)}
    for r in rows:
        t = r.tokens
        ids.append(int(t[ci["id"]]))
        types.append(int(t[ci["type"]]))
        if "mol" in ci:
            mol.append(int(t[ci["mol"]]))
        if "q" in ci:
            q.append(float(t[ci["q"]]))
            qdec = max(qdec, decimals(t[ci["q"]]))
        xyz.append([float(t[ci["x"]]), float(t[ci["y"]]), float(t[ci["z"]])])
        xdec = max(xdec, *(decimals(t[ci[c]]) for c in "xyz"))
        if len(t) == k + 3:
            img.append([int(v) for v in t[k:k + 3]])
        lines.append(r.lineno)

    cell = None
    xb, yb, zb = pf.header_floats("xlo xhi"), pf.header_floats("ylo yhi"), pf.header_floats("zlo zhi")
    tilt = pf.header_floats("xy xz yz") or [0.0, 0.0, 0.0]
    box_dec = 0
    for key in ("xlo xhi", "ylo yhi", "zlo zhi", "xy xz yz"):
        for v in (pf.header_values(key) or []):
            box_dec = max(box_dec, decimals(v))
    if xb and yb and zb and xb[1] > xb[0] and yb[1] > yb[0] and zb[1] > zb[0]:
        cell = Cell(xb[0], xb[1], yb[0], yb[1], zb[0], zb[1], *tilt, periodic=periodic)

    m = Model(
        atom_style=atom_style,
        ids=np.array(ids, dtype=np.int64),
        types=np.array(types, dtype=np.int64),
        mol=np.array(mol, dtype=np.int64) if "mol" in ci else None,
        q=np.array(q, dtype=float) if "q" in ci else None,
        xyz=np.array(xyz, dtype=float).reshape(-1, 3),
        image=np.array(img, dtype=np.int64) if img and len(img) == len(rows) else None,
        atom_linenos=lines,
        cell=cell,
        n_atom_types=pf.header_int("atom types", 0) or 0,
        q_decimals=qdec, xyz_decimals=xdec, box_decimals=box_dec,
    )

    ms = pf.section("Masses")
    if ms:
        for r in ms.rows:
            t = int(r.tokens[0])
            m.masses[t] = float(r.tokens[1])
            m.mass_rows[t] = m.mass_rows.get(t, 0) + 1
            if r.comment and t not in m.type_names:
                m.type_names[t] = r.comment.split()[0]
    if type_names:
        m.type_names = {int(k): v for k, v in type_names.items()}

    for name, arity in TOPOLOGY_ARITY.items():
        s = pf.section(name)
        if not s:
            continue
        tid, ttype, tat, tl = [], [], [], []
        for r in s.rows:
            tid.append(int(r.tokens[0]))
            ttype.append(int(r.tokens[1]))
            tat.append([int(v) for v in r.tokens[2:2 + arity]])
            tl.append(r.lineno)
        m.topology[name] = Topology(np.array(tid, np.int64), np.array(ttype, np.int64),
                                    np.array(tat, np.int64).reshape(-1, arity), tl)

    vs = pf.section("Velocities")
    if vs:
        m.velocity_ids = np.array([int(r.tokens[0]) for r in vs.rows], dtype=np.int64)
        m.velocities = np.array([[float(v) for v in r.tokens[1:4]] for r in vs.rows], dtype=float).reshape(-1, 3)
    return m


def bond_graph_components(m: Model) -> np.ndarray:
    """Connected components (by atom index) of the bond graph; returns a label per atom."""
    n = m.natoms
    parent = np.arange(n)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    b = m.topology.get("Bonds")
    if b is not None and len(b.ids):
        idx = m.index_of()
        for i, j in b.atoms:
            if int(i) in idx and int(j) in idx:
                ri, rj = find(idx[int(i)]), find(idx[int(j)])
                if ri != rj:
                    parent[ri] = rj
    return np.array([find(a) for a in range(n)])
