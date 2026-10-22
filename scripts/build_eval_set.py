"""Eval set v2 (plan Days 17-19, revised for the system class of 2026-10-20: PCE of any architecture +
INTERFACE cement minerals, in CVFF-INTERFACE (class I) and PCFF-INTERFACE (class II)).

  python scripts/build_eval_set.py   -> eval/tasks/<id>.json, data/reference/eval_v2/<id>.data (+ .json)
                                       docs/EVAL_SET.md

Each task: a natural-language request (what the system under test receives), a hidden structured
spec (for building the reference and checking), the declared validation configuration, the TC.2
comparison mode (METRICS.md), and the reference DATA FILE built by the builders. Every reference must
PASS Tiers 0-3, match itself under its TC mode, and rebuild byte-identically (determinism).
v1 tasks (tobermorite only, 2026-10-19) are kept in eval/tasks_v1/ for the record.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from builders.minerals import build_mineral  # noqa: E402
from builders.pce import ArchitectureSpec, build as build_pce  # noqa: E402
from validator import load_config, validate  # noqa: E402

OUT = os.path.join(ROOT, "data", "reference", "eval_v2")
TASKS_DIR = os.path.join(ROOT, "eval", "tasks")
FF_NAME = {"pcff": "the class II PCFF-INTERFACE force field (INTERFACE FF 1.5)",
           "cvff": "the class I CVFF-INTERFACE force field (INTERFACE FF 1.5)"}
ACID = {"kind": "acid", "alpha_methyl": False, "deprotonated": True}

TASKS = [
    # ---------------- minerals ----------------
    {"id": "m01", "difficulty": "easy", "domain": "mineral", "ff": "cvff",
     "mineral": {"model": "c3s_unit_cell_minimized", "supercell": [1, 1, 1]},
     "input": "Build a LAMMPS data file for one unit cell of tricalcium silicate (C3S, the minimized INTERFACE FF "
              "unit cell) in {ff}.",
     "exercises": ["FM02", "FM06", "FM10", "FM15", "FM22"], "note": "class I mineral; no dihedrals"},
    {"id": "m02", "difficulty": "easy", "domain": "mineral", "ff": "pcff",
     "mineral": {"model": "tob11_unit_cell", "supercell": [1, 1, 1]},
     "input": "Build a LAMMPS data file for one unit cell of tobermorite 11 Å (INTERFACE FF model) in {ff}, with "
              "the triclinic tilt within LAMMPS's documented bound.",
     "exercises": ["FM02", "FM06", "FM10", "FM15", "FM22"], "note": "triclinic, tilt reduction needed"},
    {"id": "m03", "difficulty": "representative", "domain": "mineral", "ff": "pcff",
     "mineral": {"model": "tob14_avg_cell", "supercell": [2, 2, 1]},
     "input": "Build a LAMMPS data file for a 2x2x1 supercell of the tobermorite 14 Å unit cell (INTERFACE FF "
              "model, averaged occupancies) in {ff}.",
     "exercises": ["FM10", "FM11", "FM14", "FM18", "FM22"], "note": "supercell along a: LAMMPS replicate trap"},
    {"id": "m04", "difficulty": "representative", "domain": "mineral", "ff": "pcff",
     "mineral": {"model": "ettr_unit_cell", "supercell": [1, 1, 2]},
     "input": "Build a LAMMPS data file for ettringite: the INTERFACE FF hexagonal unit cell doubled along c, "
              "in {ff}.",
     "exercises": ["FM06", "FM10", "FM14", "FM18"], "note": "hexagonal cell, water and hydroxide"},
    {"id": "m05", "difficulty": "representative", "domain": "mineral", "ff": "cvff",
     "mineral": {"model": "c3a_unit_cell", "supercell": [1, 1, 1]},
     "input": "Build a LAMMPS data file for one unit cell of tricalcium aluminate (C3A, INTERFACE FF model) in {ff}.",
     "exercises": ["FM02", "FM06", "FM15", "FM22"], "note": "class I mineral, 264 atoms"},
    {"id": "m06", "difficulty": "hard", "domain": "mineral", "ff": "pcff",
     "mineral": {"model": "tob11_unit_cell", "supercell": [1, 2, 1]},
     "input": "Build a LAMMPS data file for a 1x2x1 supercell of the tobermorite 11 Å unit cell (INTERFACE FF "
              "model) in {ff}; LAMMPS must accept the box without a tilt warning beyond its documented bound.",
     "exercises": ["FM10", "FM14", "FM18"], "note": "replication along b pushes xy beyond lx/2"},
    {"id": "m07", "difficulty": "hard", "domain": "mineral", "ff": "pcff",
     "mineral": {"model": "monosulfate_cell_221", "supercell": [2, 2, 1]},
     "input": "Build a LAMMPS data file for a 2x2x1 supercell of the INTERFACE FF monosulfate (AFm) cell in {ff}.",
     "exercises": ["FM10", "FM11", "FM14", "FM18", "FM22"], "note": "hexagonal supercell, 1272 atoms"},
    # ---------------- PCE ----------------
    {"id": "p01", "difficulty": "easy", "domain": "pce", "ff": "pcff",
     "pce": {"monomers": {"A": ACID, "E": {"kind": "ester_peg", "alpha_methyl": False, "eo_units": 2, "end": "OH"}},
             "composition": {"A": 1, "E": 1}, "sequence": "random", "end_groups": ["CH3", "CH3"],
             "counterion": "Na+", "seed": 4},
     "input": "Build a LAMMPS data file in {ff} for a short PCE oligomer: one acrylate (carboxylate) unit and one "
              "acrylate ester unit carrying a hydroxyl-terminated di(ethylene glycol) chain, methyl end caps, "
              "neutralised with one Na+.",
     "exercises": ["FM06", "FM12", "FM22"], "note": "same chemistry as the group's EMC file REF-04"},
    {"id": "p02", "difficulty": "easy", "domain": "pce", "ff": "cvff",
     "pce": {"monomers": {"A": ACID, "E": {"kind": "ester_peg", "alpha_methyl": True, "eo_units": 4, "end": "OCH3"}},
             "composition": {"A": 4, "E": 2}, "sequence": "alternating", "end_groups": ["CH3", "CH3"],
             "counterion": "Ca2+", "seed": 7},
     "input": "Build a LAMMPS data file in {ff} for a small comb copolymer: 4 acrylate (carboxylate) units and 2 "
              "methoxy-tetra(ethylene glycol) methacrylate units, side chains spread evenly along the backbone, "
              "methyl end caps, neutralised with Ca2+.",
     "exercises": ["FM06", "FM12", "FM22"], "note": "class I, deterministic sequence"},
    {"id": "p03", "difficulty": "representative", "domain": "pce", "ff": "pcff",
     "pce": {"monomers": {"A": ACID, "E": {"kind": "ester_peg", "alpha_methyl": False, "eo_units": 15, "end": "OH"}},
             "composition": {"A": 12, "E": 12}, "sequence": "random", "end_groups": ["CH3", "CH3"],
             "counterion": "Ca2+", "seed": 1},
     "input": "Build a LAMMPS data file in {ff} for a polyacrylate PCE with 12 carboxylate units and 12 acrylate "
              "ester side chains of 15 ethylene-oxide units (hydroxyl-terminated), random sequence, methyl end "
              "caps, neutralised with calcium ions.",
     "exercises": ["FM04", "FM06", "FM12", "FM22"], "note": "the group's c12e12p15 (REF-01) architecture"},
    {"id": "p04", "difficulty": "representative", "domain": "pce", "ff": "pcff",
     "pce": {"monomers": {"A": {"kind": "acid", "alpha_methyl": True, "deprotonated": True},
                          "E": {"kind": "ester_peg", "alpha_methyl": True, "eo_units": 23, "end": "OCH3"}},
             "composition": {"A": 30, "E": 10}, "sequence": "random", "end_groups": ["H", "H"],
             "counterion": "Na+", "seed": 11},
     "input": "Build a LAMMPS data file in {ff} for an MPEG-type PCE: poly(methacrylic acid) backbone, fully "
              "deprotonated, with 30 methacrylate units and 10 MPEG methacrylate side chains of 23 ethylene-oxide "
              "units (methoxy-terminated), random sequence, hydrogen chain ends, sodium counter-ions.",
     "exercises": ["FM04", "FM06", "FM12", "FM22"], "note": "2122 atoms"},
    {"id": "p05", "difficulty": "representative", "domain": "pce", "ff": "cvff",
     "pce": {"params": {"n_side_chains": 8, "n_acid": 32, "side_chain_length": 25, "anchor": "HPEG",
                        "acid": "acrylic", "side_chain_end": "OH", "deprotonated_fraction": 1.0,
                        "sequence": "alternating", "counterion": "Na+", "seed": 3}},
     "input": "Build a LAMMPS data file in {ff} for an HPEG-type PCE: 8 methallyl-ether PEG side chains of 25 "
              "ethylene-oxide units (OH-terminated) copolymerised with 32 acrylic acid units (all deprotonated), "
              "side chains evenly spaced, sodium counter-ions.",
     "exercises": ["FM06", "FM12", "FM22"], "note": "ether anchor, class I"},
    {"id": "p06", "difficulty": "representative", "domain": "pce", "ff": "pcff",
     "pce": {"params": {"n_side_chains": 6, "n_acid": 12, "side_chain_length": 4, "anchor": "VPEG",
                        "acid": "acrylic", "side_chain_end": "OH", "deprotonated_fraction": 0.5,
                        "sequence": "random", "counterion": "Na+", "seed": 21}},
     "input": "Build a LAMMPS data file in {ff} for a PCE with 6 butenyl-ether side chains of 4 ethylene-oxide "
              "units (OH-terminated) and 12 acrylic acid units of which half are deprotonated (the rest stay "
              "COOH), random sequence, sodium counter-ions.",
     "exercises": ["FM06", "FM02"], "note": "COOH typing in class II is a trap (o_2/ho2, not oh/ho)"},
    {"id": "p07", "difficulty": "hard", "domain": "pce", "ff": "pcff",
     "pce": {"params": {"n_side_chains": 6, "n_acid": 18, "side_chain_length": 30, "anchor": "TPEG",
                        "acid": "acrylic", "side_chain_end": "OH", "sequence": "gradient",
                        "counterion": "Ca2+", "seed": 5}},
     "input": "Build a LAMMPS data file in {ff} for a TPEG-type PCE: 6 isoprenyl-ether PEG side chains of 30 "
              "ethylene-oxide units with 18 acrylate units, side-chain density increasing along the backbone "
              "(gradient), neutralised with Ca2+.",
     "exercises": ["FM06", "FM12", "FM17"], "note": "1517 atoms, gradient sequence"},
    {"id": "p08", "difficulty": "hard", "domain": "pce", "ff": "cvff",
     "pce": {"monomers": {"M": {"kind": "diacid", "deprotonated": 2},
                          "P": {"kind": "ether_peg", "alpha_methyl": False, "spacer": 1, "eo_units": 20, "end": "OH"}},
             "composition": {"M": 8, "P": 8}, "sequence": "alternating", "end_groups": ["CH3", "H"],
             "counterion": "Na+", "seed": 9},
     "input": "Build a LAMMPS data file in {ff} for an alternating APEG-maleic PCE: 8 maleate units (both "
              "carboxyls deprotonated) alternating with 8 allyl-ether PEG units of 20 ethylene-oxide units "
              "(OH-terminated); one methyl and one hydrogen chain end; sodium counter-ions.",
     "exercises": ["FM06", "FM12", "FM22"], "note": "diacid backbone, class I"},
    {"id": "p09", "difficulty": "hard", "domain": "pce", "ff": "pcff",
     "pce": {"monomers": {"A": ACID, "E": {"kind": "ester_peg", "alpha_methyl": False, "eo_units": 10, "end": "OCH3"}},
             "composition": {"A": 6, "E": 3}, "sequence": "block", "end_groups": ["CH3", "CH3"],
             "n_chains": 3, "counterion": "Ca2+", "seed": 2},
     "input": "Build a LAMMPS data file in {ff} with three identical block copolymer chains, each 6 acrylate "
              "(carboxylate) units followed by 3 acrylate ester units with methoxy-capped PEG-10 side chains, "
              "methyl end caps, neutralised with calcium ions.",
     "exercises": ["FM05", "FM06", "FM12", "FM13"], "note": "multi-chain system"},
]


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def pce_spec(t):
    d = dict(t["pce"].get("params") or t["pce"])
    d.update(force_field=t["ff"], name=t["id"])
    d.setdefault("box", {"padding": 10.0})
    return d


def tc_mode(t):
    if t["domain"] == "mineral":
        return "graph", True
    seq = (t["pce"].get("params") or t["pce"]).get("sequence", "random")
    return ("chemistry" if seq in ("random", "gradient") else "graph"), False


def build_one(t, outdir):
    if t["domain"] == "mineral":
        rec = build_mineral(t["mineral"]["model"], tuple(t["mineral"]["supercell"]), t["ff"], outdir, t["id"])
    else:
        rec = build_pce(ArchitectureSpec.from_json(pce_spec(t)), outdir)
        for ext in ("car", "mdf"):
            os.remove(os.path.join(outdir, f"{t['id']}.{ext}"))
    return rec


def main():
    os.makedirs(OUT, exist_ok=True)
    if os.path.isdir(TASKS_DIR) and not os.path.isdir(os.path.join(ROOT, "eval", "tasks_v1")):
        shutil.move(TASKS_DIR, os.path.join(ROOT, "eval", "tasks_v1"))
    os.makedirs(TASKS_DIR, exist_ok=True)
    rows = []
    for t in TASKS:
        path = os.path.join(OUT, t["id"] + ".data")
        if os.path.exists(path):
            os.chmod(path, 0o644)
        rec = build_one(t, OUT)
        os.chmod(path, 0o444)
        mode, cell = tc_mode(t)
        config = f"configs/interface_{t['ff']}_{'minerals' if t['domain'] == 'mineral' else 'pce'}.yaml"
        overrides = {"tc_mode": mode, "tc_compare_cell": cell}
        if t["domain"] == "mineral":
            overrides["density_family"] = t["mineral"]["model"]
        meta = {"id": t["id"], "role": "EVAL_REFERENCE_V2", "file": os.path.relpath(path, ROOT), "sha256": _sha(path),
                "declared_config": config, "overrides": overrides,
                "trust_status": "built by builders/ (deterministic); validated through Tier 3",
                "build": {k: v for k, v in rec.items() if k not in ("data_file",)}}
        with open(os.path.join(OUT, t["id"] + ".json"), "w") as fh:
            json.dump(meta, fh, indent=2, default=str)
        # checks: all tiers, self-equivalence under the task's TC mode, byte-identical rebuild
        cfg = load_config(declared=config, overrides={"declared": overrides})
        res = validate(path, cfg, reference=path)
        with tempfile.TemporaryDirectory() as td:
            build_one(t, td)
            reproducible = _sha(os.path.join(td, t["id"] + ".data")) == _sha(path)
        task = {"id": t["id"], "difficulty": t["difficulty"], "domain": t["domain"], "force_field": t["ff"],
                "input": t["input"].format(ff=FF_NAME[t["ff"]]),
                "hidden_spec": ({"builder": "minerals", **t["mineral"], "force_field": t["ff"]} if t["domain"] == "mineral"
                                else {"builder": "pce", **pce_spec(t)}),
                "declared_config": config, "tc_mode": mode, "tc_compare_cell": cell,
                "exercises": t["exercises"], "note": t["note"],
                "reference": os.path.relpath(path, ROOT), "reference_sha256": _sha(path),
                "expected_counts": {"atoms": rec.get("natoms")}}
        with open(os.path.join(TASKS_DIR, t["id"] + ".json"), "w") as fh:
            json.dump(task, fh, indent=2, ensure_ascii=False)
        row = {"id": t["id"], "difficulty": t["difficulty"], "domain": t["domain"], "ff": t["ff"], "natoms": rec.get("natoms"),
               "verdict": res.verdict, "tc_self": res.get("TC.2").verdict, "tc_mode": mode, "reproducible": reproducible,
               "note": t["note"]}
        rows.append(row)
        print(row)
    report(rows)


def report(rows):
    L = ["# Eval set v2 — task instances\n",
         f"Generated by `scripts/build_eval_set.py` on {_dt.date.today().isoformat()}. System class of 2026-10-20 (SPEC §7.16): "
         "PCE superplasticisers of any architecture and INTERFACE cement minerals, in CVFF-INTERFACE (class I) and "
         "PCFF-INTERFACE (class II). Each `eval/tasks/<id>.json` holds the natural-language **input** (all the system "
         "under test receives), a **hidden_spec**, the declared configuration, the TC.2 comparison mode and the "
         "**reference** (`data/reference/eval_v2/`). Success is defined in `METRICS.md`; the dev/test split is in "
         "`eval/split.json`. v1 (tobermorite only, 2026-10-19) is kept in `eval/tasks_v1/`.\n",
         "| Task | Difficulty | Domain | FF | Atoms | Reference verdict | TC mode | Self-match | Rebuild identical | Note |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['id']} | {r['difficulty']} | {r['domain']} | {r['ff']} | {r['natoms']} | {r['verdict']} | "
                 f"{r['tc_mode']} | {r['tc_self']} | {'yes' if r['reproducible'] else '**no**'} | {r['note']} |")
    from collections import Counter
    L += ["", f"Difficulty: {dict(Counter(r['difficulty'] for r in rows))}; domain: {dict(Counter(r['domain'] for r in rows))}; "
          f"force field: {dict(Counter(r['ff'] for r in rows))}.",
          "",
          "**Scope note for the write-up.** The references are built by the same builders the agent will call as tools, "
          "so this benchmark measures whether a system turns a request into the right builder calls (architecture, "
          "force field, supercell, counter-ions) and produces a file that passes validation — not whether it can build "
          "structures without tools. That is the design chosen in SPEC §7.3 E."]
    with open(os.path.join(ROOT, "docs", "EVAL_SET.md"), "w") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
