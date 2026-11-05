"""Task-correctness layer (PROPERTIES TC.1, TC.2). Separate from Tiers 0-3.

TC.2 has three comparison modes (declared `tc_mode`, normally set per task; METRICS.md):
  positions  — atoms matched by minimum-image position (default; references built by the same route)
  graph      — position-free: the multiset of molecules, each identified by a Weisfeiler-Lehman hash
               of its typed, charged bond graph, must be identical; optional cell comparison
               (`tc_compare_cell`: true = all lengths and tilts; a list of axes = only those lengths,
               e.g. the lateral axes of a slab with an adsorbate). For deterministic structures built in a different geometry
               (minerals, PCE with explicit/alternating/block sequences).
  chemistry  — position- and sequence-free: per molecule, the multiset of elements, the net charge and
               the number of bonds on each element must match; every bond's (type, type) kind and every
               atom's (type, charge) must occur in the reference or in the declared join catalogue
               (`tc_allowed_bond_pairs`, `tc_allowed_type_charges`, built by eval/catalogue.py). For
               random-sequence PCE, where any draw of the requested architecture is equally correct.
               METRICS v1.2 (owner, 2026-11-05): v1.1 compared the count of each bond kind and the
               multiset of (type, charge), which depend on the draw: the bonds that join neighbouring
               units, and the types and charges of the atoms where an end group meets a unit (an H cap
               turns a CH into a CH2), so a correct draw could fail.

TC.2 compares a file with a trusted reference *property by property*. Atoms are matched by
position (minimum image) rather than by ID, so a consistent renumbering is not reported as a
difference while a changed type, charge, bond or position is. Similarity is not proof of
correctness; a disagreement is a finding to investigate (SPEC §7.8).
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional

import numpy as np

from .config import declared, element_table, periodic_flags
from .geometry import pairs_within
from .model import Model, bond_graph_components, build_model
from .parser import parse_file
from .result import FAIL, NOT_EVALUATED, PASS, CheckResult

MAXEX = 8


def _canon(kind, ats):
    if kind == "Bonds":
        return tuple(sorted(ats))
    if kind in ("Angles", "Dihedrals"):
        return min(tuple(ats), tuple(reversed(ats)))
    return tuple(ats)


def tc1_composition(m: Model, cfg) -> CheckResult:
    want = declared(cfg).get("expected_composition")
    if not want:
        return CheckResult("composition_vs_request", "TC.1", "TC", NOT_EVALUATED,
                           "no requested composition (input representation OD-D undecided)")
    table = element_table(cfg)
    got = Counter(table.get(m.type_names.get(int(t)), f"type{t}") for t in m.types)
    diff = {e: (got.get(e, 0), n) for e, n in want.items() if got.get(e, 0) != n}
    extra = {e: c for e, c in got.items() if e not in want}
    ok = not diff and not extra
    return CheckResult("composition_vs_request", "TC.1", "TC", PASS if ok else FAIL,
                       "" if ok else f"composition differs from request: {diff or ''} {('extra ' + str(extra)) if extra else ''}",
                       {"observed": dict(got), "requested": want})


def tc2_reference(pf, m: Model, cfg, ref_path: str) -> CheckResult:
    name, prop = "reference_comparison", "TC.2"
    try:
        rpf = parse_file(ref_path)
        r = build_model(rpf, m.atom_style, periodic_flags(cfg))
    except Exception as e:
        return CheckResult(name, prop, "TC", NOT_EVALUATED, f"reference unreadable: {e}")
    diffs: List[str] = []
    det: Dict = {"reference": ref_path, "reference_sha256": rpf.sha256}

    # counts ------------------------------------------------------------------------------------
    for key in ("atoms", "bonds", "angles", "dihedrals", "impropers", "atom types", "bond types",
                "angle types", "dihedral types", "improper types"):
        a, b = pf.header_int(key, 0), rpf.header_int(key, 0)
        if a != b:
            diffs.append(f"{key}: {a} vs reference {b}")
    # cell ----------------------------------------------------------------------------------------
    if m.cell is None or r.cell is None:
        return CheckResult(name, prop, "TC", NOT_EVALUATED, "box undefined in file or reference")
    tol_box = max(10.0 ** (-min(m.box_decimals, r.box_decimals)), 1e-9) if min(m.box_decimals, r.box_decimals) > 0 else 1e-9
    for lab, a, b in (("box lengths", m.cell.lengths, r.cell.lengths), ("tilt", m.cell.tilt, r.cell.tilt),
                      ("origin", m.cell.origin, r.cell.origin)):
        if np.max(np.abs(a - b)) > tol_box:
            diffs.append(f"{lab}: {np.round(a, 6).tolist()} vs reference {np.round(b, 6).tolist()}")
    # masses per type -----------------------------------------------------------------------------
    for t in sorted(set(m.masses) | set(r.masses)):
        if abs(m.masses.get(t, -1) - r.masses.get(t, -1)) > 10.0 ** -4:
            diffs.append(f"Masses type {t}: {m.masses.get(t)} vs reference {r.masses.get(t)}")
    # atom matching by position --------------------------------------------------------------------
    tol_pos = np.sqrt(3) * (10.0 ** -m.xyz_decimals + 10.0 ** -r.xyz_decimals) + 1e-9
    n = m.natoms
    both = np.vstack([m.xyz, r.xyz])
    I, J, D = pairs_within(r.cell, both, max(tol_pos, 1e-6))
    cross = (I < n) & (J >= n)
    fi, rj = I[cross], J[cross] - n
    match_f = Counter(fi.tolist())
    match_r = Counter(rj.tolist())
    mapping = {int(a): int(b) for a, b in zip(fi, rj) if match_f[a] == 1 and match_r[b] == 1}
    unmatched_f = [int(m.ids[i]) for i in range(n) if i not in mapping]
    unmatched_r = sorted(set(range(r.natoms)) - set(mapping.values()))
    det["matched_atoms"] = len(mapping)
    if unmatched_f or unmatched_r:
        diffs.append(f"{len(unmatched_f)} atom(s) with no unique positional match in the reference "
                     f"(e.g. IDs {unmatched_f[:5]}); {len(unmatched_r)} reference atom(s) unmatched "
                     f"(tolerance {tol_pos:.2g} Å)")
    # per-atom properties via the mapping ----------------------------------------------------------
    use_names = bool(m.type_names) and bool(r.type_names)
    tdiff, qdiff = [], []
    qtol = 10.0 ** -min(m.q_decimals, r.q_decimals) if (m.q is not None and r.q is not None) else None
    for i, j in mapping.items():
        ta = m.type_names.get(int(m.types[i])) if use_names else int(m.types[i])
        tb = r.type_names.get(int(r.types[j])) if use_names else int(r.types[j])
        if ta != tb or int(m.types[i]) != int(r.types[j]):
            tdiff.append((int(m.ids[i]), ta, tb))
        if qtol is not None and abs(m.q[i] - r.q[j]) > qtol / 2 + 1e-12:
            qdiff.append((int(m.ids[i]), float(m.q[i]), float(r.q[j])))
    if tdiff:
        diffs.append(f"{len(tdiff)} atom(s) with a different type than the matched reference atom "
                     f"(e.g. ID {tdiff[0][0]}: {tdiff[0][1]} vs {tdiff[0][2]})")
    if qdiff:
        diffs.append(f"{len(qdiff)} atom(s) with a different charge (e.g. ID {qdiff[0][0]}: "
                     f"{qdiff[0][1]} vs {qdiff[0][2]})")
    # topology multisets in reference numbering ----------------------------------------------------
    fidx, ridx = m.index_of(), r.index_of()
    for kind in ("Bonds", "Angles", "Dihedrals", "Impropers"):
        a, b = m.topology.get(kind), r.topology.get(kind)
        ca, cb = Counter(), Counter()
        lost = 0
        if a is not None:
            for t, ats in zip(a.types.tolist(), a.atoms.tolist()):
                try:
                    ca[(t,) + _canon(kind, [int(r.ids[mapping[fidx[x]]]) for x in ats])] += 1
                except KeyError:
                    lost += 1
        if b is not None:
            for t, ats in zip(b.types.tolist(), b.atoms.tolist()):
                cb[(t,) + _canon(kind, ats)] += 1
        extra, missing = ca - cb, cb - ca
        if extra or missing or lost:
            diffs.append(f"{kind}: {sum(missing.values())} reference entr(ies) missing, {sum(extra.values())} "
                         f"extra/changed" + (f", {lost} referencing unmatched atoms" if lost else ""))
    # coefficients written in the DATA FILE (row values per type ID) ----------------------------
    from .parser import SECTIONS_COEFF
    for sec in SECTIONS_COEFF:
        a, b = pf.section(sec), rpf.section(sec)
        if a is None and b is None:
            continue
        if (a is None) != (b is None):
            diffs.append(f"{sec}: present in only one of file / reference")
            continue
        nid = 2 if sec == "PairIJ Coeffs" else 1

        def table(s):
            out = {}
            for row in s.rows:
                key = tuple(row.tokens[:nid])
                try:
                    out[key] = tuple(float(x) for x in row.tokens[nid:])
                except ValueError:
                    out[key] = tuple(row.tokens[nid:])
            return out
        ta, tb = table(a), table(b)
        changed = [k for k in set(ta) | set(tb) if ta.get(k) != tb.get(k)]
        if changed:
            diffs.append(f"{sec}: {len(changed)} type row(s) with different coefficients "
                         f"(e.g. type {' '.join(sorted(changed)[0])})")
    det["differences"] = diffs[:MAXEX]
    return CheckResult(name, prop, "TC", FAIL if diffs else PASS,
                       f"{len(diffs)} difference(s) from the reference; first: {diffs[0]}" if diffs else "",
                       det, calibration="derived:representation")


# ---- position-free modes ------------------------------------------------------------------------
def _labels(m: Model):
    names = m.type_names or {}
    q = m.q if m.q is not None else np.zeros(m.natoms)
    return [f"{names.get(int(t), int(t))}|{round(float(c), 3):+.3f}" for t, c in zip(m.types, q)]


def _adjacency(m: Model):
    idx = m.index_of()
    adj = [[] for _ in range(m.natoms)]
    b = m.topology.get("Bonds")
    if b is not None:
        for i, j in b.atoms.tolist():
            if i in idx and j in idx:
                adj[idx[i]].append(idx[j])
                adj[idx[j]].append(idx[i])
    return adj


def molecule_hashes(m: Model, rounds: int = 24) -> Counter:
    """Weisfeiler-Lehman hash per bonded molecule (labels: type name + charge to 3 decimals).
    Not a complete isomorphism test, but it separates different sequences, types, charges and
    connectivities within `rounds` bonds; equal hashes for all molecules is the TC criterion."""
    import hashlib
    lab = _labels(m)
    adj = _adjacency(m)
    cur = lab
    for _ in range(rounds):
        cur = [hashlib.sha1((cur[i] + "(" + ",".join(sorted(cur[j] for j in adj[i])) + ")").encode()).hexdigest()[:16]
               for i in range(m.natoms)]
    comp = bond_graph_components(m)
    mols: Dict[int, List[str]] = {}
    for i, c in enumerate(comp):
        mols.setdefault(int(c), []).append(cur[i])
    return Counter(hashlib.sha1("".join(sorted(v)).encode()).hexdigest()[:16] for v in mols.values())


def _type_name(m: Model, i: int) -> str:
    return str((m.type_names or {}).get(int(m.types[i]), int(m.types[i])))


def type_charges(m: Model) -> set:
    """Every (atom type, charge rounded to 1e-3 e) that occurs."""
    q = m.q if m.q is not None else np.zeros(m.natoms)
    return {(_type_name(m, i), f"{round(float(q[i]), 3):+.3f}") for i in range(m.natoms)}


def bond_kinds(m: Model) -> set:
    """Every (type, type) pair joined by a bond, as sorted name pairs."""
    adj = _adjacency(m)
    return {tuple(sorted((_type_name(m, i), _type_name(m, j)))) for i in range(m.natoms) for j in adj[i] if i < j}


def molecule_chemistry(m: Model, elements: Dict[str, str] = None) -> Counter:
    """Per molecule: (element multiset, net charge, bonds per element); a type without an element counts as itself."""
    names = m.type_names or {}
    elements = elements or {}
    q = m.q if m.q is not None else np.zeros(m.natoms)
    adj = _adjacency(m)
    comp = bond_graph_components(m)
    mols: Dict[int, List[int]] = {}
    for i, c in enumerate(comp):
        mols.setdefault(int(c), []).append(i)
    out = Counter()
    for atoms in mols.values():
        # elements, not types: where an end group meets a unit, the atom types and bond-increment charges
        # depend on which unit it is; types and charges are compared as sets (type_charges, bond_kinds)
        el = {i: (lambda n: elements.get(n, n))(str(names.get(int(m.types[i]), int(m.types[i])))) for i in atoms}
        tc = Counter(el.values())
        # bonds per element: fixed by the architecture, whatever the order of the units
        deg = Counter()
        for i in atoms:
            deg[el[i]] += len(adj[i])
        key = (tuple(sorted(tc.items())), round(float(sum(q[i] for i in atoms)), 3), tuple(sorted(deg.items())))
        out[key] += 1
    return out


def tc2_position_free(pf, m: Model, cfg, ref_path: str, mode: str) -> CheckResult:
    name, prop = "reference_comparison", "TC.2"
    try:
        rpf = parse_file(ref_path)
        r = build_model(rpf, m.atom_style, periodic_flags(cfg))
    except Exception as e:
        return CheckResult(name, prop, "TC", NOT_EVALUATED, f"reference unreadable: {e}")
    diffs: List[str] = []
    for key in ("atoms", "bonds", "angles", "dihedrals", "impropers"):
        a, b = pf.header_int(key, 0), rpf.header_int(key, 0)
        if a != b:
            diffs.append(f"{key}: {a} vs reference {b}")
    if mode == "graph":
        a, b = molecule_hashes(m), molecule_hashes(r)
        what = "molecular graphs"
    else:
        table = element_table(cfg)
        a, b = molecule_chemistry(m, table), molecule_chemistry(r, table)
        what = "molecule chemistries"
        dec = declared(cfg)
        allowed = bond_kinds(r) | {tuple(sorted(map(str, p))) for p in dec.get("tc_allowed_bond_pairs") or []}
        extra = sorted(bond_kinds(m) - allowed)
        if extra:
            diffs.append(f"bond kinds in neither the reference nor the join catalogue: "
                         f"{', '.join('-'.join(p) for p in extra[:5])}" + (" …" if len(extra) > 5 else ""))
        allowed = type_charges(r) | {(str(t), f"{float(c):+.3f}") for t, c in dec.get("tc_allowed_type_charges") or []}
        extra = sorted(type_charges(m) - allowed)
        if extra:
            diffs.append(f"atom (type, charge) values in neither the reference nor the join catalogue: "
                         f"{', '.join(f'{t} {c} e' for t, c in extra[:5])}" + (" …" if len(extra) > 5 else ""))
    if a != b:
        diffs.append(f"{what}: {sum((a - b).values())} molecule(s) not in the reference, "
                     f"{sum((b - a).values())} reference molecule(s) not reproduced (of {sum(b.values())})")
    cc = declared(cfg).get("tc_compare_cell")
    if cc and m.cell is not None and r.cell is not None:
        # true: all lengths and tilts; a list of axes (e.g. ["x", "y"]): only those lengths, for slabs whose
        # length along the surface normal depends on the adsorbate's height
        tol = 1e-3
        ax = [0, 1, 2] if cc is True else ["xyz".index(a) for a in cc]
        bad_len = np.max(np.abs(m.cell.lengths[ax] - r.cell.lengths[ax])) > tol
        bad_tilt = cc is True and np.max(np.abs(m.cell.tilt - r.cell.tilt)) > tol
        if bad_len or bad_tilt:
            diffs.append(f"cell ({'all' if cc is True else ','.join(cc)}): lengths {np.round(m.cell.lengths, 4).tolist()} "
                         f"tilt {np.round(m.cell.tilt, 4).tolist()} vs reference {np.round(r.cell.lengths, 4).tolist()} "
                         f"{np.round(r.cell.tilt, 4).tolist()}")
    det = {"reference": ref_path, "reference_sha256": rpf.sha256, "mode": mode, "differences": diffs[:MAXEX],
           "molecules": sum(b.values())}
    return CheckResult(name, prop, "TC", FAIL if diffs else PASS,
                       f"{len(diffs)} difference(s) from the reference ({mode} mode); first: {diffs[0]}" if diffs else "",
                       det, calibration="exact")


def run_tc(pf, m: Model, cfg, reference: Optional[str]) -> List[CheckResult]:
    out = [tc1_composition(m, cfg)]
    if reference:
        mode = declared(cfg).get("tc_mode", "positions")
        if mode == "positions":
            out.append(tc2_reference(pf, m, cfg, reference))
        elif mode in ("graph", "chemistry"):
            out.append(tc2_position_free(pf, m, cfg, reference, mode))
        else:
            out.append(CheckResult("reference_comparison", "TC.2", "TC", NOT_EVALUATED, f"unknown tc_mode {mode!r}"))
    return out
