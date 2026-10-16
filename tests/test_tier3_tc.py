"""Tier 3 (needs lmp_serial) and TC.2 unit tests (plan Days 12-13)."""
from conftest import VALID, lammps_available, replace_line

from validator import validate


def failing(res):
    return {c.property for c in res.checks if c.verdict == "FAIL"}


@lammps_available
def test_tier3_valid_file_passes(write, make_cfg):
    res = validate(write(VALID), make_cfg(full=True, run_tier3=True))
    assert res.passed, res.summary()
    assert res.lammps["structure"]["counts"] == {"atoms": 6, "bonds": 4, "angles": 2}
    assert res.lammps["full"]["thermo"]["nonfinite"] == []


@lammps_available
def test_tier3_captures_lammps_error_text(write, make_cfg):
    # bond type 2 > header bond types: LAMMPS rejects it (loud) and the ERROR line is captured
    text = replace_line(VALID, "4 1 4 6\n", "4 2 4 6\n")
    res = validate(write(text), make_cfg(run_tier3=True))
    assert res.get("P3.1").verdict == "FAIL"
    assert any("Invalid bond type" in e for e in res.lammps["errors"]), res.lammps["errors"]


@lammps_available
def test_tier3_crash_is_classified(write, make_cfg):
    # FM28: bond whose *second* atom is an absent ID below max ID -> SIGSEGV with no ERROR line on
    # 22 Jul 2025 Update 6 (probe T4a). If the absent atom is listed first, LAMMPS errors instead.
    text = VALID.replace("\n4 2 1 -0.8476", "\n7 2 1 -0.8476").replace("3 1 4 5\n4 1 4 6\n", "3 1 7 5\n4 1 6 4\n")
    text = text.replace("2 1 5 4 6\n", "2 1 5 7 6\n")
    res = validate(write(text), make_cfg(run_tier3=True))
    assert "P1.5" in failing(res)
    assert res.lammps["structure"]["outcome"] == "CRASH", res.lammps["structure"]
    assert res.get("P3.4").verdict == "FAIL"


@lammps_available
def test_tier3_absent_first_atom_is_loud(write, make_cfg):
    text = VALID.replace("\n4 2 1 -0.8476", "\n7 2 1 -0.8476").replace("3 1 4 5\n4 1 4 6\n", "3 1 7 5\n4 1 4 6\n")
    text = text.replace("2 1 5 4 6\n", "2 1 5 7 6\n")
    res = validate(write(text), make_cfg(run_tier3=True))
    assert res.lammps["structure"]["outcome"] == "ERROR"
    assert any("Bonds assigned incorrectly" in e for e in res.lammps["errors"])


@lammps_available
def test_tier3_missing_executable_is_not_a_verdict(write, make_cfg):
    cfg = make_cfg(run_tier3=True)
    cfg["lammps"]["executable"] = "no_such_lammps_binary"
    res = validate(write(VALID), cfg)
    assert all(c.verdict == "NOT_EVALUATED" for c in res.checks if c.tier == 3)


def test_tc2_identical_reference_passes(write, make_cfg):
    ref = write(VALID)
    res = validate(write(VALID), make_cfg(), reference=ref, run_tier3=False)
    assert res.get("TC.2").verdict == "PASS", res.get("TC.2").message


def test_tc2_consistent_renumbering_is_equivalent(write, make_cfg):
    ref = write(VALID)
    # swap IDs 2 and 3 everywhere (Atoms and topology): same system, different numbering
    text = VALID.replace("\n2 1 2 0.4238 2.816", "\nX").replace("\n3 1 2 0.4238 1.184", "\n2 1 2 0.4238 1.184")
    text = text.replace("\nX", "\n3 1 2 0.4238 2.816")
    text = text.replace("1 1 1 2\n2 1 1 3\n", "1 1 1 3\n2 1 1 2\n")
    res = validate(write(text), make_cfg(), reference=ref, run_tier3=False)
    assert res.get("TC.2").verdict == "PASS", res.get("TC.2").details


def test_tc2_detects_type_permutation(write, make_cfg):
    ref = write(VALID)
    text = replace_line(VALID, "Masses\n\n1 15.9994 # o*\n2 1.008 # h*", "Masses\n\n1 1.008 # h*\n2 15.9994 # o*")
    text = text.replace(" 1 -0.8476 ", " X ").replace(" 2 0.4238 ", " 1 0.4238 ").replace(" X ", " 2 -0.8476 ")
    text = text.replace("1 0.1553 3.166\n2 0.0 0.0", "1 0.0 0.0\n2 0.1553 3.166")
    res = validate(write(text), make_cfg(), reference=ref, run_tier3=False)
    # consistent relabelling of types with masses and coefficients: Tier 0-2 cannot object, TC.2 must
    assert res.get("TC.2").verdict == "FAIL"


def test_tc_passed_ignores_unevaluated_tc1(write, make_cfg):
    ref = write(VALID)
    res = validate(write(VALID), make_cfg(), reference=ref, run_tier3=False)
    assert res.get("TC.1").verdict == "NOT_EVALUATED"
    assert res.tc_passed is True
