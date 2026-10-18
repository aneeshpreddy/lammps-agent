"""Self-generated evidence of use for the tobermorite references (SPEC §7.8; provenance.md).

The plan's oracle is "files that ran successfully in production". With no group production files,
the references are published INTERFACE FF models; this script supplies the missing evidence that
they behave as working simulation inputs on the declared build:

  A. Short MD on the 2x2x1 supercells of both minerals (t05, t07): energy minimisation, 5 ps NVT at
     300 K, 10 ps NPT (tri, 1 atm). Recorded: relaxation energy, temperature, cell drift vs the
     published cell, density. Logs kept in data/reference/evidence/.
  B. Extensivity: 'run 0' potential energy per unit cell of all 14 eval references and REF-05..08 must
     agree (same crystal, different supercells and cell choices) — an end-to-end check of the
     replication pipeline that does not depend on the validator.

  python scripts/evidence_runs.py      -> data/reference/evidence/, docs/REFERENCE_EVIDENCE.md
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from validator import validate  # noqa: E402
from validator.registry import config_for  # noqa: E402

LMP = "lmp_serial"
OUT = os.path.join(ROOT, "data", "reference", "evidence")
CELLS_PER = {"tob11": 1, "tob11r": 2, "tob14": 1, "tob14r": 2}   # unit cells per base cell (rectangular = 2)

MD = """units real
atom_style full
boundary p p p
pair_style lj/class2/coul/long 9.5
bond_style class2
angle_style class2
dihedral_style class2
improper_style class2
special_bonds lj/coul 0 0 1
read_data data.lmp
kspace_style ewald 1.0e-4
neighbor 2.0 bin
neigh_modify delay 0 every 1 check yes
thermo_style custom step temp pe etotal press lx ly lz xy xz yz vol density
thermo_modify norm no flush yes
thermo 250
min_style cg
minimize 1.0e-6 1.0e-8 2000 20000
reset_timestep 0
timestep 1.0
velocity all create 300.0 20261019 mom yes rot yes dist gaussian
fix nvt all nvt temp 300.0 300.0 100.0
run 5000
unfix nvt
fix npt all npt temp 300.0 300.0 100.0 tri 1.0 1.0 1000.0
run 10000
"""


def thermo_blocks(log: str):
    blocks, cur, hdr = [], None, None
    for ln in log.splitlines():
        t = ln.split()
        if t and t[0] == "Step":
            hdr, cur = t, []
            blocks.append((hdr, cur))
            continue
        if cur is not None:
            if t and t[0].lstrip("-").isdigit() and len(t) == len(hdr):
                try:
                    cur.append([float(x) for x in t])
                except ValueError:
                    cur = None
            elif t and (t[0] == "Loop" or t[0].startswith("WARNING")):
                cur = None if t[0] == "Loop" else cur
    return [(h, np.array(rows)) for h, rows in blocks if rows]


def md_evidence(tid: str, label: str):
    src = os.path.join(ROOT, "data", "reference", "eval", f"{tid}.data")
    dst = os.path.join(OUT, label)
    os.makedirs(dst, exist_ok=True)
    with tempfile.TemporaryDirectory() as wd:
        shutil.copyfile(src, os.path.join(wd, "data.lmp"))
        with open(os.path.join(wd, "in.lmp"), "w") as fh:
            fh.write(MD)
        t0 = time.time()
        p = subprocess.run([LMP, "-in", "in.lmp", "-log", "log.lammps", "-nocite"], cwd=wd, capture_output=True, text=True)
        wall = time.time() - t0
        shutil.copyfile(os.path.join(wd, "log.lammps"), os.path.join(dst, "log.lammps"))
        shutil.copyfile(os.path.join(wd, "in.lmp"), os.path.join(dst, "in.lmp"))
    log = open(os.path.join(dst, "log.lammps")).read()
    errors = [ln for ln in log.splitlines() if ln.startswith("ERROR")]
    warnings = sorted({ln.split(" (src/")[0] for ln in log.splitlines() if ln.startswith("WARNING")})
    blocks = thermo_blocks(log)
    if p.returncode != 0 or len(blocks) < 3:
        return {"label": label, "task": tid, "ok": False, "returncode": p.returncode, "errors": errors[:3]}
    (hm, mn), (hv, nvt), (hp, npt) = blocks[0], blocks[1], blocks[2]
    col = {k: i for i, k in enumerate(hp)}
    n_atoms = int(open(src).read().split(" atoms")[0].split()[-1])
    half = npt[len(npt) // 2:]
    init = npt[0]
    pub = mn[0]
    drift = {k: float((half[:, col[k]].mean() - pub[col[k]]) / pub[col[k]] * 100) for k in ("Lx", "Ly", "Lz", "Volume")}
    res = {
        "label": label, "task": tid, "ok": not errors and bool(np.isfinite(npt).all()), "returncode": p.returncode,
        "wall_s": round(wall, 1), "atoms": n_atoms,
        "minimisation_kcal_per_atom": float((mn[-1, 2] - mn[0, 2]) / n_atoms),
        "nvt_T_mean_K": float(nvt[len(nvt) // 2:, 1].mean()), "nvt_T_sd_K": float(nvt[len(nvt) // 2:, 1].std()),
        "npt_T_mean_K": float(half[:, col["Temp"]].mean()),
        "npt_density_mean": float(half[:, col["Density"]].mean()),
        "density_start": float(pub[col["Density"]]),
        "cell_change_vs_published_percent": {k: round(v, 2) for k, v in drift.items()},
        "xy_start": float(init[col["Xy"]]) if "Xy" in col else None,
        "xy_mean_npt": float(half[:, col["Xy"]].mean()) if "Xy" in col else None,
        "warnings": warnings, "errors": errors[:3],
    }
    with open(os.path.join(dst, "summary.json"), "w") as fh:
        json.dump(res, fh, indent=2)
    return res


def extensivity():
    import glob
    rows = []
    tasks = {json.load(open(f))["id"]: json.load(open(f)) for f in glob.glob(os.path.join(ROOT, "eval", "tasks", "t*.json"))}
    for f in sorted(glob.glob(os.path.join(ROOT, "data", "reference", "REF-0[5-8].data"))) + \
            sorted(glob.glob(os.path.join(ROOT, "data", "reference", "eval", "t*.data"))):
        meta = json.load(open(os.path.splitext(f)[0] + ".json"))
        model = meta["model_source"].split("/")[-2].split(".")[0]   # ".../tob11_unit_cell.car/.mdf"
        key = {"tob11_unit_cell": "tob11", "tob11_rectangular_cell": "tob11r", "tob14_avg_cell": "tob14",
               "tob14_avg_rectangular_cell": "tob14r"}[model]
        n_cells = CELLS_PER[key] * int(np.prod(meta["supercell"]))
        r = validate(f, config_for(f, meta), run_tier3=True)
        th = (r.lammps.get("full") or {}).get("thermo") or {}
        pe = th.get("values", {}).get("PotEng")
        rows.append({"file": os.path.relpath(f, ROOT), "mineral": key[:5], "cells": n_cells, "pe": pe,
                     "pe_per_cell": pe / n_cells if pe is not None else None, "verdict": r.verdict})
    out = {}
    for mineral in ("tob11", "tob14"):
        v = np.array([r["pe_per_cell"] for r in rows if r["mineral"] == mineral and r["pe_per_cell"] is not None])
        out[mineral] = {"n": int(len(v)), "mean": float(v.mean()), "spread_abs": float(v.max() - v.min()),
                        "spread_rel_percent": float((v.max() - v.min()) / abs(v.mean()) * 100)}
    return rows, out


def main():
    os.makedirs(OUT, exist_ok=True)
    md = [md_evidence("t05", "tob11_2x2x1"), md_evidence("t07", "tob14_2x2x1")]
    rows, ext = extensivity()
    with open(os.path.join(OUT, "extensivity.json"), "w") as fh:
        json.dump({"rows": rows, "summary": ext}, fh, indent=2)
    L = ["# Reference evidence — tobermorite (INTERFACE FF 1.5, PCFF-INTERFACE)\n",
         f"Generated by `scripts/evidence_runs.py` on {_dt.date.today().isoformat()} with `lmp_serial` 22 Jul 2025 – "
         "Update 6, serial, Ewald 1e-4, 9.5 Å cut-off, `special_bonds lj/coul 0 0 1`. This is the evidence of use that "
         "SPEC §7.8 asks for, produced by us because no group production files exist (LOG 2026-10-19). It shows the "
         "references are working simulation inputs; it is not a validation of the force field itself.\n",
         "## A. Short MD (minimise → 5 ps NVT 300 K → 10 ps NPT 300 K, 1 atm, tri)\n",
         "| System | Atoms | Ran clean | Minimisation ΔE (kcal/mol/atom) | ⟨T⟩ NVT / NPT (K) | ρ start → ⟨ρ⟩ NPT (g/cm³) | Cell change vs published (lx, ly, lz, V; %) | Wall (s) | Warnings |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in md:
        if not r.get("ok") and "atoms" not in r:
            L.append(f"| {r['label']} | — | **NO** (exit {r['returncode']}) {r['errors']} | | | | | | |")
            continue
        c = r["cell_change_vs_published_percent"]
        L.append(f"| {r['label']} ({r['task']}) | {r['atoms']} | {'yes' if r['ok'] else '**NO**'} | "
                 f"{r['minimisation_kcal_per_atom']:.3f} | {r['nvt_T_mean_K']:.0f} / {r['npt_T_mean_K']:.0f} | "
                 f"{r['density_start']:.3f} → {r['npt_density_mean']:.3f} | {c['Lx']:+.2f}, {c['Ly']:+.2f}, {c['Lz']:+.2f}, "
                 f"{c['Volume']:+.2f} | {r['wall_s']} | {'; '.join(w.replace('WARNING: ', '') for w in r['warnings']) or '—'} |")
    L += ["\n## B. Extensivity of the reference pipeline\n",
          "`run 0` potential energy divided by the number of unit cells, for every tobermorite reference (unit cells, "
          "rectangular cells and supercells built by `scripts/supercell.py`). The same crystal must give the same "
          "energy per cell whatever the cell choice.\n",
          "| Mineral | Files | Mean PE per unit cell (kcal/mol) | Spread (abs) | Spread (%) |", "|---|---|---|---|---|"]
    for k, v in ext.items():
        L.append(f"| {k} | {v['n']} | {v['mean']:.3f} | {v['spread_abs']:.3f} | {v['spread_rel_percent']:.4f} |")
    L += ["", "| File | Cells | PE (kcal/mol) | PE / cell | Validator |", "|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['file']} | {r['cells']} | {r['pe']:.3f} | {r['pe_per_cell']:.3f} | {r['verdict']} |")
    with open(os.path.join(ROOT, "docs", "REFERENCE_EVIDENCE.md"), "w") as fh:
        fh.write("\n".join(L) + "\n")
    print(json.dumps({"md": md, "extensivity": ext}, indent=1, default=str)[:3000])


if __name__ == "__main__":
    main()
