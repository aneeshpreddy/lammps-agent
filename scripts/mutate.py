"""Corruption operators for negative controls (plan Day 14; FAILURE_MODES §9.4).

One function per failure mode (and variant). Each takes a DataText of a parent file that passes
Tiers 0-3 and edits it in place, returning metadata, or None if the operator does not apply to
that parent (e.g. tilt operators on an orthogonal box). Edits are text-level and minimal: every
untouched line stays byte-identical to the parent. Choices are deterministic.

  python scripts/mutate.py            # rebuild data/corrupted/ and data/corrupted/manifest.json

Output naming: data/corrupted/<PARENT>__<FM>__<variant>.data with a JSON sidecar (parent ID and
SHA-256, operator, parameters, expected failing properties, documented LAMMPS behaviour).
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import shutil
import sys
from typing import Callable, Dict, List, Optional

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from dataedit import DataText, join_row, split_comment  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "corrupted")
PARENTS = ["data/reference/REF-01.data", "data/reference/REF-02.data", "data/reference/REF-03.data",
           "data/reference/REF-04.data", "data/fixtures/FIX-T11.data", "data/fixtures/FIX-T14.data"]

OPERATORS: List[Dict] = []


def operator(fm, variant, expect, tier, lammps, desc, spec_expect=None, silent_header=True):
    """Register an operator. expect: properties of which at least one must FAIL for 'caught'."""
    def deco(fn: Callable):
        OPERATORS.append({"fm": fm, "variant": variant, "fn": fn, "expect": expect, "tier": tier,
                          "lammps_expected": lammps, "description": desc,
                          "spec_expect": spec_expect if spec_expect is not None else expect,
                          "header_consistent": silent_header})
        return fn
    return deco


# ---- context helpers ------------------------------------------------------------------------
class Ctx:
    def __init__(self, path: str, meta: dict):
        self.path, self.meta = path, meta
        with open(os.path.join(ROOT, meta["declared_config"])) as fh:
            self.decl = yaml.safe_load(fh)
        self.decl.update(meta.get("overrides", {}))
        self.elements = self.decl.get("type_name_elements", {})


def atom_rows(d: DataText):
    out = []
    for i, line in d.section_rows("Atoms"):
        toks, com = split_comment(line)
        out.append([i, toks, com])
    return out


def put(d: DataText, i: int, toks, com):
    d.lines[i] = join_row(toks, com)


def type_names(d: DataText) -> Dict[int, str]:
    out = {}
    for _, line in d.section_rows("Masses"):
        toks, com = split_comment(line)
        out[int(toks[0])] = com.lstrip("#").strip().split()[0] if com else str(toks[0])
    return out


def topo_rows(d: DataText, name: str):
    return [(i, line.split()) for i, line in d.section_rows(name)]


def box(d: DataText):
    lo_hi = [list(map(float, d.header_values(k))) for k in ("xlo xhi", "ylo yhi", "zlo zhi")]
    try:
        tilt = list(map(float, d.header_values("xy xz yz")))
    except KeyError:
        tilt = None
    return lo_hi, tilt


def fmt(v: float, like: str) -> str:
    dec = len(like.split(".")[1]) if "." in like else 6
    return f"{v:.{dec}f}"


def last_section(d: DataText) -> str:
    return d.section_names()[-1]


def bonded_atoms(d: DataText) -> set:
    s = set()
    for _, t in topo_rows(d, "Bonds"):
        s.update(int(x) for x in t[2:4])
    return s


# ---- operators --------------------------------------------------------------------------------
@operator("FM01", "swap_types_diff_element", ["P1.16", "P2.3", "P2.4", "TC.2"], 1, "Silent",
          "swap two atom-type IDs of different elements in Atoms; Masses unchanged", spec_expect=["P2.6", "TC.1", "TC.2"])
def fm01_diff(d, c):
    names = type_names(d)
    rows = atom_rows(d)
    used = sorted({int(t[2]) for _, t, _ in rows})
    pairs = [(a, b) for a in used for b in used if a < b and c.elements.get(names[a]) != c.elements.get(names[b])
             and c.elements.get(names[a]) in ("C", "Si") and c.elements.get(names[b]) == "O"]
    if not pairs:
        return None
    a, b = pairs[0]
    for i, t, com in rows:
        if int(t[2]) in (a, b):
            t[2] = str(b if int(t[2]) == a else a)
            put(d, i, t, com)
    return {"types": [a, b], "names": [names[a], names[b]]}


@operator("FM01", "swap_types_same_element", ["P1.16", "TC.2"], 1, "Silent",
          "swap two atom-type IDs of the same element in Atoms (e.g. two carbon types); Masses unchanged",
          spec_expect=["P2.6", "TC.1", "TC.2"])
def fm01_same(d, c):
    names = type_names(d)
    rows = atom_rows(d)
    used = sorted({int(t[2]) for _, t, _ in rows})
    pairs = [(a, b) for a in used for b in used if a < b and c.elements.get(names[a]) == c.elements.get(names[b])
             and c.elements.get(names[a]) in ("C", "O")]
    if not pairs:
        return None
    a, b = pairs[0]
    for i, t, com in rows:
        if int(t[2]) in (a, b):
            t[2] = str(b if int(t[2]) == a else a)
            put(d, i, t, com)
    return {"types": [a, b], "names": [names[a], names[b]]}


@operator("FM02", "mass_guessed_other_element", ["P2.6"], 2, "Silent",
          "replace the mass of the first hydrogen type with helium's (a Z = type-index style guess)")
def fm02(d, c):
    names = type_names(d)
    for i, line in d.section_rows("Masses"):
        toks, com = split_comment(line)
        if c.elements.get(names[int(toks[0])]) == "H":
            toks[1] = "4.002602"
            put(d, i, toks, com)
            return {"type": int(toks[0])}
    return None


def _scale_all(d, factor, scale_box=True):
    for i, t, com in atom_rows(d):
        for k in (4, 5, 6):
            t[k] = fmt(float(t[k]) * factor, t[k])
        put(d, i, t, com)
    if scale_box:
        for key in ("xlo xhi", "ylo yhi", "zlo zhi"):
            v = d.header_values(key)
            d.set_header(key, [fmt(float(x) * factor, x) for x in v])
        try:
            v = d.header_values("xy xz yz")
            d.set_header("xy xz yz", [fmt(float(x) * factor, x) for x in v])
        except KeyError:
            pass


@operator("FM03", "coords_and_box_x10", ["P2.3", "P2.4", "P2.5"], 2, "Silent",
          "multiply coordinates and box by 10 (length unit confusion, e.g. nm read as Å)")
def fm03_up(d, c):
    _scale_all(d, 10.0)
    return {"factor": 10.0}


@operator("FM03", "coords_and_box_x0.1", ["P2.3", "P2.4", "P2.5"], 2, "Silent",
          "multiply coordinates and box by 0.1 (Å read as nm)")
def fm03_down(d, c):
    _scale_all(d, 0.1)
    return {"factor": 0.1}


@operator("FM03", "wrong_units_hint", ["P1.15"], 1, "Warn (Inconsistent units in data file)",
          "write 'units = metal' on line 1 while the declared units are real")
def fm03_hint(d, c):
    d.lines[0] = d.lines[0] + "  units = metal"
    return {}


@operator("FM04", "drop_bond_header_adjusted", ["P1.10", "TC.2"], 1, "Silent",
          "delete one bond row and lower the header count (silent variant)", spec_expect=["P1.10", "TC.2"])
def fm04_silent(d, c):
    rows = topo_rows(d, "Bonds")
    i, t = rows[len(rows) // 2]
    d.delete_line(i)
    d.set_header("bonds", [d.header_int("bonds") - 1])
    return {"deleted_bond": t}


@operator("FM04", "drop_bond_header_kept", ["P1.1"], 1, "Loud", "delete one bond row, header unchanged",
          silent_header=False)
def fm04_loud(d, c):
    rows = topo_rows(d, "Bonds")
    i, t = rows[len(rows) // 2]
    d.delete_line(i)
    return {"deleted_bond": t}


@operator("FM04", "angles_dihedrals_impropers_dropped", ["P1.17", "TC.2"], 1, "Silent",
          "delete every Angles/Dihedrals/Impropers row and set their header counts to 0 (what an ASE "
          "lammps-data round trip does, docs/R13_ASE_ROUNDTRIP.md)")
def fm04_higher(d, c):
    removed = {}
    for name, key in (("Impropers", "impropers"), ("Dihedrals", "dihedrals"), ("Angles", "angles")):
        k = d.section_index(name)
        if k is None:
            continue
        rows = d.section_rows(name)
        end = rows[-1][0] + 1 if rows else k + 2
        while end < len(d.lines) and not d.lines[end].strip():
            end += 1
        del d.lines[k:end]
        removed[name] = len(rows)
        d.set_header(key, [0])
    while d.lines and not d.lines[-1].strip():
        d.lines.pop()
    return removed or None


@operator("FM05", "reversed_duplicate_bond", ["P1.6"], 1, "Silent",
          "append a reversed copy of an existing bond and raise the header count")
def fm05(d, c):
    rows = topo_rows(d, "Bonds")
    i, t = rows[0]
    n = d.header_int("bonds") + 1
    new = join_row([str(n), t[1], t[3], t[2]])
    d.insert_lines(rows[-1][0] + 1, [new])
    d.set_header("bonds", [n])
    return {"duplicated_bond": t}


@operator("FM06", "flip_largest_charge", ["P2.1"], 2, "Silent (Warn only with kspace and |Q|>1e-5)",
          "flip the sign of the largest-magnitude charge")
def fm06_flip(d, c):
    rows = atom_rows(d)
    i, t, com = max(rows, key=lambda r: abs(float(r[1][3])))
    t[3] = fmt(-float(t[3]), t[3])
    put(d, i, t, com)
    return {"atom": int(t[0])}


@operator("FM06", "zero_all_charges", ["P2.1"], 2, "Warn (Using kspace solver on system with no charge)",
          "set every charge to zero")
def fm06_zero(d, c):
    for i, t, com in atom_rows(d):
        t[3] = fmt(0.0, t[3])
        put(d, i, t, com)
    return {}


@operator("FM06", "round_charges_1dp", ["TC.2"], "TC", "Silent",
          "round every charge to one decimal place (individual charges lost; total may stay near zero)",
          spec_expect=["P2.1"])
def fm06_round(d, c):
    for i, t, com in atom_rows(d):
        t[3] = f"{round(float(t[3]), 1):.4f}"
        put(d, i, t, com)
    return {}


@operator("FM07", "written_as_charge_style", ["P0.4"], 0, "Loud (field count) / Silent if counts match",
          "drop the molecule-ID column (atom_style charge layout) in a file declared atom_style full")
def fm07_charge(d, c):
    for i, t, com in atom_rows(d):
        del t[1]
        put(d, i, t, com)
    return {}


@operator("FM07", "written_as_molecular_style", ["P0.4"], 0, "Loud (field count) / Silent if counts match",
          "drop the charge column (atom_style molecular layout) in a file declared atom_style full")
def fm07_mol(d, c):
    for i, t, com in atom_rows(d):
        del t[3]
        put(d, i, t, com)
    return {}


@operator("FM08", "coords_x1.5_box_kept", ["P2.2", "P2.3", "P2.4"], 2, "Silent (periodic remap)",
          "multiply all coordinates by 1.5, box unchanged")
def fm08(d, c):
    _scale_all(d, 1.5, scale_box=False)
    return {"factor": 1.5}


@operator("FM09", "random_image_flags", ["P2.7"], 2, "Warn at run setup (Inconsistent image flags)",
          "add random non-zero image flags in {-1,0,1} to every atom", spec_expect=["P1.9", "P2.7"])
def fm09(d, c):
    if c.decl.get("image_consistency") != "required":
        return None
    rng = np.random.default_rng(20261016)
    for i, t, com in atom_rows(d):
        flags = [str(v) for v in rng.integers(-1, 2, size=3)]
        t = t[:7] + flags
        put(d, i, t, com)
    return {"seed": 20261016}


@operator("FM10", "tilt_sign_flipped", ["P2.2", "P2.3", "P2.4"], 2, "Silent",
          "flip the sign of the xy tilt factor")
def fm10_flip(d, c):
    _, tilt = box(d)
    if not tilt or not any(tilt):
        return None
    v = d.header_values("xy xz yz")
    d.set_header("xy xz yz", [fmt(-float(v[0]), v[0])] + v[1:])
    return {}


@operator("FM10", "tilt_zeroed", ["P2.2", "P2.3", "P2.4"], 2, "Silent", "set all tilt factors to zero")
def fm10_zero(d, c):
    _, tilt = box(d)
    if not tilt or not any(tilt):
        return None
    v = d.header_values("xy xz yz")
    d.set_header("xy xz yz", [fmt(0.0, x) for x in v])
    return {}


@operator("FM10", "tilt_line_dropped", ["P0.8"], 0, "Silent", "delete the 'xy xz yz' line of a triclinic box")
def fm10_drop(d, c):
    _, tilt = box(d)
    if not tilt or not any(tilt):
        return None
    d.delete_line(d.header_index("xy xz yz"))
    return {}


@operator("FM10", "tilt_over_skewed_same_lattice", ["P2.8"], 2, "Warn on a different criterion (or none)",
          "add lx to xy: the same lattice, but beyond the documented tilt bound", spec_expect=["P2.8"])
def fm10_skew(d, c):
    lohi, tilt = box(d)
    if not tilt or not any(tilt):
        return None
    lx = lohi[0][1] - lohi[0][0]
    v = d.header_values("xy xz yz")
    xy = float(v[0])
    new = xy + lx if xy < 0 else xy - lx
    d.set_header("xy xz yz", [fmt(new, v[0])] + v[1:])
    return {"xy_before": xy, "xy_after": new}


@operator("FM11", "atom_ids_permuted_topology_stale", ["P1.16", "P2.4", "TC.2"], 2, "Silent",
          "swap the IDs of two distant atoms in Atoms without updating the topology")
def fm11(d, c):
    rows = atom_rows(d)
    names = type_names(d)
    first = rows[0]
    el0 = c.elements.get(names[int(first[1][2])])
    other = next((r for r in reversed(rows) if c.elements.get(names[int(r[1][2])]) != el0
                  and int(r[1][0]) in bonded_atoms(d)), None)
    if other is None:
        return None
    a, b = first[1][0], other[1][0]
    first[1][0], other[1][0] = b, a
    put(d, first[0], first[1], first[2])
    put(d, other[0], other[1], other[2])
    return {"swapped_ids": [int(a), int(b)]}


def _delete_atom_with_topology(d: DataText, atom_id: str):
    for i, t, com in atom_rows(d):
        if t[0] == atom_id:
            d.delete_line(i)
            break
    d.set_header("atoms", [d.header_int("atoms") - 1])
    removed = {}
    for name, key in (("Bonds", "bonds"), ("Angles", "angles"), ("Dihedrals", "dihedrals"), ("Impropers", "impropers")):
        rows = topo_rows(d, name)
        hit = [i for i, t in rows if atom_id in t[2:]]
        for i in reversed(hit):
            d.delete_line(i)
        if hit:
            d.set_header(key, [d.header_int(key) - len(hit)])
            removed[name] = len(hit)
    return removed


@operator("FM12", "counter_ion_removed", ["P2.1", "TC.2"], 2, "Silent",
          "delete the unbonded atom with the largest |q| (a counter-ion) and adjust the header")
def fm12_ion(d, c):
    bonded = bonded_atoms(d)
    cands = [(abs(float(t[3])), t[0]) for _, t, _ in atom_rows(d) if int(t[0]) not in bonded]
    if not cands:
        return None
    q, aid = max(cands)
    _delete_atom_with_topology(d, aid)
    return {"atom": int(aid), "abs_q": q}


@operator("FM12", "hydrogen_removed", ["TC.2"], "TC", "Silent",
          "delete one hydrogen and every topology entry containing it; adjust the header",
          spec_expect=["P2.1", "P2.5", "TC.1"])
def fm12_h(d, c):
    names = type_names(d)
    for _, t, _ in atom_rows(d):
        if c.elements.get(names[int(t[2])]) == "H":
            removed = _delete_atom_with_topology(d, t[0])
            return {"atom": int(t[0]), "topology_removed": removed}
    return None


@operator("FM13", "duplicate_row_same_id", ["P1.2"], 1, "Silent if max ID >= natoms, else Loud",
          "duplicate one Atoms row (same ID) and raise the atom count")
def fm13_same(d, c):
    rows = atom_rows(d)
    i, t, com = rows[-1]
    d.insert_lines(i + 1, [join_row(list(t), com)])
    d.set_header("atoms", [d.header_int("atoms") + 1])
    return {"atom": int(t[0])}


@operator("FM13", "duplicate_atom_new_id", ["P2.3", "TC.2"], 2, "Silent",
          "duplicate one Atoms row under a new ID (max ID + 1) at the same position")
def fm13_new(d, c):
    rows = atom_rows(d)
    i, t, com = rows[-1]
    new = list(t)
    new[0] = str(max(int(r[1][0]) for r in rows) + 1)
    d.insert_lines(i + 1, [join_row(new, com)])
    d.set_header("atoms", [d.header_int("atoms") + 1])
    return {"new_id": int(new[0])}


@operator("FM14", "atom_count_plus_one", ["P1.1"], 1, "Loud", "raise the header atom count by one",
          silent_header=False)
def fm14(d, c):
    d.set_header("atoms", [d.header_int("atoms") + 1])
    return {}


@operator("FM27", "surplus_final_row", ["P0.11", "P1.1"], 0, "Silent (one surplus row at EOF is ignored)",
          "lower the count of the last section by one, so its final row is surplus")
def fm27(d, c):
    sec = last_section(d)
    key = {"Bonds": "bonds", "Angles": "angles", "Dihedrals": "dihedrals", "Impropers": "impropers",
           "Atoms": "atoms"}.get(sec)
    if key is None:
        return None
    d.set_header(key, [d.header_int(key) - 1])
    return {"section": sec}


@operator("FM15", "masses_values_permuted", ["P2.6"], 2, "Silent",
          "swap the mass values of the first two Masses rows with different masses")
def fm15(d, c):
    rows = [(i, *split_comment(line)) for i, line in d.section_rows("Masses")]
    for a in range(len(rows)):
        for b in range(a + 1, len(rows)):
            if abs(float(rows[a][1][1]) - float(rows[b][1][1])) > 1:
                ta, tb = rows[a][1], rows[b][1]
                ta[1], tb[1] = tb[1], ta[1]
                put(d, rows[a][0], ta, rows[a][2])
                put(d, rows[b][0], tb, rows[b][2])
                return {"types": [int(ta[0]), int(tb[0])]}
    return None


@operator("FM17", "atom_moved_onto_another", ["P2.3"], 2, "Silent at read_data; PE may be inf at run",
          "move an unbonded or terminal atom onto the position of a non-bonded atom 0.3 Å away")
def fm17(d, c):
    rows = atom_rows(d)
    bonded = {}
    for _, t in topo_rows(d, "Bonds"):
        bonded.setdefault(t[2], set()).add(t[3])
        bonded.setdefault(t[3], set()).add(t[2])
    src = rows[-1]
    tgt = next(r for r in rows if r[1][0] != src[1][0] and r[1][0] not in bonded.get(src[1][0], set()))
    for k in (4, 5, 6):
        src[1][k] = fmt(float(tgt[1][k]) + (0.3 if k == 4 else 0.0), src[1][k])
    put(d, *src)
    return {"moved": int(src[1][0]), "onto": int(tgt[1][0])}


@operator("FM18", "atom_displaced_3A", ["P2.4", "P2.7"], 2, "Silent at read_data",
          "displace one bonded atom by 3 Å along x")
def fm18(d, c):
    rows = atom_rows(d)
    bonded = bonded_atoms(d)
    r = next(r for r in rows if int(r[1][0]) in bonded)
    r[1][4] = fmt(float(r[1][4]) + 3.0, r[1][4])
    put(d, *r)
    return {"atom": int(r[1][0])}


@operator("FM19", "box_scaled_1.3_atoms_kept", ["P2.5", "P2.2"], 2, "Silent",
          "scale the box by 1.3 about its origin; atoms unchanged")
def fm19(d, c):
    for key in ("xlo xhi", "ylo yhi", "zlo zhi"):
        lo, hi = map(float, d.header_values(key))
        v = d.header_values(key)
        d.set_header(key, [v[0], fmt(lo + (hi - lo) * 1.3, v[1])])
    try:
        v = d.header_values("xy xz yz")
        d.set_header("xy xz yz", [fmt(float(x) * 1.3, x) for x in v])
    except KeyError:
        pass
    return {"factor": 1.3}


@operator("FM20", "row_over_254_chars", ["P0.6"], 0, "Silent (truncated at 254 characters)",
          "pad the first Atoms row's z coordinate with 250 trailing digits")
def fm20(d, c):
    i, t, com = atom_rows(d)[0]
    t[6] = t[6] + "0" * 250
    put(d, i, t, com)
    return {}


@operator("FM21", "keyword_case_changed", ["P0.2"], 0, "Loud (Unknown identifier)", "'Masses' written as 'masses'")
def fm21_case(d, c):
    i = d.section_index("Masses")
    d.lines[i] = d.lines[i].replace("Masses", "masses")
    return {}


@operator("FM21", "header_line_after_section", ["P0.1"], 0, "Loud (Unknown identifier)",
          "move the 'atom types' header line to just after the Masses section")
def fm21_misplaced(d, c):
    hi = d.header_index("atom types")
    line = d.delete_line(hi)
    rows = d.section_rows("Masses")
    d.insert_lines(rows[-1][0] + 1, [line])
    return {}


def _coeff_rows(d, name):
    return [(i, *split_comment(line)) for i, line in d.section_rows(name)] if d.section_index(name) else []


@operator("FM22", "bond_coeff_values_permuted", ["TC.2"], "TC", "Silent",
          "swap the parameter values (not the IDs or comments) of the first two Bond Coeffs rows",
          spec_expect=["P1.7", "TC.2"])
def fm22_vals(d, c):
    rows = _coeff_rows(d, "Bond Coeffs")
    if len(rows) < 2:
        return None
    (ia, ta, ca), (ib, tb, cb) = rows[0], rows[1]
    ta[1:], tb[1:] = tb[1:], ta[1:]
    put(d, ia, ta, ca)
    put(d, ib, tb, cb)
    return {}


@operator("FM22", "bond_coeff_rows_relabelled", ["P1.16", "TC.2"], 1, "Silent",
          "swap the type IDs of the first two Bond Coeffs rows (values and comments move together)")
def fm22_ids(d, c):
    rows = _coeff_rows(d, "Bond Coeffs")
    if len(rows) < 2:
        return None
    (ia, ta, ca), (ib, tb, cb) = rows[0], rows[1]
    ta[0], tb[0] = tb[0], ta[0]
    put(d, ia, tb, cb)
    put(d, ib, ta, ca)
    return {}


@operator("FM32", "coeff_type_row_duplicated", ["P1.7"], 1, "Silent under nocoeff; Loud@run",
          "replace the second Bond Coeffs row with a copy of the first (type 1 twice, type 2 missing)")
def fm32(d, c):
    rows = _coeff_rows(d, "Bond Coeffs")
    if len(rows) < 2:
        return None
    put(d, rows[1][0], list(rows[0][1]), rows[0][2])
    return {}


@operator("FM23", "box_origin_reset", ["P2.2"], 2, "Silent (periodic)",
          "move the box so its origin is 0 (or shift it by half a box if it already is); atoms unchanged")
def fm23(d, c):
    lo, hi = map(float, d.header_values("xlo xhi"))
    v = d.header_values("xlo xhi")
    shift = -lo if abs(lo) > 1e-9 else 0.5 * (hi - lo)
    d.set_header("xlo xhi", [fmt(lo + shift, v[0]), fmt(hi + shift, v[1])])
    return {"shift_x": shift}


@operator("FM24", "general_triclinic_header", ["P0.5"], 0, "Accepted by this LAMMPS (out of project scope)",
          "add an 'avec' line (general-triclinic keyword, unsupported in scope)")
def fm24(d, c):
    lo, hi = map(float, d.header_values("xlo xhi"))
    d.insert_lines(d.header_index("zlo zhi") + 1, [f"  {hi - lo:.6f} 0.0 0.0  avec"])
    return {}


@operator("FM25", "zlo_zhi_deleted", ["P0.8"], 0, "Silent, no warning (defaults -0.5 0.5)",
          "delete the 'zlo zhi' line")
def fm25(d, c):
    d.delete_line(d.header_index("zlo zhi"))
    return {}


@operator("FM26", "no_blank_after_keyword", ["P0.7"], 0, "Loud in tested cases",
          "remove the blank line after the 'Bonds' keyword")
def fm26(d, c):
    i = d.section_index("Bonds")
    if i is None or d.lines[i + 1].strip():
        return None
    d.delete_line(i + 1)
    return {}


@operator("FM28", "bond_to_absent_atom", ["P1.5"], 1, "Crash (SIGSEGV) or Loud",
          "delete the Atoms row of the second atom of a bond (ID < max ID), leaving the topology")
def fm28(d, c):
    rows = atom_rows(d)
    maxid = max(int(t[0]) for _, t, _ in rows)
    target = next(t[3] for _, t in topo_rows(d, "Bonds") if int(t[3]) < maxid)
    for i, t, com in rows:
        if t[0] == target:
            d.delete_line(i)
            break
    d.set_header("atoms", [d.header_int("atoms") - 1])
    return {"deleted_atom": int(target)}


@operator("FM29", "velocities_duplicate_id", ["P1.14"], 1, "Silent", "append a Velocities section in which "
          "the last atom ID is listed twice and the first atom has no row")
def fm29(d, c):
    ids = [t[0] for _, t, _ in atom_rows(d)]
    rows = [join_row([a, "0.0", "0.0", "0.0"]) for a in ids[1:]] + [join_row([ids[-1], "0.0", "0.0", "0.0"])]
    d.append_section("Velocities", rows)
    return {}


@operator("FM30", "negative_molecule_id", ["P1.8"], 1, "Silent", "set one molecule ID to -1")
def fm30(d, c):
    i, t, com = atom_rows(d)[0]
    t[1] = "-1"
    put(d, i, t, com)
    return {}


@operator("FM31", "masses_row_duplicated", ["P1.4"], 1, "Loud@run only (Tier 3a misses it)",
          "replace the second Masses row with a copy of the first")
def fm31(d, c):
    rows = d.section_rows("Masses")
    d.lines[rows[1][0]] = rows[0][1]
    return {}


@operator("FM33", "equal_length_style_comment", ["P1.11"], 1, "Silent (equal-length names)",
          "label the Atoms section '# bond' (same length as 'full')")
def fm33(d, c):
    i = d.section_index("Atoms")
    d.lines[i] = "Atoms # bond"
    return {}


@operator("FM34", "header_keyword_repeated", ["P0.10"], 0, "Silent (last value wins)",
          "repeat the 'atoms' header line with the count minus one")
def fm34(d, c):
    hi = d.header_index("atoms")
    n = d.header_int("atoms")
    d.insert_lines(hi + 1, [f"  {n - 1}  atoms"])
    return {}


@operator("FM35", "fortran_d_exponent", ["P0.3"], 0, "Loud", "write the first Masses value with a Fortran D exponent")
def fm35(d, c):
    i, line = d.section_rows("Masses")[0]
    toks, com = split_comment(line)
    toks[1] = f"{float(toks[1]):.6E}".replace("E", "D")
    put(d, i, toks, com)
    return {}


# ---- driver -----------------------------------------------------------------------------------
def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    if os.path.isdir(OUT):
        for f in glob.glob(os.path.join(OUT, "*")):
            os.remove(f)
    os.makedirs(OUT, exist_ok=True)
    manifest = []
    for parent in PARENTS:
        ppath = os.path.join(ROOT, parent)
        with open(os.path.splitext(ppath)[0] + ".json") as fh:
            pmeta = json.load(fh)
        ctx = Ctx(ppath, pmeta)
        for op in OPERATORS:
            d = DataText.read(ppath)
            try:
                params = op["fn"](d, ctx)
            except (KeyError, StopIteration, IndexError):
                params = None
            if params is None:
                continue
            name = f"{pmeta['id']}__{op['fm']}__{op['variant']}"
            out = os.path.join(OUT, name + ".data")
            d.write(out)
            meta = {
                "id": name, "file": os.path.relpath(out, ROOT), "sha256": sha256(out),
                "parent_id": pmeta["id"], "parent_file": parent, "parent_sha256": sha256(ppath),
                "failure_mode": op["fm"], "operator": op["fn"].__name__, "variant": op["variant"],
                "description": op["description"], "params": params,
                "expected_failing_properties": op["expect"], "expected_tier": op["tier"],
                "spec_expected_properties": op["spec_expect"],
                "expected_lammps_behaviour": op["lammps_expected"],
                "header_consistent": op["header_consistent"],
                "declared_config": pmeta["declared_config"], "overrides": pmeta.get("overrides", {}),
            }
            with open(os.path.join(OUT, name + ".json"), "w") as fh:
                json.dump(meta, fh, indent=2, default=str)
            manifest.append({k: meta[k] for k in ("id", "file", "parent_id", "failure_mode", "variant",
                                                   "expected_failing_properties", "expected_tier",
                                                   "expected_lammps_behaviour")})
    with open(os.path.join(OUT, "manifest.json"), "w") as fh:
        json.dump({"generated_by": "scripts/mutate.py", "operators": len(OPERATORS), "files": manifest}, fh, indent=2)
    fms = sorted({m["failure_mode"] for m in manifest})
    print(f"{len(manifest)} corrupted files from {len(PARENTS)} parents, {len(OPERATORS)} operators, "
          f"{len(fms)} failure modes: {', '.join(fms)}")


if __name__ == "__main__":
    main()
