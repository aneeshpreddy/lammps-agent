"""Task-correctness layer (PROPERTIES TC.1, TC.2). Separate from Tiers 0-3.

TC.2 compares a file with a trusted reference *property by property*. Atoms are matched by
position (minimum image) rather than by ID, so a consistent renumbering is not reported as a
difference while a changed type, charge, bond or position is. Similarity is not proof of
correctness; a disagreement is a finding to investigate (SPEC §7.8).
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional

import numpy as np

from .config import declared, periodic_flags
from .geometry import pairs_within
from .model import Model, build_model
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
    table = declared(cfg).get("type_name_elements") or {}
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
    tol_box = 10.0 ** (-min(m.box_decimals, r.box_decimals)) if min(m.box_decimals, r.box_decimals) > 0 else 1e-9
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


def run_tc(pf, m: Model, cfg, reference: Optional[str]) -> List[CheckResult]:
    out = [tc1_composition(m, cfg)]
    if reference:
        out.append(tc2_reference(pf, m, cfg, reference))
    return out
