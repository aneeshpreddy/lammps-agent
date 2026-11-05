"""Derive Tier 2 tolerances from declared references (plan Day 11; PROPERTIES §8.5).

  python scripts/calibrate.py pce        -> calibration/pce_emc.json            (REF-01..REF-04)
  python scripts/calibrate.py fixture    -> calibration/tobermorite_fixture.json (FIX-T11, FIX-T14)

Every tolerance records what is measured, how it is derived, the reference IDs + SHA-256 used,
and a status. Margins are stated constants (below) with a written basis. Status ACCEPTED: the supervisor
accepted the margins on 2026-10-26 and the project owner the records on 2026-11-05 (SPEC §7.14). Changing a reference
invalidates the record: re-run this script and commit the new JSON.
"""
from __future__ import annotations

import datetime as _dt
import glob
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from validator.geometry import AMU_PER_A3_TO_G_PER_CM3, pairs_within  # noqa: E402
from validator.model import bond_graph_components, build_model  # noqa: E402
from validator.parser import parse_file  # noqa: E402
from validator.config import element_table  # noqa: E402
from validator.registry import config_for, load_sidecar  # noqa: E402
from validator.tier2 import bond_r0, bonded_index_pairs  # noqa: E402

DERIVATION_VERSION = "calibrate.py v1 (2026-10-16)"
BOND_MARGIN_REL = 0.10      # widen [min, max] of reference bond lengths by 10 % each side
OVERLAP_MARGIN_REL = 0.25   # d_min = 75 % of the closest non-bonded contact seen in the references
CONTACT_SEARCH_A = 4.0      # element pairs with no contact below this distance stay uncalibrated
DENSITY_MARGIN_REL = 0.02   # not reference-derived; accepted by the supervisor 2026-10-26 (see basis text)
TAU_M_AMU = 0.01            # mass tolerance per type
CENTROID_FACTOR = 3.0
R0_PAIR_MARGIN = 0.03       # P2.9: +- 0.03 on the observed (mean length / r0) ratio of each type pair
R0_DEFAULT_FACTOR = 2.0     # P2.9 default tolerance: 2 x the largest |ratio - 1| seen in the set (min 0.03)       # tau_centroid = max(0.02, ceil_0.01(3 x largest observed excursion))

SETS = {
    "pce": {"out": "calibration/pce_emc.json", "id": "pce_emc", "status": "ACCEPTED",
            "files": ["data/reference/REF-01.data", "data/reference/REF-02.data",
                      "data/reference/REF-03.data", "data/reference/REF-04.data"],
            "density_basis": {
                "pce_emc_dense": "REF-01, REF-02 were built by EMC at the requested density1 = 1 g/cm3 (REF-0x.params) "
                                 "and both measure 1.0000 g/cm3. The ±2 % margin is NOT reference-derived (two "
                                 "identical values give no spread): it is an owner requirement (PROPERTIES §8.5 "
                                 "rule 4), proposed by the project and accepted by the supervisor on 2026-10-26.",
                "pce_emc_dilute": None}},
    "tobermorite": {"out": "calibration/tobermorite_interface.json", "id": "tobermorite_interface",
                    "status": "ACCEPTED",
                    "files": ["data/reference/REF-05.data", "data/reference/REF-06.data",
                              "data/reference/REF-07.data", "data/reference/REF-08.data"],
                    "density_margin_rel": 1e-4,
                    "density_basis": {
                        f"tobermorite{n}": f"Crystal: every supercell of the tobermorite {n} Å model has exactly the "
                                           "unit-cell density, and the unit and rectangular cells agree. The ±1e-4 "
                                           "relative margin covers box lengths printed to >= 6 significant digits; it is "
                                           "a representation tolerance, not a physical one (PROPERTIES §8.5 rule 3)."
                        for n in (11, 14)}},
    "pce_builder": {"out": "calibration/pce_builder.json", "id": "pce_builder", "status": "ACCEPTED",
                    "files": ["data/reference/REF-01.data", "data/reference/REF-02.data",
                              "data/reference/REF-03.data", "data/reference/REF-04.data"],
                    "density_basis": {"pce_emc_dense": None, "pce_emc_dilute": None},
                    # Ion-oxygen (and other ion) contact floors: the EMC files hold almost no ion contacts
                    # (one Na+, 3.18 Å from any O). Published INTERFACE structures in which the ions are
                    # coordinated supply them; only element pairs containing an ion are taken from these.
                    "contact_sources": ["data/reference/contact_sources/mont0_333_Na_15_cell_1x1x1_pcff.data",
                                        "data/reference/contact_sources/mont0_333_K_15_cell_1x1x1_pcff.data",
                                        "data/reference/REF-05.data", "data/reference/REF-06.data",
                                        "data/reference/REF-07.data", "data/reference/REF-08.data"],
                    "contact_ions": ["Na", "K", "Ca"],
                    "extra_density": {"pce_builder": {"applicable": False,
                                                      "basis": "builders/pce.py writes isolated chains in a box slightly "
                                                               "bigger than the atoms (supervisor 2026-10-26; P2.10 checks "
                                                               "the margin): no bulk density to check"}}},
    "fixture": {"out": "calibration/tobermorite_fixture.json", "id": "tobermorite_fixture", "status": "SYNTHETIC",
                "files": ["data/fixtures/FIX-T11.data", "data/fixtures/FIX-T14.data"],
                "density_basis": {
                    "tobermorite_interface": "Range of the two INTERFACE FF tobermorite models (11 Å and 14 Å) "
                                             "widened by the same ±2 % placeholder. Synthetic: for code-path tests only."}},
}


def ceil_to(x, step):
    return math.ceil(x / step - 1e-12) * step


def mineral_set(ff: str) -> dict:
    files = sorted(os.path.relpath(f, ROOT) for f in glob.glob(os.path.join(ROOT, "data", "reference", "minerals", f"*_{ff}.data")))
    fams = {json.load(open(os.path.join(ROOT, f[:-5] + ".json")))["overrides"]["density_family"] for f in files}
    basis = {fam: None if fam == "surface" else
             "Crystal model: every supercell has the model's density exactly; ±1e-4 relative is a representation "
             "tolerance (PROPERTIES §8.5 rule 3), not a physical one." for fam in fams}
    return {"out": f"calibration/minerals_{ff}.json", "id": f"minerals_{ff}", "status": "ACCEPTED",
            "files": files, "density_margin_rel": 1e-4, "density_basis": basis}


def composite_set(ff: str) -> dict:
    """PCE on a mineral surface: the union of the PCE (EMC) and mineral references of that force field, with
    the ion contact sources. Cross pairs (PCE atom - slab atom) that no reference holds stay uncalibrated:
    get the cross-pair fallback (see main)."""
    m = mineral_set(ff)
    files = SETS["pce_builder"]["files"] + m["files"]
    return {"out": f"calibration/composite_{ff}.json", "id": f"composite_{ff}", "status": "ACCEPTED",
            "files": files, "density_margin_rel": 1e-4, "density_basis": {},
            "contact_sources": SETS["pce_builder"]["contact_sources"], "contact_ions": SETS["pce_builder"]["contact_ions"],
            "cross_pair_fallback": True,
            "extra_density": {"composite": {"applicable": False,
                                            "basis": "mineral slab + vacuum + adsorbed PCE (builders/composite.py): "
                                                     "no bulk density to check"}}}


def main(which: str):
    if which in SETS:
        spec = SETS[which]
    elif which.startswith("composite_"):
        spec = composite_set(which.split("_", 1)[1])
    else:
        spec = mineral_set(which.split("_", 1)[1])
    refs = []
    bonds = defaultdict(list)
    ebonds = defaultdict(list)
    r0_ratios = defaultdict(list)
    contact = {}
    density = defaultdict(list)
    centroid_exc = []
    for f in spec["files"]:
        path = os.path.join(ROOT, f)
        meta = load_sidecar(path)
        cfg = config_for(path, meta)
        dec = cfg["declared"]
        el_table = element_table(cfg)
        pf = parse_file(path)
        m = build_model(pf, dec["atom_style"])
        names = m.type_names
        idx = m.index_of()
        refs.append({"id": meta["id"], "file": f, "sha256": pf.sha256, "family": dec.get("density_family")})
        # bond lengths per atom-type-name pair (minimum image)
        b = m.topology.get("Bonds")
        if b is not None:
            ii = np.array([idx[a] for a in b.atoms[:, 0]])
            jj = np.array([idx[a] for a in b.atoms[:, 1]])
            L = m.cell.min_image_distances(m.xyz[jj] - m.xyz[ii])
            for k, l in enumerate(L):
                key = "|".join(sorted((names[int(m.types[ii[k]])], names[int(m.types[jj[k]])])))
                bonds[key].append(float(l))
                ekey = "|".join(sorted((el_table[names[int(m.types[ii[k]])]], el_table[names[int(m.types[jj[k]])]])))
                ebonds[ekey].append(float(l))
            r0 = bond_r0(pf, cfg)
            for t in np.unique(b.types):
                t = int(t)
                if r0.get(t, 0) <= 0:
                    continue
                sel = b.types == t
                k0 = int(np.nonzero(sel)[0][0])
                key = "|".join(sorted((names[int(m.types[ii[k0]])], names[int(m.types[jj[k0]])])))
                r0_ratios[key].append(float(L[sel].mean()) / r0[t])
        # closest non-bonded (all pairs except 1-2) contact per element pair
        bonded = bonded_index_pairs(m)
        I, J, D = pairs_within(m.cell, m.xyz, CONTACT_SEARCH_A)
        for i, j, d in zip(I.tolist(), J.tolist(), D.tolist()):
            if (i, j) in bonded:
                continue
            key = "|".join(sorted((el_table[names[int(m.types[i])]], el_table[names[int(m.types[j])]])))
            if key not in contact or d < contact[key]["observed_min"]:
                contact[key] = {"observed_min": d, "reference": meta["id"],
                                "atom_ids": [int(m.ids[i]), int(m.ids[j])]}
        rho = sum(m.masses[int(t)] for t in m.types) / m.cell.volume * AMU_PER_A3_TO_G_PER_CM3
        density[dec.get("density_family")].append((meta["id"], rho))
        if dec.get("coordinate_wrapping") == "unwrapped_clusters":
            s = m.cell.fractional(m.xyz)
            comp = bond_graph_components(m)
            for c in np.unique(comp):
                cen = s[comp == c].mean(0)
                centroid_exc.append(float(np.max(np.maximum(-cen, cen - 1.0).clip(min=0))))

    # ---- ion contact sources (geometry only) ---------------------------------------------------
    contact_src = []
    if spec.get("contact_sources"):
        from builders.ff import tables as frc_tables
        frc_el = {t: el for t, (mass, el) in frc_tables("pcff").masses.items()}
        ions = set(spec["contact_ions"])
        for f in spec["contact_sources"]:
            path = os.path.join(ROOT, f)
            pf = parse_file(path)
            m = build_model(pf, "full")
            el_of = {t: frc_el.get(n) for t, n in m.type_names.items()}
            bonded = bonded_index_pairs(m)
            I, J, D = pairs_within(m.cell, m.xyz, CONTACT_SEARCH_A)
            n_used = 0
            for i, j, d in zip(I.tolist(), J.tolist(), D.tolist()):
                if (i, j) in bonded:
                    continue
                ei, ej = el_of.get(int(m.types[i])), el_of.get(int(m.types[j]))
                if not ei or not ej or not ({ei, ej} & ions):
                    continue
                key = "|".join(sorted((ei, ej)))
                n_used += 1
                if key not in contact or d < contact[key]["observed_min"]:
                    contact[key] = {"observed_min": d, "reference": os.path.basename(f),
                                    "atom_ids": [int(m.ids[i]), int(m.ids[j])]}
            contact_src.append({"file": f, "sha256": pf.sha256, "ion_pairs_used": n_used})

    # ---- assemble ----------------------------------------------------------------------------
    bond_tab = {}
    for key, v in sorted(bonds.items()):
        v = np.array(v)
        bond_tab[key] = {"n": int(len(v)), "min": round(float(v.min()), 5), "max": round(float(v.max()), 5),
                         "mean": round(float(v.mean()), 5), "sd": round(float(v.std()), 5),
                         "lo": round(float(v.min()) * (1 - BOND_MARGIN_REL), 4),
                         "hi": round(float(v.max()) * (1 + BOND_MARGIN_REL), 4)}
    ebond_tab = {}
    for key, v in sorted(ebonds.items()):
        v = np.array(v)
        ebond_tab[key] = {"n": int(len(v)), "min": round(float(v.min()), 5), "max": round(float(v.max()), 5),
                          "lo": round(float(v.min()) * (1 - BOND_MARGIN_REL), 4),
                          "hi": round(float(v.max()) * (1 + BOND_MARGIN_REL), 4)}
    overlap = {k: {"observed_min": round(v["observed_min"], 4), "d_min": round(v["observed_min"] * (1 - OVERLAP_MARGIN_REL), 4),
                   "closest_pair_in": v["reference"], "atom_ids": v["atom_ids"]} for k, v in sorted(contact.items())}
    if spec.get("cross_pair_fallback"):
        # PCE-slab element pairs that no reference contains (e.g. Ca|Na, C|Si): d_min = the smallest calibrated
        # d_min of any pair containing either element. Permissive by construction (it never exceeds what the
        # references allow for those elements), so it targets only gross overlaps — P2.3's purpose.
        els = sorted({e for k in overlap for e in k.split("|")})
        for i, a in enumerate(els):
            for b in els[i:]:
                key = "|".join(sorted((a, b)))
                if key in overlap:
                    continue
                cands = [(v["d_min"], k) for k, v in overlap.items() if "fallback_from" not in v and ({a, b} & set(k.split("|")))]
                d, src = min(cands)
                overlap[key] = {"observed_min": None, "d_min": d, "fallback_from": src}
        overlap = dict(sorted(overlap.items()))
    # separation check: a widened bond window must stay below the closest non-bonded contact of that element pair
    sep = []
    el_of_name = {}
    for f in spec["files"]:
        el_of_name.update(element_table(config_for(os.path.join(ROOT, f))))
    for key, w in bond_tab.items():
        a, b2 = key.split("|")
        ekey = "|".join(sorted((el_of_name[a], el_of_name[b2])))
        nb = contact.get(ekey, {}).get("observed_min")
        sep.append({"bond_pair": key, "element_pair": ekey, "window_hi": w["hi"], "closest_nonbonded": round(nb, 4) if nb else None,
                    "ok": (nb is None) or (w["hi"] < nb)})
    dens = {}
    for fam, vals in density.items():
        basis = spec["density_basis"].get(fam)
        if basis is None:
            dens[fam] = {"applicable": False, "values": {r: round(v, 6) for r, v in vals},
                         "basis": "isolated chain(s) in a mostly empty periodic box: no bulk density to check"}
            continue
        lo, hi = min(v for _, v in vals), max(v for _, v in vals)
        mr = spec.get("density_margin_rel", DENSITY_MARGIN_REL)
        dens[fam] = {"applicable": True, "values": {r: round(v, 6) for r, v in vals}, "margin_rel": mr,
                     "lo": round(lo * (1 - mr), 6), "hi": round(hi * (1 + mr), 6), "basis": basis}
    dens.update(spec.get("extra_density", {}))
    allr = [x for v in r0_ratios.values() for x in v]
    r0_block = None
    if allr:
        worst = max(abs(x - 1) for x in allr)
        r0_block = {"measured": "mean bond length of each bond type / that type's own r0 (Bond Coeffs or coeff file)",
                    "derivation": f"per atom-type pair: [min - {R0_PAIR_MARGIN}, max + {R0_PAIR_MARGIN}] of the observed ratios; "
                                  f"other pairs: |ratio - 1| <= max(0.03, {R0_DEFAULT_FACTOR} x largest observed |ratio - 1|)",
                    "basis": "structures sit systematically off r0 (crystal geometry vs force-field fit, crowded centres), "
                             "but each pair's ratio is stable; a coefficient row moved to another bond type changes it",
                    "observed_max_abs_deviation": round(worst, 4),
                    "default_tau_rel": round(max(0.03, R0_DEFAULT_FACTOR * worst), 4),
                    "pairs": {k: {"n_types": len(v), "min": round(min(v), 4), "max": round(max(v), 4),
                                  "lo": round(min(v) - R0_PAIR_MARGIN, 4), "hi": round(max(v) + R0_PAIR_MARGIN, 4)}
                              for k, v in sorted(r0_ratios.items())}}
    out = {
        "calibration_id": spec["id"], "version": 1, "status": spec["status"],
        "date": _dt.date.today().isoformat(), "derivation_version": DERIVATION_VERSION,
        "references": refs,
        "contact_sources": contact_src,
        "bond_length": {"measured": "minimum-image bond length per atom-type-name pair (Å)",
                        "derivation": f"[min x (1-{BOND_MARGIN_REL}), max x (1+{BOND_MARGIN_REL})] over the references",
                        "basis": "references show a spread of sd ≈ 3 % of the bond length around the FF r0; a 10 % "
                                 "widening beyond the observed extremes admits re-built or relaxed geometries while "
                                 "staying below the closest non-bonded contact of the same element pair "
                                 "(separation_check)", "margin_rel": BOND_MARGIN_REL,
                        "pairs": bond_tab, "separation_check": sep,
                        "element_pairs": ebond_tab,
                        "element_pairs_note": "fallback for type pairs with no window (e.g. other force-field "
                                              "type names); same derivation, keyed by element pair",
                        "separation_ok": all(s["ok"] for s in sep)},
        "overlap": {"measured": "minimum-image distance of non-bonded pairs (all pairs except 1-2 bonds), per element pair (Å)",
                    "derivation": f"d_min = (1-{OVERLAP_MARGIN_REL}) x closest such contact in the references; "
                                  f"element pairs with no contact below {CONTACT_SEARCH_A} Å are uncalibrated"
                                  + ("; composite sets: a pair absent from every reference takes the smallest d_min of the "
                                     "calibrated pairs containing either of its elements ('fallback_from')"
                                     if spec.get("cross_pair_fallback") else ""),
                    "basis": "P2.3 targets gross overlaps (coincident/duplicated sites, collapsed geometry); the "
                             "references are unrelaxed builds whose closest contacts are already short, so the "
                             "threshold is placed well below them", "margin_rel": OVERLAP_MARGIN_REL, "pairs": overlap},
        "density": dens,
        "bond_r0": r0_block,
        "mass": {"tau_m_amu": TAU_M_AMU, "measured": "|Masses value - standard atomic weight of the mapped element|",
                 "basis": "FF mass tables print 2-5 decimals and use older IUPAC editions (e.g. H 1.00794/1.00797, "
                          "Ca 40.08, Si 28.086); the largest such difference for the elements in scope is 0.002 amu. "
                          "0.01 amu covers it while any element swap differs by > 0.9 amu."},
    }
    if centroid_exc:
        obs = max(centroid_exc)
        out["cell"] = {"policy": "unwrapped_clusters", "observed_max_centroid_excursion": round(obs, 5),
                       "tau_centroid": round(max(0.02, ceil_to(CENTROID_FACTOR * obs, 0.01)), 2),
                       "measured": "fractional distance of each bonded cluster's centroid outside [0,1) per periodic dim",
                       "basis": "EMC writes whole (unwrapped) molecules with centroids near the cell; tau = "
                                f"max(0.02, ceil_0.01({CENTROID_FACTOR} x largest observed excursion))"}
    with open(os.path.join(ROOT, spec["out"]), "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"wrote {spec['out']}: {len(bond_tab)} bond pairs, {len(overlap)} element pairs, density {list(dens)}, "
          f"separation_ok={out['bond_length']['separation_ok']}"
          + (f", tau_centroid={out['cell']['tau_centroid']}" if 'cell' in out else ""))
    bad = [s for s in sep if not s["ok"]]
    for s in bad:
        print("  SEPARATION VIOLATION:", s)


if __name__ == "__main__":
    for w in (sys.argv[1:] or ["pce", "pce_builder", "tobermorite", "fixture"]):
        main(w)
