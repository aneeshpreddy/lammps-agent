"""Builders: PCE graph/typing/charges, msi2lmp refusal policy, EMC equivalence, end-to-end validation."""
import copy
import os
import re
import shutil

import numpy as np
import pytest

from builders import ff as fftools
from builders.pce import ArchitectureSpec, add_unit, architecture_from_params, build, fill_hydrogens, make_sequence
from builders.molgraph import Mol
from validator import load_config, validate
from validator.parser import parse_file

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UGRP = os.path.dirname(ROOT)
needs_lammps = pytest.mark.skipif(shutil.which("lmp_serial") is None, reason="lmp_serial not installed")
needs_models = pytest.mark.skipif(not os.path.exists(os.path.join(UGRP, "INTERFACE_FF_1_5")), reason="INTERFACE FF not present")

ACID = {"kind": "acid", "alpha_methyl": False, "deprotonated": True}
EST = {"kind": "ester_peg", "alpha_methyl": False, "eo_units": 2, "end": "OH"}


@needs_models
def test_interface_peo_increments_reproduce_the_published_peo_model():
    root = os.path.join(UGRP, "INTERFACE_FF_1_5", "MODEL_DATABASE", "PEO", "peo46_h2o4394_pcff")
    peo = ("ce1", "he1", "oe1", "oa1", "ha1")
    types, conns, charge = {}, {}, {}
    for ln in open(root + ".mdf"):
        if ":" in ln and not ln.startswith(("@", "!", "#")):
            t = ln.split()
            if t[2] not in peo:
                continue
            res = t[0].split(":")[0]
            types[t[0]] = t[2]
            charge[t[0]] = float(t[6])
            # connections without a residue prefix belong to the same residue
            conns[t[0]] = [(c if ":" in c else f"{res}:{c}").split("/")[0] for c in t[12:]]
    tb = fftools.tables("pcff")
    checked = 0
    for name, ty in types.items():
        q = sum(tb.increment(ty, types[n])[0] for n in conns[name] if n in types)
        assert abs(q - charge[name]) < 2e-3, (name, ty, q, charge[name])
        checked += 1
    assert checked > 200


@pytest.mark.parametrize("ff", ["pcff", "cvff"])
@pytest.mark.parametrize("unit,expected", [
    (ACID, -1), ({"kind": "acid", "alpha_methyl": True, "deprotonated": False}, 0), (EST, 0),
    ({"kind": "ester_peg", "alpha_methyl": True, "eo_units": 5, "end": "OCH3"}, 0),
    ({"kind": "ether_peg", "alpha_methyl": True, "spacer": 2, "eo_units": 4, "end": "OH"}, 0),
    ({"kind": "diacid", "deprotonated": 2}, -2), ({"kind": "diacid", "deprotonated": 1}, -1)])
def test_unit_charges_are_integers(ff, unit, expected):
    m = Mol()
    c1, c2, q = add_unit(m, "X_1", unit, peo_types=(ff == "pcff"))
    for cap in (c1, c2):                     # cap the backbone so every carbon is saturated
        me = m.add("C", "C_sp3", "T_1")
        m.bond(cap, me)
    fill_hydrogens(m)
    fftools.assign_types(m, ff, peo_types=(ff == "pcff"))
    fftools.assign_charges(m, ff)
    assert q == expected
    assert abs(sum(a.q for a in m.atoms) - expected) < 1e-9


def test_sequence_modes_preserve_composition():
    spec = ArchitectureSpec.from_json({"name": "s", "monomers": {"A": ACID, "E": EST}, "composition": {"A": 9, "E": 3}})
    rng = np.random.default_rng(0)
    for mode in ("random", "alternating", "gradient", "block"):
        spec.sequence = mode
        seq = make_sequence(spec, rng)
        assert sorted(seq) == sorted(["A"] * 9 + ["E"] * 3), mode
    spec.sequence = "alternating"
    seq = make_sequence(spec, rng)
    gaps = np.diff([i for i, x in enumerate(seq) if x == "E"])
    assert gaps.min() >= 3                    # evenly spread
    spec.sequence = ["A", "E"] * 3 + ["A"] * 6
    assert make_sequence(spec, rng) == spec.sequence


def test_convenience_parameters():
    d = architecture_from_params({"n_side_chains": 4, "n_acid": 8, "side_chain_length": 10, "anchor": "TPEG",
                                  "deprotonated_fraction": 0.5})
    assert d["composition"] == {"S": 4, "A": 4, "H": 4}
    assert d["monomers"]["S"] == {"kind": "ether_peg", "alpha_methyl": True, "spacer": 2, "eo_units": 10, "end": "OCH3"}


@needs_lammps
@needs_models
def test_emc_replica_matches_ref04(tmp_path):
    d = {"name": "c1e1p2", "monomers": {"A": ACID, "E": EST}, "composition": {"A": 1, "E": 1},
         "counterion": "Na+", "force_field": "pcff"}
    rec = build(ArchitectureSpec.from_json(d), str(tmp_path))
    a, b = parse_file(str(tmp_path / "c1e1p2.data")), parse_file(os.path.join(ROOT, "data", "reference", "REF-04.data"))
    for k in ("atoms", "bonds", "angles", "dihedrals", "impropers"):
        assert a.header_int(k) == b.header_int(k), k
    assert rec["net_charge"] == 0


@needs_lammps
@needs_models
def test_builder_refuses_missing_parameters(tmp_path, monkeypatch):
    # with generic oh/ho typing of a carboxylic acid, PCFF-INTERFACE lacks torsion/oop terms
    monkeypatch.setattr(fftools, "_acid_oxygen", lambda m, o: False)
    d = {"name": "cooh", "monomers": {"H": {"kind": "acid", "alpha_methyl": False, "deprotonated": False}},
         "composition": {"H": 3}, "counterion": None, "force_field": "pcff"}
    with pytest.raises(RuntimeError, match="lacks parameters"):
        build(ArchitectureSpec.from_json(d), str(tmp_path))
    assert not (tmp_path / "cooh.data").exists()


@needs_lammps
@needs_models
@pytest.mark.parametrize("ff", ["pcff", "cvff"])
def test_built_pce_passes_validation(tmp_path, ff):
    d = {"name": "small", "monomers": {"A": ACID, "E": {"kind": "ester_peg", "alpha_methyl": True, "eo_units": 4, "end": "OCH3"}},
         "composition": {"A": 4, "E": 2}, "sequence": "alternating", "counterion": "Ca2+", "force_field": ff}
    build(ArchitectureSpec.from_json(d), str(tmp_path))
    res = validate(str(tmp_path / "small.data"), load_config(declared=f"configs/interface_{ff}_pce.yaml"))
    assert res.passed, res.summary()


def test_composite_slab_normal_and_orientation():
    import numpy as np
    from builders.composite import Data, orient, slab_geometry
    ref = os.path.join(ROOT, "data", "reference", "minerals")
    for f, axis in (("tob11_004_surface_pcff.data", 2), ("c3s_040_surface_cvff.data", 1), ("tob11_100_surface_pcff.data", 0)):
        g = slab_geometry(Data(os.path.join(ref, f)))
        assert g["axis"] == axis, f
        assert g["gap"] > 20 and g["thickness"] > 5
    with pytest.raises(ValueError, match="not a slab"):
        slab_geometry(Data(os.path.join(ref, "tob11_rectangular_cell_pcff.data")))
    rng = np.random.default_rng(0)
    xyz = rng.normal(size=(200, 3)) * [1.0, 6.0, 3.0]
    for normal in range(3):
        out = orient(xyz, normal, "flat")
        ext = out.max(0) - out.min(0)
        assert np.argmin(ext) == normal
        d0 = np.linalg.norm(xyz[1:] - xyz[0], axis=1)
        assert np.allclose(np.linalg.norm(out[1:] - out[0], axis=1), d0)    # rigid rotation


def test_composite_too_narrow_suggests_another_seed(tmp_path):
    # the refusal must name both ways out, so an agent bound to the requested cell changes the seed, not the cell
    import json
    from builders.composite import build as build_composite
    spec = json.load(open(os.path.join(ROOT, "examples", "composite", "tob11_004_small.json")))
    spec["pce"]["composition"] = {"A": 16, "E": 8}
    spec["surface"]["supercell"] = [1, 1, 1]
    spec["orientation"] = "as_built"
    with pytest.raises(ValueError, match=r"slab cells along .*keep it and try another seed"):
        build_composite(spec, str(tmp_path))


def test_bond_strain_accepts_references_and_flags_stretched_bonds(tmp_path):
    from builders.pce import bond_strain, strained
    ref = os.path.join(ROOT, "data", "reference", "eval_v3", "p07.data")
    st = bond_strain(ref)
    assert not strained(st), st
    lines = open(ref).read().splitlines()
    k = next(i for i, ln in enumerate(lines) if ln.startswith("Bond Coeffs")) + 2
    t = lines[k].split()
    t[1] = f"{float(t[1]) * 0.85:.4f}"         # bond type 1 r0 shortened by 15 %: its bonds now look stretched
    lines[k] = " ".join(t)
    p = tmp_path / "x.data"
    p.write_text("\n".join(lines) + "\n")
    assert strained(bond_strain(str(p)))
