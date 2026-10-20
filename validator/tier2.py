"""Tier 2 — physically plausible (PROPERTIES §8.3, P2.1–P2.8).

Every tolerance comes from the calibration record (calibration/*.json, built by scripts/calibrate.py
from the declared references) or from a representation-precision derivation (§8.5 rule 3).
A property without a tolerance returns NOT_CALIBRATED, never PASS.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from .config import declared, element_table, load_calibration
from .elements import STANDARD_MASS, nearest_element
from .geometry import AMU_PER_A3_TO_G_PER_CM3, pairs_within, tilt_checks
from .model import Model, bond_graph_components
from .parser import ParsedFile
from .result import (FAIL, NOT_APPLICABLE, NOT_CALIBRATED, NOT_EVALUATED, PASS, CheckResult)

MAXEX = 10
# Tier 1 properties each Tier 2 property depends on (§8.2 item 3).
DEPENDS = {
    "P2.1": [], "P2.2": ["P1.5"], "P2.3": ["P1.2", "P1.3", "P1.5"], "P2.4": ["P1.3", "P1.5"],
    "P2.5": ["P1.3", "P1.4"], "P2.6": ["P1.4"], "P2.7": ["P1.5", "P1.9"], "P2.8": [],
}
NAMES = {"P2.1": "net_charge", "P2.2": "cell_consistency", "P2.3": "atom_overlap", "P2.4": "bond_lengths",
         "P2.5": "density", "P2.6": "mass_to_element", "P2.7": "bond_image_consistency", "P2.8": "tilt_bound"}


def _c(prop, verdict, msg="", details=None, warnings=None, cal=None):
    return CheckResult(NAMES[prop], prop, 2, verdict, msg, details or {}, warnings or [], cal)


def _cal_tag(cal: Optional[dict]) -> Optional[str]:
    if not cal:
        return None
    return f"{cal.get('status', 'UNKNOWN').lower()}:{cal.get('calibration_id')}@v{cal.get('version')}"


def _element_map(m: Model, cfg) -> Dict[int, Optional[str]]:
    table = element_table(cfg)
    return {t: table.get(m.type_names.get(t)) for t in range(1, m.n_atom_types + 1)}


# ----------------------------------------------------------------------------------------------
def p2_1_charge(pf, m: Model, cfg, cal) -> CheckResult:
    nc = declared(cfg).get("net_charge")
    if m.q is None:
        return _c("P2.1", NOT_APPLICABLE, f"atom_style {m.atom_style} carries no charges")
    if not nc or nc.get("required") is None:
        return _c("P2.1", NOT_EVALUATED, "net-charge requirement not declared (OD-H)")
    problems = []
    qsum = float(m.q.sum())
    # Rounding floor (PROPERTIES §8.5 rule 3, amended v0.5). 'worst_case': every charge off by half a
    # unit in the last printed place, N*0.5*10^-d. 'statistical' (default from v0.5): independent
    # uniform rounding errors, 5 sigma of their sum, 5*sqrt(N)*10^-d/sqrt(12). Both get a floating-point
    # floor so files printed at full double precision (write_data) are not judged on 1e-15 noise.
    mode = nc.get("floor", "worst_case")
    step = 10.0 ** (-m.q_decimals)
    worst = m.natoms * 0.5 * step
    stat = 5.0 * np.sqrt(m.natoms) * step / np.sqrt(12.0)
    fp = m.natoms * 1e-12 * max(1.0, float(np.abs(m.q).max()) if m.natoms else 1.0)
    floor = (stat if mode == "statistical" else worst) + fp
    tau = max(floor, float(nc.get("tolerance_e") or 0.0))
    target = float(nc.get("target", 0.0))
    if nc.get("required") and abs(qsum - target) > tau:
        problems.append(f"total charge = {qsum:+.6f} e, target {target:+.4f} e "
                        f"(tolerance {tau:.4g} e = {mode} rounding floor for {m.natoms} charges at {m.q_decimals} decimals)")
    if declared(cfg).get("charged_system") and not np.any(m.q != 0.0):
        problems.append("all charges are zero, but the declared configuration describes a charged system (P2.1b)")
    det = {"total_charge": qsum, "target": target, "tolerance": tau, "floor_mode": mode, "rounding_floor": floor,
           "worst_case_floor": worst, "statistical_floor": stat, "charge_decimals": m.q_decimals, "natoms": m.natoms}
    return _c("P2.1", FAIL if problems else PASS, "; ".join(problems), det,
              cal=f"derived:{mode}-rounding-floor" + (f"+declared {nc.get('tolerance_e')}" if nc.get("tolerance_e") else ""))


def p2_2_cell(pf, m: Model, cfg, cal) -> CheckResult:
    if m.cell is None:
        return _c("P2.2", NOT_EVALUATED, "box not defined")
    policy = declared(cfg).get("coordinate_wrapping")
    per = m.cell.periodic
    s = m.cell.fractional(m.xyz)
    if not np.all(np.isfinite(s)):
        return _c("P2.2", FAIL, "non-finite fractional coordinates")
    lo, hi = s.min(0), s.max(0)
    det = {"policy": policy, "frac_min": lo.round(4).tolist(), "frac_max": hi.round(4).tolist()}
    if policy == "wrapped":
        eps = max(10.0 ** (-m.xyz_decimals) / float(m.cell.perpendicular_widths().min()), 1e-9)
        out = np.zeros(len(s), bool)
        for d in range(3):
            if per[d]:
                out |= (s[:, d] < -eps) | (s[:, d] >= 1.0 + eps)
        bad = np.nonzero(out)[0]
        det.update({"outside": int(len(bad)), "eps_frac": eps})
        if len(bad):
            k = bad[0]
            return _c("P2.2", FAIL, f"{len(bad)} atom(s) outside the cell in a periodic dimension under the declared "
                      f"'wrapped' policy (first: line {m.atom_linenos[k]}, s={s[k].round(4).tolist()})", det,
                      cal="derived:representation")
        return _c("P2.2", PASS, "", det, cal="derived:representation")
    if policy == "unwrapped_clusters":
        cc = (cal or {}).get("cell", {})
        tau = cc.get("tau_centroid")
        if tau is None:
            return _c("P2.2", NOT_CALIBRATED, "no calibrated centroid tolerance (τ_cell)", det)
        comp = bond_graph_components(m)
        labels, inv = np.unique(comp, return_inverse=True)
        cent = np.zeros((len(labels), 3))
        np.add.at(cent, inv, s)
        cent /= np.bincount(inv)[:, None]
        exc = np.zeros(len(labels))
        for d in range(3):
            if per[d]:
                exc = np.maximum(exc, np.maximum(-cent[:, d], cent[:, d] - 1.0))
        worst = int(np.argmax(exc)) if len(exc) else 0
        det.update({"clusters": int(len(labels)), "max_centroid_excursion": float(exc.max()) if len(exc) else 0.0,
                    "tau_centroid": tau})
        if len(exc) and exc.max() > tau:
            nbad = int((exc > tau).sum())
            return _c("P2.2", FAIL, f"{nbad} bonded cluster(s) with centroid outside the cell by more than "
                      f"τ={tau} (fractional); worst excursion {exc[worst]:.4f}, centroid s={cent[worst].round(4).tolist()}",
                      det, cal=_cal_tag(cal))
        return _c("P2.2", PASS, "", det, cal=_cal_tag(cal))
    return _c("P2.2", NOT_EVALUATED, f"coordinate_wrapping policy not declared ({policy!r})", det)


def bonded_index_pairs(m: Model) -> set:
    """Index pairs (i<j) joined by a bond. P2.3 excludes exactly these (P2.4 covers them)."""
    idx = m.index_of()
    t = m.topology.get("Bonds")
    if t is None:
        return set()
    out = set()
    for a, b in t.atoms.tolist():
        i, j = idx[a], idx[b]
        out.add((min(i, j), max(i, j)))
    return out


def p2_3_overlap(pf, m: Model, cfg, cal) -> CheckResult:
    if m.cell is None:
        return _c("P2.3", NOT_EVALUATED, "box not defined")
    el = _element_map(m, cfg)
    if any(e is None for t, e in el.items() if t in set(m.types.tolist())):
        return _c("P2.3", NOT_EVALUATED, "element of some atom types unknown (type names / OD-J map)",
                  {"elements": el})
    ov = (cal or {}).get("overlap", {}).get("pairs", {})
    if not ov:
        return _c("P2.3", NOT_CALIBRATED, "no calibrated d_min table")
    dmin = {k: v["d_min"] for k, v in ov.items()}
    cutoff = max(dmin.values())
    I, J, D = pairs_within(m.cell, m.xyz, cutoff)
    bonded = bonded_index_pairs(m)
    viol, uncal = [], []
    for i, j, d in zip(I.tolist(), J.tolist(), D.tolist()):
        if (i, j) in bonded:
            continue
        key = "|".join(sorted((el[int(m.types[i])], el[int(m.types[j])])))
        lim = dmin.get(key)
        if lim is None:
            uncal.append((key, d, i, j))
        elif d < lim:
            viol.append((key, d, i, j))
    det = {"cutoff": cutoff, "violations": len(viol), "uncalibrated_close_pairs": len(uncal),
           "examples": [{"pair": k, "distance": round(d, 4), "atom_ids": [int(m.ids[i]), int(m.ids[j])],
                         "d_min": dmin.get(k)} for k, d, i, j in sorted(viol, key=lambda x: x[1])[:MAXEX]]}
    if viol:
        k, d, i, j = min(viol, key=lambda x: x[1])
        return _c("P2.3", FAIL, f"{len(viol)} non-bonded pair(s) closer than d_min; closest: atoms "
                  f"{int(m.ids[i])}-{int(m.ids[j])} ({k}) at {d:.4f} Å < {dmin[k]:.3f} Å", det, cal=_cal_tag(cal))
    if uncal:
        det["uncalibrated_pairs"] = sorted({k for k, *_ in uncal})
        return _c("P2.3", NOT_CALIBRATED, f"{len(uncal)} close pair(s) of element pairs with no calibrated d_min: "
                  f"{det['uncalibrated_pairs']}", det, cal=_cal_tag(cal))
    return _c("P2.3", PASS, "", det, cal=_cal_tag(cal))


def p2_4_bonds(pf, m: Model, cfg, cal) -> CheckResult:
    b = m.topology.get("Bonds")
    if b is None or not len(b.ids):
        return _c("P2.4", NOT_APPLICABLE, "no bonds")
    if m.cell is None:
        return _c("P2.4", NOT_EVALUATED, "box not defined")
    table = (cal or {}).get("bond_length", {}).get("pairs", {})
    etable = (cal or {}).get("bond_length", {}).get("element_pairs", {})
    if not table and not etable:
        return _c("P2.4", NOT_CALIBRATED, "no calibrated bond-length windows")
    if not m.type_names:
        return _c("P2.4", NOT_EVALUATED, "atom type names unknown (bond windows are keyed by type names; OD-J)")
    el = _element_map(m, cfg)
    idx = m.index_of()
    ii = np.array([idx[int(a)] for a in b.atoms[:, 0]])
    jj = np.array([idx[int(a)] for a in b.atoms[:, 1]])
    L = m.cell.min_image_distances(m.xyz[jj] - m.xyz[ii])
    viol, uncal, by_element = [], [], 0
    for k in range(len(L)):
        ni, nj = m.type_names.get(int(m.types[ii[k]]), "?"), m.type_names.get(int(m.types[jj[k]]), "?")
        key = "|".join(sorted((ni, nj)))
        w = table.get(key)
        if w is None:     # fall back to the element-pair window (wider, but force-field independent)
            ei, ej = el.get(int(m.types[ii[k]])), el.get(int(m.types[jj[k]]))
            if ei and ej:
                w = etable.get("|".join(sorted((ei, ej))))
                if w is not None:
                    by_element += 1
                    key = key + " [element " + "|".join(sorted((ei, ej))) + "]"
        if w is None:
            uncal.append((key, L[k], k))
        elif not (w["lo"] <= L[k] <= w["hi"]):
            viol.append((key, L[k], k, w))
    det = {"bonds": int(len(L)), "violations": len(viol), "uncalibrated_bonds": len(uncal),
           "judged_by_element_pair_window": by_element,
           "length_min": float(L.min()), "length_max": float(L.max()),
           "examples": [{"line": b.linenos[k], "pair": key, "length": round(float(l), 4),
                         "window": [w["lo"], w["hi"]]} for key, l, k, w in viol[:MAXEX]]}
    if viol:
        key, l, k, w = max(viol, key=lambda x: abs(x[1] - (x[3]["lo"] + x[3]["hi"]) / 2))
        return _c("P2.4", FAIL, f"{len(viol)} bond(s) outside the calibrated window; worst: line {b.linenos[k]} "
                  f"{key} = {l:.4f} Å, window [{w['lo']:.3f}, {w['hi']:.3f}] Å", det, cal=_cal_tag(cal))
    if uncal:
        det["uncalibrated_pairs"] = sorted({k for k, *_ in uncal})
        return _c("P2.4", NOT_CALIBRATED, f"{len(uncal)} bond(s) between type pairs with no calibrated window: "
                  f"{det['uncalibrated_pairs'][:5]}", det, cal=_cal_tag(cal))
    return _c("P2.4", PASS, "", det, cal=_cal_tag(cal))


def p2_5_density(pf, m: Model, cfg, cal) -> CheckResult:
    units = declared(cfg).get("units")
    if units not in ("real", "metal"):
        return _c("P2.5", NOT_EVALUATED, f"density conversion not defined for units {units!r} (OD-C3)")
    if m.cell is None:
        return _c("P2.5", NOT_EVALUATED, "box not defined")
    fam = declared(cfg).get("density_family")
    if not m.masses:
        return _c("P2.5", NOT_EVALUATED, "no masses in the DATA FILE")
    total = float(sum(m.masses.get(int(t), 0.0) for t in m.types))
    rho = total / m.cell.volume * AMU_PER_A3_TO_G_PER_CM3
    det = {"density_g_cm3": rho, "total_mass_amu": total, "volume_A3": m.cell.volume, "family": fam}
    fams = (cal or {}).get("density", {})
    if fam is None:
        return _c("P2.5", NOT_CALIBRATED, f"density family not declared (ρ = {rho:.4f} g/cm³)", det)
    entry = fams.get(fam)
    if entry is None:
        return _c("P2.5", NOT_CALIBRATED, f"no calibrated density range for family '{fam}' (ρ = {rho:.4f} g/cm³)", det)
    if entry.get("applicable") is False:
        return _c("P2.5", NOT_APPLICABLE, f"family '{fam}': {entry.get('basis', 'not a bulk system')}", det)
    det.update({"window": [entry["lo"], entry["hi"]]})
    ok = entry["lo"] <= rho <= entry["hi"]
    return _c("P2.5", PASS if ok else FAIL,
              "" if ok else f"density {rho:.4f} g/cm³ outside [{entry['lo']:.4f}, {entry['hi']:.4f}] for family '{fam}'",
              det, cal=_cal_tag(cal))


def p2_6_masses(pf, m: Model, cfg, cal) -> CheckResult:
    if not m.masses:
        return _c("P2.6", NOT_EVALUATED, "no Masses section")
    tau = (cal or {}).get("mass", {}).get("tau_m_amu")
    if tau is None:
        return _c("P2.6", NOT_CALIBRATED, "τ_m not calibrated")
    el = _element_map(m, cfg)
    bad, unknown = [], []
    for t in range(1, m.n_atom_types + 1):
        e = el.get(t)
        if e is None or e not in STANDARD_MASS or t not in m.masses:
            unknown.append(t)
            continue
        dm = abs(m.masses[t] - STANDARD_MASS[e])
        if dm > tau:
            near = nearest_element(m.masses[t])[0]
            bad.append(f"type {t} ({m.type_names.get(t)}→{e}): mass {m.masses[t]} differs from {e} "
                       f"{STANDARD_MASS[e]} by {dm:.4f} amu (nearest element by mass: {near})")
    det = {"tau_m_amu": tau, "elements": {str(k): v for k, v in el.items()}, "unmapped_types": unknown}
    if bad:
        return _c("P2.6", FAIL, f"{len(bad)} type(s) whose mass does not match the mapped element; first: {bad[0]}",
                  dict(det, problems=bad[:MAXEX]), cal=_cal_tag(cal))
    if unknown:
        return _c("P2.6", NOT_EVALUATED, f"type(s) {unknown[:MAXEX]} have no element mapping (OD-J)", det)
    return _c("P2.6", PASS, "", det, cal=_cal_tag(cal))


def p2_7_image_consistency(pf, m: Model, cfg, cal) -> CheckResult:
    pol = declared(cfg).get("image_consistency", "not_applicable")
    if pol != "required":
        return _c("P2.7", NOT_APPLICABLE, f"no declared use of unwrapped coordinates (image_consistency: {pol})")
    b = m.topology.get("Bonds")
    if b is None or not len(b.ids):
        return _c("P2.7", NOT_APPLICABLE, "no bonds")
    if m.cell is None:
        return _c("P2.7", NOT_EVALUATED, "box not defined")
    idx = m.index_of()
    ii = np.array([idx[int(a)] for a in b.atoms[:, 0]])
    jj = np.array([idx[int(a)] for a in b.atoms[:, 1]])
    img = m.image if m.image is not None else np.zeros((m.natoms, 3), dtype=np.int64)
    with np.errstate(all="ignore"):
        unwrapped = (m.xyz[jj] + img[jj] @ m.cell.H.T) - (m.xyz[ii] + img[ii] @ m.cell.H.T)
    mi = m.cell.min_image_vectors(m.xyz[jj] - m.xyz[ii])
    dev = np.linalg.norm(unwrapped - mi, axis=1)
    nmax = int(np.abs(img).max()) if len(img) else 0
    # printed-precision term + image term + a floating-point floor: writers that print 16-17 digits
    # (e.g. ASE) would otherwise push tau below double-precision rounding noise (~1e-15 x |x|).
    fp_floor = 1e-12 * max(1.0, float(np.abs(m.xyz).max()), float(m.cell.lengths.max()) * (1 + nmax))
    tau = (2 * np.sqrt(3) * 10.0 ** (-m.xyz_decimals)
           + (2 * nmax * np.sqrt(3) * 0.5 * 10.0 ** (-m.box_decimals) if nmax else 0.0) + fp_floor)
    bad = np.nonzero(dev > tau)[0]
    det = {"bonds": int(len(dev)), "inconsistent": int(len(bad)), "tau_img": tau, "max_deviation": float(dev.max()),
           "image_flags_present": m.image is not None}
    if len(bad):
        k = int(bad[np.argmax(dev[bad])])
        return _c("P2.7", FAIL, f"{len(bad)} bond(s) whose unwrapped vector differs from the minimum-image vector "
                  f"(worst: line {b.linenos[k]}, |Δ| = {dev[k]:.4f} Å > τ_img = {tau:.2g} Å)", det,
                  cal="derived:representation")
    return _c("P2.7", PASS, "", det, cal="derived:representation")


def p2_8_tilt(pf, m: Model, cfg, cal) -> CheckResult:
    if m.cell is None:
        return _c("P2.8", NOT_EVALUATED, "box not defined")
    if not m.cell.triclinic:
        return _c("P2.8", PASS, "orthogonal box")
    pol = declared(cfg).get("tilt_policy", "both")
    action = declared(cfg).get("tilt_violation", "fail")
    tc = tilt_checks(m.cell)
    viol = []
    if pol in ("doc", "both") and tc["doc"]:
        viol.append("documented bound broken: " + ", ".join(
            f"|{k}|={v['value']:.4f} > {v['bound']:.4f}" for k, v in tc["doc"].items()))
    if pol in ("source", "both") and tc["source"]:
        viol.append("LAMMPS skew-warning criterion met: " + ", ".join(f"{k}={v:.3f} > 0.5" for k, v in tc["source"].items()))
    det = {"tilt": m.cell.tilt.tolist(), "lengths": m.cell.lengths.tolist(), "policy": pol,
           "doc_violations": tc["doc"], "source_violations": tc["source"]}
    if viol and action == "fail":
        return _c("P2.8", FAIL, "; ".join(viol), det, cal="exact")
    return _c("P2.8", PASS, "", det, warnings=viol, cal="exact")


TIER2 = {"P2.1": p2_1_charge, "P2.2": p2_2_cell, "P2.3": p2_3_overlap, "P2.4": p2_4_bonds,
         "P2.5": p2_5_density, "P2.6": p2_6_masses, "P2.7": p2_7_image_consistency, "P2.8": p2_8_tilt}


def run_tier2(pf: ParsedFile, m: Model, cfg, tier1: List[CheckResult]) -> List[CheckResult]:
    cal = load_calibration(cfg)
    t1 = {c.property: c.verdict for c in tier1}
    out = []
    for prop, fn in TIER2.items():
        failed = [d for d in DEPENDS[prop] if t1.get(d) == FAIL]
        if failed:
            out.append(_c(prop, NOT_EVALUATED, f"depends on failed Tier 1 propert(ies) {failed}"))
            continue
        try:
            out.append(fn(pf, m, cfg, cal))
        except Exception as e:   # a crash is not a verdict (plan Day 6)
            out.append(_c(prop, NOT_EVALUATED, f"internal error while checking: {type(e).__name__}: {e}"))
    return out
