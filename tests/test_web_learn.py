"""The Learn tutorial (web/learn.py): its facts must come from the project files, so these tests fail if they drift."""
from __future__ import annotations

import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "web"))
import learn  # noqa: E402


def test_example_file_sections_and_counts():
    hc = learn.header_counts()
    assert hc["atoms"] == 560 and hc["bonds"] == 547
    for name in ("Masses", "Pair Coeffs", "Bond Coeffs", "BondBond Coeffs", "Atoms", "Bonds", "Angles", "Dihedrals", "Impropers"):
        lines = learn.section(name, 2)
        assert lines[0].split("#")[0].strip() == name and len(lines) == 3
    assert len(learn.section("Atoms", 1)[1].split("#")[0].split()) == 10      # atom_style full + image flags
    assert sum(n for _, n in learn.file_map()) == len(learn.example_lines())


def test_bond_curve_uses_the_file_coefficients():
    row = learn.section("Bond Coeffs", 1)[1].split()
    assert [float(x) for x in row[1:5]] == [1.53, 299.67, -501.77, 679.81]    # the values drawn in step 6


def test_atom_types_match_the_force_field_file():
    frc = open(os.path.join(os.path.dirname(ROOT), "INTERFACE_FF_1_5", "FORCE_FIELDS", "pcff_interface_v1_5.frc")).read()
    for t, el, _ in learn.ATOM_TYPES:
        assert any(line.split()[2:5:2] == [t, el] for line in frc.splitlines() if len(line.split()) > 4), t


def test_mineral_models_and_formulas():
    for key, (_, model, _, _) in learn.MINERALS.items():
        assert os.path.exists(os.path.join(ROOT, "data", "reference", "minerals", f"{model}_pcff.data")), model
    assert learn.formula({"Ca": 18, "Si": 6, "O": 30}) == "Ca<sub>3</sub>SiO<sub>5</sub>"
    assert learn.formula({"Ca": 72, "Al": 48, "O": 144}) == "Ca<sub>3</sub>Al<sub>2</sub>O<sub>6</sub>"


def test_demo_sequences_keep_the_composition():
    for mode in ("random", "alternating", "block", "gradient"):
        seq = learn.demo_sequence(mode, 3)
        assert Counter(seq) == {"A": 12, "S": 4}


def test_quiz_answers_are_consistent():
    for q, opts, ans, why in learn.QUIZ:
        assert 0 <= ans < len(opts) and why
    assert learn.QUIZ[2][1][learn.QUIZ[2][2]] == str(6 * 2 // 2)
