"""Tier 0 unit tests: the valid base file passes; each malformed variant fails exactly its rule."""
from conftest import VALID, replace_line

from validator import validate


def failing(res):
    return {c.property for c in res.checks if c.verdict == "FAIL"}


def run(write, make_cfg, text, **kw):
    return validate(write(text), make_cfg(**kw), run_tier3=False)


def test_valid_base_file_passes_tiers_0_to_2(write, make_cfg):
    res = run(write, make_cfg, VALID)
    assert failing(res) == set(), res.summary()
    assert all(c.verdict in ("PASS", "NOT_APPLICABLE") for c in res.checks if c.tier in (0, 1, 2)), res.summary()
    assert res.tier_reached == 2


def test_p0_1_unknown_header_line(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "2 angles\n", "2 angles\n7 atom kinds\n"))
    assert failing(res) == {"P0.1"}


def test_p0_1_comment_without_blank(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "6 atoms\n", "6 atoms#six\n"))
    assert failing(res) == {"P0.1"}


def test_p0_1_trailing_junk_after_keyword(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "6 atoms\n", "6 atoms extra\n"))
    assert failing(res) == {"P0.1"}


def test_p0_2_misspelled_section(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "Bond Coeffs # harmonic", "Bond  Coeffs # harmonic"))
    assert "P0.2" in failing(res)


def test_p0_2_wrong_case(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "\nAngles\n", "\nangles\n"))
    assert "P0.2" in failing(res)


def test_p0_2_unsupported_section(write, make_cfg):
    res = run(write, make_cfg, VALID + "\nAtom Type Labels\n\n1 O\n2 H\n")
    assert "P0.2" in failing(res)


def test_p0_3_fortran_exponent(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "1 15.9994 # o*", "1 1.59994D1 # o*"))
    assert failing(res) == {"P0.3"}


def test_p0_3_float_in_integer_field(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "1 1 1 2\n", "1 1 1.0 2\n"))
    assert failing(res) == {"P0.3"}


def test_p0_3_nan_coordinate(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "4 2 1 -0.8476 6.000", "4 2 1 -0.8476 nan"))
    assert failing(res) == {"P0.3"}


def test_p0_4_wrong_column_count(write, make_cfg):
    # 'charge'-style row (6 fields) in a file declared atom_style full (7 or 10)
    res = run(write, make_cfg, replace_line(VALID, "4 2 1 -0.8476 6.000 6.000 6.000", "4 1 -0.8476 6.000 6.000 6.000"))
    assert failing(res) == {"P0.4"}


def test_p0_4_image_flags_on_some_rows(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "4 2 1 -0.8476 6.000 6.000 6.000", "4 2 1 -0.8476 6.000 6.000 6.000 0 0 0"))
    assert failing(res) == {"P0.4"}


def test_p0_5_lo_not_below_hi(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "0.0 12.0 zlo zhi", "12.0 0.0 zlo zhi"))
    assert failing(res) == {"P0.5"}


def test_p0_5_general_triclinic_unsupported(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "0.0 12.0 zlo zhi\n", "0.0 12.0 zlo zhi\n12 0 0 avec\n"))
    assert "P0.5" in failing(res)


def test_p0_6_line_too_long(write, make_cfg):
    long_x = "2." + "0" * 260
    res = run(write, make_cfg, replace_line(VALID, "1 1 1 -0.8476 2.000", f"1 1 1 -0.8476 {long_x}"))
    assert failing(res) == {"P0.6"}


def test_p0_7_no_blank_after_keyword(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "Bonds\n\n", "Bonds\n"))
    assert "P0.7" in failing(res)


def test_p0_8_missing_box_line(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "0.0 12.0 zlo zhi\n", ""))
    assert failing(res) == {"P0.8"}


def test_p0_8_declared_triclinic_without_tilt(write, make_cfg):
    res = run(write, make_cfg, VALID, box_kind="triclinic")
    assert failing(res) == {"P0.8"}


def test_p0_9_bonds_before_atoms(write, make_cfg):
    atoms = VALID[VALID.index("Atoms # full"):VALID.index("Bonds\n")]
    bonds = VALID[VALID.index("Bonds\n"):VALID.index("Angles\n")]
    text = VALID.replace(atoms + bonds, bonds + atoms)
    res = run(write, make_cfg, text)
    assert failing(res) == {"P0.9"}


def test_p0_10_duplicate_header_keyword(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "4 bonds\n", "4 bonds\n4 bonds\n"))
    assert failing(res) == {"P0.10"}


def test_p0_11_surplus_row_at_eof(write, make_cfg):
    # FM27: exactly one surplus final row, no trailing blank line — LAMMPS silently ignores it
    res = run(write, make_cfg, VALID + "3 1 2 1 3\n")
    assert failing(res) == {"P0.11"}


def test_p0_11_blank_line_inside_section(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "1 1 1 2\n2 1 1 3\n", "1 1 1 2\n\n2 1 1 3\n"))
    assert "P0.11" in failing(res)


def test_p0_12_crlf_rejected_under_ascii_lf(write, make_cfg):
    res = run(write, make_cfg, VALID.replace("\n", "\r\n"))
    assert failing(res) == {"P0.12"}


def test_p0_12_crlf_allowed_by_policy(write, make_cfg):
    res = run(write, make_cfg, VALID.replace("\n", "\r\n"), encoding_policy="ascii_lf_or_crlf")
    assert failing(res) == set()


def test_p0_12_non_ascii_outside_comment(write, make_cfg):
    raw = VALID.replace("2 1.008 # h*", "2 1.008 # h*").encode("utf-8")
    res = run(write, make_cfg, raw.decode("latin-1"))
    assert "P0.12" in failing(res)


def test_p0_12_missing_final_newline(write, make_cfg):
    res = run(write, make_cfg, VALID.rstrip("\n"))
    assert failing(res) == {"P0.12"}


def test_tier0_failure_stops_evaluation(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "0.0 12.0 zlo zhi\n", ""))
    later = [c for c in res.checks if c.tier in (1, 2, 3)]
    assert later and all(c.verdict == "NOT_EVALUATED" for c in later)
    assert res.tier_reached == -1 and res.verdict == "FAIL"
