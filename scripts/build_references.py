"""Build the tobermorite references and eval-set reference outputs (plan Days 17-19; SPEC §7.8, §7.14).

Pipeline, every step deterministic and recorded in the sidecar:
  1. INTERFACE FF 1.5 model (.car/.mdf, UGRP/INTERFACE_FF_1_5/MODEL_DATABASE/CEMENT_MINERALS; Heinz et al.,
     Langmuir 2013, 29, 1754; tobermorite structures after Merlino 1999)
  2. msi2lmp v3.9.11 (LAMMPS tools; compiled from the Homebrew share directory into build/msi2lmp)
     -class II -frc pcff_interface_v1_5.frc -ignore      (-ignore zeros the class II cross terms the .frc
     does not define for tobermorite; all bond/angle terms are defined and purely quadratic)
  3. tilt reduction + wrap (scripts/cellops.py; same lattice, Cartesian sites unchanged)
  4. supercell by scripts/supercell.py (bond-walking minimum-image replication), then LAMMPS 22 Jul 2025 U6
     read_data + write_data pair ii (format normalisation + acceptance; kspace ewald because this build's
     PPPM segfaults on many of these cells, FAILURE_MODES §9.6).
     Not LAMMPS `replicate ... bond/periodic`: on these tilt-reduced cells it silently joins Si to the
     wrong periodic image of O (5.87 Å "bonds") when replicating along a (FAILURE_MODES §9.6). Its
     outputs are kept as natural negatives, and where it is correct it must agree with ours:
       python scripts/build_references.py crosscheck
  5. tilt reduction again if replication pushed |xy| beyond lx/2
  6. comments (type names) copied back from step 3 by type ID; data lines verified unchanged

  python scripts/build_references.py base     # REF-05..REF-08 (calibration + positive controls)
  python scripts/build_references.py eval     # data/reference/eval/tNN.data + eval/tasks/tNN.json

The agent will build structures with its own tools (pymatgen/ASE + helpers); this route is
deliberately different so that the answer key does not share its failure modes.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
from cellops import reduce_and_wrap, tilt_within_bound  # noqa: E402
from supercell import make_supercell  # noqa: E402
from dataedit import DataText, split_comment  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UGRP = os.path.dirname(ROOT)
MODEL_DIR = os.path.join(UGRP, "INTERFACE_FF_1_5", "MODEL_DATABASE", "CEMENT_MINERALS")
FRC = os.path.join(UGRP, "INTERFACE_FF_1_5", "FORCE_FIELDS", "pcff_interface_v1_5.frc")
MSI2LMP_SRC = "/opt/homebrew/opt/lammps/share/lammps/tools/msi2lmp/src"
MSI2LMP = os.path.join(ROOT, "build", "msi2lmp", "msi2lmp")
BUILD = os.path.join(ROOT, "data", "reference", "build")
LMP = "lmp_serial"
CONFIG = "configs/interface_pcff_tobermorite.yaml"

MODELS = {
    "tob11": {"src": "tob11_unit_cell", "family": "tobermorite11", "box_kind": "triclinic",
              "desc": "tobermorite 11 Å unit cell (Merlino 1999), Ca4Si6O15(OH)2·5H2O, Z = 2"},
    "tob11r": {"src": "tob11_rectangular_cell", "family": "tobermorite11", "box_kind": "orthogonal",
               "desc": "tobermorite 11 Å, rectangular (orthogonal) repeat of the same structure"},
    "tob14": {"src": "tob14_avg_cell", "family": "tobermorite14", "box_kind": "triclinic",
              "desc": "tobermorite 14 Å unit cell with averaged occupancies (Merlino 1999), Ca5Si6O16(OH)2·7H2O, Z = 2"},
    "tob14r": {"src": "tob14_avg_rectangular_cell", "family": "tobermorite14", "box_kind": "orthogonal",
               "desc": "tobermorite 14 Å, rectangular (orthogonal) repeat of the same structure"},
}
BASE = [("REF-05", "tob11", (1, 1, 1)), ("REF-06", "tob14", (1, 1, 1)),
        ("REF-07", "tob11r", (1, 1, 1)), ("REF-08", "tob14r", (1, 1, 1))]
COMMON_FM = ["FM01", "FM02", "FM06", "FM15", "FM22"]
TASKS = [  # id, difficulty, model, supercell, extra failure modes exercised, note
    ("t01", "easy", "tob11", (1, 1, 1), ["FM10"], "unit cell, triclinic"),
    ("t02", "easy", "tob14", (1, 1, 1), ["FM10"], "unit cell, triclinic, 10 atom types"),
    ("t03", "easy", "tob11r", (1, 1, 1), [], "orthogonal cell"),
    ("t04", "representative", "tob11", (2, 1, 1), ["FM10", "FM18"], "supercell along a"),
    ("t05", "representative", "tob11", (2, 2, 1), ["FM10", "FM18"], "supercell in the layer plane"),
    ("t06", "representative", "tob11", (1, 1, 2), ["FM10", "FM18"], "supercell across layers"),
    ("t07", "representative", "tob14", (2, 2, 1), ["FM10", "FM18"], "14 Å supercell in the layer plane"),
    ("t08", "representative", "tob14", (1, 1, 2), ["FM10", "FM18"], "14 Å supercell across layers"),
    ("t09", "representative", "tob11r", (2, 1, 1), ["FM18"], "orthogonal supercell"),
    ("t10", "representative", "tob14r", (1, 1, 1), [], "orthogonal 14 Å cell"),
    ("t11", "representative", "tob14", (2, 1, 1), ["FM10", "FM18"], "14 Å supercell along a"),
    ("t12", "hard", "tob11", (1, 2, 1), ["FM10", "FM18"], "replication along b pushes xy beyond lx/2: tilt must be reduced"),
    ("t13", "hard", "tob14", (3, 3, 1), ["FM10", "FM18", "FM14"], "large triclinic supercell (936 atoms)"),
    ("t14", "hard", "tob11", (3, 3, 2), ["FM10", "FM18", "FM14"], "large triclinic supercell (1584 atoms)"),
]
COEFF_SECTIONS = ["Masses", "Pair Coeffs", "Bond Coeffs", "Angle Coeffs", "Dihedral Coeffs", "Improper Coeffs",
                  "BondBond Coeffs", "BondAngle Coeffs", "MiddleBondTorsion Coeffs", "EndBondTorsion Coeffs",
                  "AngleTorsion Coeffs", "AngleAngleTorsion Coeffs", "BondBond13 Coeffs", "AngleAngle Coeffs"]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def ensure_msi2lmp():
    if os.path.exists(MSI2LMP):
        return MSI2LMP
    os.makedirs(os.path.dirname(MSI2LMP), exist_ok=True)
    srcs = [os.path.join(MSI2LMP_SRC, f) for f in sorted(os.listdir(MSI2LMP_SRC)) if f.endswith(".c")]
    subprocess.run(["cc", "-O2", "-w", "-o", MSI2LMP] + srcs + ["-lm"], check=True)
    return MSI2LMP


def run_msi2lmp(model: str) -> dict:
    """Steps 1-3 for one model; returns paths and the list of missing-parameter messages."""
    os.makedirs(BUILD, exist_ok=True)
    src = MODELS[model]["src"]
    with tempfile.TemporaryDirectory() as wd:
        for ext in ("car", "mdf"):
            shutil.copyfile(os.path.join(MODEL_DIR, f"{src}.{ext}"), os.path.join(wd, f"{src}.{ext}"))
        shutil.copyfile(FRC, os.path.join(wd, "pcff_interface_v1_5.frc"))
        p = subprocess.run([ensure_msi2lmp(), src, "-class", "II", "-frc", "./pcff_interface_v1_5.frc",
                            "-print", "0", "-ignore"], cwd=wd, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"msi2lmp failed for {src}: {p.stdout[-500:]} {p.stderr[-500:]}")
        raw = os.path.join(BUILD, f"{model}.msi2lmp.data")
        shutil.copyfile(os.path.join(wd, f"{src}.data"), raw)
        missing = sorted({ln.strip() for ln in (p.stdout + p.stderr).splitlines() if "Unable" in ln})
    d = DataText.read(raw)
    info = reduce_and_wrap(d, note="tilt reduced + wrapped (scripts/cellops.py)")
    cell = os.path.join(BUILD, f"{model}.cell.data")
    d.write(cell)
    kinds = sorted({m.split()[3] for m in missing})
    return {"raw": raw, "cell": cell, "missing_param_kinds": kinds, "n_missing": len(missing), "reduce": info}


LMP_INPUT = """units real
atom_style full
boundary p p p
pair_style lj/class2/coul/long 9.5
bond_style class2
angle_style class2
dihedral_style class2
improper_style class2
special_bonds lj/coul 0 0 1
read_data cell.data
kspace_style ewald 1.0e-4
{replicate}
write_data out.data pair ii
"""


def lammps_replicate(cell: str, rep, out: str) -> str:
    with tempfile.TemporaryDirectory() as wd:
        shutil.copyfile(cell, os.path.join(wd, "cell.data"))
        r = "" if tuple(rep) == (1, 1, 1) else f"replicate {rep[0]} {rep[1]} {rep[2]} bond/periodic"
        with open(os.path.join(wd, "in.lmp"), "w") as fh:
            fh.write(LMP_INPUT.format(replicate=r))
        p = subprocess.run([LMP, "-in", "in.lmp", "-log", "log.lammps", "-nocite"], cwd=wd,
                           capture_output=True, text=True)
        if p.returncode != 0 or not os.path.exists(os.path.join(wd, "out.data")):
            raise RuntimeError(f"LAMMPS replicate failed: {p.stdout[-800:]}")
        shutil.copyfile(os.path.join(wd, "out.data"), out)
        return p.stdout.splitlines()[0]


def _strip(d: DataText):
    return [split_comment(ln)[0] for ln in d.lines[1:]]


def annotate(path: str, cell: str) -> int:
    """Copy '# type-name' comments from the msi2lmp cell file into Masses/Coeff rows, by type ID."""
    d, s = DataText.read(path), DataText.read(cell)
    before = _strip(d)
    added = 0
    for name in COEFF_SECTIONS:
        src = {}
        for _, line in s.section_rows(name):
            toks, com = split_comment(line) if name == "Masses" else (line.split("#")[0].split(), line.split("#", 1)[1].strip() if "#" in line else "")
            if com:
                src[toks[0]] = com.lstrip("#").strip()
        for i, line in d.section_rows(name):
            if "#" in line:
                continue
            key = line.split()[0]
            if key in src:
                d.lines[i] = f"{line.rstrip()} # {src[key]}"
                added += 1
    if _strip(d) != before:
        raise AssertionError("annotation changed data tokens")
    d.write(path)
    return added


def build_one(model, rep, out, label):
    prep = run_msi2lmp(model)
    src = prep["cell"]
    if tuple(rep) != (1, 1, 1):
        src = os.path.join(BUILD, f"{model}_{rep[0]}x{rep[1]}x{rep[2]}.supercell.data")
        d = make_supercell(DataText.read(prep["cell"]), rep)
        d.write(src)
    banner = lammps_replicate(src, (1, 1, 1), out)
    d = DataText.read(out)
    second = None
    if not tilt_within_bound(d):
        second = reduce_and_wrap(d, note="")
    d.lines[0] = d.lines[0] + f" | {label}: INTERFACE FF 1.5 {MODELS[model]['src']} {rep[0]}x{rep[1]}x{rep[2]} via scripts/build_references.py"
    d.write(out)
    n_comments = annotate(out, prep["cell"])
    return prep, {"lammps": banner, "tilt_reduced_after_replicate": second, "comments_added": n_comments}


def pipeline_record(model, rep, prep, post):
    return {
        "model_source": f"UGRP/INTERFACE_FF_1_5/MODEL_DATABASE/CEMENT_MINERALS/{MODELS[model]['src']}.car/.mdf",
        "model_source_sha256": {ext: sha(os.path.join(MODEL_DIR, f"{MODELS[model]['src']}.{ext}")) for ext in ("car", "mdf")},
        "model_description": MODELS[model]["desc"],
        "force_field": "PCFF-INTERFACE (INTERFACE FF 1.5, pcff_interface_v1_5.frc)", "frc_sha256": sha(FRC),
        "citation": "Heinz, Lin, Mishra, Emami, Langmuir 2013, 29, 1754-1765 (INTERFACE FF); Merlino et al. 1999 (structure)",
        "steps": ["msi2lmp v3.9.11 -class II -frc pcff_interface_v1_5.frc -ignore",
                  f"scripts/cellops.reduce_and_wrap (k={prep['reduce']['basis_shift']['k']})",
                  f"scripts/supercell.make_supercell {rep[0]}x{rep[1]}x{rep[2]}" if tuple(rep) != (1, 1, 1) else "no replication",
                  f"LAMMPS {post['lammps']}: read_data + write_data pair ii (kspace ewald)",
                  "cellops.reduce_and_wrap again" if post["tilt_reduced_after_replicate"] else "no further tilt reduction needed",
                  f"comments copied back ({post['comments_added']} rows)"],
        "msi2lmp_missing_parameter_kinds": prep["missing_param_kinds"],
        "msi2lmp_missing_parameter_messages": prep["n_missing"],
        "intermediate_sha256": {"msi2lmp": sha(prep["raw"]), "cell": sha(prep["cell"])},
        "supercell": list(rep),
    }


def build_base():
    for rid, model, rep in BASE:
        out = os.path.join(ROOT, "data", "reference", f"{rid}.data")
        if os.path.exists(out):
            os.chmod(out, 0o644)
        prep, post = build_one(model, rep, out, rid)
        os.chmod(out, 0o444)
        meta = {"id": rid, "role": "REFERENCE_PUBLISHED_MODEL", "file": os.path.relpath(out, ROOT), "sha256": sha(out),
                "declared_config": CONFIG, "overrides": {"density_family": MODELS[model]["family"],
                                                         "box_kind": MODELS[model]["box_kind"]},
                "trust_status": "PUBLISHED MODEL + documented pipeline + self-generated MD evidence; "
                                "supervisor confirmation pending (default-unless-objection, LOG 2026-10-19)"}
        meta.update(pipeline_record(model, rep, prep, post))
        with open(os.path.join(ROOT, "data", "reference", f"{rid}.json"), "w") as fh:
            json.dump(meta, fh, indent=2)
        print(rid, model, rep, sha(out)[:16])


def nl_request(model, rep, note):
    m = MODELS[model]
    cell = "rectangular (orthogonal) cell" if model.endswith("r") else "unit cell"
    size = "the" if tuple(rep) == (1, 1, 1) else f"a {rep[0]}x{rep[1]}x{rep[2]} supercell of the"
    return (f"Build a LAMMPS data file for {size} tobermorite {'11' if model.startswith('tob11') else '14'} Å {cell} "
            f"from the INTERFACE FF 1.5 model database ({m['src']}) with the PCFF-INTERFACE force field "
            f"(pcff_interface_v1_5.frc): atom_style full, real units, periodic in x, y and z, all force-field "
            f"coefficients and masses written in the data file, triclinic tilt within LAMMPS's documented bound.")


def build_eval():
    sys.path.insert(0, ROOT)
    from validator.parser import parse_file
    outdir = os.path.join(ROOT, "data", "reference", "eval")
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(os.path.join(ROOT, "eval", "tasks"), exist_ok=True)
    table = json.load(open(os.path.join(ROOT, "calibration", "tobermorite_interface.json")))["references"] \
        if os.path.exists(os.path.join(ROOT, "calibration", "tobermorite_interface.json")) else []
    del table
    for tid, diff, model, rep, fms, note in TASKS:
        out = os.path.join(outdir, f"{tid}.data")
        if os.path.exists(out):
            os.chmod(out, 0o644)
        prep, post = build_one(model, rep, out, tid)
        os.chmod(out, 0o444)
        pf = parse_file(out)
        counts = {k: pf.header_int(k, 0) for k in ("atoms", "bonds", "angles", "dihedrals", "impropers", "atom types")}
        meta = {"id": tid, "role": "EVAL_REFERENCE", "file": os.path.relpath(out, ROOT), "sha256": sha(out),
                "declared_config": CONFIG, "overrides": {"density_family": MODELS[model]["family"],
                                                         "box_kind": MODELS[model]["box_kind"]},
                "trust_status": "built by the reference pipeline (not by the agent); see REF-05..08 for evidence"}
        meta.update(pipeline_record(model, rep, prep, post))
        with open(os.path.join(outdir, f"{tid}.json"), "w") as fh:
            json.dump(meta, fh, indent=2)
        task = {
            "id": tid, "difficulty": diff,
            "input": nl_request(model, rep, note),
            "spec": {"system_family": "tobermorite_interface", "model": MODELS[model]["src"],
                     "supercell": list(rep), "force_field": "pcff_interface_v1_5.frc", "atom_style": "full",
                     "units": "real", "boundary": ["p", "p", "p"], "coefficients_in_data_file": True,
                     "box_kind": MODELS[model]["box_kind"],
                     "expected_counts": counts},
            "exercises": sorted(set(COMMON_FM + fms)),
            "note": note,
            "declared_config": CONFIG,
            "reference": os.path.relpath(out, ROOT), "reference_sha256": sha(out),
        }
        with open(os.path.join(ROOT, "eval", "tasks", f"{tid}.json"), "w") as fh:
            json.dump(task, fh, indent=2, ensure_ascii=False)
        print(tid, diff, model, rep, counts["atoms"], "atoms", "(tilt re-reduced)" if post["tilt_reduced_after_replicate"] else "")


def crosscheck():
    """Build every eval supercell a second way, with LAMMPS `replicate ... bond/periodic`, judge it with the
    validator, and compare it with our reference (TC.2). Outputs go to data/converted/lammps_replicate/
    with sidecars: where LAMMPS is wrong they are real-tool natural negatives for the validator."""
    sys.path.insert(0, ROOT)
    from validator import validate
    from validator.registry import config_for
    outdir = os.path.join(ROOT, "data", "converted", "lammps_replicate")
    os.makedirs(outdir, exist_ok=True)
    rows = []
    for tid, diff, model, rep, fms, note in TASKS:
        if tuple(rep) == (1, 1, 1):
            continue
        ref = os.path.join(ROOT, "data", "reference", "eval", f"{tid}.data")
        prep = run_msi2lmp(model)
        alt = os.path.join(outdir, f"{tid}__lammps_replicate.data")
        lammps_replicate(prep["cell"], rep, alt)
        d = DataText.read(alt)
        if not tilt_within_bound(d):
            reduce_and_wrap(d, note="")
        d.write(alt)
        annotate(alt, prep["cell"])
        meta = {"id": f"{tid}__lammps_replicate", "role": "CONVERTER_OUTPUT", "parent_id": tid,
                "parent_file": os.path.relpath(ref, ROOT), "converter": "LAMMPS 22 Jul 2025 U6 replicate bond/periodic",
                "declared_config": CONFIG, "overrides": {"density_family": MODELS[model]["family"]}}
        with open(os.path.splitext(alt)[0] + ".json", "w") as fh:
            json.dump(meta, fh, indent=2)
        res = validate(alt, config_for(alt, meta), reference=ref, run_tier3=False)
        tc = res.get("TC.2")
        fails = [c.property for c in res.checks if c.verdict == "FAIL" and c.tier in (0, 1, 2)]
        rows.append({"task": tid, "model": model, "supercell": list(rep), "own_checks_failing": fails,
                     "tc2": tc.verdict, "differences": tc.details.get("differences", [])[:3]})
        print(tid, model, rep, "own checks FAIL:", fails or "none", "| TC.2 vs reference:", tc.verdict)
    with open(os.path.join(BUILD, "crosscheck.json"), "w") as fh:
        json.dump(rows, fh, indent=2)
    agree = [r for r in rows if not r["own_checks_failing"]]
    assert all(r["tc2"] == "PASS" for r in agree), "LAMMPS replicate output is validator-clean but differs from our reference"
    print(f"{len(agree)}/{len(rows)} LAMMPS-replicated supercells are clean and identical to ours; "
          f"{len(rows) - len(agree)} are corrupted and rejected by the validator's own checks")
    return rows


if __name__ == "__main__":
    which = sys.argv[1:] or ["base", "eval"]
    if "crosscheck" in which:
        crosscheck()
    if "base" in which:
        build_base()
    if "eval" in which:
        build_eval()
