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


@lammps_available
def test_pppm_build_crash_is_attributed_to_build():
    # On 22 Jul 2025 U6 (Homebrew) PPPM segfaults on this valid 1x1x2 tobermorite cell; the fallback
    # Ewald run is clean, so the crash must not count against the DATA FILE (FAILURE_MODES §9.6).
    import os
    from validator.config import REPO_ROOT
    from validator.registry import config_for
    path = os.path.join(str(REPO_ROOT), "data", "reference", "eval", "t06.data")
    if not os.path.exists(path):
        import pytest
        pytest.skip("eval references not built")
    cfg = config_for(path)
    cfg["declared"]["tier3"]["kspace"] = "kspace_style pppm 1.0e-4"
    cfg["declared"]["tier3"]["crash_fallback_kspace"] = "kspace_style ewald 1.0e-4"
    res = validate(path, cfg)
    if res.lammps["full"]["outcome"] != "CRASH":
        import pytest
        pytest.skip("PPPM did not crash on this LAMMPS build")
    assert res.lammps["full_fallback"]["outcome"] == "CLEAN"
    assert res.get("P3.2").verdict == "PASS" and res.get("P3.2").warnings
    assert res.get("P3.4").verdict == "PASS" and "LAMMPS build" in res.get("P3.4").details["attribution"]


def _cfg_mode(make_cfg, mode):
    cfg = make_cfg()
    cfg["declared"]["tc_mode"] = mode
    return cfg


def test_graph_mode_ignores_positions_and_numbering(write, make_cfg):
    ref = write(VALID)
    # move the second water by 1 Å and swap IDs 2/3: same molecules, different geometry and numbering
    text = VALID.replace("4 2 1 -0.8476 6.000 6.000 6.000", "4 2 1 -0.8476 7.000 6.000 6.000") \
        .replace("5 2 2 0.4238 6.816 6.577 6.000", "5 2 2 0.4238 7.816 6.577 6.000") \
        .replace("6 2 2 0.4238 5.184 6.577 6.000", "6 2 2 0.4238 6.184 6.577 6.000")
    for mode in ("graph", "chemistry"):
        res = validate(write(text), _cfg_mode(make_cfg, mode), reference=ref, run_tier3=False)
        assert res.get("TC.2").verdict == "PASS", (mode, res.get("TC.2").message)
    res = validate(write(text), make_cfg(), reference=ref, run_tier3=False)      # positions mode notices
    assert res.get("TC.2").verdict == "FAIL"


def test_graph_and_chemistry_detect_changed_charge(write, make_cfg):
    ref = write(VALID)
    text = VALID.replace("6 2 2 0.4238", "6 2 2 0.4338").replace("5 2 2 0.4238", "5 2 2 0.4138")
    for mode in ("graph", "chemistry"):
        res = validate(write(text), _cfg_mode(make_cfg, mode), reference=ref, run_tier3=False)
        assert res.get("TC.2").verdict == "FAIL", mode


def test_graph_and_chemistry_detect_changed_connectivity(write, make_cfg):
    ref = write(VALID)
    text = VALID.replace("4 1 4 6\n", "4 1 5 6\n")       # H-H bond instead of O-H: same counts
    for mode in ("graph", "chemistry"):
        res = validate(write(text), _cfg_mode(make_cfg, mode), reference=ref, run_tier3=False)
        assert res.get("TC.2").verdict == "FAIL", mode


def test_chemistry_catalogue_admits_listed_values_only(write, make_cfg):
    # METRICS v1.2: a bond kind or (type, charge) absent from the reference passes only if the catalogue lists it
    ref = write(VALID)
    text = VALID.replace("4 1 4 6\n", "4 1 5 6\n")
    cfg = _cfg_mode(make_cfg, "chemistry")
    res = validate(write(text), cfg, reference=ref, run_tier3=False)
    assert "bond kinds in neither" in res.get("TC.2").message
    pair = res.get("TC.2").message.split("join catalogue: ")[1].split(",")[0].strip().split("-")
    cfg["declared"]["tc_allowed_bond_pairs"] = [pair]       # listed in the catalogue: that difference is gone
    res = validate(write(text), cfg, reference=ref, run_tier3=False)
    assert "bond kinds in neither" not in res.get("TC.2").message


def test_cell_comparison_on_selected_axes(write, make_cfg):
    ref = write(VALID)
    taller = VALID.replace("0.0 12.0 zlo zhi", "0.0 15.0 zlo zhi")     # only the normal (z) length differs
    cfg = _cfg_mode(make_cfg, "chemistry")
    cfg["declared"]["tc_compare_cell"] = ["x", "y"]
    assert validate(write(taller), cfg, reference=ref, run_tier3=False).get("TC.2").verdict == "PASS"
    cfg["declared"]["tc_compare_cell"] = True
    res = validate(write(taller), cfg, reference=ref, run_tier3=False)
    assert res.get("TC.2").verdict == "FAIL" and "cell (all)" in res.get("TC.2").message
    wider = VALID.replace("0.0 12.0 xlo xhi", "0.0 13.0 xlo xhi")
    cfg["declared"]["tc_compare_cell"] = ["x", "y"]
    assert validate(write(wider), cfg, reference=ref, run_tier3=False).get("TC.2").verdict == "FAIL"
