"""Mineral builder -> LAMMPS DATA FILE for any INTERFACE FF 1.5 model, supercell and force field.

Models: every .car/.mdf pair in UGRP/CEMENT_MINERALS (C3S, C3A, ettringite, monosulfate,
tobermorite 11/14 Å; unit cells, rectangular cells, surfaces, hydrated surfaces) and the rest of
the INTERFACE model database (clays, silica, metals, Ca sulfates, apatite, PEO), looked up by name.

Pipeline (same as the reference pipeline, scripts/build_references.py):
  msi2lmp (-class I/II with the INTERFACE .frc; any missing parameter other than a class II cross
  term is refused) -> tilt reduction + wrap -> supercell (scripts/supercell.py; LAMMPS replicate
  bond/periodic is avoided, FAILURE_MODES §9.6) -> LAMMPS read_data/write_data (Ewald) ->
  type-name comments restored.

Force-field coverage (msi2lmp survey 2026-10-20; INTERFACE documentation §2):
  PCFF-INTERFACE (class II): all cement minerals (class II cross terms are not defined -> zero)
  CVFF-INTERFACE (class I) : C3S and C3A only ("CVFF and CHARMM currently support tricalcium
                             silicate and tricalcium aluminate only")
  c3s_unit_cell is a defective database entry (.car/.mdf atom lists differ); use
  c3s_unit_cell_minimized.

  python -m builders.minerals tob11_unit_cell --supercell 2 2 1 --ff pcff --out runs/minerals
  python -m builders.minerals --list
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

from .ff import FORCE_FIELDS
from .pce import CROSS_TERMS, ensure_msi2lmp, non_finite_lines

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UGRP = os.path.dirname(REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
from cellops import reduce_and_wrap, tilt_within_bound  # noqa: E402
from dataedit import DataText, split_comment  # noqa: E402
from supercell import make_supercell  # noqa: E402

SEARCH = [os.path.join(UGRP, "CEMENT_MINERALS")] + \
    sorted(glob.glob(os.path.join(UGRP, "INTERFACE_FF_1_5", "MODEL_DATABASE", "*")))
KNOWN_DEFECTIVE = {"c3s_unit_cell": "the .car and .mdf atom lists differ (ND vs CA2); use c3s_unit_cell_minimized"}
LMP_STYLES = {
    "pcff": "pair_style lj/class2/coul/long 9.5\nbond_style class2\nangle_style class2\n"
            "dihedral_style class2\nimproper_style class2",
    "cvff": "pair_style lj/cut/coul/long 9.5\nbond_style harmonic\nangle_style harmonic\n"
            "dihedral_style harmonic\nimproper_style cvff",
}
COEFF_SECTIONS = ["Masses", "Pair Coeffs", "Bond Coeffs", "Angle Coeffs", "Dihedral Coeffs", "Improper Coeffs",
                  "BondBond Coeffs", "BondAngle Coeffs", "MiddleBondTorsion Coeffs", "EndBondTorsion Coeffs",
                  "AngleTorsion Coeffs", "AngleAngleTorsion Coeffs", "BondBond13 Coeffs", "AngleAngle Coeffs"]


def list_models():
    out = {}
    for d in SEARCH:
        for car in sorted(glob.glob(os.path.join(d, "*.car"))):
            name = os.path.basename(car)[:-4]
            if os.path.exists(car[:-4] + ".mdf"):
                out.setdefault(name, d)
    return out


def find_model(name: str) -> str:
    if name in KNOWN_DEFECTIVE:
        raise ValueError(f"{name}: {KNOWN_DEFECTIVE[name]}")
    models = list_models()
    if name not in models:
        raise KeyError(f"unknown model {name!r}; see python -m builders.minerals --list")
    return os.path.join(models[name], name)


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def msi2lmp_model(root: str, ff: str, out_data: str, allow_missing=()) -> dict:
    info = FORCE_FIELDS[ff]
    name = os.path.basename(root)
    with tempfile.TemporaryDirectory() as wd:
        for ext in ("car", "mdf"):
            shutil.copyfile(f"{root}.{ext}", os.path.join(wd, f"{name}.{ext}"))
        shutil.copyfile(info["frc"], os.path.join(wd, "ff.frc"))
        p = subprocess.run([ensure_msi2lmp(), name, "-class", info["class"], "-frc", "./ff.frc", "-print", "1",
                            "-ignore"], cwd=wd, capture_output=True, text=True)
        out = p.stdout + p.stderr
        missing = sorted({ln.strip() for ln in out.splitlines() if "Unable to find" in ln})
        core = [ln for ln in missing if ln.split()[3] not in CROSS_TERMS and ln.split()[3] not in allow_missing]
        produced = os.path.join(wd, f"{name}.data")
        if not os.path.exists(produced):
            raise RuntimeError(f"msi2lmp failed for {name}: {out.strip().splitlines()[-1] if out.strip() else ''}")
        if core:
            raise RuntimeError(f"{info['name']} lacks parameters for {name} (refusing to write zeros): "
                               + "; ".join(core[:6]))
        bad = non_finite_lines(produced)
        if bad:
            raise RuntimeError(f"msi2lmp wrote non-finite parameters for {name} ({info['name']}), refusing: "
                               + "; ".join(bad[:3]))
        shutil.copyfile(produced, out_data)
    return {"missing_kinds": sorted({ln.split()[3] for ln in missing}), "cross_terms_zeroed": bool(missing),
            "allowed_missing_kinds": sorted(allow_missing),
            "simulation_ready": not any(ln.split()[3] in allow_missing for ln in missing)}


def lammps_normalise(src: str, ff: str, out: str) -> str:
    with tempfile.TemporaryDirectory() as wd:
        shutil.copyfile(src, os.path.join(wd, "in.data"))
        with open(os.path.join(wd, "in.lmp"), "w") as fh:
            fh.write(f"units real\natom_style full\nboundary p p p\n{LMP_STYLES[ff]}\n"
                     "special_bonds lj/coul 0 0 1\nread_data in.data\nkspace_style ewald 1.0e-4\n"
                     "write_data out.data pair ii\n")
        p = subprocess.run(["lmp_serial", "-in", "in.lmp", "-log", "log.lammps", "-nocite"], cwd=wd,
                           capture_output=True, text=True)
        if p.returncode != 0 or not os.path.exists(os.path.join(wd, "out.data")):
            err = [l for l in p.stdout.splitlines() if l.startswith("ERROR")]
            raise RuntimeError(f"LAMMPS read/write failed: {err[:1] or p.stdout[-400:]}")
        shutil.copyfile(os.path.join(wd, "out.data"), out)
        return p.stdout.splitlines()[0]


def _strip(d):
    return [split_comment(ln)[0] for ln in d.lines[1:]]


def annotate(path: str, source: str) -> int:
    d, s = DataText.read(path), DataText.read(source)
    before = _strip(d)
    added = 0
    for name in COEFF_SECTIONS:
        src = {}
        for _, line in s.section_rows(name):
            if "#" in line:
                src[line.split()[0]] = line.split("#", 1)[1].strip()
        for i, line in d.section_rows(name):
            if "#" not in line and line.split()[0] in src:
                d.lines[i] = f"{line.rstrip()} # {src[line.split()[0]]}"
                added += 1
    if _strip(d) != before:
        raise AssertionError("annotation changed data tokens")
    d.write(path)
    return added


def build_mineral(model: str, supercell=(1, 1, 1), ff: str = "pcff", outdir: str = "runs/minerals",
                  name: str = None, allow_missing=()) -> dict:
    """allow_missing: parameter kinds tolerated as zero (e.g. ('oop',)) — ONLY for geometry-only uses
    such as calibration contact sources; the record then says simulation_ready: false."""
    root = find_model(model)
    os.makedirs(outdir, exist_ok=True)
    name = name or f"{model}_{supercell[0]}x{supercell[1]}x{supercell[2]}_{ff}"
    out = os.path.join(outdir, name + ".data")
    with tempfile.TemporaryDirectory() as wd:
        raw = os.path.join(wd, "raw.data")
        rec = msi2lmp_model(root, ff, raw, allow_missing)
        d = DataText.read(raw)
        red = reduce_and_wrap(d, note="tilt reduced + wrapped")
        cell = os.path.join(wd, "cell.data")
        d.write(cell)
        src = cell
        if tuple(supercell) != (1, 1, 1):
            sc = make_supercell(DataText.read(cell), supercell)
            src = os.path.join(wd, "super.data")
            sc.write(src)
        banner = lammps_normalise(src, ff, out)
        d2 = DataText.read(out)
        rered = None
        if not tilt_within_bound(d2):
            rered = reduce_and_wrap(d2, note="")
        d2.lines[0] += f" | {name}: INTERFACE FF 1.5 {model} {supercell[0]}x{supercell[1]}x{supercell[2]} via builders/minerals.py"
        d2.write(out)
        n_com = annotate(out, cell)
    pf = DataText.read(out)
    record = {"name": name, "model": model, "model_dir": os.path.relpath(os.path.dirname(root), UGRP),
              "model_sha256": {e: _sha(f"{root}.{e}") for e in ("car", "mdf")},
              "supercell": list(supercell), "force_field": FORCE_FIELDS[ff]["name"],
              "frc_sha256": _sha(FORCE_FIELDS[ff]["frc"]), "lammps": banner,
              "tilt_reduction": red["basis_shift"], "tilt_reduced_after_supercell": bool(rered),
              "comments_restored": n_com, "natoms": pf.header_int("atoms"),
              "data_file": out, "data_sha256": _sha(out)}
    record.update(rec)
    with open(os.path.join(outdir, name + ".build.json"), "w") as fh:
        json.dump(record, fh, indent=2)
    return record


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m builders.minerals", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model", nargs="?")
    ap.add_argument("--supercell", nargs=3, type=int, default=[1, 1, 1])
    ap.add_argument("--ff", choices=list(FORCE_FIELDS), default="pcff")
    ap.add_argument("--out", default="runs/minerals")
    ap.add_argument("--name")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--allow-missing", nargs="*", default=[], help="geometry-only use: tolerate these missing kinds")
    a = ap.parse_args(argv)
    if a.list or not a.model:
        for k, v in list_models().items():
            print(f"{k:40s} {os.path.relpath(v, UGRP)}{'   (defective: ' + KNOWN_DEFECTIVE[k] + ')' if k in KNOWN_DEFECTIVE else ''}")
        return
    rec = build_mineral(a.model, tuple(a.supercell), a.ff, a.out, a.name, tuple(a.allow_missing))
    print(json.dumps({k: rec[k] for k in ("name", "force_field", "natoms", "data_file", "missing_kinds")}, indent=1))


if __name__ == "__main__":
    main()
