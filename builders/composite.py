"""PCE on an INTERFACE FF 1.5 mineral surface -> LAMMPS DATA FILE, in either force field.

Supervisor 2026-10-26: "yes a combined builder" (PCE adsorbed on a cement-mineral surface, SPEC §7.16).

Spec (JSON):
  name          output name
  force_field   "pcff" (PCFF-INTERFACE, class II) | "cvff" (CVFF-INTERFACE, class I: C3S and C3A surfaces only)
  surface       {"model": "tob11_004_surface", "supercell": [nx, ny, nz] | "auto"}
                any slab model of builders/minerals.py (a cell with an empty gap of >= MIN_VACUUM_A along
                one axis, the surface normal); "auto" repeats the slab laterally until the PCE fits
  pce           PCE architecture, full or convenience form of builders/pce.py (its force_field and box
                are set here)
  height        Å between the topmost slab atom and the lowest PCE / counter-ion atom (default 3.0)
  orientation   "flat" (the PCE's shortest principal axis along the surface normal, default) | "as_built"
  lateral_gap   minimum Å between the PCE and its lateral periodic image (default 4.0)
  vacuum_above  minimum Å between the PCE top and the periodic image of the slab bottom (default 10.0)

Pipeline: slab DATA FILE (builders/minerals.py: msi2lmp, supercell, LAMMPS read/write) + PCE DATA FILE
(builders/pce.py: msi2lmp, relaxation, tight box) -> the slab is made contiguous along the normal and
its top face found -> the PCE is rotated, centred laterally and lifted to `height` above the top face ->
the two files are merged: every type, atom, molecule and topology ID of the PCE is offset past the
slab's; coefficient rows are copied unchanged, so both parts keep exactly the parameters msi2lmp gave
them. Box: the slab's lateral cell; along the normal the slab model's own length, extended when the PCE
needs more. Velocities are dropped (static structure). The slab bottom sits 1 Å above the box face.

  python -m builders.composite examples/composite/tob11_004_small.json --out runs/composite
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import tempfile
from typing import Dict, List

import numpy as np

from .ff import FORCE_FIELDS
from .minerals import DataText, build_mineral
from .pce import ArchitectureSpec, build as build_pce

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_VACUUM_A = 8.0
BOTTOM_CLEARANCE_A = 1.0
AXES = "xyz"
TOPOLOGY = [("Bonds", "bond", 2), ("Angles", "angle", 3), ("Dihedrals", "dihedral", 4), ("Impropers", "improper", 4)]
# coefficient sections and the type kind that indexes them
COEFF_KIND = {"Masses": "atom", "Pair Coeffs": "atom", "Bond Coeffs": "bond", "Angle Coeffs": "angle",
              "BondBond Coeffs": "angle", "BondAngle Coeffs": "angle", "Dihedral Coeffs": "dihedral",
              "MiddleBondTorsion Coeffs": "dihedral", "EndBondTorsion Coeffs": "dihedral",
              "AngleTorsion Coeffs": "dihedral", "AngleAngleTorsion Coeffs": "dihedral",
              "BondBond13 Coeffs": "dihedral", "Improper Coeffs": "improper", "AngleAngle Coeffs": "improper"}


# ---------------------------------------------------------------------------------------------
class Data:
    """The parts of a DATA FILE needed to merge two of them (orthogonal box, atom_style full)."""

    def __init__(self, path: str):
        d = DataText.read(path)
        self.counts = {k: self._int(d, f"{k}s") for _, k, _ in TOPOLOGY}
        self.counts["atom"] = d.header_int("atoms")
        self.types = {k: self._int(d, f"{k} types") for k in ("atom", "bond", "angle", "dihedral", "improper")}
        if d.header_index("xy xz yz") is not None:
            vals = [float(v) for v in d.header_values("xy xz yz")]
            if any(abs(v) > 0 for v in vals):
                raise ValueError(f"{path}: triclinic box; the composite builder needs an orthogonal slab cell")
        self.lo = np.array([float(d.header_values(f"{a}lo {a}hi")[0]) for a in AXES])
        self.hi = np.array([float(d.header_values(f"{a}lo {a}hi")[1]) for a in AXES])
        self.sections: Dict[str, List[str]] = {}
        self.hints: Dict[str, str] = {}
        for name in list(COEFF_KIND) + ["Atoms"] + [s for s, _, _ in TOPOLOGY]:
            k = d.section_index(name)
            if k is None:
                continue
            self.hints[name] = d.lines[k].split("#", 1)[1].strip() if "#" in d.lines[k] else ""
            self.sections[name] = [ln for _, ln in d.section_rows(name)]
        self.atoms = []          # [id, mol, type, q, xyz(3), img(3), comment]
        for ln in self.sections.get("Atoms", []):
            body, _, com = ln.partition("#")
            t = body.split()
            img = [int(v) for v in t[7:10]] if len(t) >= 10 else [0, 0, 0]
            self.atoms.append([int(t[0]), int(t[1]), int(t[2]), t[3], np.array([float(v) for v in t[4:7]]),
                               np.array(img), com.strip()])

    @staticmethod
    def _int(d, key):
        try:
            return d.header_int(key)
        except KeyError:
            return 0

    @property
    def xyz(self):
        return np.array([a[4] for a in self.atoms])

    @property
    def lengths(self):
        return self.hi - self.lo


def slab_geometry(slab: Data) -> dict:
    """Surface normal = the axis with the largest empty gap between atom layers (periodic). Returns the
    normal axis, the slab's bottom and top along it (contiguous, possibly beyond the box) and the gap."""
    best = None
    for ax in range(3):
        L = slab.lengths[ax]
        c = np.sort((slab.xyz[:, ax] - slab.lo[ax]) % L)
        gaps = np.diff(np.append(c, c[0] + L))
        k = int(np.argmax(gaps))
        if best is None or gaps[k] > best["gap"]:
            # empty space runs from c[k] (slab top) to c[k+1] (bottom of the slab's next image)
            top = slab.lo[ax] + c[k]
            bottom = slab.lo[ax] + (c[(k + 1) % len(c)] if k + 1 < len(c) else c[0] + L)
            if bottom > top:
                bottom -= L
            best = {"axis": ax, "gap": float(gaps[k]), "top": float(top), "bottom": float(bottom),
                    "thickness": float(top - bottom)}
    if best["gap"] < MIN_VACUUM_A:
        raise ValueError(f"not a slab model: the largest empty gap along any axis is {best['gap']:.1f} Å "
                         f"(< {MIN_VACUUM_A} Å); use a *_surface model")
    return best


def orient(xyz: np.ndarray, normal: int, mode: str) -> np.ndarray:
    """Rotate the PCE about its centroid. 'flat': principal axes (largest -> first lateral axis, middle ->
    second lateral axis, smallest -> normal); a proper rotation (no mirror image)."""
    c = xyz - xyz.mean(0)
    if mode == "as_built":
        return c
    if mode != "flat":
        raise ValueError("orientation must be 'flat' or 'as_built'")
    w, v = np.linalg.eigh(np.cov(c.T))
    order = np.argsort(w)[::-1]            # largest first
    lateral = [a for a in range(3) if a != normal]
    R = np.zeros((3, 3))
    R[lateral[0]] = v[:, order[0]]
    R[lateral[1]] = v[:, order[1]]
    R[normal] = v[:, order[2]]
    if np.linalg.det(R) < 0:
        R[normal] *= -1
    return c @ R.T


# ---------------------------------------------------------------------------------------------
def merge(slab: Data, pce: Data, pce_xyz: np.ndarray, lo, hi, normal: int, title: str) -> str:
    to = {k: slab.types[k] for k in slab.types}
    n_atom = max(a[0] for a in slab.atoms)
    n_mol = max(a[1] for a in slab.atoms)
    lines = [title, ""]
    for _, k, _ in [(None, "atom", None)] + TOPOLOGY:
        lines.append(f"{slab.counts[k] + pce.counts[k]} {k}s")
    lines.append("")
    for k in ("atom", "bond", "angle", "dihedral", "improper"):
        lines.append(f"{slab.types[k] + pce.types[k]} {k} types")
    lines.append("")
    for a in range(3):
        lines.append(f"{lo[a]:.9f} {hi[a]:.9f} {AXES[a]}lo {AXES[a]}hi")
    for name, kind in COEFF_KIND.items():
        rows = list(slab.sections.get(name, []))
        for ln in pce.sections.get(name, []):
            t = ln.split(None, 1)
            rows.append(f"{int(t[0]) + to[kind]} {t[1]}")
        if not rows:
            continue
        if len(rows) != slab.types[kind] + pce.types[kind]:
            raise ValueError(f"{name}: {len(rows)} rows for {slab.types[kind] + pce.types[kind]} {kind} types "
                             "(one part lacks the section)")
        hint = slab.hints.get(name) or pce.hints.get(name)
        lines += ["", f"{name}{' # ' + hint if hint else ''}", ""] + rows
    lines += ["", "Atoms # full", ""]
    for a in slab.atoms:
        lines.append(" ".join([str(a[0]), str(a[1]), str(a[2]), a[3]] + [f"{v:.9f}" for v in a[4]]
                              + [str(v) for v in a[5]]) + (f" # {a[6]}" if a[6] else ""))
    for a, x in zip(pce.atoms, pce_xyz):
        lines.append(" ".join([str(a[0] + n_atom), str(a[1] + n_mol), str(a[2] + to["atom"]), a[3]]
                              + [f"{v:.9f}" for v in x] + ["0", "0", "0"]) + (f" # {a[6]}" if a[6] else ""))
    for sec, kind, n in TOPOLOGY:
        rows = list(slab.sections.get(sec, []))
        for ln in pce.sections.get(sec, []):
            t = ln.split("#")[0].split()
            rows.append(" ".join([str(int(t[0]) + slab.counts[kind]), str(int(t[1]) + to[kind])]
                                 + [str(int(v) + n_atom) for v in t[2:2 + n]]))
        if rows:
            lines += ["", sec, ""] + rows
    return "\n".join(lines) + "\n"


def build(spec: dict, outdir: str) -> dict:
    spec = copy.deepcopy(spec)
    name, ff = spec["name"], spec["force_field"]
    if ff not in FORCE_FIELDS:
        raise ValueError(f"force_field must be one of {list(FORCE_FIELDS)}")
    height = float(spec.get("height", 3.0))
    lateral_gap = float(spec.get("lateral_gap", 4.0))
    vacuum_above = float(spec.get("vacuum_above", 10.0))
    orientation = spec.get("orientation", "flat")
    surf = spec["surface"]
    os.makedirs(outdir, exist_ok=True)
    with tempfile.TemporaryDirectory() as wd:
        # PCE (relaxed, tight box, whole molecules, image flags zero)
        pd = dict(spec["pce"])
        pd.update(force_field=ff, name=f"{name}_pce")
        pspec = ArchitectureSpec.from_json(pd)
        prec = build_pce(pspec, wd)
        pce = Data(os.path.join(wd, f"{name}_pce.data"))
        # slab geometry from one cell, then the lateral supercell
        cell_rec = build_mineral(surf["model"], (1, 1, 1), ff, wd, f"{name}_cell")
        geo = slab_geometry(Data(cell_rec["data_file"]))
        n_ax = geo["axis"]
        lateral = [a for a in range(3) if a != n_ax]
        p_xyz = orient(pce.xyz, n_ax, orientation)
        ext = p_xyz.max(0) - p_xyz.min(0)
        cell_L = Data(cell_rec["data_file"]).lengths
        sc = surf.get("supercell", "auto")
        if sc == "auto":
            sc = [1, 1, 1]
            for a in lateral:
                sc[a] = max(1, math.ceil((ext[a] + lateral_gap) / cell_L[a]))
        sc = [int(v) for v in sc]
        if sc[n_ax] != 1:
            raise ValueError(f"supercell must be 1 along the surface normal ({AXES[n_ax]})")
        for a in lateral:
            if ext[a] + lateral_gap > sc[a] * cell_L[a] + 1e-9:
                need = math.ceil((ext[a] + lateral_gap) / cell_L[a])
                raise ValueError(f"the PCE is {ext[a]:.1f} Å wide along {AXES[a]}; with a {lateral_gap} Å gap to its "
                                 f"periodic image it needs >= {need} slab cells along {AXES[a]} (got {sc[a]})")
        srec = cell_rec if sc == [1, 1, 1] else build_mineral(surf["model"], tuple(sc), ff, wd, f"{name}_slab")
        slab = Data(srec["data_file"])
        geo = slab_geometry(slab)
        # make the slab contiguous along the normal: atoms below the gap's far edge belong to the image above
        L = slab.lengths
        for a in slab.atoms:
            c = a[4][n_ax]
            while c < geo["bottom"] - 1e-6:
                c += L[n_ax]
            while c > geo["top"] + 1e-6:
                c -= L[n_ax]
            a[4][n_ax] = c
            a[5][n_ax] = 0
        # box along the normal
        h_pce = ext[n_ax]
        need = BOTTOM_CLEARANCE_A + geo["thickness"] + height + h_pce + vacuum_above
        Ln = max(L[n_ax], need)
        lo, hi = slab.lo.copy(), slab.hi.copy()
        lo[n_ax] = geo["bottom"] - BOTTOM_CLEARANCE_A
        hi[n_ax] = lo[n_ax] + Ln
        # place the PCE: lateral centre of the cell, lowest atom `height` above the top face
        shift = np.zeros(3)
        for a in lateral:
            shift[a] = (lo[a] + hi[a]) / 2 - (p_xyz[:, a].min() + p_xyz[:, a].max()) / 2
        shift[n_ax] = geo["top"] + height - p_xyz[:, n_ax].min()
        p_xyz = p_xyz + shift
        title = (f"LAMMPS data file | {name}: PCE on INTERFACE FF 1.5 {surf['model']} {sc[0]}x{sc[1]}x{sc[2]} "
                 f"({FORCE_FIELDS[ff]['name']}) via builders/composite.py")
        out = os.path.join(outdir, name + ".data")
        with open(out, "w") as fh:
            fh.write(merge(slab, pce, p_xyz, lo, hi, n_ax, title))
    # closest PCE-slab distance (periodic laterally) as a placement record; only atoms near the interface
    s_xyz = np.array([a[4] for a in slab.atoms])
    s_xyz = s_xyz[s_xyz[:, n_ax] > geo["top"] - 6.0]
    p_xyz = p_xyz[p_xyz[:, n_ax] < geo["top"] + height + 6.0]
    d = np.inf
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            off = np.zeros(3)
            off[lateral[0]], off[lateral[1]] = dx * L[lateral[0]], dy * L[lateral[1]]
            dd = np.linalg.norm(p_xyz[:, None, :] - (s_xyz[None, :, :] + off), axis=2).min()
            d = min(d, float(dd))
    record = {
        "name": name, "force_field": FORCE_FIELDS[ff]["name"], "surface_model": surf["model"], "supercell": sc,
        "surface_normal": AXES[n_ax], "slab_thickness_A": round(geo["thickness"], 4),
        "height_A": height, "orientation": orientation, "lateral_gap_A": lateral_gap, "vacuum_above_A": vacuum_above,
        "pce_extent_A": [round(float(v), 3) for v in ext], "closest_pce_slab_distance_A": round(d, 4),
        "box": [round(float(v), 4) for v in hi - lo],
        "natoms": len(slab.atoms) + len(pce.atoms), "slab_atoms": len(slab.atoms), "pce_atoms": len(pce.atoms),
        "pce": {k: prec[k] for k in ("sequences", "chain_charges", "counterions", "elements", "net_charge")},
        "pce_spec": prec["spec"], "slab_build": {k: srec[k] for k in ("model", "supercell", "model_sha256", "lammps")},
        "data_file": os.path.relpath(out, REPO) if out.startswith(REPO) else out,
        "data_sha256": hashlib.sha256(open(out, "rb").read()).hexdigest(),
    }
    with open(os.path.join(outdir, name + ".build.json"), "w") as fh:
        json.dump(record, fh, indent=2, default=str)
    return record


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m builders.composite", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", help="composite JSON")
    ap.add_argument("--ff", choices=list(FORCE_FIELDS), help="override the spec's force_field")
    ap.add_argument("--out", default="runs/composite")
    a = ap.parse_args(argv)
    spec = json.load(open(a.spec))
    if a.ff:
        spec["force_field"] = a.ff
    rec = build(spec, a.out)
    print(json.dumps({k: rec[k] for k in ("name", "force_field", "surface_model", "supercell", "surface_normal",
                                          "natoms", "closest_pce_slab_distance_A", "box", "data_file")}, indent=1))


if __name__ == "__main__":
    main()
