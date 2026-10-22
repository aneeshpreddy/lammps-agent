"""Tiny hand-written DATA FILEs for unit tests (plan Day 6: one valid file, one variant per rule).

The base system is two SPC/E-like waters (6 atoms, 4 bonds, 2 angles) in a 12 Å periodic box,
atom_style full, with Masses and Coeff sections in the file. The test configuration and its
calibration are written to a temporary directory so the tests never depend on project references.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from validator.config import load_config  # noqa: E402

VALID = """\
LAMMPS data file: two waters (unit-test base file)

6 atoms
4 bonds
2 angles

2 atom types
1 bond types
1 angle types

0.0 12.0 xlo xhi
0.0 12.0 ylo yhi
0.0 12.0 zlo zhi

Masses

1 15.9994 # o*
2 1.008 # h*

Pair Coeffs # lj/cut/coul/cut

1 0.1553 3.166
2 0.0 0.0

Bond Coeffs # harmonic

1 554.1349 1.0 # h*,o*

Angle Coeffs # harmonic

1 45.7696 109.47 # h*,o*,h*

Atoms # full

1 1 1 -0.8476 2.000 2.000 2.000
2 1 2 0.4238 2.816 2.577 2.000
3 1 2 0.4238 1.184 2.577 2.000
4 2 1 -0.8476 6.000 6.000 6.000
5 2 2 0.4238 6.816 6.577 6.000
6 2 2 0.4238 5.184 6.577 6.000

Bonds

1 1 1 2
2 1 1 3
3 1 4 5
4 1 4 6

Angles

1 1 2 1 3
2 1 5 4 6
"""

FULL_TEMPLATE = """\
units           {units}
atom_style      {atom_style}
boundary        {boundary}
pair_style      lj/cut/coul/cut 5.0
bond_style      harmonic
angle_style     harmonic
read_data       {datafile}
thermo_style    custom step pe ke etotal evdwl ecoul ebond eangle press
run             0
"""

DECLARED = {
    "config_id": "unit-test", "config_version": 1, "status": "TEST",
    "units": "real", "atom_style": "full", "boundary": ["p", "p", "p"], "box_kind": "any",
    "masses_location": "data_file", "coeffs_location": "data_file",
    "required_coeff_sections": ["Pair Coeffs", "Bond Coeffs", "Angle Coeffs"],
    "image_flag_policy": "optional", "coordinate_wrapping": "wrapped", "image_consistency": "not_applicable",
    "units_hint_policy": "optional", "encoding_policy": "ascii_lf", "tilt_policy": "both", "tilt_violation": "fail",
    "net_charge": {"required": True, "target": 0.0, "tolerance_e": None}, "charged_system": True,
    "molecule_bond_policy": "within_molecule", "bonded_term_consistency": "required",
    "bonded_term_completeness": "required", "improper_center_index": 1,
    "topology_signature_policy": "consistent",
    "coeff_param_counts": {"Pair Coeffs": 2, "Bond Coeffs": 2, "Angle Coeffs": 2},
    "styles": {"pair": "lj/cut/coul/cut", "bond": "harmonic", "angle": "harmonic"},
    "type_name_elements": {"o*": "O", "h*": "H"},
    "density_family": "test_water",
    "tier3": {"structure_template": os.path.join(ROOT, "templates", "accept_structure.in"),
              "full_template": None, "timeout_s": 60,
              "warning_allow_list": ["No fixes with time integration, atoms won't move"]},
}

CALIBRATION = {
    "calibration_id": "unit-test", "version": 1, "status": "TEST",
    "bond_length": {"pairs": {"h*|o*": {"lo": 0.9, "hi": 1.1}}},
    "overlap": {"pairs": {"H|H": {"d_min": 1.0}, "H|O": {"d_min": 1.2}, "O|O": {"d_min": 2.0}}},
    "density": {"test_water": {"applicable": True, "lo": 0.01, "hi": 0.05}},
    "mass": {"tau_m_amu": 0.01},
    "cell": {"tau_centroid": 0.05},
    "bond_r0": {"pairs": {"h*|o*": {"lo": 0.97, "hi": 1.03}}, "default_tau_rel": 0.06},
}


@pytest.fixture
def workdir(tmp_path):
    return tmp_path


@pytest.fixture
def make_cfg(tmp_path):
    def _make(full=False, run_tier3=False, **declared_overrides):
        dec = copy.deepcopy(DECLARED)
        cal_path = tmp_path / "cal.json"
        cal_path.write_text(json.dumps(CALIBRATION))
        dec["calibration"] = str(cal_path)
        if full:
            tp = tmp_path / "full.in"
            tp.write_text(FULL_TEMPLATE)
            dec["tier3"]["full_template"] = str(tp)
        for k, v in declared_overrides.items():
            dec[k] = v
        cfg = load_config(overrides={"validator": {"run_tier3": run_tier3}})
        cfg["declared"] = dec
        return cfg
    return _make


@pytest.fixture
def write(tmp_path):
    counter = {"n": 0}

    def _write(text: str, binary: bool = False):
        counter["n"] += 1
        p = tmp_path / f"case{counter['n']}.data"
        if binary:
            p.write_bytes(text)
        else:
            p.write_text(text)
        return str(p)
    return _write


def replace_line(text: str, old: str, new: str) -> str:
    assert old in text, f"test bug: {old!r} not in base file"
    return text.replace(old, new, 1)


lammps_available = pytest.mark.skipif(shutil.which("lmp_serial") is None, reason="lmp_serial not installed")
