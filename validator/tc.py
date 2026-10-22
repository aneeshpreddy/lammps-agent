"""Task-correctness layer (PROPERTIES TC.1, TC.2). Separate from Tiers 0-3.

TC.2 has three comparison modes (declared `tc_mode`, normally set per task; METRICS.md):
  positions  — atoms matched by minimum-image position (default; references built by the same route)
  graph      — position-free: the multiset of molecules, each identified by a Weisfeiler-Lehman hash
               of its typed, charged bond graph, must be identical; optional cell comparison
               (`tc_compare_cell`). For deterministic structures built in a different geometry
               (minerals, PCE with explicit/alternating/block sequences).
  chemistry  — position- and sequence-free: per molecule, the multiset of (atom type, charge), the
               net charge and the counts of bond type-signatures must match. For random-sequence PCE,
               where any draw of the requested architecture is equally correct.

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


def molecule_chemistry(m: Model) -> Counter:
    names = m.type_names or {}
    q = m.q if m.q is not None else np.zeros(m.natoms)
    adj = _adjacency(m)
    comp = bond_graph_components(m)
    mols: Dict[int, List[int]] = {}
    for i, c in enumerate(comp):
        mols.setdefault(int(c), []).append(i)
    out = Counter()
    for atoms in mols.values():
        # (type, charge) multiset: bond-increment charges depend only on bonded neighbours, so this is
        # independent of the monomer sequence but catches redistributed charges
        tc = Counter(f"{names.get(int(m.types[i]), int(m.types[i]))}|{round(float(q[i]), 3):+.3f}" for i in atoms)
        bc = Counter("|".join(sorted((str(names.get(int(m.types[i]), "")), str(names.get(int(m.types[j]), "")))))
                     for i in atoms for j in adj[i] if i < j)
        key = (tuple(sorted(tc.items())), round(float(sum(q[i] for i in atoms)), 3), tuple(sorted(bc.items())))
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
        a, b = molecule_chemistry(m), molecule_chemistry(r)
        what = "molecule chemistries"
    if a != b:
        diffs.append(f"{what}: {sum((a - b).values())} molecule(s) not in the reference, "
                     f"{sum((b - a).values())} reference molecule(s) not reproduced (of {sum(b.values())})")
    if declared(cfg).get("tc_compare_cell") and m.cell is not None and r.cell is not None:
        tol = 1e-3
        if np.max(np.abs(m.cell.lengths - r.cell.lengths)) > tol or np.max(np.abs(m.cell.tilt - r.cell.tilt)) > tol:
            diffs.append(f"cell: lengths {np.round(m.cell.lengths, 4).tolist()} tilt {np.round(m.cell.tilt, 4).tolist()} vs "
                         f"reference {np.round(r.cell.lengths, 4).tolist()} {np.round(r.cell.tilt, 4).tolist()}")
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
