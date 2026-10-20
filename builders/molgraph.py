"""Molecular graph, 3D growth and Materials Studio .car/.mdf output for the structure builders.

The builders describe chemistry with force-field-neutral *roles* (e.g. 'C_carbonyl', 'O_ester');
builders/ff.py turns roles into CVFF-INTERFACE or PCFF-INTERFACE types and charges, and msi2lmp
(LAMMPS tools) turns the .car/.mdf into a LAMMPS DATA FILE with the force-field parameters.

Geometry is grown atom by atom along a spanning tree (NeRF construction from bond length, angle
and torsion). Each atom's unplaced neighbours are placed together at tetrahedral (sp3) or trigonal
(sp2) positions; the group's torsion is chosen from a preference-ordered candidate list (trans
first for heavy-atom chains) and accepted as soon as no new atom comes closer than a clash
distance to any atom more than three bonds away. Deterministic for a given seed.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---- geometry tables (Å, degrees); close to the CVFF/PCFF equilibrium values -----------------
BOND_LENGTH = {
    ("C_sp3", "C_sp3"): 1.53, ("C_sp3", "H_C"): 1.09, ("C_sp3", "C_carbonyl"): 1.51,
    ("C_sp3", "C_carboxylate"): 1.52, ("C_carbonyl", "O_carbonyl"): 1.21, ("C_carbonyl", "O_ester"): 1.34,
    ("C_carbonyl", "O_hydroxyl"): 1.34, ("C_carboxylate", "O_carboxylate"): 1.26,
    ("C_sp3", "O_ester"): 1.44, ("C_sp3", "O_ether"): 1.42, ("C_sp3", "O_hydroxyl"): 1.42,
    ("O_hydroxyl", "H_O"): 0.96,
}
ANGLE = {"C_sp3": 109.47, "C_carbonyl": 120.0, "C_carboxylate": 120.0, "O_ether": 112.0,
         "O_ester": 116.0, "O_hydroxyl": 108.0, "O_carbonyl": 120.0, "O_carboxylate": 120.0}
CLASH = {"heavy": 2.6, "H": 2.0}       # accept a torsion if no new atom is closer than this


def bond_length(r1: str, r2: str) -> float:
    return BOND_LENGTH.get((r1, r2)) or BOND_LENGTH.get((r2, r1)) or 1.5


@dataclass
class Atom:
    element: str
    role: str
    residue: str = "RES_1"
    formal: float = 0.0
    tags: set = field(default_factory=set)   # e.g. {'peg', 'backbone', 'peg_end'}
    name: str = ""
    ftype: str = ""
    q: float = 0.0
    xyz: Optional[np.ndarray] = None


class Mol:
    def __init__(self, name: str = "MOL"):
        self.name = name
        self.atoms: List[Atom] = []
        self.bonds: Dict[Tuple[int, int], float] = {}
        self.adj: List[List[int]] = []

    # -- construction --------------------------------------------------------------------------
    def add(self, element, role, residue, formal=0.0, tags=()) -> int:
        self.atoms.append(Atom(element, role, residue, formal, set(tags)))
        self.adj.append([])
        return len(self.atoms) - 1

    def bond(self, i: int, j: int, order: float = 1.0):
        key = (min(i, j), max(i, j))
        if key in self.bonds or i == j:
            raise ValueError(f"bad bond {i}-{j}")
        self.bonds[key] = order
        self.adj[i].append(j)
        self.adj[j].append(i)

    def add_h(self, heavy: int, n: int, residue: str):
        for _ in range(n):
            h = self.add("H", "H_O" if self.atoms[heavy].element == "O" else "H_C", residue,
                         tags=self.atoms[heavy].tags & {"peg", "peg_end"})
            self.bond(heavy, h)

    def n_h(self, i: int) -> int:
        return sum(1 for j in self.adj[i] if self.atoms[j].element == "H")

    def merge(self, other: "Mol", offset_xyz=None) -> int:
        """Append another molecule's atoms and bonds; returns the index offset."""
        off = len(self.atoms)
        for a in other.atoms:
            b = Atom(a.element, a.role, a.residue, a.formal, set(a.tags), a.name, a.ftype, a.q,
                     None if a.xyz is None else (a.xyz + (offset_xyz if offset_xyz is not None else 0)))
            self.atoms.append(b)
            self.adj.append([])
        for (i, j), o in other.bonds.items():
            self.bond(i + off, j + off, o)
        return off

    # -- names ---------------------------------------------------------------------------------
    def assign_names(self):
        """Atom names unique within each residue (msi2lmp resolves connections by name)."""
        counters: Dict[Tuple[str, str], int] = {}
        for a in self.atoms:
            k = (a.residue, a.element)
            counters[k] = counters.get(k, 0) + 1
            a.name = f"{a.element}{counters[k]}"
            if len(a.residue) + 1 + len(a.name) > 15:
                raise ValueError(f"residue/atom name too long for msi2lmp: {a.residue}:{a.name}")

    # -- geometry ------------------------------------------------------------------------------
    def reorder_by_residue(self):
        """Make every residue's atoms contiguous (msi2lmp groups residues by consecutive runs).
        Returns old->new index map."""
        first = {}
        for i, a in enumerate(self.atoms):
            first.setdefault(a.residue, i)
        order = sorted(range(len(self.atoms)), key=lambda i: (first[self.atoms[i].residue], i))
        new_of = {old: new for new, old in enumerate(order)}
        atoms = [self.atoms[i] for i in order]
        bonds = {(min(new_of[i], new_of[j]), max(new_of[i], new_of[j])): o for (i, j), o in self.bonds.items()}
        self.atoms, self.bonds = atoms, bonds
        self.adj = [[] for _ in atoms]
        for (i, j) in bonds:
            self.adj[i].append(j)
            self.adj[j].append(i)
        return new_of

    def grow(self, root: int, priority, rng: np.random.Generator, mode: str = "random"):
        """Place every atom. priority(i) -> sort key; lower keys are expanded first (backbone).
        mode 'extended': trans preferred for every heavy-atom torsion; 'random': the preferred torsion
        is drawn per group (trans 50 %, gauche+ 25 %, gauche- 25 %), giving coil-like chains."""
        n = len(self.atoms)
        pos = np.full((n, 3), np.nan)
        parent = [-1] * n
        grid: Dict[Tuple[int, int, int], List[int]] = {}
        cell = 3.0

        def put(i, x):
            pos[i] = x
            key = tuple(np.floor(x / cell).astype(int))
            grid.setdefault(key, []).append(i)

        def near(x, r):
            k = np.floor(x / cell).astype(int)
            out = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        out.extend(grid.get((k[0] + dx, k[1] + dy, k[2] + dz), ()))
            return [j for j in out if np.linalg.norm(pos[j] - x) < r]

        def topo_within(i, depth=3):
            seen, frontier = {i}, [i]
            for _ in range(depth):
                nxt = []
                for a in frontier:
                    for b in self.adj[a]:
                        if b not in seen:
                            seen.add(b)
                            nxt.append(b)
                frontier = nxt
            return seen

        # root and its first neighbour
        put(root, np.zeros(3))
        heap = [(priority(root), root)]
        placed = {root}
        import heapq
        heapq.heapify(heap)
        while heap:
            _, p = heapq.heappop(heap)
            kids = [c for c in self.adj[p] if c not in placed]
            if not kids:
                continue
            # heavy atoms first so the preferred torsion goes to the chain continuation
            kids.sort(key=lambda c: (self.atoms[c].element == "H", priority(c)))
            g = parent[p]
            role_p = self.atoms[p].role
            theta = ANGLE.get(role_p, 109.47)
            sp2 = role_p in ("C_carbonyl", "C_carboxylate")
            if g < 0:
                # root: put its first neighbour along +x and treat it as the parent of the rest
                first = kids.pop(0)
                put(first, pos[p] + np.array([bond_length(role_p, self.atoms[first].role), 0.0, 0.0]))
                parent[first] = p
                placed.add(first)
                heapq.heappush(heap, (priority(first), first))
                frame_a = pos[p] + np.array([0.0, 1.0, 0.0])
                frame_b = pos[first]
                if not kids:
                    continue
            else:
                frame_b = pos[g]
                a = parent[g]
                if a < 0:
                    others = [x for x in self.adj[g] if x != p and x in placed]
                    frame_a = pos[others[0]] if others else pos[g] + np.array([0.0, 1.0, 0.0])
                else:
                    frame_a = pos[a]
            # torsion offsets for a group: sp3 -> 0, 120, 240 ; sp2 -> 0, 180 ; first expansion of
            # the root has no 'b' neighbour placed, which the frame above emulates.
            n_placed_nb = sum(1 for x in self.adj[p] if x in placed)
            step = 180.0 if sp2 else 120.0
            offsets = [k * step for k in range(len(kids))]
            if sp2 and n_placed_nb == 1 and len(kids) == 2:
                offsets = [0.0, 180.0]
            heavy_chain = self.atoms[kids[0]].element != "H"
            if not heavy_chain:
                prefs = [180.0]
            elif mode == "extended":
                prefs = [180.0, 60.0, -60.0]
            else:
                first_pref = rng.choice([180.0, 60.0, -60.0], p=[0.5, 0.25, 0.25])
                prefs = [first_pref] + [x for x in (180.0, 60.0, -60.0) if x != first_pref]
            cands = []
            for base in prefs:
                cands.append(base + rng.uniform(-12, 12))
            cands += [k * 15.0 + rng.uniform(-4, 4) for k in range(24)]
            best, best_score = None, -1.0
            excls = {c: topo_within(c) for c in kids}
            for phi0 in cands:
                trial = []
                for c, off in zip(kids, offsets):
                    r = bond_length(role_p, self.atoms[c].role)
                    trial.append(nerf(frame_a, frame_b, pos[p], r, theta, phi0 + off))
                score = 1e9
                for c, x in zip(kids, trial):
                    excl = excls[c]
                    for j in near(x, 3.2):
                        if j in excl:
                            continue
                        d = np.linalg.norm(pos[j] - x)
                        lim = CLASH["H"] if (self.atoms[c].element == "H" or self.atoms[j].element == "H") else CLASH["heavy"]
                        score = min(score, d / lim)
                    # new atoms of the group against each other are fixed by geometry
                if score >= 1.0:
                    best = trial
                    break
                if score > best_score:
                    best, best_score = trial, score
            for c, x in zip(kids, best):
                put(c, x)
                parent[c] = p
                placed.add(c)
                heapq.heappush(heap, (priority(c), c))
        if len(placed) != n:
            raise ValueError(f"grow(): {n - len(placed)} atoms not connected to the root")
        for i, a in enumerate(self.atoms):
            a.xyz = pos[i]

    def min_nonbonded_distance(self, depth: int = 3):
        xyz = np.array([a.xyz for a in self.atoms])
        best = (np.inf, None)
        from collections import defaultdict
        grid = defaultdict(list)
        for i, x in enumerate(xyz):
            grid[tuple(np.floor(x / 3.0).astype(int))].append(i)
        for i, x in enumerate(xyz):
            excl = {i}
            frontier = [i]
            for _ in range(depth):
                frontier = [b for a in frontier for b in self.adj[a] if b not in excl]
                excl.update(frontier)
            k = np.floor(x / 3.0).astype(int)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for j in grid.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                            if j > i and j not in excl:
                                d = float(np.linalg.norm(xyz[j] - x))
                                if d < best[0]:
                                    best = (d, (i, j))
        return best


def nerf(a, b, c, r, theta_deg, phi_deg):
    """Place D with |CD| = r, angle BCD = theta, dihedral ABCD = phi."""
    theta, phi = math.radians(theta_deg), math.radians(phi_deg)
    bc = c - b
    bc /= np.linalg.norm(bc)
    n = np.cross(b - a, bc)
    nn = np.linalg.norm(n)
    if nn < 1e-8:                      # collinear reference: pick any perpendicular
        n = np.cross(bc, [1.0, 0.0, 0.0])
        if np.linalg.norm(n) < 1e-8:
            n = np.cross(bc, [0.0, 1.0, 0.0])
        nn = np.linalg.norm(n)
    n /= nn
    m = np.cross(n, bc)
    d2 = np.array([-r * math.cos(theta), r * math.sin(theta) * math.cos(phi), r * math.sin(theta) * math.sin(phi)])
    return c + d2[0] * bc + d2[1] * m + d2[2] * n


# ---- Materials Studio archive output (read by msi2lmp) -------------------------------------
def write_car_mdf(molecules: List[Mol], box, root: str, title: str = "generated by builders"):
    """molecules: list of Mol with ftype, q, name and xyz set; box: (a, b, c) orthogonal lengths."""
    a, b, c = box
    with open(root + ".car", "w") as fh:
        fh.write("!BIOSYM archive 3\nPBC=ON\n")
        fh.write(f"{title[:70]}\n!DATE generated\n")
        fh.write(f"PBC{a:10.4f}{b:10.4f}{c:10.4f}{90.0:10.4f}{90.0:10.4f}{90.0:10.4f} (P1)\n")
        for k, m in enumerate(molecules, start=1):
            for at in m.atoms:
                res = at.residue.rsplit("_", 1)[0]
                # msi2lmp reads this column as the LAMMPS molecule ID (ReadCarFile.c), so it carries the
                # molecule index; residue identity for connections lives in the .mdf
                fh.write(f"{at.name:<5s} {at.xyz[0]:14.9f} {at.xyz[1]:14.9f} {at.xyz[2]:14.9f} "
                         f"{res:<4s} {k:<6d} {at.ftype:<7s} {at.element:<2s} {at.q:7.4f}\n")
            fh.write("end\n")
        fh.write("end\n")
    with open(root + ".mdf", "w") as fh:
        fh.write("!BIOSYM molecular_data 4\n\n!DATE: generated\n\n#topology\n\n")
        cols = ["element", "atom_type", "charge_group", "isotope", "formal_charge", "charge",
                "switching_atom", "oop_flag", "chirality_flag", "occupancy", "xray_temp_factor", "connections"]
        for i, cname in enumerate(cols, start=1):
            fh.write(f"@column {i} {cname}\n")
        fh.write("\n")
        for k, m in enumerate(molecules, start=1):
            fh.write(f"@molecule {m.name}_{k}\n\n")
            for i, at in enumerate(m.atoms):
                conns = []
                for j in m.adj[i]:
                    o = m.bonds[(min(i, j), max(i, j))]
                    t = f"{m.atoms[j].residue}:{m.atoms[j].name}"
                    if o != 1.0:
                        t += f"/{o:.1f}"
                    conns.append(t)
                if len(conns) > 8:
                    raise ValueError("msi2lmp allows at most 8 connections per atom")
                fh.write(f"{at.residue}:{at.name:<8s} {at.element:<2s} {at.ftype:<7s} ? 0 {int(round(at.formal))} "
                         f"{at.q:9.4f} 0 0 8 1.0000 0.0000 {' '.join(conns)}\n")
            fh.write("\n")
        fh.write("#end\n")
