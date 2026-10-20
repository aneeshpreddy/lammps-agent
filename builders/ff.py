"""Force-field typing and charges for the builders (CVFF-INTERFACE = class I, PCFF-INTERFACE = class II).

Typing maps the builders' chemistry roles to the atom types of each .frc file. Charges follow the
CVFF/PCFF convention used by Materials Studio and msi2lmp's force fields: q_i = formal_i + sum over
bonds of the bond increment delta_ij read from the .frc #bond_increments table (looked up directly,
then through #equivalence and #auto_equivalence). A missing increment is an error, never a zero.

INTERFACE PEO types (ce1/he1/oe1/oa1/ha1) carry fixed model charges in the INTERFACE database rather
than .frc increments (only ce1-o_2 is tabulated). Their increments are therefore derived from the
INTERFACE PEO model (MODEL_DATABASE/PEO/peo46_h2o4394_pcff.car) and checked against it in
tests/test_builders.py: he1 +0.053, oe1 -0.400 (two ce1), oa1 -0.600, ha1 +0.400, ce1 = sum.
"""
from __future__ import annotations

import os
import re
from typing import Dict, Optional, Tuple

from .molgraph import Mol

UGRP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRC_DIR = os.path.join(UGRP, "INTERFACE_FF_1_5", "FORCE_FIELDS")
FORCE_FIELDS = {
    "pcff": {"frc": os.path.join(FRC_DIR, "pcff_interface_v1_5.frc"), "class": "II",
             "name": "PCFF-INTERFACE (INTERFACE FF 1.5, class II)"},
    "cvff": {"frc": os.path.join(FRC_DIR, "cvff_interface_v1_5.frc"), "class": "I",
             "name": "CVFF-INTERFACE (INTERFACE FF 1.5, class I)"},
}
# Increments implied by the INTERFACE PEO model charges (see module docstring).
INTERFACE_PEO_INCREMENTS = {
    ("ce1", "he1"): (-0.053, 0.053), ("ce1", "oe1"): (0.200, -0.200), ("ce1", "oa1"): (0.200, -0.200),
    ("oa1", "ha1"): (-0.400, 0.400), ("ce1", "ce1"): (0.0, 0.0),
}
ION_TYPES = {"pcff": {"ION_Ca": "ca+", "ION_Na": "na+", "ION_K": "k+"},
             "cvff": {"ION_Ca": "ca+", "ION_Na": "na+", "ION_K": "k+"}}


def _sp3_carbon(nh: int) -> str:
    return {0: "c", 1: "c1", 2: "c2", 3: "c3"}[nh]


def _acid_oxygen(m: Mol, o: int) -> bool:
    """True for the OH oxygen of a carboxylic acid (bonded to a carbonyl carbon)."""
    return any(m.atoms[j].role == "C_carbonyl" for j in m.adj[o])


def assign_types(m: Mol, ff: str, peo_types: bool = True):
    """Set Atom.ftype for every atom. peo_types: use the INTERFACE PEO types for PEG units (PCFF only)."""
    use_peo = peo_types and ff == "pcff"
    for i, a in enumerate(m.atoms):
        r, peg = a.role, ("peg" in a.tags)
        if r == "C_sp3":
            a.ftype = "ce1" if (use_peo and peg) else _sp3_carbon(m.n_h(i))
        elif r == "H_C":
            c = m.adj[i][0]
            a.ftype = "he1" if (use_peo and "peg" in m.atoms[c].tags) else "h"
        elif r == "H_O":
            o = m.adj[i][0]
            if use_peo and "peg_end" in m.atoms[o].tags:
                a.ftype = "ha1"
            elif ff == "pcff" and _acid_oxygen(m, o):
                a.ftype = "ho2"          # cff91 carboxylic-acid convention: c_1(=o_1)-o_2-ho2
            else:
                a.ftype = "ho"
        elif r == "O_hydroxyl":
            if use_peo and "peg_end" in a.tags:
                a.ftype = "oa1"
            elif ff == "pcff" and _acid_oxygen(m, i):
                a.ftype = "o_2"
            else:
                a.ftype = "oh"
        elif r == "O_ether":
            a.ftype = "oe1" if (use_peo and peg) else ("oc" if ff == "pcff" else "o")
        elif r == "O_ester":
            a.ftype = "o_2" if ff == "pcff" else "o"
        elif r == "C_carbonyl":
            a.ftype = "c_1" if ff == "pcff" else "c'"
        elif r == "O_carbonyl":
            a.ftype = "o_1" if ff == "pcff" else "o'"
        elif r == "C_carboxylate":
            a.ftype = "c-"
        elif r == "O_carboxylate":
            a.ftype = "o-"
        elif r in ION_TYPES[ff]:
            a.ftype = ION_TYPES[ff][r]
        else:
            raise ValueError(f"no {ff} type for role {r}")


class FrcTables:
    """The parts of a .frc file needed for charges: bond increments and equivalences."""

    def __init__(self, path: str):
        self.path = path
        self.incr: Dict[Tuple[str, str], Tuple[float, float]] = {}
        self.eq_bond: Dict[str, str] = {}
        self.auto_incr: Dict[str, str] = {}
        self.masses: Dict[str, Tuple[float, str]] = {}
        section = None
        with open(path, errors="replace") as fh:
            for line in fh:
                if line.startswith("#"):
                    section = line.split()[0]
                    continue
                if line.startswith(("!", "@", ">")) or not line.strip():
                    continue
                t = line.split()
                if not re.match(r"^\d", t[0]):
                    continue
                if section == "#bond_increments" and len(t) >= 6:
                    self.incr.setdefault((t[2], t[3]), (float(t[4]), float(t[5])))
                elif section == "#equivalence" and len(t) >= 8:
                    self.eq_bond.setdefault(t[2], t[4])
                elif section == "#auto_equivalence" and len(t) >= 6:
                    self.auto_incr.setdefault(t[2], t[4])
                elif section == "#atom_types" and len(t) >= 5:
                    self.masses.setdefault(t[2], (float(t[3]), t[4]))

    def increment(self, ti: str, tj: str) -> Optional[Tuple[float, float, str]]:
        """(delta_i, delta_j, how) for a bond i-j, or None."""
        tries = [(ti, tj, "direct")]
        if (ti, tj) in INTERFACE_PEO_INCREMENTS or (tj, ti) in INTERFACE_PEO_INCREMENTS:
            pass
        ei, ej = self.eq_bond.get(ti, ti), self.eq_bond.get(tj, tj)
        tries.append((ei, ej, "equivalence"))
        ai, aj = self.auto_incr.get(ti, ti), self.auto_incr.get(tj, tj)
        tries.append((ai, aj, "auto_equivalence"))
        for a, b, how in tries:
            if (a, b) in self.incr:
                d = self.incr[(a, b)]
                return d[0], d[1], how
            if (b, a) in self.incr:
                d = self.incr[(b, a)]
                return d[1], d[0], how
        for (a, b), d in INTERFACE_PEO_INCREMENTS.items():
            if (ti, tj) == (a, b):
                return d[0], d[1], "interface_peo_model"
            if (tj, ti) == (a, b):
                return d[1], d[0], "interface_peo_model"
        return None


_TABLES: Dict[str, FrcTables] = {}


def tables(ff: str) -> FrcTables:
    if ff not in _TABLES:
        _TABLES[ff] = FrcTables(FORCE_FIELDS[ff]["frc"])
    return _TABLES[ff]


def assign_charges(m: Mol, ff: str) -> Dict[str, int]:
    """q = formal + bond increments. Returns how each increment was found (for the build record)."""
    t = tables(ff)
    for a in m.atoms:
        a.q = a.formal
    how_count: Dict[str, int] = {}
    missing = []
    for (i, j) in m.bonds:
        ti, tj = m.atoms[i].ftype, m.atoms[j].ftype
        r = t.increment(ti, tj)
        if r is None:
            missing.append((ti, tj))
            continue
        m.atoms[i].q += r[0]
        m.atoms[j].q += r[1]
        how_count[r[2]] = how_count.get(r[2], 0) + 1
    if missing:
        raise KeyError(f"{ff}: no bond increment for type pair(s) {sorted(set(missing))}")
    return how_count
