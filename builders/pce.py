"""PCE (polycarboxylate ether/ester superplasticiser) builder -> LAMMPS DATA FILE, any architecture.

A PCE is a vinyl backbone made of monomer units, some carrying poly(ethylene oxide) side chains,
plus counter-ions. Everything is set by a JSON architecture spec (see ArchitectureSpec and
examples/pce/*.json):

  monomers     label -> unit definition
               {"kind": "acid",      "alpha_methyl": false, "deprotonated": true}          acrylate (COO-)
               {"kind": "acid",      "alpha_methyl": true,  "deprotonated": false}         methacrylic acid
               {"kind": "ester_peg", "alpha_methyl": true,  "eo_units": 23, "end": "OCH3"}  MPEG methacrylate
               {"kind": "ether_peg", "alpha_methyl": true,  "spacer": 2, "eo_units": 50, "end": "OH"}  TPEG
               {"kind": "ether_peg", "alpha_methyl": false, "spacer": 1, ...}  APEG ; alpha_methyl true -> HPEG
               {"kind": "diacid",    "deprotonated": 2}                                    maleic unit
  composition  label -> number of units per chain             (or use the convenience form below)
  sequence     "random" | "alternating" | "block" | "gradient" | explicit list of labels
  end_groups   [head, tail], each "CH3" or "H"
  n_chains     number of identical-architecture chains (each with its own sequence draw)
  counterion   "Ca2+" | "Na+" | "K+" | null
  box          {"padding": 10.0} or {"lengths": [Lx, Ly, Lz]}
  force_field  "pcff" (PCFF-INTERFACE, class II) | "cvff" (CVFF-INTERFACE, class I)

Convenience form (expanded into monomers + composition by architecture_from_params):
  {"n_side_chains": 12, "n_acid": 12, "side_chain_length": 15, "anchor": "ester", "acid": "acrylic", ...}

Output: <out>/<name>.data (LAMMPS DATA FILE written by msi2lmp with the force-field parameters),
<name>.car/.mdf, <name>.build.json (spec, sequence, composition, charges, missing-parameter record).
Deterministic for a given spec (seeded).

Example (the group's EMC c12e12p15 architecture):
  python -m builders.pce examples/pce/c12e12p15.json --ff pcff --out runs/pce/
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

import numpy as np

from .ff import FORCE_FIELDS, assign_charges, assign_types
from .molgraph import Mol, write_car_mdf

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MSI2LMP = os.path.join(REPO, "build", "msi2lmp", "msi2lmp")
MSI2LMP_SRC = "/opt/homebrew/opt/lammps/share/lammps/tools/msi2lmp/src"
CROSS_TERMS = {"bondbond", "bondangle", "angleangle", "angleangledihedral", "angledihedral",
               "endbonddihedral", "midbonddihedral", "bondbond13"}
ION = {"Ca2+": ("Ca", "ION_Ca", 2.0), "Na+": ("Na", "ION_Na", 1.0), "K+": ("K", "ION_K", 1.0)}


# ---------------------------------------------------------------------------------------------
@dataclass
class ArchitectureSpec:
    name: str
    monomers: Dict[str, dict]
    composition: Dict[str, int]
    sequence: object = "random"
    end_groups: List[str] = field(default_factory=lambda: ["CH3", "CH3"])
    n_chains: int = 1
    counterion: Optional[str] = "Ca2+"
    box: dict = field(default_factory=lambda: {"padding": 10.0})
    force_field: str = "pcff"
    seed: int = 1
    conformation: str = "random"       # "random" coil-like growth or "extended" (all-trans preference)
    relax: bool = True                 # LAMMPS soft-core + force-field minimisation (builders/relax.py)

    @classmethod
    def from_json(cls, d: dict) -> "ArchitectureSpec":
        d = dict(d)
        if "monomers" not in d:
            d = architecture_from_params(d)
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        spec = cls(**known)
        spec.check()
        return spec

    def check(self):
        if self.force_field not in FORCE_FIELDS:
            raise ValueError(f"force_field must be one of {list(FORCE_FIELDS)}")
        for lab, m in self.monomers.items():
            if m.get("kind") not in ("acid", "ester_peg", "ether_peg", "diacid"):
                raise ValueError(f"monomer {lab}: unknown kind {m.get('kind')!r}")
            if len(lab) > 3 or not lab.isalnum():
                raise ValueError(f"monomer label {lab!r} must be 1-3 alphanumeric characters")
            if m.get("kind") in ("ester_peg", "ether_peg") and int(m.get("eo_units", 0)) < 1:
                raise ValueError(f"monomer {lab}: eo_units must be >= 1")
        missing = set(self.composition) - set(self.monomers)
        if missing:
            raise ValueError(f"composition uses undefined monomers {missing}")
        if sum(self.composition.values()) < 1:
            raise ValueError("composition is empty")
        for e in self.end_groups:
            if e not in ("CH3", "H"):
                raise ValueError("end_groups entries must be 'CH3' or 'H'")
        if self.counterion not in (None, *ION):
            raise ValueError(f"counterion must be one of {list(ION)} or null")


def architecture_from_params(p: dict) -> dict:
    """Convenience parameters -> full spec.

    n_side_chains, side_chain_length (EO units), n_acid (or acid_to_side_chain ratio),
    anchor: 'ester' | 'APEG' | 'HPEG' | 'TPEG' | 'VPEG', acid: 'acrylic' | 'methacrylic',
    deprotonated_fraction (0..1), side_chain_end: 'OH' | 'OCH3'.
    """
    ns = int(p["n_side_chains"])
    na = int(p.get("n_acid", round(ns * float(p.get("acid_to_side_chain", 3.0)))))
    n = int(p.get("side_chain_length", 23))
    acid_methyl = p.get("acid", "acrylic") == "methacrylic"
    end = p.get("side_chain_end", "OCH3")
    anchor = p.get("anchor", "ester")
    anchors = {
        "ester": {"kind": "ester_peg", "alpha_methyl": acid_methyl, "eo_units": n, "end": end},
        "APEG": {"kind": "ether_peg", "alpha_methyl": False, "spacer": 1, "eo_units": n, "end": end},
        "HPEG": {"kind": "ether_peg", "alpha_methyl": True, "spacer": 1, "eo_units": n, "end": end},
        "TPEG": {"kind": "ether_peg", "alpha_methyl": True, "spacer": 2, "eo_units": n, "end": end},
        "VPEG": {"kind": "ether_peg", "alpha_methyl": False, "spacer": 2, "eo_units": n, "end": end},
    }
    frac = float(p.get("deprotonated_fraction", 1.0))
    n_dep = int(round(na * frac))
    monomers = {"S": anchors[anchor]}
    comp = {"S": ns}
    if n_dep:
        monomers["A"] = {"kind": "acid", "alpha_methyl": acid_methyl, "deprotonated": True}
        comp["A"] = n_dep
    if na - n_dep:
        monomers["H"] = {"kind": "acid", "alpha_methyl": acid_methyl, "deprotonated": False}
        comp["H"] = na - n_dep
    out = {k: v for k, v in p.items() if k in ArchitectureSpec.__dataclass_fields__}
    out.update({"monomers": monomers, "composition": comp})
    out.setdefault("name", f"pce_{anchor}_s{ns}_a{na}_n{n}")
    return out


# ---------------------------------------------------------------------------------------------
def make_sequence(spec: ArchitectureSpec, rng: np.random.Generator) -> List[str]:
    comp = spec.composition
    labels = [lab for lab in comp for _ in range(comp[lab])]
    s = spec.sequence
    if isinstance(s, list):
        if sorted(s) != sorted(labels):
            raise ValueError("explicit sequence does not match the composition")
        return list(s)
    side = [lab for lab in comp if spec.monomers[lab]["kind"] in ("ester_peg", "ether_peg")]
    other = [lab for lab in comp if lab not in side]
    if s == "random":
        rng.shuffle(labels)
        return labels
    if s == "block":
        return labels
    if s in ("alternating", "gradient"):
        n_side = sum(comp[x] for x in side)
        n_tot = len(labels)
        side_pool = [x for x in side for _ in range(comp[x])]
        other_pool = [x for x in other for _ in range(comp[x])]
        rng.shuffle(side_pool)
        rng.shuffle(other_pool)
        if s == "alternating":       # side chains spread as evenly as possible (Bresenham)
            slots = {int(np.floor((k + 0.5) * n_tot / n_side)) for k in range(n_side)} if n_side else set()
        else:                        # gradient: side-chain density increases along the chain
            w = np.linspace(0.1, 1.9, n_tot)
            order = np.argsort(-(w + rng.uniform(0, 0.05, n_tot)))
            slots = set(order[:n_side].tolist())
        return [side_pool.pop() if i in slots else other_pool.pop() for i in range(n_tot)]
    raise ValueError(f"unknown sequence mode {s!r}")


def _add_acid(m: Mol, c1: int, res: str, deprotonated: bool):
    if deprotonated:
        c = m.add("C", "C_carboxylate", res)
        o1 = m.add("O", "O_carboxylate", res)
        o2 = m.add("O", "O_carboxylate", res)
        m.bond(c1, c)
        m.bond(c, o1, 1.5)
        m.bond(c, o2, 1.5)
        return -1
    c = m.add("C", "C_carbonyl", res)
    o1 = m.add("O", "O_carbonyl", res)
    o2 = m.add("O", "O_hydroxyl", res)
    m.bond(c1, c)
    m.bond(c, o1, 2.0)
    m.bond(c, o2)
    return 0


def _add_peg(m: Mol, start: int, res: str, n: int, end: str, tag: bool):
    """Append n ethylene-oxide units [CH2-CH2-O] to the O atom `start`; the last O ends the chain
    as -OH (end 'OH') or -O-CH3 (end 'OCH3'). EMC's 'O(CCO)15' is start=O, n=15."""
    tags = {"peg"} if tag else set()
    prev = start
    for k in range(n):
        ca = m.add("C", "C_sp3", res, tags=tags)
        cb = m.add("C", "C_sp3", res, tags=tags)
        last = k == n - 1
        role = "O_hydroxyl" if (last and end == "OH") else "O_ether"
        o = m.add("O", role, res, tags=tags | ({"peg_end"} if (last and end == "OH" and tag) else set()))
        m.bond(prev, ca)
        m.bond(ca, cb)
        m.bond(cb, o)
        prev = o
    if end == "OCH3":
        me = m.add("C", "C_sp3", res, tags=tags)
        m.bond(prev, me)
    return 0


def add_unit(m: Mol, res: str, unit: dict, peo_types: bool):
    """Add one backbone unit; returns (head C1, tail C2, charge)."""
    c1 = m.add("C", "C_sp3", res, tags={"backbone"})
    c2 = m.add("C", "C_sp3", res, tags={"backbone"})
    m.bond(c1, c2)
    q = 0
    kind = unit["kind"]
    if unit.get("alpha_methyl") and kind != "diacid":
        me = m.add("C", "C_sp3", res)
        m.bond(c1, me)
    if kind == "acid":
        q += _add_acid(m, c1, res, bool(unit.get("deprotonated", True)))
    elif kind == "diacid":
        nd = int(unit.get("deprotonated", 2))
        q += _add_acid(m, c1, res, nd >= 1)
        q += _add_acid(m, c2, res, nd >= 2)
    elif kind == "ester_peg":
        c = m.add("C", "C_carbonyl", res)
        o1 = m.add("O", "O_carbonyl", res)
        oe = m.add("O", "O_ester", res)
        m.bond(c1, c)
        m.bond(c, o1, 2.0)
        m.bond(c, oe)
        _add_peg(m, oe, res, int(unit["eo_units"]), unit.get("end", "OCH3"), tag=peo_types)
    elif kind == "ether_peg":
        prev = c1
        for _ in range(int(unit.get("spacer", 1))):
            cs = m.add("C", "C_sp3", res)
            m.bond(prev, cs)
            prev = cs
        # anchor ether O on the spacer, then eo_units EO units (EMC 'CCO(CCO)4': spacer 2, eo_units 4).
        # Ether-anchored chains use generic types: INTERFACE has no parameters linking its PEO types
        # to an alkyl spacer.
        o = m.add("O", "O_ether", res)
        m.bond(prev, o)
        _add_peg(m, o, res, int(unit["eo_units"]), unit.get("end", "OH"), tag=False)
    return c1, c2, q


def fill_hydrogens(m: Mol):
    valence = {"C_sp3": 4, "O_hydroxyl": 2}
    for i in range(len(m.atoms)):
        a = m.atoms[i]
        if a.role in valence:
            need = valence[a.role] - len(m.adj[i])
            if need < 0:
                raise ValueError(f"over-bonded atom {a.residue} {a.role}")
            m.add_h(i, need, a.residue)


def build_chain(spec: ArchitectureSpec, seq: List[str], chain_no: int, rng) -> (Mol, int):
    m = Mol(f"PCE{chain_no}")
    peo = spec.force_field == "pcff"
    heads, tails, q = [], [], 0
    for k, lab in enumerate(seq, start=1):
        c1, c2, dq = add_unit(m, f"{lab}_{k}", spec.monomers[lab], peo)
        heads.append(c1)
        tails.append(c2)
        q += dq
    for k in range(len(seq) - 1):
        m.bond(tails[k], heads[k + 1])          # head-to-tail: ...-C1(R)-C2-C1(R)-C2-...
    for which, atom in (("head", heads[0]), ("tail", tails[-1])):
        eg = spec.end_groups[0 if which == "head" else 1]
        if eg == "CH3":
            me = m.add("C", "C_sp3", f"T_{1 if which == 'head' else 2}")
            m.bond(atom, me)
    fill_hydrogens(m)
    new_of = m.reorder_by_residue()
    heads = [new_of[i] for i in heads]
    tails = [new_of[i] for i in tails]
    assign_types(m, spec.force_field, peo_types=peo)
    assign_charges(m, spec.force_field)
    m.assign_names()
    bb = {a: i for i, a in enumerate(x for pair in zip(heads, tails) for x in pair)}
    depth = _side_depth(m, set(bb))
    nbb = len(bb)

    def priority(i):
        # each unit's side group is grown before the backbone continues, so the backbone avoids it
        if i in bb:
            return (bb[i], 0)
        anchor, d = depth[i]
        return (bb.get(anchor, nbb), d)

    m.grow(heads[0], priority, rng, mode=spec.conformation)
    return m, q


def _side_depth(m: Mol, backbone: set):
    """For every non-backbone atom: (nearest backbone anchor, bond distance)."""
    out = {}
    from collections import deque
    for b in backbone:
        dq = deque([(b, 0)])
        seen = {b}
        while dq:
            x, d = dq.popleft()
            for y in m.adj[x]:
                if y in seen or y in backbone:
                    continue
                seen.add(y)
                if y not in out or d + 1 < out[y][1]:
                    out[y] = (b, d + 1)
                dq.append((y, d + 1))
    return out


# ---------------------------------------------------------------------------------------------
def place_system(spec: ArchitectureSpec, chains: List[Mol], charges: List[int], rng):
    """Translate chains apart, add counter-ions next to carboxylates, define an orthogonal box."""
    molecules = []
    offset = np.zeros(3)
    for m in chains:
        xyz = np.array([a.xyz for a in m.atoms])
        lo, hi = xyz.min(0), xyz.max(0)
        shift = offset - lo
        for a in m.atoms:
            a.xyz = a.xyz + shift
        offset = offset + np.array([hi[0] - lo[0] + 8.0, 0.0, 0.0])
        molecules.append(m)
    q_total = sum(charges)
    ions = []
    if spec.counterion and q_total != 0:
        el, role, z = ION[spec.counterion]
        n_ion = abs(q_total) / z
        if abs(n_ion - round(n_ion)) > 1e-9 or q_total > 0:
            raise ValueError(f"cannot neutralise chain charge {q_total} with {spec.counterion}")
        n_ion = int(round(n_ion))
        sites = []
        for m in chains:
            for i, a in enumerate(m.atoms):
                if a.role == "C_carboxylate":
                    os_ = [m.atoms[j].xyz for j in m.adj[i] if m.atoms[j].role == "O_carboxylate"]
                    mid = (os_[0] + os_[1]) / 2
                    d = mid - a.xyz
                    sites.append(mid + 1.9 * d / np.linalg.norm(d))
        order = rng.permutation(len(sites))
        all_xyz = np.vstack([np.array([a.xyz for a in m.atoms]) for m in chains])
        placed = []
        for k in order:
            if len(placed) == n_ion:
                break
            p = sites[k]
            if np.min(np.linalg.norm(all_xyz - p, axis=1)) < 2.1:
                continue
            if placed and np.min(np.linalg.norm(np.array(placed) - p, axis=1)) < 4.5:
                continue
            placed.append(p)
        lo, hi = all_xyz.min(0) - 6, all_xyz.max(0) + 6
        tries = 0
        while len(placed) < n_ion:
            tries += 1
            p = rng.uniform(lo, hi)
            if np.min(np.linalg.norm(all_xyz - p, axis=1)) > 3.0 and \
                    (not placed or np.min(np.linalg.norm(np.array(placed) - p, axis=1)) > 4.5):
                placed.append(p)
            if tries > 100000:
                raise RuntimeError("could not place counter-ions")
        for k, p in enumerate(placed, start=1):
            im = Mol(f"ION{k}")
            idx = im.add(el, role, f"I_{k}", formal=z)
            im.atoms[idx].xyz = np.array(p)
            assign_types(im, spec.force_field)
            im.atoms[idx].q = z
            im.atoms[idx].name = el.upper()
            ions.append(im)
    molecules += ions
    xyz = np.vstack([np.array([a.xyz for a in m.atoms]) for m in molecules])
    lo, hi = xyz.min(0), xyz.max(0)
    if "lengths" in spec.box:
        L = np.array(spec.box["lengths"], float)
        if np.any(hi - lo > L - 2.0):
            raise ValueError(f"system extent {np.round(hi - lo, 1)} does not fit in box {L}")
    else:
        L = (hi - lo) + 2 * float(spec.box.get("padding", 10.0))
    centre = (lo + hi) / 2
    for m in molecules:          # box centred on the origin (msi2lmp -nocenter): [-L/2, L/2)
        for a in m.atoms:
            a.xyz = a.xyz - centre
    return molecules, L, len(ions)


def non_finite_lines(path: str):
    """Lines in which msi2lmp wrote nan/inf: it does so silently (no 'Unable to find' message), e.g. for the
    zero-constant CVFF wildcard torsions '* ac1 oc4 *' of hydroxylated C3A (FAILURE_MODES §9.6)."""
    bad = []
    with open(path) as fh:
        for k, ln in enumerate(fh, start=1):
            body = ln.split("#")[0].lower()
            if re.search(r"(^|\s)[+-]?(nan|inf)(\s|$)", body):
                bad.append(f"line {k}: {ln.strip()[:80]}")
    return bad


# ---------------------------------------------------------------------------------------------
def ensure_msi2lmp() -> str:
    if not os.path.exists(MSI2LMP):
        os.makedirs(os.path.dirname(MSI2LMP), exist_ok=True)
        srcs = [os.path.join(MSI2LMP_SRC, f) for f in sorted(os.listdir(MSI2LMP_SRC)) if f.endswith(".c")]
        subprocess.run(["cc", "-O2", "-w", "-o", MSI2LMP] + srcs + ["-lm"], check=True)
    return MSI2LMP


def run_msi2lmp(root: str, ff: str, out_data: str) -> dict:
    """Run msi2lmp; refuse the result if any parameter other than a class II cross term is missing."""
    info = FORCE_FIELDS[ff]
    wd = os.path.dirname(root)
    shutil.copyfile(info["frc"], os.path.join(wd, "ff.frc"))
    base = os.path.basename(root)
    p = subprocess.run([ensure_msi2lmp(), base, "-class", info["class"], "-frc", "./ff.frc", "-print", "1",
                        "-ignore", "-nocenter"], cwd=wd, capture_output=True, text=True)
    out = p.stdout + p.stderr
    missing = sorted({ln.strip() for ln in out.splitlines() if "Unable to find" in ln})
    kinds = sorted({ln.split()[3] for ln in missing if len(ln.split()) > 3})
    core = [ln for ln in missing if ln.split()[3] not in CROSS_TERMS]
    produced = os.path.join(wd, base + ".data")
    if not os.path.exists(produced):
        raise RuntimeError(f"msi2lmp failed:\n{out[-1500:]}")
    if core:
        raise RuntimeError(f"{info['name']} lacks parameters for this structure (refusing to write zeros):\n  "
                           + "\n  ".join(core[:15]))
    bad = non_finite_lines(produced)
    if bad:
        raise RuntimeError(f"msi2lmp wrote non-finite parameters ({info['name']}), refusing: " + "; ".join(bad[:4]))
    shutil.copyfile(produced, out_data)
    return {"msi2lmp_missing_kinds": kinds, "msi2lmp_missing_messages": len(missing),
            "cross_terms_zeroed": bool(missing)}


def build(spec: ArchitectureSpec, outdir: str) -> dict:
    os.makedirs(outdir, exist_ok=True)
    rng = np.random.default_rng(spec.seed)
    chains, charges, seqs = [], [], []
    for c in range(1, spec.n_chains + 1):
        seq = make_sequence(spec, rng)
        m, q = build_chain(spec, seq, c, rng)
        chains.append(m)
        charges.append(q)
        seqs.append(seq)
    molecules, L, n_ions = place_system(spec, chains, charges, rng)
    root = os.path.join(outdir, spec.name)
    with tempfile.TemporaryDirectory() as wd:
        tmp_root = os.path.join(wd, spec.name)
        write_car_mdf(molecules, L, tmp_root, title=f"{spec.name} built by builders/pce.py")
        for ext in ("car", "mdf"):
            shutil.copyfile(f"{tmp_root}.{ext}", f"{root}.{ext}")
        rec = run_msi2lmp(tmp_root, spec.force_field, root + ".data")
    if spec.relax:
        from .relax import relax
        rec.update(relax(root + ".data", spec.force_field))
    natoms = sum(len(m.atoms) for m in molecules)
    q_sum = float(sum(a.q for m in molecules for a in m.atoms))
    mind = [m.min_nonbonded_distance()[0] for m in chains]
    elements: Dict[str, int] = {}
    for m in molecules:
        for a in m.atoms:
            elements[a.element] = elements.get(a.element, 0) + 1
    record = {
        "name": spec.name, "spec": asdict(spec), "force_field": FORCE_FIELDS[spec.force_field]["name"],
        "frc": os.path.relpath(FORCE_FIELDS[spec.force_field]["frc"], os.path.dirname(REPO)),
        "sequences": ["".join(s) if all(len(x) == 1 for x in s) else s for s in seqs],
        "chain_charges": charges, "counterions": n_ions, "natoms": natoms, "elements": elements,
        "net_charge": round(q_sum, 6), "box": [round(float(x), 4) for x in L],
        "grower_min_nonbonded_distance_A": [round(float(d), 3) for d in mind],
        "data_file": os.path.relpath(root + ".data", REPO) if root.startswith(REPO) else root + ".data",
        "data_sha256": hashlib.sha256(open(root + ".data", "rb").read()).hexdigest(),
    }
    record.update(rec)
    with open(root + ".build.json", "w") as fh:
        json.dump(record, fh, indent=2, default=str)
    return record


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m builders.pce", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", help="architecture JSON")
    ap.add_argument("--ff", choices=list(FORCE_FIELDS), help="override the spec's force_field")
    ap.add_argument("--out", default="runs/pce")
    ap.add_argument("--name", help="override the spec's name")
    a = ap.parse_args(argv)
    d = json.load(open(a.spec))
    if a.ff:
        d["force_field"] = a.ff
    if a.name:
        d["name"] = a.name
    spec = ArchitectureSpec.from_json(d)
    rec = build(spec, a.out)
    print(json.dumps({k: rec[k] for k in ("name", "force_field", "natoms", "elements", "chain_charges",
                                          "counterions", "net_charge", "box", "data_file",
                                          "msi2lmp_missing_kinds")}, indent=1))


if __name__ == "__main__":
    main()
