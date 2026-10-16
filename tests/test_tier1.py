"""Tier 1 unit tests (plan Days 7-8)."""
from conftest import VALID, replace_line

from validator import validate


def failing(res):
    return {c.property for c in res.checks if c.verdict == "FAIL"}


def verdict(res, prop):
    return res.get(prop).verdict


def run(write, make_cfg, text, **kw):
    return validate(write(text), make_cfg(**kw), run_tier3=False)


def test_p1_1_header_count_too_high(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "4 bonds\n", "5 bonds\n"))
    assert "P1.1" in failing(res)


def test_p1_1_section_present_count_zero(write, make_cfg):
    text = replace_line(VALID, "2 angles\n", "0 angles\n")
    text = text[:text.index("Angles\n")]
    res = run(write, make_cfg, text + "Angles\n\n1 1 2 1 3\n")
    assert "P1.1" in failing(res) or "P0.11" in failing(res)


def test_p1_2_duplicate_atom_id(write, make_cfg):
    # FM13 silent variant: IDs 1,2,3,4,6,6 (max ID >= natoms, LAMMPS does not notice)
    text = replace_line(VALID, "5 2 2 0.4238 6.816", "6 2 2 0.4238 6.816")
    text = replace_line(text, "3 1 4 5\n", "3 1 4 6\n")
    res = run(write, make_cfg, text)
    assert "P1.2" in failing(res)


def test_p1_3_atom_type_out_of_range(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "3 1 2 0.4238 1.184", "3 1 3 0.4238 1.184"))
    assert "P1.3" in failing(res)


def test_p1_4_missing_masses_row(write, make_cfg):
    text = replace_line(VALID, "2 1.008 # h*\n", "1 1.008 # h*\n")     # FM31: type 1 twice, type 2 none
    res = run(write, make_cfg, text)
    assert "P1.4" in failing(res)


def test_p1_4_masses_required_but_absent(write, make_cfg):
    text = VALID.replace("Masses\n\n1 15.9994 # o*\n2 1.008 # h*\n\n", "")
    res = run(write, make_cfg, text)
    assert "P1.4" in failing(res)


def test_p1_5_dangling_atom_reference(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "4 1 4 6\n", "4 1 4 9\n"))
    assert "P1.5" in failing(res)


def test_p1_5_atom_repeated_in_entry(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "4 1 4 6\n", "4 1 4 4\n"))
    assert "P1.5" in failing(res)


def test_p1_6_reversed_duplicate_bond(write, make_cfg):
    text = replace_line(VALID, "4 bonds\n", "5 bonds\n")
    text = replace_line(text, "4 1 4 6\n", "4 1 4 6\n5 1 2 1\n")
    res = run(write, make_cfg, text)
    assert failing(res) == {"P1.6"}


def test_p1_7_duplicated_coeff_type(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "2 0.0 0.0\n", "1 0.0 0.0\n"))
    assert failing(res) == {"P1.7"}


def test_p1_7_parameter_count(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "1 554.1349 1.0 # h*,o*", "1 554.1349 # h*,o*"))
    assert failing(res) == {"P1.7"}


def test_p1_8_negative_molecule_id(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "6 2 2 0.4238", "6 -2 2 0.4238"))
    assert "P1.8" in failing(res)


def test_p1_8_bond_crossing_molecules(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "6 2 2 0.4238", "6 1 2 0.4238"))
    assert failing(res) == {"P1.8"}


def test_p1_9_nonzero_flag_in_nonperiodic_dim(write, make_cfg):
    text = VALID
    for i in range(1, 7):
        line = [ln for ln in text.splitlines() if ln.startswith(f"{i} ") and len(ln.split()) == 7][0]
        text = text.replace(line, line + (" 0 0 1" if i == 1 else " 0 0 0"), 1)
    res = run(write, make_cfg, text, boundary=["p", "p", "f"])
    assert "P1.9" in failing(res)


def test_p1_10_angle_without_bond(write, make_cfg):
    text = replace_line(VALID, "4 bonds\n", "3 bonds\n")
    text = replace_line(text, "4 1 4 6\n", "")
    res = run(write, make_cfg, text)
    assert "P1.10" in failing(res)


def test_p1_11_equal_length_style_comment(write, make_cfg):
    # FM33: '# bond' has the same length as 'full' — LAMMPS gives no warning
    res = run(write, make_cfg, replace_line(VALID, "Atoms # full", "Atoms # bond"))
    assert failing(res) == {"P1.11"}


def test_p1_11_accelerator_suffix_ignored(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "Bond Coeffs # harmonic", "Bond Coeffs # harmonic/omp"))
    assert failing(res) == set()


def test_p1_12_nonperiodic_containment(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "1 1 1 -0.8476 2.000 2.000 2.000", "1 1 1 -0.8476 2.000 2.000 12.000"),
              boundary=["p", "p", "f"])
    assert "P1.12" in failing(res)


def test_p1_13_topology_type_exceeds_header(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "2 1 5 4 6\n", "2 2 5 4 6\n"))
    assert "P1.13" in failing(res)


def test_p1_14_duplicated_velocity_id(write, make_cfg):
    vel = "\nVelocities\n\n1 0 0 0\n2 0 0 0\n3 0 0 0\n4 0 0 0\n5 0 0 0\n5 0 0 0\n"
    res = run(write, make_cfg, VALID + vel)
    assert failing(res) == {"P1.14"}


def test_p1_14_complete_velocities_pass(write, make_cfg):
    vel = "\nVelocities\n\n" + "".join(f"{i} 0.001 0 0\n" for i in range(1, 7))
    res = run(write, make_cfg, VALID + vel)
    assert verdict(res, "P1.14") == "PASS"


def test_p1_15_units_hint_mismatch(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "LAMMPS data file: two waters", "LAMMPS data file via write_data, units = metal"))
    assert failing(res) == {"P1.15"}


def test_p1_16_type_swap_breaks_signature(write, make_cfg):
    # FM01: swap atom types of one H and its O; Masses unchanged
    text = replace_line(VALID, "4 2 1 -0.8476", "4 2 2 -0.8476")
    text = replace_line(text, "5 2 2 0.4238", "5 2 1 0.4238")
    res = run(write, make_cfg, text)
    assert "P1.16" in failing(res)


def test_p1_17_angle_dropped_with_header_adjusted(write, make_cfg):
    # converter drops an angle but keeps the file self-consistent: only completeness can object
    text = replace_line(VALID, "2 angles\n", "1 angles\n")
    text = replace_line(text, "2 1 5 4 6\n", "")
    res = run(write, make_cfg, text)
    assert failing(res) == {"P1.17"}
