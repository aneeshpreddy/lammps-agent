"""Remove close contacts left by the grower: LAMMPS energy minimisation in two stages.

Stage 1 replaces the pair style with a soft-core potential (finite at r = 0, so even coincident
atoms separate), stage 2 restores the force field's own Lennard-Jones + cut-off Coulomb pair style
with the Pair Coeffs from the DATA FILE. Bonded terms are the force field's throughout. The relaxed
coordinates and image flags are copied back into the original msi2lmp file by atom ID, so types,
charges, topology, coefficients and comments stay byte-identical; only coordinates change.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

STYLES = {
    "pcff": {"pair_cut": "lj/class2/coul/cut 10.0", "bonded": "bond_style class2\nangle_style class2\n"
             "dihedral_style class2\nimproper_style class2", "pair_read": "lj/class2/coul/long 10.0"},
    "cvff": {"pair_cut": "lj/cut/coul/cut 10.0", "bonded": "bond_style harmonic\nangle_style harmonic\n"
             "dihedral_style harmonic\nimproper_style cvff", "pair_read": "lj/cut/coul/long 10.0"},
}


def _pair_coeffs(data_text: str):
    lines = data_text.splitlines()
    out, i = [], None
    for k, ln in enumerate(lines):
        if ln.strip().startswith("Pair Coeffs"):
            i = k + 2
            break
    if i is None:
        raise ValueError("no Pair Coeffs section to restore after the soft stage")
    while i < len(lines) and lines[i].strip():
        t = lines[i].split("#")[0].split()
        out.append(f"pair_coeff {t[0]} {t[0]} {' '.join(t[1:])}")
        i += 1
    return out


def relax(data_path: str, ff: str, lmp: str = "lmp_serial", soft_stages=(10.0, 40.0, 100.0)) -> dict:
    st = STYLES[ff]
    text = open(data_path).read()
    pcs = _pair_coeffs(text)
    soft = "\n".join(f"pair_coeff * * {a}\nminimize 1.0e-4 1.0e-6 2000 20000" for a in soft_stages)
    inp = f"""units real
atom_style full
boundary p p p
pair_style {st['pair_read']}
{st['bonded']}
special_bonds lj/coul 0 0 1
read_data data.lmp
neighbor 2.0 bin
neigh_modify delay 0 every 1 check yes one 5000 page 500000
thermo_style custom step pe ebond eangle edihed evdwl ecoul
thermo 500
min_style cg
pair_style soft 3.0
{soft}
pair_style {st['pair_cut']}
{chr(10).join(pcs)}
minimize 1.0e-6 1.0e-8 5000 50000
write_dump all custom relaxed.dump id x y z ix iy iz modify sort id format float %.10f
"""
    with tempfile.TemporaryDirectory() as wd:
        shutil.copyfile(data_path, os.path.join(wd, "data.lmp"))
        with open(os.path.join(wd, "in.relax"), "w") as fh:
            fh.write(inp)
        p = subprocess.run([lmp, "-in", "in.relax", "-log", "log.lammps", "-nocite"], cwd=wd,
                           capture_output=True, text=True, timeout=1800)
        if p.returncode != 0 or not os.path.exists(os.path.join(wd, "relaxed.dump")):
            err = [l for l in p.stdout.splitlines() if l.startswith("ERROR")]
            raise RuntimeError(f"relaxation failed (exit {p.returncode}): {err[:2] or p.stdout[-800:]}")
        dump = open(os.path.join(wd, "relaxed.dump")).read().splitlines()
        log = open(os.path.join(wd, "log.lammps")).read()
    k = dump.index("ITEM: ATOMS id x y z ix iy iz")
    new = {}
    for ln in dump[k + 1:]:
        t = ln.split()
        new[t[0]] = t[1:]
    # patch the Atoms rows of the original file
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip().startswith("Atoms")) + 2
    i = start
    while i < len(lines) and lines[i].strip():
        body, _, com = lines[i].partition("#")
        t = body.split()
        x, y, z, ix, iy, iz = new[t[0]]
        t = t[:4] + [x, y, z] + [ix, iy, iz]
        lines[i] = "  ".join(t) + (f"  # {com.strip()}" if com.strip() else "")
        i += 1
    with open(data_path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    finals = []
    for k2, ln in enumerate(log.splitlines()):
        if ln.strip().startswith("Energy initial, next-to-last, final"):
            finals.append(log.splitlines()[k2 + 1].split())
    return {"relaxed": True, "stages": [f"soft A={a}" for a in soft_stages] + [st["pair_cut"]],
            "final_energy_kcal_mol": float(finals[-1][2]) if finals else None}
