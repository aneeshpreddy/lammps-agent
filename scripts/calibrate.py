"""Derive Tier 2 tolerances from declared references (plan Day 11; PROPERTIES §8.5).

  python scripts/calibrate.py pce        -> calibration/pce_emc.json            (REF-01..REF-04)
  python scripts/calibrate.py fixture    -> calibration/tobermorite_fixture.json (FIX-T11, FIX-T14)

Every tolerance records what is measured, how it is derived, the reference IDs + SHA-256 used,
and a status. Margins are stated constants (below) with a written basis; they are PROVISIONAL
until the owner confirms the references as trusted and accepts the margins. Changing a reference
invalidates the record: re-run this script and commit the new JSON.
"""
from __future__ import annotations

import datetime as _dt
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
from validator.registry import config_for, load_sidecar  # noqa: E402
from validator.tier2 import bonded_index_pairs  # noqa: E402

DERIVATION_VERSION = "calibrate.py v1 (2026-10-16)"
BOND_MARGIN_REL = 0.10      # widen [min, max] of reference bond lengths by 10 % each side
OVERLAP_MARGIN_REL = 0.25   # d_min = 75 % of the closest non-bonded contact seen in the references
CONTACT_SEARCH_A = 4.0      # element pairs with no contact below this distance stay uncalibrated
DENSITY_MARGIN_REL = 0.02   # PLACEHOLDER pending an owner requirement (see basis text)
TAU_M_AMU = 0.01            # mass tolerance per type
CENTROID_FACTOR = 3.0       # tau_centroid = max(0.02, ceil_0.01(3 x largest observed excursion))

SETS = {
    "pce": {"out": "calibration/pce_emc.json", "id": "pce_emc", "status": "PROVISIONAL",
            "files": ["data/reference/REF-01.data", "data/reference/REF-02.data",
                      "data/reference/REF-03.data", "data/reference/REF-04.data"],
            "density_basis": {
                "pce_emc_dense": "REF-01, REF-02 were built by EMC at the requested density1 = 1 g/cm3 (REF-0x.params) "
                                 "and both measure 1.0000 g/cm3. The ±2 % margin is NOT reference-derived (two "
                                 "identical values give no spread): it is a PLACEHOLDER for an owner requirement "
                                 "(PROPERTIES §8.5 rule 4) and must be confirmed or replaced.",
                "pce_emc_dilute": None}},
    "fixture": {"out": "calibration/tobermorite_fixture.json", "id": "tobermorite_fixture", "status": "SYNTHETIC",
                "files": ["data/fixtures/FIX-T11.data", "data/fixtures/FIX-T14.data"],
                "density_basis": {
                    "tobermorite_interface": "Range of the two INTERFACE FF tobermorite models (11 Å and 14 Å) "
                                             "widened by the same ±2 % placeholder. Synthetic: for code-path tests only."}},
}


def ceil_to(x, step):
    return math.ceil(x / step - 1e-12) * step


def main(which: str):
    spec = SETS[which]
    refs = []
    bonds = defaultdict(list)
    contact = {}
    density = defaultdict(list)
    centroid_exc = []
    for f in spec["files"]:
        path = os.path.join(ROOT, f)
        meta = load_sidecar(path)
        cfg = config_for(path, meta)
        dec = cfg["declared"]
        el_table = dec.get("type_name_elements", {})
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

    # ---- assemble ----------------------------------------------------------------------------
    bond_tab = {}
    for key, v in sorted(bonds.items()):
        v = np.array(v)
        bond_tab[key] = {"n": int(len(v)), "min": round(float(v.min()), 5), "max": round(float(v.max()), 5),
                         "mean": round(float(v.mean()), 5), "sd": round(float(v.std()), 5),
                         "lo": round(float(v.min()) * (1 - BOND_MARGIN_REL), 4),
                         "hi": round(float(v.max()) * (1 + BOND_MARGIN_REL), 4)}
    overlap = {k: {"observed_min": round(v["observed_min"], 4), "d_min": round(v["observed_min"] * (1 - OVERLAP_MARGIN_REL), 4),
                   "closest_pair_in": v["reference"], "atom_ids": v["atom_ids"]} for k, v in sorted(contact.items())}
    # separation check: a widened bond window must stay below the closest non-bonded contact of that element pair
    sep = []
    el_of_name = {}
    for f in spec["files"]:
        el_of_name.update(config_for(os.path.join(ROOT, f))["declared"].get("type_name_elements", {}))
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
        dens[fam] = {"applicable": True, "values": {r: round(v, 6) for r, v in vals}, "margin_rel": DENSITY_MARGIN_REL,
                     "lo": round(lo * (1 - DENSITY_MARGIN_REL), 4), "hi": round(hi * (1 + DENSITY_MARGIN_REL), 4),
                     "basis": basis}
    out = {
        "calibration_id": spec["id"], "version": 1, "status": spec["status"],
        "date": _dt.date.today().isoformat(), "derivation_version": DERIVATION_VERSION,
        "references": refs,
        "bond_length": {"measured": "minimum-image bond length per atom-type-name pair (Å)",
                        "derivation": f"[min x (1-{BOND_MARGIN_REL}), max x (1+{BOND_MARGIN_REL})] over the references",
                        "basis": "references show a spread of sd ≈ 3 % of the bond length around the FF r0; a 10 % "
                                 "widening beyond the observed extremes admits re-built or relaxed geometries while "
                                 "staying below the closest non-bonded contact of the same element pair "
                                 "(separation_check)", "margin_rel": BOND_MARGIN_REL,
                        "pairs": bond_tab, "separation_check": sep,
                        "separation_ok": all(s["ok"] for s in sep)},
        "overlap": {"measured": "minimum-image distance of non-bonded pairs (all pairs except 1-2 bonds), per element pair (Å)",
                    "derivation": f"d_min = (1-{OVERLAP_MARGIN_REL}) x closest such contact in the references; "
                                  f"element pairs with no contact below {CONTACT_SEARCH_A} Å are uncalibrated",
                    "basis": "P2.3 targets gross overlaps (coincident/duplicated sites, collapsed geometry); the "
                             "references are unrelaxed builds whose closest contacts are already short, so the "
                             "threshold is placed well below them", "margin_rel": OVERLAP_MARGIN_REL, "pairs": overlap},
        "density": dens,
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
    for w in (sys.argv[1:] or ["pce", "fixture"]):
        main(w)
