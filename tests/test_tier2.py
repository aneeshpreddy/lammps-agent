"""Tier 2 unit tests (plan Days 9 and 11) and geometry helpers."""
import numpy as np
from conftest import VALID, replace_line

from validator import validate
from validator.geometry import Cell, pairs_within


def failing(res):
    return {c.property for c in res.checks if c.verdict == "FAIL"}


def run(write, make_cfg, text, **kw):
    return validate(write(text), make_cfg(**kw), run_tier3=False)


def test_p2_1_flipped_charge(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "6 2 2 0.4238", "6 2 2 -0.4238"))
    assert failing(res) == {"P2.1"}
    assert "total charge" in res.get("P2.1").message


def test_p2_1_all_charges_zero(write, make_cfg):
    text = VALID
    for q in ("-0.8476", "0.4238"):
        text = text.replace(f" {q} ", " 0.0 ")
    res = run(write, make_cfg, text)
    assert failing(res) == {"P2.1"}
    assert "all charges are zero" in res.get("P2.1").message


def test_p2_1_rounding_floor(write, make_cfg):
    # 4 decimals, 6 atoms -> floor 6*0.5e-4 = 3e-4; an error of 1e-4 is inside it
    res = run(write, make_cfg, replace_line(VALID, "6 2 2 0.4238", "6 2 2 0.4239"))
    assert res.get("P2.1").verdict == "PASS"


def test_p2_2_atom_shifted_by_box_vector(write, make_cfg):
    # shift one atom by +A without an image flag: outside the cell under the 'wrapped' policy
    res = run(write, make_cfg, replace_line(VALID, "2 1 2 0.4238 2.816", "2 1 2 0.4238 14.816"))
    assert failing(res) == {"P2.2"}


def test_p2_3_overlapping_atoms(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "4 2 1 -0.8476 6.000 6.000 6.000", "4 2 1 -0.8476 2.500 2.000 2.000"))
    assert "P2.3" in failing(res)


def test_p2_4_stretched_bond(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "2 1 2 0.4238 2.816 2.577", "2 1 2 0.4238 3.816 2.577"))
    assert "P2.4" in failing(res)


def test_p2_5_density_out_of_range(write, make_cfg):
    text = VALID.replace("0.0 12.0 xlo xhi", "0.0 3.5 xlo xhi")
    res = run(write, make_cfg, text, coordinate_wrapping="unwrapped_clusters")
    assert "P2.5" in failing(res)


def test_p2_6_mass_of_wrong_element(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "2 1.008 # h*", "2 15.9994 # h*"))
    assert "P2.6" in failing(res)


def test_p2_7_unwrapped_bond_inconsistent(write, make_cfg):
    # with image_consistency required, an atom moved by a full box vector breaks the unwrapped molecule
    res = run(write, make_cfg, replace_line(VALID, "2 1 2 0.4238 2.816", "2 1 2 0.4238 14.816"),
              image_consistency="required", coordinate_wrapping="unwrapped_clusters")
    assert "P2.7" in failing(res)


def test_p2_7_consistent_image_flag_passes(write, make_cfg):
    text = VALID
    for i in range(1, 7):
        line = [ln for ln in text.splitlines() if ln.startswith(f"{i} ") and len(ln.split()) == 7][0]
        new = line + " 0 0 0"
        if i == 2:
            new = line.replace("2.816", "14.816") + " -1 0 0"
        text = text.replace(line, new, 1)
    res = run(write, make_cfg, text, image_consistency="required", coordinate_wrapping="unwrapped_clusters")
    assert res.get("P2.7").verdict == "PASS", res.get("P2.7").message


def test_p2_8_tilt_beyond_documented_bound(write, make_cfg):
    res = run(write, make_cfg, replace_line(VALID, "0.0 12.0 zlo zhi\n", "0.0 12.0 zlo zhi\n6.5 0.0 0.0 xy xz yz\n"))
    assert "P2.8" in failing(res)


def test_p2_not_calibrated_is_not_pass(write, make_cfg):
    res = run(write, make_cfg, VALID, density_family="unknown_family")
    assert res.get("P2.5").verdict == "NOT_CALIBRATED"
    assert not res.passed and res.verdict == "INCOMPLETE"


def test_min_image_triclinic_matches_bruteforce():
    rng = np.random.default_rng(0)
    cell = Cell(0, 6.7, 0, 6.2, 0, 22.0, xy=-4.05)
    x = cell.cartesian(rng.random((60, 3)))
    I, J, D = pairs_within(cell, x, 3.0)
    got = {(int(i), int(j)): d for i, j, d in zip(I, J, D)}
    # brute force over a wide image range
    imgs = np.array([[a, b, c] for a in range(-2, 3) for b in range(-2, 3) for c in range(-1, 2)], float)
    for i in range(60):
        for j in range(i + 1, 60):
            d = min(np.linalg.norm(x[j] - x[i] + cell.H @ n) for n in imgs)
            if d < 3.0:
                assert (i, j) in got and abs(got[(i, j)] - d) < 1e-9
            else:
                assert (i, j) not in got


def test_cell_list_matches_bruteforce_large():
    rng = np.random.default_rng(1)
    cell = Cell(-1, 29, 0, 30, 2, 32, xy=3.0, xz=-2.0, yz=4.0)
    x = cell.cartesian(rng.random((400, 3)) * [1, 1, 1]) + rng.normal(0, 3, (400, 3))
    from validator.geometry import _pairs_bruteforce
    a = pairs_within(cell, x, 3.5)
    b = _pairs_bruteforce(cell, x, 3.5)
    sa = {(int(i), int(j)): d for i, j, d in zip(*a)}
    sb = {(int(i), int(j)): d for i, j, d in zip(*b)}
    assert sa.keys() == sb.keys()
    assert max(abs(sa[k] - sb[k]) for k in sa) < 1e-9


def test_p2_1_statistical_floor_catches_missing_hydrogen(write, make_cfg):
    # 300 waters (900 atoms) at 4 decimals with one H charge 0.0400 e too small: inside the worst-case
    # floor (900*0.5e-4 = 0.045 e) but well outside the statistical floor (5*sqrt(900)*1e-4/sqrt(12) = 0.0043 e).
    atoms, bonds, angles = [], [], []
    for k in range(300):
        x, y, z = (k % 10) * 3 + 1.0, (k // 10 % 10) * 3 + 1.0, (k // 100) * 3 + 1.0
        o = 3 * k + 1
        q_h2 = "0.4238" if k else "0.3838"
        atoms += [f"{o} {k+1} 1 -0.8476 {x:.3f} {y:.3f} {z:.3f}",
                  f"{o+1} {k+1} 2 0.4238 {x+0.816:.3f} {y+0.577:.3f} {z:.3f}",
                  f"{o+2} {k+1} 2 {q_h2} {x-0.816:.3f} {y+0.577:.3f} {z:.3f}"]
        bonds += [f"{2*k+1} 1 {o} {o+1}", f"{2*k+2} 1 {o} {o+2}"]
        angles += [f"{k+1} 1 {o+1} {o} {o+2}"]
    head = VALID.split("Atoms # full")[0].replace("6 atoms", "900 atoms").replace("4 bonds", "600 bonds") \
        .replace("2 angles", "300 angles").replace("0.0 12.0", "0.0 30.0")
    text = head + "Atoms # full\n\n" + "\n".join(atoms) + "\n\nBonds\n\n" + "\n".join(bonds) + "\n\nAngles\n\n" + "\n".join(angles) + "\n"
    worst = validate(write(text), make_cfg(density_family="x", net_charge={"required": True, "target": 0.0, "floor": "worst_case"}), run_tier3=False)
    stat = validate(write(text), make_cfg(density_family="x", net_charge={"required": True, "target": 0.0, "floor": "statistical"}), run_tier3=False)
    assert worst.get("P2.1").verdict == "PASS"
    assert stat.get("P2.1").verdict == "FAIL"
