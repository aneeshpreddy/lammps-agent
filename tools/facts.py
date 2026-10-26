"""Plain facts about a DATA FILE or a mineral model, for the tools' answers.

Counting only (atoms, elements by mass, charge sum, molecules, box): no tolerance, no verdict. The
validator stays with the orchestrator (SPEC §7.3; plan "Key design decisions") — these facts let the
model compare what it built with what was asked, nothing more.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from builders.composite import Data, slab_geometry  # noqa: E402
from builders.minerals import KNOWN_DEFECTIVE, UGRP, list_models  # noqa: E402  (puts scripts/ on the path)
from dataedit import DataText, split_comment  # noqa: E402
from validator.elements import nearest_element  # noqa: E402

REFERENCE_MINERALS = os.path.join(ROOT, "data", "reference", "minerals")
FORCE_FIELDS = ("pcff", "cvff")


def cement_models() -> list:
    """The system class's mineral models: UGRP/CEMENT_MINERALS (builders/minerals.py also finds other
    INTERFACE FF models, which are outside the system class)."""
    d = os.path.join(UGRP, "CEMENT_MINERALS")
    return sorted(n[:-4] for n in os.listdir(d) if n.endswith(".car") and os.path.exists(os.path.join(d, n[:-4] + ".mdf")))


def data_facts(path: str, type_table: bool = False) -> dict:
    d = DataText.read(path)
    counts = {k: (d.header_int(k) if d.header_index(k) is not None else 0)
              for k in ("atoms", "bonds", "angles", "dihedrals", "impropers", "atom types")}
    lo_hi = [[float(v) for v in d.header_values(f"{a}lo {a}hi")[:2]] for a in "xyz"]
    tilt = [float(v) for v in d.header_values("xy xz yz")[:3]] if d.header_index("xy xz yz") is not None else [0.0] * 3
    masses, labels = {}, {}
    for _, ln in d.section_rows("Masses"):
        tok, com = split_comment(ln)
        masses[int(tok[0])], labels[int(tok[0])] = float(tok[1]), com.lstrip("#").strip()
    element = {t: nearest_element(m)[0] for t, m in masses.items()}
    per_type, charges, mols = Counter(), {}, set()
    total_q = 0.0
    for _, ln in d.section_rows("Atoms"):
        tok, _ = split_comment(ln)
        t, q = int(tok[2]), float(tok[3])
        per_type[t] += 1
        charges.setdefault(t, set()).add(round(q, 4))
        mols.add(int(tok[1]))
        total_q += q
    elements = Counter()
    for t, n in per_type.items():
        elements[element[t]] += n
    out = {"atoms": counts["atoms"], "bonds": counts["bonds"], "angles": counts["angles"],
           "dihedrals": counts["dihedrals"], "impropers": counts["impropers"], "atom_types": counts["atom types"],
           "molecule_ids": len(mols), "elements": dict(sorted(elements.items())),
           "net_charge_e": round(total_q, 4) + 0.0,
           "box_A": {"lengths": [round(h - l, 3) for l, h in lo_hi], "tilt_xy_xz_yz": [round(v, 3) for v in tilt]}}
    if type_table:
        out["atom_type_table"] = [
            {"type": t, "ff_type": labels[t], "element": element[t], "mass": masses[t], "count": per_type[t],
             "charges_e": sorted(charges.get(t, []))[:6]} for t in sorted(masses)]
    return out


def model_reference(model: str, ff: str) -> str:
    return os.path.join(REFERENCE_MINERALS, f"{model}_{ff}.data")


def model_facts(model: str, ff: str) -> dict:
    """Cell, composition, atom types and charges of one INTERFACE FF mineral model in one force field.
    Raises ValueError (with what to do instead) for unknown, defective or uncovered models."""
    if model in KNOWN_DEFECTIVE:
        raise ValueError(f"{model}: defective database entry, do not use ({KNOWN_DEFECTIVE[model]})")
    if model not in cement_models():
        raise ValueError(f"unknown model {model!r}; cement-mineral models: {', '.join(cement_models())}")
    models = list_models()
    covered = [f for f in FORCE_FIELDS if os.path.exists(model_reference(model, f))]
    if ff not in covered:
        raise ValueError(f"{model} is not available in {ff}; available in: {', '.join(covered) or 'none'} "
                         "(CVFF-INTERFACE covers only the C3S and C3A models)")
    car = os.path.join(models[model], model + ".car")
    pbc = next(l for l in open(car) if l.startswith("PBC "))
    a, b, c, al, be, ga = (float(x) for x in pbc.split()[1:7])
    ref = model_reference(model, ff)
    kind = "surface slab" if "surface" in model else ("rectangular (orthogonal) cell" if "rectangular" in model else "unit cell")
    out = {"model": model, "force_field": ff, "kind": kind, "force_fields_available": covered,
           "cell_abc_A": [a, b, c], "cell_angles_deg": [al, be, ga],
           "source": os.path.relpath(car, UGRP), **data_facts(ref, type_table=True)}
    if kind == "surface slab":
        try:
            g = slab_geometry(Data(ref))
            out["surface"] = {"normal": "xyz"[g["axis"]], "slab_thickness_A": round(g["thickness"], 2),
                              "vacuum_gap_A": round(g["gap"], 2), "usable_by_composite_builder": True}
        except ValueError:
            out["surface"] = {"normal": None, "usable_by_composite_builder": False,
                              "note": "no vacuum gap (the gap is filled with water)"}
    return out
